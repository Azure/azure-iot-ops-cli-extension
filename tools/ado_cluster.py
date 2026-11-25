# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Execute one ops scenario on fresh resources; never sweep the shared resource group."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from uuid import UUID
from xml.etree import ElementTree

import yaml

import ado_diagnostics as diagnostics
import owned_resources
from ado_integration import (
    ROOT, attempt_resources, expected_locations, expected_phases, junit_results, producer, read, required,
    scenario_timeout, strict_skips, write, cloud_name, digest, output_variable, ownership_identity,
)
from release_pipeline import validate_cluster_region


K3S_VERSION = "v1.31.1+k3s1"
MARKERS = {
    "python-edge-int": "edge", "python-long-int": "long_running",
    "python-rpsaas-int": "rpsaas and not long_running", "python-runtime-int": "runtime_channel",
    "python-upgrade-int": "upgrade", "python-mgmtactions-int": "mgmtactions",
    "python-livedata-int": "livedata", "python-wlif-int": "require_wlif_setup",
}


def stop_process_group(process):
    signum = signal.SIGTERM
    for grace in (20, 5):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            process.wait(timeout=5)
            return
        deadline = time.monotonic() + grace
        while True:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                process.wait(timeout=5)
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
        signum = signal.SIGKILL
    raise RuntimeError("Owned command process group did not terminate.")


class Commands:
    def __init__(self, auth=None, budget=None, cancel=None):
        self.auth = auth
        self.deadline = time.monotonic() + budget if budget is not None else None
        self.cancel = cancel

    def run(self, arguments, *, capture=False, env=None, cwd=None, timeout=1800):
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("The configured scenario execution budget expired.")
        # The finally block owns bounded termination of the entire subprocess group.
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            arguments, stdout=subprocess.PIPE if capture else None, text=True,
            env=env, cwd=cwd, start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        try:
            while True:
                if self.auth is not None and self.auth.poll() is not None:
                    raise RuntimeError("Credential renewal stopped; aborting scenario execution.")
                if self.cancel is not None and self.cancel.is_set():
                    raise InterruptedError("Scenario canceled.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Command timed out: {arguments[0]}")
                try:
                    stdout, _ = process.communicate(timeout=min(5, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, arguments)
            return stdout
        finally:
            stop_process_group(process)

    def cancellable(self, cancel):
        """A copy sharing this budget, for another thread, that stops once cancel is set."""
        commands = Commands(self.auth, cancel=cancel)
        commands.deadline = self.deadline
        return commands

    def az_json(self, *arguments):
        return json.loads(self.run(["az", *arguments, "--output", "json"], capture=True))


def validate_state(state):
    if state["producer"] != producer() or state["subscription"] != str(UUID(required("OPS_SUBSCRIPTION"))):
        raise ValueError("Provisioning state does not match this run and approved subscription.")
    suffix = state["suffix"]
    if not re.fullmatch(r"[0-9a-f]{15}", suffix):
        raise ValueError("Invalid attempt resource suffix.")
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", state["resourceGroup"]):
        raise ValueError("Invalid resource group.")
    if state["resourceGroup"] != required("OPS_RESOURCE_GROUP"):
        raise ValueError("Provisioning state does not match the approved resource group.")
    prefix = f"/subscriptions/{state['subscription']}/resourceGroups/{state['resourceGroup']}/providers"
    if (state["resources"] != attempt_resources(prefix, suffix, state["row"]["scenario"])
            or state["cluster"] != f"opado{suffix}" or state["instance"] != f"inst{suffix}"):
        raise ValueError("Refusing resources outside this attempt's exact ownership manifest.")
    cloud = state.get("cloud", "AzureCloud")
    if cloud != cloud_name():
        raise ValueError("Provisioning state does not match the approved cloud.")
    validate_cluster_region(state["locations"]["clusterRegion"], cloud)
    if cloud == "AzureUSGovernment" and (
            state["locations"] != dict.fromkeys(("clusterRegion", "resourceRegion", "namespaceRegion"), "usgovvirginia")
            or state["row"]["scenario"]["channel"] != "stable"):
        raise ValueError("Fairfax requires stable runtime with all resources in usgovvirginia.")
    if state.get("health"):
        from integration_health import validate
        validate(state["health"]["profile"])
        planned = {key: state["health"]["profile"][key] for key in
                   ("clusterRegion", "resourceRegion", "namespaceRegion")}
        if state["locations"] != planned:
            raise ValueError("Resource locations differ from the health profile.")
    if state.get("monitor") or os.environ.get("OPS_MONITOR_BUNDLE"):
        from release_monitor_adapter import validate_state as validate_monitor
        validate_monitor(state)
    owned_resources.validate_context(state.get("ownership", {}))
    if any(state["ownership"].get(key) != value for key, value in ownership_identity(state).items()):
        raise ValueError("Resource ownership context differs from the scenario identity.")


def check_account(commands, state):
    account = commands.az_json("account", "show")
    if (account["id"].lower() != state["subscription"]
            or account["environmentName"] != state.get("cloud", "AzureCloud")):
        raise ValueError("Azure CLI is not using the approved cloud and subscription.")


def resource_ids(commands, state):
    return {item["id"].lower() for item in commands.az_json("resource", "list", "-g", state["resourceGroup"])}


def start_auth(output):
    ready = output / "auth.ready"
    ready.unlink(missing_ok=True)
    # The caller owns this process until scenario cleanup has completed.
    process = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, str(ROOT / "tools/ado_auth.py"), "--ready", str(ready)],
    )
    try:
        for _ in range(90):
            if process.poll() is not None:
                raise RuntimeError("ADO credential preflight failed.")
            if ready.is_file():
                return process
            time.sleep(1)
        raise TimeoutError("ADO credential preflight did not become ready.")
    except BaseException:
        stop_auth(process)
        raise


def stop_auth(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
        raise RuntimeError("Credential renewal did not shut down cleanly.") from None


def cluster_paths(state):
    directory = Path(required("AGENT_TEMPDIRECTORY")) / f"ops-k3s-{state['suffix']}"
    return directory, f"ops-k3s-{state['suffix']}"


def wait_cluster(commands, state, directory, unit, started):
    kubectl = ["sudo", "-n", str(directory / "k3s"), "kubectl", "--kubeconfig", str(directory / "config")]
    for attempt in range(60):
        commands.run(["sudo", "-n", "systemctl", "is-active", "--quiet", unit], timeout=10)
        try:
            commands.run([*kubectl, "wait", "--for=condition=Ready", f"node/{state['cluster']}",
                          "--timeout=5s"], timeout=20)
            commands.run([*kubectl, "get", "--raw=/readyz", "--request-timeout=5s"], timeout=10)
            controller = json.loads(commands.run(
                [*kubectl, "get", "lease/k3s-cloud-controller-manager", "--namespace=kube-system",
                 "--output=json", "--request-timeout=5s"], capture=True, timeout=10,
            )).get("spec", {})
            renewed = controller.get("renewTime")
            # Node/API readiness precedes CCM startup; a pre-restart lease is not proof of readiness.
            if (controller.get("holderIdentity") and renewed
                    and datetime.fromisoformat(renewed.replace("Z", "+00:00")).timestamp() >= started):
                time.sleep(5)
                commands.run(["sudo", "-n", "systemctl", "is-active", "--quiet", unit], timeout=10)
                return
        except subprocess.CalledProcessError:
            if attempt == 59:
                raise
        if attempt == 59:
            raise TimeoutError("K3s cloud controller did not renew its leader lease after startup.")
        time.sleep(5)


def start_cluster(commands, state, output, issuer=None):
    directory, unit = cluster_paths(state)
    directory.mkdir(parents=True, exist_ok=True)
    # Agent default ACLs can keep a volume's fsGroup read-only despite the provisioner's chmod.
    commands.run(["setfacl", "--remove-default", "--", str(directory)], timeout=10)
    binary = directory / "k3s"
    if not binary.exists():
        release = f"https://github.com/k3s-io/k3s/releases/download/{K3S_VERSION}"
        commands.run(["curl", "--fail", "--location", "--max-time", "180", "-o", str(binary), f"{release}/k3s"])
        checksums = commands.run(
            ["curl", "--fail", "--location", "--max-time", "60", f"{release}/sha256sum-amd64.txt"], capture=True,
        )
        expected = next((line.split()[0] for line in checksums.splitlines() if line.split()[-1] == "k3s"), None)
        if expected is None or hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
            raise ValueError("Pinned k3s binary checksum mismatch.")
        binary.chmod(0o755)
    if issuer:
        commands.run(["sudo", "-n", "systemctl", "stop", unit])
    state["clusterStarted"] = True
    write(output / "state.json", state)
    arguments = [
        "sudo", "-n", "systemd-run", "--unit", unit, "--collect", str(binary), "server", "--cluster-init",
        "--data-dir", str(directory / "data"), "--node-name", state["cluster"],
        "--write-kubeconfig", str(directory / "config"), "--write-kubeconfig-mode", "600",
    ]
    if issuer:
        arguments += ["--kube-apiserver-arg", f"service-account-issuer={issuer}",
                      "--kube-apiserver-arg", "service-account-max-token-expiration=24h"]
    for attempt in range(4):
        started = time.time()
        commands.run(arguments)
        try:
            wait_cluster(commands, state, directory, unit, started)
            break
        except (subprocess.CalledProcessError, TimeoutError):
            log = diagnostics.journal(unit, since=started)
            folder = output / "diagnostics"
            folder.mkdir(exist_ok=True)
            (folder / f"k3s-startup-{int(started)}-{attempt + 1}.log").write_text(
                diagnostics.sanitize(log)[-diagnostics.LIMIT:], encoding="utf-8",
            )
            retryable = re.search(
                r"cloud-controller-manager exited:.*extension-apiserver-authentication.*forbidden", log,
            )
            # --collect can unload an exited unit: show then returns 1 with state inactive.
            status = diagnostics.command(
                ["sudo", "-n", "systemctl", "show", unit, "--property=ActiveState", "--value"],
                accepted_codes=(0, 1),
            ).strip()
            if attempt == 3 or not retryable or status not in {"inactive", "failed"}:
                raise
            diagnostics.command(["sudo", "-n", "systemctl", "reset-failed", unit], accepted_codes=(0, 1))
            print(f"Retrying the known K3s cloud-controller-manager startup race ({attempt + 1}/3).", flush=True)
            time.sleep(5 * (attempt + 1))
    config = directory / "user-config"
    with config.open("w", encoding="utf-8") as stream:
        subprocess.run(["sudo", "-n", "cat", str(directory / "config")], stdout=stream, check=True)
    config.chmod(0o600)
    os.environ["KUBECONFIG"] = str(config)


def configure_trust(commands):
    # Share the existing static trust setup rather than maintain a divergent copy.
    action = yaml.safe_load((ROOT / ".github/actions/setup-trust-bundle/action.yml").read_text(encoding="utf-8"))
    for step in action["runs"]["steps"]:
        if set(step) - {"name", "shell", "run"} or step.get("shell") != "bash" or "${{" in step["run"]:
            raise ValueError("Trust action is no longer static; update the ADO adapter explicitly.")
        commands.run(["bash", "-e", "-c", step["run"]], cwd=ROOT)


def connect_cluster(commands, state, output):
    if os.environ.get("OPS_DEPENDENCY_LOCK"):
        from integration_dependencies import verify_connected
        verify_connected()
    else:
        commands.run(["az", "extension", "add", "--name", "connectedk8s", "--yes"])
    common = ["--name", state["cluster"], "--resource-group", state["resourceGroup"]]
    custom = ["--custom-locations-oid", state["customLocationsObjectId"]]
    location = ["--location", state["locations"]["clusterRegion"]]
    for attempt in range(3):
        try:
            commands.run(["az", "connectedk8s", "connect", *common, *custom, *location], timeout=1800)
            break
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            print(f"Arc connection attempt {attempt + 1} failed; retrying in 60 seconds.", file=sys.stderr)
            time.sleep(60)
    commands.run(["az", "connectedk8s", "enable-features", "--features", "custom-locations", "cluster-connect",
                  *common, *custom])
    scenario = state["row"]["scenario"]
    workload_identity = (
        scenario["needs_trust"] or scenario["tox_env"] == "python-mgmtactions-int"
        or (scenario["tox_env"] == "python-livedata-int" and scenario["channel"] == "preview")
    )
    if workload_identity:
        commands.run(["az", "connectedk8s", "update", *common, "--enable-oidc-issuer", "--enable-workload-identity"])
    for attempt in range(20):
        cluster = commands.az_json("connectedk8s", "show", *common)
        issuer = (cluster.get("oidcIssuerProfile") or {}).get("issuerUrl")
        if cluster.get("connectivityStatus") == "Connected" and (not workload_identity or issuer):
            break
        if attempt == 19:
            raise RuntimeError("Arc cluster connectivity or workload identity issuer did not become ready.")
        time.sleep(15)
    if workload_identity:
        if not issuer.startswith("https://"):
            raise ValueError("Invalid Arc workload identity issuer.")
        start_cluster(commands, state, output, issuer)
        configuration = json.loads(commands.run(
            ["kubectl", "get", "--raw", "/.well-known/openid-configuration"], capture=True,
        ))
        if configuration.get("issuer") != issuer:
            raise RuntimeError("Kubernetes OpenID issuer differs from the configured Arc issuer.")
    if cluster["location"].replace(" ", "").lower() != state["locations"]["clusterRegion"]:
        raise ValueError("Arc cluster location differs from the selected region.")


def create_resources(commands, state):
    names = {key: value.rsplit("/", 1)[-1] for key, value in state["resources"].items()}
    common = ["--resource-group", state["resourceGroup"]]
    location = ["--location", state["locations"]["resourceRegion"]] if "resourceRegion" in state["locations"] else []
    commands.run([
        "az", "storage", "account", "create", *common, "--name", names["storage"],
        "--enable-hierarchical-namespace", "--public-network-access", "Disabled",
        "--allow-shared-key-access", "false", "--allow-blob-public-access", "false", "--default-action", "Deny",
        "--output", "none", *location,
    ])
    commands.run([
        "az", "iot", "ops", "schema", "registry", "create", *common, "--name", names["registry"],
        "--rn", f"init-ns-{state['suffix']}", "--sa-resource-id", state["resources"]["storage"],
        "--output", "none", *location,
    ])
    commands.run([
        "az", "iot", "ops", "ns", "create", *common, "--name", names["namespace"],
        "--location", state["locations"].get("namespaceRegion", "australiaeast"),
        "--output", "none",
    ])
    if "keyvault" in names:
        commands.run([
            "az", "keyvault", "create", *common, "--name", names["keyvault"], "--output", "none", *location,
        ])
        # Key Vault Secrets Officer, as the tests would assign to a vault they create.
        commands.run([
            "az", "role", "assignment", "create", "--role", "b86a8fe4-44ce-4948-aee5-eccb2c155cd7",
            "--assignee", required("AZURE_CLIENT_ID"), "--scope", state["resources"]["keyvault"], "--output", "none",
        ])
        commands.run(["az", "identity", "create", *common, "--name", names["identity"], "--output", "none", *location])


def test_environment(state, output):
    scenario = state["row"]["scenario"]
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("azext_edge_") and key not in {"SYSTEM_ACCESSTOKEN", "idToken", "servicePrincipalKey"}
    }
    environment.update({
        "azext_edge_wheel": state["wheel"], "azext_edge_wheel_sha256": state["sha256"],
        "azext_edge_rg": state["resourceGroup"], "azext_edge_cluster": state["cluster"],
        "azext_edge_instance": state["instance"], "azext_edge_runtime_channel": scenario["channel"],
        "azext_edge_cloud": state.get("cloud", "AzureCloud"),
        "azext_edge_upgrade_baseline": json.dumps(scenario["baseline"]),
        "azext_edge_init_args": scenario["init_args"], "azext_edge_create_args": scenario["create_args"],
        "azext_edge_schema_registry_id": state["resources"]["registry"],
        "azext_edge_adr_namespace_id": state["resources"]["namespace"],
        "azext_edge_sp_object_id": required("AZURE_CLIENT_ID"),
        **({"azext_edge_kv": state["resources"]["keyvault"],
            "azext_edge_user_assigned_mi_id": state["resources"]["identity"]}
           if "keyvault" in state["resources"] else {}),
        "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "no", "AZURE_TEST_RUN_LIVE": "True",
        "COVERAGE_FILE": str(output / "coverage.dat"),
        owned_resources.ENV: str((output / "state.json").resolve()),
    })
    protected = {"azext_edge_aio_cleanup", "azext_edge_init_continue_on_error", "azext_edge_skip_init"}
    for item in scenario["env"]:
        if (not re.fullmatch(r"(azext_edge_|AIO_CLI_)[A-Za-z0-9_]+", item["name"])
                or item["name"] in environment or item["name"] in protected):
            raise ValueError("Unsupported scenario environment override.")
        environment[item["name"]] = item["value"]
    return environment


def verify_locations(commands, state, output):
    if not state.get("health") and state.get("cloud") != "AzureUSGovernment":
        return
    observed = {}
    for key, expected in expected_locations(state["locations"]).items():
        args = ["resource", "show", "--ids", state["resources"][key]]
        if key in {"registry", "namespace"}:
            args += ["--api-version", "2026-04-01"]
        location = commands.az_json(*args)["location"].replace(" ", "").lower()
        if location != expected:
            raise ValueError(f"{key} was deployed outside the configured health region.")
        observed[key] = location
    state["observedLocations"] = observed
    write(output / "state.json", state)


def test_phase(commands, state, output, phase, marker):
    environment = test_environment(state, output)
    target = Path(required("AZURE_EXTENSION_DIR")) / "azure-iot-ops"
    junit = output / "junit" / f"{phase}.xml"
    source = ROOT
    if state.get("monitor"):
        from release_monitor_adapter import test_source
        source = test_source(state)
    args = [
        sys.executable, str(ROOT / "tools/integration_runner.py"), "--extension-dir", str(target),
        "--tests", str(source / "azext_edge/tests"), "--work-dir", str(output / "work" / phase),
        "--junit", str(junit), "--coverage-config", str(source / ".coveragerc"), "--scenario", marker,
    ]
    if state.get("monitor"):
        args.append("--monitor")
    if phase == "scenario" and state["row"]["scenario"].get("tests"):
        args += ["--test-files", ",".join(state["row"]["scenario"]["tests"])]
    if phase == "scenario" and state["row"]["scenario"]["parallel"]:
        args += ["-n", "6", "--dist", "worksteal"]
    commands.run(args, env=environment, cwd=output, timeout=18000)
    compatibility = state.get("monitor", {}).get("testCompatibility")
    if compatibility is not None and read(output / "work" / phase / "test-compatibility.json") != compatibility:
        raise ValueError("Executed test compatibility differs from the monitored release plan.")
    junit_results(junit, allow_skips=not strict_skips(state["row"], phase, state.get("monitor")))
    state["phases"][phase] = "passed"
    write(output / "state.json", state)


def smoke(commands, state, output):
    diagnostics = output / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    suite = ElementTree.Element("testsuite", name="ops-smoke")
    arguments = [
        ["support", "create-bundle"], ["support", "create-bundle", "--svc", "broker", "--broker-traces"],
        ["support", "create-bundle", "--ops-service", "acs", "secretstore"], ["check"], ["check", "--pre"],
        ["check", "--post"], ["check", "--as-object"],
        ["check", "--svc", "broker", "--resources", "broker", "brokerlistener"],
        ["asset", "query", "-g", state["resourceGroup"], "--location",
         state["locations"].get("namespaceRegion", "westus")],
        ["get-versions", "--inline"],
    ]
    if state["row"]["scenario"].get("quick_smoke"):
        # Another shard of the same scenario runs the full suite on the same runtime.
        arguments = [["check"], ["support", "create-bundle", "--ops-service", "acs", "secretstore"]]
    try:
        for args in arguments:
            case = ElementTree.SubElement(suite, "testcase", classname="ops.smoke", name=" ".join(args))
            try:
                commands.run(["az", "iot", "ops", *args], cwd=diagnostics)
            except (subprocess.CalledProcessError, RuntimeError, TimeoutError):
                ElementTree.SubElement(case, "failure", message="Smoke command did not complete successfully.")
                raise
    finally:
        path = output / "junit" / "smoke.xml"
        path.parent.mkdir(exist_ok=True)
        suite.set("tests", str(len(suite)))
        suite.set("failures", str(sum(case.find("failure") is not None for case in suite)))
        suite.set("errors", "0")
        suite.set("skipped", "0")
        ElementTree.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    state["phases"]["smoke"] = "passed"
    write(output / "state.json", state)


def purge_key_vault(commands, state):
    """The owned vault is already deleted and uniquely named; a failed purge only leaves soft-deleted state."""
    name = state["resources"]["keyvault"].rsplit("/", 1)[-1]
    for attempt in range(4):
        try:
            commands.run(["az", "keyvault", "purge", "--name", name], timeout=300)
            return
        except (subprocess.CalledProcessError, TimeoutError):
            if attempt < 3:
                time.sleep(15)  # The deleted-vault list can lag the delete.
    print(f"##vso[task.logissue type=warning]Could not purge deleted Key Vault {name}.", flush=True)


def cleanup(output):
    if not (output / "state.json").exists():
        print("No provisioning state: execution never reached resource creation.", flush=True)
        return
    state = read(output / "state.json")
    validate_state(state)
    deadline = time.monotonic() + 1050
    commands = Commands(budget=1050)
    state["cleanup"] = "incomplete"
    state["resourceCleanup"] = "incomplete"
    state["ownershipGuard"] = "not-checked"
    write(output / "state.json", state)
    errors = []
    try:
        if state["ownershipChecked"]:
            check_account(commands, state)
            owned_resources.activate(output / "state.json")
            present = resource_ids(commands, state)
            if state["resources"]["instance"].lower() in present:
                try:
                    commands.run(["az", "iot", "ops", "delete", "--name", state["instance"],
                                  "-g", state["resourceGroup"], "--yes", "--force"], timeout=900)
                except (subprocess.CalledProcessError, TimeoutError) as error:
                    print(f"##vso[task.logissue type=error]Instance cleanup failed ({type(error).__name__}).")
                    errors.append("instance")
            try:
                owned_resources.cleanup(output / "state.json", timeout=min(600, max(0, deadline - time.monotonic())))
            except owned_resources.OwnershipViolationError:
                state["resourceCleanup"] = "passed"
                state["ownershipGuard"] = "rejected"
                write(output / "state.json", state)
                raise
            state["resourceCleanup"] = "passed"
            state["ownershipGuard"] = "passed"
            write(output / "state.json", state)
            if "keyvault" in state["resources"]:
                purge_key_vault(commands, state)
    finally:
        if state.get("clusterStarted"):
            _, unit = cluster_paths(state)
            result = subprocess.run(
                ["sudo", "-n", "systemctl", "show", unit, "--property=LoadState", "--value"],
                capture_output=True, text=True, check=False, timeout=30,
            )
            if result.stdout.strip() != "not-found":
                result.check_returncode()
                Commands().run(["sudo", "-n", "systemctl", "stop", unit], timeout=60)
    if errors:
        raise RuntimeError(f"Cleanup had failures: {', '.join(errors)}. Inspect retained state and retry cleanup.")
    state["cleanup"] = "passed"
    write(output / "state.json", state)
    if state["ownershipChecked"] is True:
        # Bind task-scoped completion evidence to the final persisted state.
        output_variable("cleanupStateDigest", digest(output / "state.json"))


def cleanup_proof(output):
    output_variable("complete", "false")
    try:
        if os.environ.get("AGENT_JOBSTATUS", "").lower() == "canceled":
            raise ValueError("Canceled execution requires fallback cleanup.")
        expected_digest = required("OPS_CLEANUP_STATE_DIGEST")
        if (not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
                or digest(output / "state.json") != expected_digest):
            raise ValueError("Cleanup state does not match the completed task output.")
        state = read(output / "state.json")
        validate_state(state)
        if (state["attempt"] != int(required("SYSTEM_JOBATTEMPT"))
                or state["row"]["key"] != required("OPS_ROW")
                or state["sha256"] != required("OPS_CANDIDATE_DIGEST")):
            raise ValueError("Cleanup proof belongs to another attempt, row, or candidate.")
        if (state.get("ownershipChecked") is not True
                or any(state.get(key) != "passed" for key in ("cleanup", "resourceCleanup", "ownershipGuard"))):
            raise ValueError("Cleanup or ownership verification is incomplete.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"No valid cleanup proof ({type(error).__name__}); running fallback cleanup.", flush=True)
        return
    print("Verified current-attempt cleanup proof; skipping redundant Azure login.", flush=True)
    output_variable("complete", "true")


def run(output):
    state = read(output / "state.json")
    validate_state(state)
    if state.get("monitor"):
        from release_monitor_adapter import test_source
        test_source(state)
    auth = None
    collector = None
    try:
        auth = start_auth(output)
        commands = Commands(auth, budget=scenario_timeout() * 60)
        check_account(commands, state)
        commands.az_json("group", "show", "--name", state["resourceGroup"])
        if resource_ids(commands, state) & {value.lower() for value in state["resources"].values()}:
            raise ValueError("Attempt resource names already exist; refusing reuse.")
        state["ownershipChecked"] = True
        write(output / "state.json", state)
        owned_resources.activate(output / "state.json")
        directory, unit = cluster_paths(state)
        collector = diagnostics.HookCollector(
            output, directory, unit, f"ops-diagnostics-{state['row']['key']}-{state['attempt']}",
        )
        # Cloud resources do not need the cluster; create them while it bootstraps.
        canceled = threading.Event()
        pool = ThreadPoolExecutor(max_workers=1)
        resources = pool.submit(create_resources, commands.cancellable(canceled), state)
        try:
            start_cluster(commands, state, output)
            collector.start()
            if state["row"]["scenario"]["needs_trust"]:
                configure_trust(commands)
            connect_cluster(commands, state, output)
            resources.result()
        finally:
            canceled.set()
            # Cleanup must never race creation, even if another cancel signal interrupts this wait.
            while True:
                try:
                    resources.exception()  # Waits for the worker without raising its error.
                    break
                except InterruptedError:
                    continue
            pool.shutdown(wait=False)
        scenario = state["row"]["scenario"]
        test_phase(commands, state, output, "init", "init_scenario_test")
        if state.get("monitor"):
            from release_monitor_adapter import verify_runtime
            if not scenario.get("requires_baseline"):
                verify_runtime(commands, state, output)
        verify_locations(commands, state, output)
        if scenario["tox_env"]:
            test_phase(commands, state, output, "scenario", MARKERS[scenario["tox_env"]])
            if state.get("monitor") and scenario.get("requires_baseline"):
                verify_runtime(commands, state, output)
        smoke(commands, state, output)
        if scenario["test_redeploy"]:
            commands.run(["az", "iot", "ops", "delete", "--name", state["instance"],
                          "-g", state["resourceGroup"], "--yes"], timeout=1800)
            test_phase(commands, state, output, "redeploy", "init_scenario_test")
            if state.get("monitor"):
                verify_runtime(commands, state, output)
        if any(state["phases"].get(phase) != "passed" for phase in expected_phases(state["row"])):
            raise ValueError("Required scenario phase is incomplete.")
        if auth.poll() is not None:
            raise RuntimeError("Credential renewal failed before completion.")
        state["status"] = "passed"
        write(output / "state.json", state)
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            if collector is not None:
                try:
                    collector.finish(failed)
                except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
                    collector.warn("finalization", error)
        finally:
            try:
                cleanup(output)
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
                print(f"##vso[task.logissue type=error]Cleanup failed ({type(error).__name__}).", flush=True)
                if not failed:
                    raise
            finally:
                if auth is not None:
                    stop_auth(auth)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["run", "cleanup", "cleanup-proof"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "run":
        def interrupted(_signum, _frame):
            raise InterruptedError("Scenario canceled; cleanup is required.")
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        run(args.output.resolve())
    elif args.operation == "cleanup":
        cleanup(args.output.resolve())
    else:
        cleanup_proof(args.output.resolve())


if __name__ == "__main__":
    main()
