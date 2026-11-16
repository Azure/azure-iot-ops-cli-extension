# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bounded hook evidence from this agent's owned cluster, retained before rollback/cleanup."""

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


NAMESPACE = "azure-iot-operations"
LIMIT = 65536


def sanitize(text):
    for name, value in os.environ.items():
        if len(value) >= 8 and re.search(r"token|secret|password|credential|servicePrincipalKey", name, re.I):
            text = text.replace(value, "[redacted]")
    text = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[redacted PEM]", text, flags=re.S)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[redacted JWT]", text)
    text = re.sub(r"(?i)\b(Bearer|Basic)\s+\S+", r"\1 [redacted]", text)
    text = re.sub(r"(https?://)[^\s/@]+(?::[^\s/@]*)?@", r"\1[redacted]@", text)
    text = re.sub(r"(https?://[^\s?\"'<>]+)\?[^\s\"'<>]+", r"\1?[redacted]", text)
    text = re.sub(
        r"(?im)^.*(?:authorization|password|token|secret|credential|connectionstring|accountkey|"
        r"sharedaccesssignature|client[-_]key[-_]data|client[-_]certificate[-_]data)"
        r"[\"']?\s*[:=].*$", "[redacted sensitive line]", text,
    )
    return text.replace("##vso[", "[ADO command removed]").replace("##[", "[ADO marker removed]")


def command(arguments, timeout=10, accepted_codes=(0,)):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode not in accepted_codes:
        raise subprocess.CalledProcessError(result.returncode, arguments)
    return result.stdout


def journal(unit, since=None):
    arguments = ["sudo", "-n", "journalctl", "--unit", unit, "--no-pager", "-n", "1500", "-o", "short-iso"]
    if since is not None:
        arguments += ["--since", f"@{int(since)}"]
    return command(arguments)


def summary(item):
    metadata = item.get("metadata", {})
    spec = item.get("spec", {})
    return {
        "kind": item.get("kind"), "name": metadata.get("name"), "uid": metadata.get("uid"),
        "namespace": metadata.get("namespace"), "owners": metadata.get("ownerReferences", []),
        "hook": metadata.get("annotations", {}).get("helm.sh/hook"),
        "status": item.get("status", {}),
        "containers": [{"name": value.get("name"), "image": value.get("image"),
                        "securityContext": value.get("securityContext", {}),
                        "workingDir": value.get("workingDir"), "volumeMounts": value.get("volumeMounts", [])}
                       for key in ("initContainers", "containers") for value in spec.get(key, [])],
        "securityContext": spec.get("securityContext", {}),
        "volumeClaims": [
            {"name": value.get("name"), "claim": value["persistentVolumeClaim"]}
            for value in spec.get("volumes", []) if "persistentVolumeClaim" in value
        ],
        "node": spec.get("nodeName"), "serviceAccount": spec.get("serviceAccountName"),
        "backoffLimit": spec.get("backoffLimit"), "activeDeadlineSeconds": spec.get("activeDeadlineSeconds"),
    }


def sanitize_json(value):
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, dict):
        return {key: sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    return value


def problem_pod(pod):
    status = pod.get("status", {})
    if status.get("phase") in ("Pending", "Failed"):
        return True
    return status.get("phase") == "Running" and any(
        not entry.get("ready", False) or entry.get("restartCount", 0)
        for entry in status.get("containerStatuses", [])
    )


class HookCollector:
    def __init__(self, output, directory, unit, artifact):
        self.output = output / "diagnostics"
        self.folder = self.output / "hooks"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.kubectl = ["kubectl", "--kubeconfig", str(directory / "user-config"), "--request-timeout=8s",
                        "--namespace", NAMESPACE]
        self.unit = unit
        self.directory = directory
        self.artifact = artifact
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.failures = set()
        self.errors = set()
        self.uploads = 0

    def save(self, name, text):
        self.folder.joinpath(name).write_text(sanitize(text)[-LIMIT:], encoding="utf-8")

    def save_json(self, name, value):
        text = json.dumps(sanitize_json(value), separators=(",", ":"))
        if len(text) > LIMIT:
            raise ValueError("Structured diagnostics exceed the evidence size limit.")
        self.folder.joinpath(name).write_text(text, encoding="utf-8")

    def warn(self, operation, error):
        message = f"Hook diagnostics {operation} failed ({type(error).__name__})."
        if message not in self.errors:
            self.errors.add(message)
            print(f"##vso[task.logissue type=warning]{message}", flush=True)
            self.save("collection-errors.txt", "\n".join(sorted(self.errors)))

    def snapshot(self, final=False):
        payload = json.loads(command([*self.kubectl, "get", "jobs,pods", "-o", "json"]))
        items = payload["items"]
        jobs = {item["metadata"]["uid"]: item for item in items if item["kind"] == "Job" and (
            item["metadata"].get("annotations", {}).get("helm.sh/hook")
            or "upgrade" in item["metadata"]["name"]
        )}
        pods = [item for item in items if item["kind"] == "Pod"]
        for item in [*jobs.values(), *pods]:
            uid = item["metadata"]["uid"]
            if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", uid):
                raise ValueError("Invalid Kubernetes evidence UID.")
            self.save_json(f"{uid}.json", summary(item))
        failed = {uid for uid, item in jobs.items() if item.get("status", {}).get("failed")}
        self.logs([pod for pod in pods if problem_pod(pod) or any(
            owner.get("uid") in jobs for owner in pod["metadata"].get("ownerReferences", [])
        )], final)
        if final:
            self.runtime_storage(pods)
        if final or failed - self.failures:
            self.events()
        if failed - self.failures and self.uploads < 5:
            try:
                self.publish()
            except (OSError, ValueError) as error:
                self.warn("publish", error)
        self.failures.update(failed)

    def runtime_storage(self, pods):
        backends = [pod for pod in pods if pod["metadata"]["name"].startswith("aio-broker-backend-")]
        for pod in backends[:8]:
            for entry in pod.get("status", {}).get("containerStatuses", []):
                identity = re.fullmatch(r"containerd://([a-f0-9]{64})", entry.get("containerID", ""))
                if entry.get("name") != "broker" or identity is None:
                    continue
                try:
                    payload = json.loads(command([
                        "sudo", "-n", str(self.directory / "k3s"), "crictl",
                        "--config", str(self.directory / "data/agent/etc/crictl.yaml"),
                        "inspect", identity[1],
                    ], timeout=5))
                    labels = payload["status"]["labels"]
                    if (labels.get("io.kubernetes.pod.uid") != pod["metadata"]["uid"]
                            or labels.get("io.kubernetes.pod.namespace") != NAMESPACE):
                        raise ValueError("Container runtime identity differs from the owned pod.")
                    spec = payload["info"]["runtimeSpec"]
                    process = spec["process"]
                    self.save_json(f"runtime-{identity[1]}.json", {
                        "pod": pod["metadata"]["name"], "podUid": pod["metadata"]["uid"],
                        "process": {key: process.get(key) for key in ("cwd", "user", "apparmorProfile")},
                        "root": spec.get("root"),
                        "mounts": [mount for mount in spec.get("mounts", [])
                                   if mount.get("destination") in ("/mnt/persistence", "/tmp")],
                        "persistencePathEnvironment": [
                            value for value in process.get("env", [])
                            if re.fullmatch(
                                r"[A-Z0-9_]*PERSIST[A-Z0-9_]*(?:PATH|DIRECTORY|DIR)=/[A-Za-z0-9_./-]+", value,
                            )
                        ],
                    })
                except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
                    self.warn("container runtime storage", error)

    def events(self):
        items = json.loads(command([*self.kubectl, "get", "events", "-o", "json"]))["items"]
        items.sort(key=lambda item: (
            item.get("type") == "Warning",
            item.get("lastTimestamp") or item.get("eventTime") or item.get("metadata", {}).get("creationTimestamp", ""),
        ), reverse=True)
        payload = {"items": [], "omitted": len(items)}
        remaining = LIMIT - len(json.dumps(payload, separators=(",", ":")))
        for item in items:
            record = sanitize_json({
                key: item.get(key)
                for key in ("type", "reason", "message", "count", "firstTimestamp", "lastTimestamp", "eventTime")
            })
            record["creationTimestamp"] = item.get("metadata", {}).get("creationTimestamp")
            record["object"] = {
                key: item.get("involvedObject", {}).get(key) for key in ("kind", "name", "uid")
            }
            size = len(json.dumps(record, separators=(",", ":"))) + 1
            if size > remaining:
                continue
            payload["items"].append(record)
            remaining -= size
        payload["omitted"] -= len(payload["items"])
        self.save_json("events.json", payload)

    def logs(self, pods, final):
        deadline = time.monotonic() + 20
        pods.sort(key=lambda pod: (pod.get("status", {}).get("phase") != "Failed", not problem_pod(pod)))
        for pod in pods[:24]:
            for entry in pod.get("status", {}).get("initContainerStatuses", []) + (
                pod.get("status", {}).get("containerStatuses", [])
            ):
                if entry.get("state", {}).get("waiting") and not entry.get("restartCount", 0):
                    continue
                for previous in ([False, True] if entry.get("restartCount", 0) else [False]):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or self.stop.is_set() and not final:
                        return
                    arguments = [*self.kubectl, "logs", pod["metadata"]["name"], "-c", entry["name"],
                                 "--timestamps=true", "--tail=1000", f"--limit-bytes={LIMIT}"]
                    if previous:
                        arguments.append("--previous=true")
                    try:
                        text = command(arguments, timeout=min(10, remaining))
                        name = f"{pod['metadata']['uid']}-{entry['name']}-{'previous' if previous else 'current'}.log"
                        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
                            raise ValueError("Invalid container evidence name.")
                        self.save(name, text)
                    except (OSError, subprocess.SubprocessError, ValueError) as error:
                        self.warn("container logs", error)

    def storage(self):
        claims = json.loads(command([*self.kubectl, "get", "pvc", "-o", "json"]))["items"]
        claims = {item["spec"]["volumeName"]: item for item in claims if item.get("spec", {}).get("volumeName")}
        if not claims:
            return
        names = sorted(claims)[:24]
        if len(names) != len(claims):
            self.warn("storage claim limit", ValueError("Too many bound claims."))
        if any(not re.fullmatch(r"[a-zA-Z0-9_.-]{1,253}", name) for name in names):
            raise ValueError("Invalid persistent volume evidence name.")
        payload = json.loads(command([*self.kubectl, "get", "pv", *names, "-o", "json"]))
        deadline = time.monotonic() + 20
        for volume in payload.get("items", [payload]):
            name = volume["metadata"]["name"]
            if name not in names:
                raise ValueError("Unrequested persistent volume returned.")
            claim = claims[name]
            reference = volume["spec"].get("claimRef", {})
            if (reference.get("namespace") != NAMESPACE
                    or reference.get("uid") != claim["metadata"]["uid"]
                    or reference.get("name") != claim["metadata"]["name"]):
                raise ValueError("Persistent volume does not belong to the selected namespace claim.")
            record = {
                "volume": name, "claim": claim["metadata"]["name"], "claimStatus": claim.get("status", {}),
                "storageClass": volume["spec"].get("storageClassName"),
                "accessModes": volume["spec"].get("accessModes"), "volumeMode": volume["spec"].get("volumeMode"),
            }
            path = volume["spec"].get("local", {}).get("path") or volume["spec"].get("hostPath", {}).get("path")
            if path:
                record["path"] = path
                roots = (self.directory / "data/storage", Path("/var/lib/rancher/k3s/storage"))
                owned = any(Path(path).parent == root for root in roots) and Path(path).name.startswith(
                    f"pvc-{claim['metadata']['uid']}_{NAMESPACE}_",
                )
                record["ownedLocalPath"] = owned
                if owned:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self.warn("storage inspection budget", TimeoutError())
                        return
                    record["modeUidGidType"] = command(
                        ["sudo", "-n", "stat", "--printf=%a %u %g %F\\n", "--", path],
                        timeout=min(5, remaining),
                    ).strip()
                    for field, arguments in (
                        ("pathComponents", ["namei", "--long", "--", path]),
                        ("filesystem", ["findmnt", "--noheadings", "--output",
                                        "TARGET,SOURCE,FSTYPE,OPTIONS", "--target", path]),
                        ("acl", ["getfacl", "--absolute-names", "--", path]),
                    ):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            self.warn("storage inspection budget", TimeoutError())
                            break
                        try:
                            record[field] = command(["sudo", "-n", *arguments], timeout=min(5, remaining)).strip()
                        except (OSError, subprocess.SubprocessError) as error:
                            self.warn(f"storage {field}", error)
                else:
                    self.warn("storage path ownership", ValueError("Unverified local volume path."))
            self.save_json(f"storage-{name}.json", record)

    def watch(self):
        while not self.stop.is_set():
            if self.lock.acquire(blocking=False):  # pylint: disable=consider-using-with
                try:
                    self.snapshot()
                except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
                    self.warn("snapshot", error)
                finally:
                    self.lock.release()
            self.stop.wait(10)

    def start(self):
        self.thread = threading.Thread(target=self.watch, name="owned-hook-diagnostics", daemon=True)
        self.thread.start()

    def publish(self):
        self.uploads += 1
        archive = self.output / f"hooks-{self.uploads}.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
            for path in sorted(self.folder.iterdir()):
                if path.is_file():
                    bundle.write(path, path.name)
        command_text = f"##vso[artifact.upload containerfolder={self.artifact};artifactname={self.artifact};]"
        print(command_text + str(archive), flush=True)

    def secret_sync(self):
        records = {"secretSync": [], "secretProviderClass": []}
        for key, resource in (
            ("secretSync", "secretsync.secret-sync.x-k8s.io"),
            ("secretProviderClass", "secretproviderclass.secrets-store.csi.x-k8s.io"),
        ):
            try:
                items = json.loads(command([*self.kubectl, "get", resource, "-o", "json"])).get("items", [])
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                self.warn(key, error)
                continue
            for item in items[:24]:
                metadata = item.get("metadata", {})
                spec = item.get("spec", {})
                records[key].append({
                    "kind": item.get("kind"),
                    "name": metadata.get("name"),
                    "uid": metadata.get("uid"),
                    "namespace": metadata.get("namespace"),
                    "generation": metadata.get("generation"),
                    "deletionTimestamp": metadata.get("deletionTimestamp"),
                    "finalizers": metadata.get("finalizers", []),
                    "specRefs": {
                        field: spec.get(field)
                        for field in (
                            "serviceAccountName",
                            "secretProviderClassName",
                            "kubernetesSecretType",
                            "provider",
                        )
                        if field in spec
                    },
                    "status": item.get("status", {}),
                })
        self.save_json("secret-sync.json", records)

        extension_pods = []
        deadline = time.monotonic() + 15
        for ext_ns in ("azure-secret-store", "azure-arc"):
            ext_kubectl = [
                "kubectl", "--kubeconfig", str(self.directory / "user-config"),
                "--request-timeout=8s", "--namespace", ext_ns,
            ]
            try:
                pods = json.loads(command([*ext_kubectl, "get", "pods", "-o", "json"])).get("items", [])
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                self.warn(f"{ext_ns} pods", error)
                continue
            for pod in pods[:24]:
                extension_pods.append(summary(pod))
            for pod in [item for item in pods if problem_pod(item)][:8]:
                for entry in pod.get("status", {}).get("initContainerStatuses", []) + (
                    pod.get("status", {}).get("containerStatuses", [])
                ):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        text = command(
                            [*ext_kubectl, "logs", pod["metadata"]["name"], "-c", entry["name"],
                             "--timestamps=true", "--tail=500", f"--limit-bytes={LIMIT}"],
                            timeout=min(8, remaining),
                        )
                        name = f"ext-{pod['metadata']['uid']}-{entry['name']}.log"
                        if re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
                            self.save(name, text)
                    except (OSError, subprocess.SubprocessError, ValueError) as error:
                        self.warn(f"{ext_ns} container logs", error)
        if extension_pods:
            self.save_json("extension-pods.json", {"items": extension_pods[:32]})

    def finish(self, failed):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=45)
            if self.thread.is_alive():
                self.warn("collector stop", TimeoutError("Hook collector did not stop before cleanup."))
        if not failed:
            return
        acquired = self.lock.acquire(timeout=5)  # pylint: disable=consider-using-with
        if not acquired:
            self.warn("collector lock", TimeoutError("Hook collector lock busy during final diagnostics."))
            return
        try:
            for name, collect in (
                ("final snapshot", lambda: self.snapshot(final=True)),
                ("secret sync snapshot", self.secret_sync),
                ("storage snapshot", self.storage),
                ("K3s unit settings", lambda: self.save("k3s-unit-settings.log", command(
                    ["sudo", "-n", "systemctl", "show", self.unit, "--property=UMask", "--property=User",
                     "--property=Group", "--property=ProtectSystem", "--property=ProtectHome",
                     "--property=PrivateTmp", "--property=ReadOnlyPaths", "--property=ReadWritePaths"],
                ))),
                ("K3s journal", lambda: self.save("k3s-journal.log", journal(self.unit))),
            ):
                try:
                    collect()
                except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
                    self.warn(name, error)
            try:
                self.publish()
            except (OSError, ValueError) as error:
                self.warn("publish", error)
        finally:
            self.lock.release()
