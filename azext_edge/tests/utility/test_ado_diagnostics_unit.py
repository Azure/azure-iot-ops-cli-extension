# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Failure evidence survives hook deletion without copying credentials or pod specifications."""

import json
import subprocess
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from azext_edge.tests.utility.test_ado_integration_unit import cluster


diagnostics = cluster.diagnostics


def test_sanitization_removes_credentials_and_pipeline_commands(monkeypatch):
    monkeypatch.setenv("SYSTEM_ACCESSTOKEN", "offline-sensitive-token")
    text = (
        "known offline-sensitive-token\nAuthorization: Bearer abc\npassword=private\n"
        "url=https://user:pass@example.test/path?sig=signed\n"
        "eyJheader.eyJbody.signature\n-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY-----\n"
        "##vso[task.complete result=Succeeded;]fake\nBackoffLimitExceeded exitCode=1"
    )
    result = diagnostics.sanitize(text)
    for secret in ("offline-sensitive-token", "Bearer abc", "private", "signed", "user:pass", "eyJheader", "##vso["):
        assert secret not in result
    assert "BackoffLimitExceeded exitCode=1" in result


def test_hook_snapshot_retains_logs_before_deletion_and_publishes_early(tmp_path, monkeypatch, capsys):
    collector = diagnostics.HookCollector(tmp_path, tmp_path / "owned", "ops-k3s-owned", "ops-diagnostics-owned-1")
    job = {
        "kind": "Job",
        "metadata": {"uid": "job-uid", "name": "broker-hook", "annotations": {"helm.sh/hook": "pre-upgrade"}},
        "spec": {"template": {"spec": {"containers": [{"env": [{"value": "do-not-export"}]}]}}},
        "status": {"failed": 1},
    }
    pod = {
        "kind": "Pod", "metadata": {"uid": "pod-uid", "name": "hook-pod", "ownerReferences": [{"uid": "job-uid"}]},
        "spec": {"containers": [{"name": "hook", "image": "example/hook:1", "env": [{"value": "do-not-export"}]}]},
        "status": {"phase": "Failed", "containerStatuses": [{"name": "hook", "restartCount": 1}]},
    }
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        if "jobs,pods" in arguments:
            return json.dumps({"items": [job, pod]})
        if "events" in arguments:
            return '{"items": [{"reason": "BackoffLimitExceeded"}]}'
        return "hook failed: exit 1\npassword=do-not-export"

    monkeypatch.setattr(diagnostics, "command", run)
    collector.snapshot()
    assert collector.uploads == 1
    assert any("--previous=true" in arguments for arguments in calls)
    assert all(arguments[1:3] == ["--kubeconfig", str(tmp_path / "owned/user-config")] for arguments in calls)
    with ZipFile(tmp_path / "diagnostics/hooks-1.zip") as archive:
        contents = "\n".join(archive.read(name).decode() for name in archive.namelist())
    assert "do-not-export" not in contents and "hook failed: exit 1" in contents
    assert "artifact.upload" in capsys.readouterr().out
    monkeypatch.setattr(diagnostics, "command", Mock(return_value='{"items": []}'))
    collector.snapshot()
    assert (collector.folder / "pod-uid-hook-current.log").is_file()
    assert collector.uploads == 1


def test_crashing_runtime_pod_logs_are_retained_without_a_hook(tmp_path, monkeypatch):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    pod = {
        "kind": "Pod", "metadata": {"uid": "broker-uid", "name": "aio-broker-backend-1-0"},
        "spec": {"securityContext": {"fsGroup": 1000},
                 "containers": [{"name": "broker", "image": "example/broker:1",
                                 "securityContext": {"runAsUser": 1000},
                                 "env": [{"name": "PASSWORD", "value": "do-not-export"}]}]},
        "status": {"phase": "Running", "containerStatuses": [
            {"name": "broker", "ready": False, "restartCount": 2,
             "state": {"waiting": {"reason": "CrashLoopBackOff"}}},
        ]},
    }
    healthy = {
        "kind": "Pod", "metadata": {"uid": "healthy-uid", "name": "healthy"},
        "status": {"phase": "Running", "containerStatuses": [{"name": "healthy", "ready": True}]},
    }
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        if "jobs,pods" in arguments:
            return json.dumps({"items": [healthy, pod]})
        return "broker exited before readiness\npassword=do-not-export"

    monkeypatch.setattr(diagnostics, "command", run)
    collector.snapshot()
    assert (collector.folder / "broker-uid-broker-current.log").is_file()
    assert (collector.folder / "broker-uid-broker-previous.log").is_file()
    assert not any("logs" in arguments and "healthy" in arguments for arguments in calls)
    saved = (collector.folder / "broker-uid.json").read_text()
    assert json.loads(saved)["status"]["containerStatuses"][0]["restartCount"] == 2
    assert json.loads(saved)["securityContext"] == {"fsGroup": 1000}
    assert json.loads(saved)["containers"][0]["securityContext"] == {"runAsUser": 1000}
    assert "do-not-export" not in saved
    monkeypatch.setattr(diagnostics, "command", Mock(return_value='{"items": []}'))
    collector.snapshot()
    assert "broker exited before readiness" in (collector.folder / "broker-uid-broker-previous.log").read_text()


def test_large_events_remain_valid_json_and_prioritize_warnings(tmp_path, monkeypatch):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    events = [
        {"type": "Normal", "message": "started " + "x" * 1000, "lastTimestamp": "2026-11-03T05:10:00Z",
         "involvedObject": {"kind": "Pod", "name": f"healthy-{index}"}} for index in range(100)
    ] + [
        {"type": "Warning", "reason": "BackOff", "message": "broker keeps crashing",
         "lastTimestamp": "2026-11-03T05:00:00Z", "involvedObject": {"name": "broker"}},
        {"type": "Warning", "message": "authorization: private-value",
         "lastTimestamp": "2026-11-03T05:01:00Z"},
    ]
    monkeypatch.setattr(diagnostics, "command", Mock(return_value=json.dumps({"items": events})))
    collector.events()
    text = (collector.folder / "events.json").read_text()
    saved = json.loads(text)
    assert len(text.encode()) <= diagnostics.LIMIT
    assert saved["omitted"] == len(events) - len(saved["items"]) > 0
    assert saved["items"][0]["lastTimestamp"] == "2026-11-03T05:01:00Z"
    assert saved["items"][1]["reason"] == "BackOff"
    assert saved["items"][1]["object"]["name"] == "broker"
    assert "private-value" not in text
    collector.save_json("status.json", {"message": "authorization: private-value", "phase": "Failed"})
    assert json.loads((collector.folder / "status.json").read_text())["phase"] == "Failed"


@pytest.mark.parametrize("acl_missing", [False, True])
def test_storage_inspection_is_bound_to_owned_namespace_claim_paths(tmp_path, monkeypatch, capsys, acl_missing):
    collector = diagnostics.HookCollector(tmp_path, tmp_path / "owned", "ops-k3s-owned", "ops-diagnostics-owned-1")
    claims = [
        {"metadata": {"uid": f"claim-{index}", "name": f"claim-{index}"},
         "spec": {"volumeName": f"pv-{index}"}, "status": {"phase": "Bound"}} for index in range(2)
    ]
    owned_path = str(tmp_path / "owned/data/storage/pvc-claim-0_azure-iot-operations_claim-0")
    volumes = [
        {"metadata": {"name": f"pv-{index}"}, "spec": {
            "claimRef": {"namespace": diagnostics.NAMESPACE, "uid": f"claim-{index}", "name": f"claim-{index}"},
            "hostPath": {"path": path}, "storageClassName": "local-path",
        }} for index, path in enumerate([owned_path, "/unowned/directory"])
    ]
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        if "pvc" in arguments:
            return json.dumps({"items": claims})
        if "pv" in arguments:
            return json.dumps({"items": volumes})
        assert arguments[-1] == owned_path
        if "findmnt" in arguments:
            return "/mnt /dev/sdb1 ext4 rw,nosuid\n"
        if "namei" in arguments:
            return "drwx------ root root owned\n"
        if "getfacl" in arguments:
            if acl_missing:
                raise subprocess.CalledProcessError(1, arguments)
            return "user::rwx\ngroup::rwx\nother::rwx\n"
        return "755 0 0 directory\n"

    monkeypatch.setattr(diagnostics, "command", run)
    collector.storage()
    saved = json.loads((collector.folder / "storage-pv-0.json").read_text())
    assert saved["modeUidGidType"] == "755 0 0 directory" and saved["ownedLocalPath"]
    assert saved["filesystem"] == "/mnt /dev/sdb1 ext4 rw,nosuid"
    assert saved["pathComponents"] == "drwx------ root root owned"
    assert ("acl" not in saved) == acl_missing
    assert not json.loads((collector.folder / "storage-pv-1.json").read_text())["ownedLocalPath"]
    assert not any("/unowned/directory" in arguments for arguments in calls)
    output = capsys.readouterr().out
    assert "storage path ownership" in output
    assert ("storage acl" in output) == acl_missing
    volumes[0]["spec"]["claimRef"]["namespace"] = "another-namespace"
    calls.clear()
    with pytest.raises(ValueError, match="does not belong"):
        collector.storage()
    assert not any("stat" in arguments for arguments in calls)


def test_api_failure_still_retains_owned_k3s_journal_and_reports_error(tmp_path, monkeypatch, capsys):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    monkeypatch.setattr(diagnostics, "command", Mock(side_effect=subprocess.TimeoutExpired("kubectl", 10)))
    journal = Mock(return_value="k3s exited with status 1")
    monkeypatch.setattr(diagnostics, "journal", journal)
    collector.finish(failed=True)
    journal.assert_called_once_with("ops-k3s-owned")
    assert (collector.folder / "k3s-journal.log").read_text() == "k3s exited with status 1"
    output = capsys.readouterr().out
    assert "type=warning" in output and "artifact.upload" in output


def test_runtime_storage_records_effective_identity_without_exporting_credentials(tmp_path, monkeypatch):
    collector = diagnostics.HookCollector(tmp_path, tmp_path / "owned", "ops-k3s-owned", "ops-diagnostics-owned-1")
    identity = "a" * 64
    pod = {
        "metadata": {"name": "aio-broker-backend-1-0", "uid": "pod-uid"},
        "status": {"containerStatuses": [{"name": "broker", "containerID": f"containerd://{identity}"}]},
    }
    payload = {
        "status": {"labels": {"io.kubernetes.pod.uid": "pod-uid",
                              "io.kubernetes.pod.namespace": diagnostics.NAMESPACE}},
        "info": {"runtimeSpec": {
            "process": {
                "cwd": "/", "user": {"uid": 65532, "gid": 65532}, "apparmorProfile": "runtime-profile",
                "args": ["private-value"], "env": [
                    "PASSWORD=private-value", "PERSISTENCE_PATH=/mnt/persistence", "PERSISTENCE_TOKEN=/private-value",
                ],
            },
            "root": {"path": "rootfs", "readonly": False},
            "mounts": [{"destination": "/mnt/persistence", "source": "/owned/volume", "options": ["rw"]},
                       {"destination": "/credentials", "source": "private-value"}],
        }},
    }
    runner = Mock(return_value=json.dumps(payload))
    monkeypatch.setattr(diagnostics, "command", runner)
    collector.runtime_storage([pod])
    saved = (collector.folder / f"runtime-{identity}.json").read_text()
    value = json.loads(saved)
    assert value["process"]["user"] == {"uid": 65532, "gid": 65532}
    assert value["mounts"] == [payload["info"]["runtimeSpec"]["mounts"][0]]
    assert value["persistencePathEnvironment"] == ["PERSISTENCE_PATH=/mnt/persistence"]
    assert "private-value" not in saved
    assert runner.call_args.args[0][:3] == ["sudo", "-n", str(tmp_path / "owned/k3s")]


def test_runtime_storage_rejects_another_pod_without_saving_its_spec(tmp_path, monkeypatch, capsys):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    pod = {
        "metadata": {"name": "aio-broker-backend-1-0", "uid": "pod-uid"},
        "status": {"containerStatuses": [{"name": "broker", "containerID": "containerd://" + "a" * 64}]},
    }
    monkeypatch.setattr(diagnostics, "command", Mock(return_value=json.dumps({
        "status": {"labels": {"io.kubernetes.pod.uid": "other-pod",
                              "io.kubernetes.pod.namespace": diagnostics.NAMESPACE}},
    })))
    collector.runtime_storage([pod])
    assert not list(collector.folder.glob("runtime-*.json"))
    assert "container runtime storage" in capsys.readouterr().out
