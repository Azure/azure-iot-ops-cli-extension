# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Execute one ops scenario on fresh resources; never sweep the shared resource group."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from uuid import UUID
from xml.etree import ElementTree

import requests
import yaml

from ado_integration import (
    ROOT, expected_locations, expected_phases, junit_results, producer, read, required, scenario_timeout, write,
)


K3S_VERSION = "v1.31.1+k3s1"
MARKERS = {
    "python-edge-int": "edge", "python-long-int": "long_running",
    "python-rpsaas-int": "rpsaas and not long_running", "python-runtime-int": "runtime_channel",
    "python-upgrade-int": "upgrade", "python-mgmtactions-int": "mgmtactions",
    "python-livedata-int": "livedata", "python-wlif-int": "require_wlif_setup",
}


class Commands:
    def __init__(self, auth=None, budget=None):
        self.auth = auth
        self.deadline = time.monotonic() + budget if budget is not None else None

    def run(self, arguments, *, capture=False, env=None, cwd=None, timeout=1800):
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("The configured health scenario execution budget expired.")
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
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()

    def az_json(self, *arguments):
        return json.loads(self.run(["az", *arguments, "--output", "json"], capture=True))


def get_json(url, *, token=None, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with requests.get(url, headers=headers, params=params, timeout=(10, 30), allow_redirects=False) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Admission lookup failed with HTTP {response.status_code}.")
        return response.json()


def admission(now=None):
    now = now or datetime.now(timezone.utc)
    # Existing GitHub cleanup starts at 08:00 UTC and the daily integration at 09:00.
    # Reserve the full configured job timeout plus an hour for cancellation/cleanup.
    window = timedelta(minutes=scenario_timeout() + 60)
    for hour in (8, 9):
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)
        if scheduled - now < window:
            raise ValueError("Insufficient safe time before scheduled ops cleanup/integration; no resources created.")
    runs = get_json(
        "https://dev.azure.com/azureiotdevxp/aziotcli/_apis/build/builds",
        token=required("SYSTEM_ACCESSTOKEN"),
        params={"statusFilter": "inProgress,notStarted",
                "api-version": "7.1", "$top": 100},
    )
    if len(runs["value"]) >= 100:
        raise ValueError("Too many ADO runs to establish safe admission.")
    for build in runs["value"]:
        definition = build["definition"]
        family = definition["id"] == 164 or definition["name"] == "Azure IoT Operations CLI - Integration Health"
        if family and str(build["id"]) != required("BUILD_BUILDID"):
            raise ValueError("Another ADO ops integration or health run is active or queued.")


def validate_state(state):
    if state["producer"] != producer() or state["subscription"] != str(UUID(required("OPS_SUBSCRIPTION"))):
        raise ValueError("Provisioning state does not match this run and approved subscription.")
    suffix = state["suffix"]
    if not re.fullmatch(r"[0-9a-f]{11}", suffix):
        raise ValueError("Invalid attempt resource suffix.")
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", state["resourceGroup"]):
        raise ValueError("Invalid resource group.")
    if state["resourceGroup"] != required("OPS_RESOURCE_GROUP"):
        raise ValueError("Provisioning state does not match the approved resource group.")
    prefix = f"/subscriptions/{state['subscription']}/resourceGroups/{state['resourceGroup']}/providers"
    expected = {
        "cluster": f"{prefix}/Microsoft.Kubernetes/connectedClusters/opado{suffix}",
        "instance": f"{prefix}/Microsoft.IoTOperations/instances/inst{suffix}",
        "storage": f"{prefix}/Microsoft.Storage/storageAccounts/initstore{suffix}",
        "registry": f"{prefix}/Microsoft.DeviceRegistry/schemaRegistries/init-registry{suffix}",
        "namespace": f"{prefix}/Microsoft.DeviceRegistry/namespaces/init-adr-{suffix}",
    }
    if (state["resources"] != expected or state["cluster"] != f"opado{suffix}"
            or state["instance"] != f"inst{suffix}"):
        raise ValueError("Refusing resources outside this attempt's exact ownership manifest.")
    if state.get("health"):
        from integration_health import validate
        validate(state["health"]["profile"])
        planned = {key: state["health"]["profile"][key] for key in
                   ("clusterRegion", "resourceRegion", "namespaceRegion")}
        if state["locations"] != planned:
            raise ValueError("Resource locations differ from the health profile.")


def check_account(commands, state):
    account = commands.az_json("account", "show")
    if account["id"].lower() != state["subscription"] or account["environmentName"] != "AzureCloud":
        raise ValueError("Azure CLI is not using the approved public-cloud subscription.")


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


def check_agent_capacity():
    cpus = os.cpu_count() or 0
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    free = shutil.disk_usage(required("AGENT_TEMPDIRECTORY")).free
    print(f"Agent capacity: {cpus} CPUs, {memory / 10**9:.1f} GB RAM, {free / 10**9:.1f} GB free disk.", flush=True)
    if cpus < 4 or memory < 16 * 10**9 or free < 30 * 10**9:
        raise ValueError("Ops integration requires at least 4 CPUs, 16 GB RAM and 30 GB free agent disk.")


def start_cluster(commands, state, output, issuer=None):
    directory, unit = cluster_paths(state)
    directory.mkdir(parents=True, exist_ok=True)
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
    commands.run(arguments)
    for attempt in range(60):
        try:
            commands.run(["sudo", "-n", str(binary), "kubectl", "--kubeconfig", str(directory / "config"),
                          "wait", "--for=condition=Ready", f"node/{state['cluster']}", "--timeout=5s"], timeout=20)
            break
        except subprocess.CalledProcessError:
            if attempt == 59:
                raise
            time.sleep(5)
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
    commands.run(["az", "extension", "add", "--name", "connectedk8s", "--yes"])
    common = ["--name", state["cluster"], "--resource-group", state["resourceGroup"]]
    custom = ["--custom-locations-oid", state["customLocationsObjectId"]]
    location = ["--location", state["locations"]["clusterRegion"]] if state.get("health") else []
    commands.run(["az", "connectedk8s", "connect", *common, *custom, *location], timeout=1800)
    commands.run(["az", "connectedk8s", "enable-features", "--features", "custom-locations", "cluster-connect",
                  *common, *custom])
    trust = state["row"]["scenario"]["needs_trust"]
    if trust:
        commands.run(["az", "connectedk8s", "update", *common, "--enable-oidc-issuer", "--enable-workload-identity"])
    for attempt in range(20):
        cluster = commands.az_json("connectedk8s", "show", *common)
        if cluster.get("connectivityStatus") == "Connected":
            break
        if attempt == 19:
            raise RuntimeError("Arc cluster did not become connected.")
        time.sleep(15)
    if trust:
        issuer = cluster["oidcIssuerProfile"]["issuerUrl"]
        if not issuer.startswith("https://"):
            raise ValueError("Invalid Arc workload identity issuer.")
        start_cluster(commands, state, output, issuer)
    if state.get("health") and cluster["location"].replace(" ", "").lower() != state["locations"]["clusterRegion"]:
        raise ValueError("Arc cluster location differs from the health profile.")


def create_resources(commands, state):
    names = {key: value.rsplit("/", 1)[-1] for key, value in state["resources"].items()}
    common = ["--resource-group", state["resourceGroup"]]
    location = ["--location", state["locations"]["resourceRegion"]] if state.get("health") else []
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
        "--location", state["locations"]["namespaceRegion"] if state.get("health") else "australiaeast",
        "--output", "none",
    ])


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
        "azext_edge_upgrade_baseline": json.dumps(scenario["baseline"]),
        "azext_edge_init_args": scenario["init_args"], "azext_edge_create_args": scenario["create_args"],
        "azext_edge_schema_registry_id": state["resources"]["registry"],
        "azext_edge_adr_namespace_id": state["resources"]["namespace"],
        "azext_edge_sp_object_id": required("AZURE_CLIENT_ID"),
        "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "no", "AZURE_TEST_RUN_LIVE": "True",
        "COVERAGE_FILE": str(output / "coverage.dat"),
    })
    protected = {"azext_edge_aio_cleanup", "azext_edge_init_continue_on_error", "azext_edge_skip_init"}
    for item in scenario["env"]:
        if (not re.fullmatch(r"(azext_edge_|AIO_CLI_)[A-Za-z0-9_]+", item["name"])
                or item["name"] in environment or item["name"] in protected):
            raise ValueError("Unsupported scenario environment override.")
        environment[item["name"]] = item["value"]
    return environment


def verify_locations(commands, state, output):
    if not state.get("health"):
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
    args = [
        sys.executable, str(ROOT / "tools/integration_runner.py"), "--extension-dir", str(target),
        "--tests", str(ROOT / "azext_edge/tests"), "--work-dir", str(output / "work" / phase),
        "--junit", str(junit), "--coverage-config", str(ROOT / ".coveragerc"), "--scenario", marker,
    ]
    if phase == "scenario" and state["row"]["scenario"]["parallel"]:
        args += ["-n", "6", "--dist", "worksteal"]
    commands.run(args, env=environment, cwd=output, timeout=18000)
    junit_results(junit)
    state["phases"][phase] = "passed"
    write(output / "state.json", state)


def smoke(commands, state, output):
    diagnostics = output / "diagnostics"
    diagnostics.mkdir()
    suite = ElementTree.Element("testsuite", name="ops-smoke")
    arguments = [
        ["support", "create-bundle"], ["support", "create-bundle", "--svc", "broker", "--broker-traces"],
        ["support", "create-bundle", "--ops-service", "acs", "secretstore"], ["check"], ["check", "--pre"],
        ["check", "--post"], ["check", "--as-object"],
        ["check", "--svc", "broker", "--resources", "broker", "brokerlistener"],
        ["asset", "query", "-g", state["resourceGroup"], "--location",
         state["locations"]["namespaceRegion"] if state.get("health") else "westus"],
        ["get-versions", "--inline"],
    ]
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


def cleanup(output):
    if not (output / "state.json").exists():
        print("No provisioning state: execution never reached resource creation.", flush=True)
        return
    state = read(output / "state.json")
    validate_state(state)
    commands = Commands()
    state["cleanup"] = "incomplete"
    write(output / "state.json", state)
    errors = []
    try:
        if state["ownershipChecked"]:
            check_account(commands, state)
            present = resource_ids(commands, state)
            if state["resources"]["instance"].lower() in present:
                try:
                    commands.run(["az", "iot", "ops", "delete", "--name", state["instance"],
                                  "-g", state["resourceGroup"], "--yes", "--force"], timeout=900)
                except (subprocess.CalledProcessError, TimeoutError) as error:
                    print(f"##vso[task.logissue type=error]Instance cleanup failed ({type(error).__name__}).")
                    errors.append("instance")
            present = resource_ids(commands, state)
            for key in ("instance", "cluster", "registry", "namespace", "storage"):
                resource = state["resources"][key]
                if resource.lower() in present:
                    args = ["az", "resource", "delete", "--ids", resource]
                    if key in {"registry", "namespace"}:
                        args += ["--api-version", "2026-04-01"]
                    try:
                        commands.run(args, timeout=180)
                    except (subprocess.CalledProcessError, TimeoutError) as error:
                        print(f"##vso[task.logissue type=error]{key} cleanup failed ({type(error).__name__}).")
                        errors.append(key)
            for attempt in range(20):
                remaining = resource_ids(commands, state) & {value.lower() for value in state["resources"].values()}
                if not remaining:
                    break
                if attempt == 19:
                    raise RuntimeError("Attempt resources remain after cleanup.")
                print(f"Waiting for {len(remaining)} deleted attempt resources to disappear.", flush=True)
                time.sleep(15)
    finally:
        if state.get("clusterStarted"):
            _, unit = cluster_paths(state)
            result = subprocess.run(
                ["sudo", "-n", "systemctl", "show", unit, "--property=LoadState", "--value"],
                capture_output=True, text=True, check=False,
            )
            if result.stdout.strip() != "not-found":
                result.check_returncode()
                commands.run(["sudo", "-n", "systemctl", "stop", unit])
    if errors:
        raise RuntimeError(f"Cleanup had failures: {', '.join(errors)}. Inspect retained state and retry cleanup.")
    state["cleanup"] = "passed"
    write(output / "state.json", state)


def run(output):
    state = read(output / "state.json")
    validate_state(state)
    auth = None
    try:
        check_agent_capacity()
        admission()
        auth = start_auth(output)
        commands = Commands(auth, budget=scenario_timeout() * 60 if state.get("health") else None)
        check_account(commands, state)
        commands.az_json("group", "show", "--name", state["resourceGroup"])
        if resource_ids(commands, state) & {value.lower() for value in state["resources"].values()}:
            raise ValueError("Attempt resource names already exist; refusing reuse.")
        state["ownershipChecked"] = True
        write(output / "state.json", state)
        start_cluster(commands, state, output)
        if state["row"]["scenario"]["needs_trust"]:
            configure_trust(commands)
        connect_cluster(commands, state, output)
        create_resources(commands, state)
        test_phase(commands, state, output, "init", "init_scenario_test")
        verify_locations(commands, state, output)
        scenario = state["row"]["scenario"]
        if scenario["tox_env"]:
            test_phase(commands, state, output, "scenario", MARKERS[scenario["tox_env"]])
        smoke(commands, state, output)
        if scenario["test_redeploy"]:
            commands.run(["az", "iot", "ops", "delete", "--name", state["instance"],
                          "-g", state["resourceGroup"], "--yes"], timeout=1800)
            test_phase(commands, state, output, "redeploy", "init_scenario_test")
        if any(state["phases"].get(phase) != "passed" for phase in expected_phases(state["row"])):
            raise ValueError("Required scenario phase is incomplete.")
        if auth.poll() is not None:
            raise RuntimeError("Credential renewal failed before completion.")
        state["status"] = "passed"
        write(output / "state.json", state)
    finally:
        try:
            cleanup(output)
        finally:
            if auth is not None:
                stop_auth(auth)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["run", "cleanup"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "run":
        def interrupted(_signum, _frame):
            raise InterruptedError("Scenario canceled; cleanup is required.")
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        run(args.output.resolve())
    else:
        cleanup(args.output.resolve())


if __name__ == "__main__":
    main()
