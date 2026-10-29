# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Offline contract tests for ops ADO orchestration and fail-closed qualification."""

import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
try:
    pipeline = importlib.import_module("ado_integration")
    cluster = importlib.import_module("ado_cluster")
    auth = importlib.import_module("ado_auth")
finally:
    sys.path.pop(0)

SUBSCRIPTION = "a386d5ea-ea90-441a-8263-d816368c84a1"
UUID_VALUE = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def pipeline_environment(monkeypatch, tmp_path):
    for name, value in {
        "SYSTEM_DEFINITIONID": "164", "BUILD_BUILDID": "123", "BUILD_SOURCEVERSION": "a" * 40,
        "SYSTEM_JOBATTEMPT": "1", "OPS_SCENARIOS": "edge", "OPS_CHANNELS": "stable", "OPS_PYTHONS": "3.13",
        "OPS_BASELINES": "{}", "OPS_SUBSCRIPTION": SUBSCRIPTION, "OPS_RESOURCE_GROUP": "ops-cli-int-test-rg",
        "OPS_CUSTOM_LOCATIONS_OID": UUID_VALUE, "OPS_CANDIDATE_DIGEST": "b" * 64,
        "OPS_SCENARIO_TIMEOUT_MINUTES": "360",
        "AZURE_CLIENT_ID": UUID_VALUE, "AZURE_TENANT_ID": UUID_VALUE, "SYSTEM_ACCESSTOKEN": "offline-token",
        "AZURESUBSCRIPTION_SERVICE_CONNECTION_ID": UUID_VALUE, "SYSTEM_TEAMPROJECTID": UUID_VALUE,
        "SYSTEM_PLANID": UUID_VALUE, "SYSTEM_JOBID": UUID_VALUE, "AGENT_TEMPDIRECTORY": str(tmp_path),
        "AZURE_EXTENSION_DIR": str(tmp_path / "azure-cli-extensions"),
    }.items():
        monkeypatch.setenv(name, value)


def make_state():
    suffix = "a" * 11
    prefix = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/ops-cli-int-test-rg/providers"
    return {
        "schema": 1, "producer": pipeline.producer(), "attempt": 1, "suffix": suffix,
        "subscription": SUBSCRIPTION, "resourceGroup": "ops-cli-int-test-rg", "customLocationsObjectId": UUID_VALUE,
        "cluster": f"opado{suffix}", "instance": f"inst{suffix}", "wheel": "/candidate.whl", "sha256": "b" * 64,
        "resources": {
            "cluster": f"{prefix}/Microsoft.Kubernetes/connectedClusters/opado{suffix}",
            "instance": f"{prefix}/Microsoft.IoTOperations/instances/inst{suffix}",
            "storage": f"{prefix}/Microsoft.Storage/storageAccounts/initstore{suffix}",
            "registry": f"{prefix}/Microsoft.DeviceRegistry/schemaRegistries/init-registry{suffix}",
            "namespace": f"{prefix}/Microsoft.DeviceRegistry/namespaces/init-adr-{suffix}",
        },
        "row": {"key": "edge_stable_py313", "python": "3.13", "scenario": {
            "name": "edge-stable", "channel": "stable", "tox_env": "python-edge-int", "parallel": True,
            "test_redeploy": False, "needs_trust": False, "baseline": None, "env": [],
            "init_args": "", "create_args": "",
        }},
        "ownershipChecked": True, "phases": {"init": "passed", "scenario": "passed", "smoke": "passed"},
        "cleanup": "passed", "status": "passed",
    }


def test_plan_reuses_channel_matrix(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPS_SCENARIOS", "edge,runtime-channel")
    monkeypatch.setenv("OPS_CHANNELS", "stable,preview")
    monkeypatch.setenv("OPS_PYTHONS", "3.10,3.13")
    pipeline.plan(tmp_path)
    result = pipeline.read(tmp_path / "plan.json")
    assert len(result["rows"]) == 8
    assert len({row["key"] for row in result["rows"]}) == 8
    assert result["producer"] == pipeline.producer()
    assert result["scenarioTimeoutMinutes"] == 360
    for row in result["rows"]:
        assert ("--use-preview" in row["scenario"]["create_args"]) == (row["scenario"]["channel"] == "preview")
    assert "isOutput=true" in capsys.readouterr().out


@pytest.mark.parametrize("name,value", [
    ("OPS_SCENARIOS", "edge,typo"), ("OPS_SCENARIOS", "Default scenarios,edge"),
    ("OPS_SCENARIOS", "edge,edge"), ("OPS_PYTHONS", "3.9"), ("OPS_PYTHONS", "3.13,3.13"),
    ("OPS_RESOURCE_GROUP", "rg;echo hello"), ("OPS_SUBSCRIPTION", "not-a-guid"),
    ("OPS_CHANNELS", "unknown"), ("OPS_BASELINES", "[]"), ("BUILD_SOURCEVERSION", "main"),
    ("SYSTEM_DEFINITIONID", "0"),
    ("OPS_SCENARIO_TIMEOUT_MINUTES", "0"), ("OPS_SCENARIO_TIMEOUT_MINUTES", "91"),
])
def test_plan_rejects_invalid_inputs(monkeypatch, tmp_path, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        pipeline.plan(tmp_path)
    assert not (tmp_path / "plan.json").exists()


def test_default_selection_excludes_explicit_scenarios(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_SCENARIOS", "Default scenarios")
    pipeline.plan(tmp_path)
    names = {row["scenario"]["name"] for row in pipeline.read(tmp_path / "plan.json")["rows"]}
    assert "edge-stable" in names
    assert not any(name.startswith(("upgrade-path", "broker-diagnostics-removal")) for name in names)


def test_upgrade_requires_pinned_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_SCENARIOS", "upgrade-path")
    with pytest.raises(ValueError, match="baseline"):
        pipeline.plan(tmp_path)


@pytest.mark.parametrize("bad_name", ["../../bad.whl", "azure_iot-1.0-py3-none-any.whl"])
def test_candidate_rejects_other_distribution_or_paths(tmp_path, bad_name):
    pipeline.write(tmp_path / "candidate.json", {
        "schema": 1, "producer": pipeline.producer(), "wheel": {"file": bad_name, "sha256": "b" * 64},
    })
    with pytest.raises(ValueError, match="filename"):
        pipeline.verified_candidate(tmp_path, "b" * 64)


def test_candidate_requires_digest_and_current_producer(tmp_path):
    wheel = tmp_path / "azure_iot_ops-1.0-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("azext_edge/__init__.py", "# test\n")
    value = {"schema": 1, "producer": pipeline.producer(),
             "wheel": {"file": wheel.name, "sha256": pipeline.digest(wheel)}}
    pipeline.write(tmp_path / "candidate.json", value)
    assert pipeline.verified_candidate(tmp_path, value["wheel"]["sha256"]) == wheel
    with pytest.raises(ValueError, match="digest"):
        pipeline.verified_candidate(tmp_path, "b" * 64)
    value["producer"]["build"] = "124"
    pipeline.write(tmp_path / "candidate.json", value)
    with pytest.raises(ValueError, match="producer"):
        pipeline.verified_candidate(tmp_path, pipeline.digest(wheel))


@pytest.mark.parametrize("content", [
    "<testsuite/>", '<testsuite><testcase name="case"><skipped/></testcase></testsuite>',
    '<testsuite><testcase name="case"><failure/></testcase></testsuite>',
    '<testsuite><testcase name="case"><error/></testcase></testsuite>',
])
def test_junit_empty_skipped_failed_or_error_not_qualification(tmp_path, content):
    path = tmp_path / "junit.xml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        pipeline.junit_results(path)


def test_junit_passed_with_explicit_skips(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text('<testsuite><testcase name="passed"/><testcase name="skip"><skipped/></testcase></testsuite>')
    assert pipeline.junit_results(path) == {"passed": 1, "skipped": 1, "total": 2}


@pytest.mark.parametrize("field,value", [
    ("status", "incomplete"), ("cleanup", "incomplete"), ("phases", {"init": "passed"}),
])
def test_report_does_not_hide_incomplete_execution(tmp_path, field, value):
    state = make_state()
    state[field] = value
    pipeline.write(tmp_path / "state.json", state)
    with pytest.raises(ValueError, match="failed"):
        pipeline.report(tmp_path)
    assert pipeline.read(tmp_path / "receipt.json")["status"] == "incomplete"


def test_report_missing_state_fails_and_retains_receipt(tmp_path):
    with pytest.raises(ValueError, match="setup"):
        pipeline.report(tmp_path)
    assert pipeline.read(tmp_path / "receipt.json")["status"] == "incomplete"


def seed_gate(tmp_path, monkeypatch):
    state = make_state()
    plan = tmp_path / "plan.json"
    pipeline.write(plan, {"producer": pipeline.producer(), "rows": [state["row"]]})
    monkeypatch.setenv("OPS_PLAN", str(plan))
    monkeypatch.setenv("OPS_HISTORY", str(tmp_path))
    unit_coverage = tmp_path / "unit-coverage"
    unit_coverage.write_bytes(b"offline unit coverage")
    monkeypatch.setenv("OPS_UNIT_COVERAGE", str(unit_coverage))
    directory = tmp_path / "ops-attempt-edge_stable_py313-1"
    pipeline.write(directory / "state.json", state)
    pipeline.report(directory)
    for phase in pipeline.expected_phases(state["row"]):
        path = directory / "junit" / f"{phase}.xml"
        path.parent.mkdir(exist_ok=True)
        path.write_text('<testsuite><testcase name="passed"/></testsuite>')
    (directory / "coverage.dat").write_bytes(b"offline coverage")
    monkeypatch.setattr(pipeline.subprocess, "run", Mock())
    return directory


def test_gate_accepts_complete_selected_scope_not_release(tmp_path, monkeypatch):
    seed_gate(tmp_path, monkeypatch)
    pipeline.gate(tmp_path / "qualification")
    value = pipeline.read(tmp_path / "qualification/qualification.json")
    assert value["scope"] == "selected ops scenarios" and value["releaseQualified"] is False
    assert len(value["scenarios"]) == 1


@pytest.mark.parametrize("mutation", [
    "missing", "digest", "producer", "cleanup", "phase", "junit", "coverage", "newer",
])
def test_gate_rejects_missing_stale_or_failed_evidence(tmp_path, monkeypatch, mutation):
    directory = seed_gate(tmp_path, monkeypatch)
    receipt = pipeline.read(directory / "receipt.json")
    if mutation == "missing":
        (directory / "receipt.json").unlink()
    elif mutation == "coverage":
        (directory / "coverage.dat").unlink()
    elif mutation == "junit":
        (directory / "junit/init.xml").write_text("<testsuite/>")
    else:
        if mutation == "digest":
            receipt["sha256"] = "c" * 64
        elif mutation == "producer":
            receipt["producer"]["commit"] = "c" * 40
        elif mutation == "cleanup":
            receipt["cleanup"] = "incomplete"
        elif mutation == "phase":
            receipt["phases"].pop("init")
        elif mutation == "newer":
            receipt["attempt"] = 2
            receipt["status"] = "incomplete"
            directory = directory.with_name("ops-attempt-edge_stable_py313-2")
        pipeline.write(directory / "receipt.json", receipt)
    with pytest.raises(ValueError):
        pipeline.gate(tmp_path / "qualification")


@pytest.mark.parametrize("field", ["producer", "resources", "subscription", "suffix", "cluster", "instance"])
def test_cleanup_rejects_foreign_state_before_commands(tmp_path, monkeypatch, field):
    state = make_state()
    if field == "producer":
        state[field]["build"] = "999"
    elif field == "resources":
        state[field]["storage"] = "/subscriptions/other/resourceGroups/production/storage"
    else:
        state[field] = "foreign"
    pipeline.write(tmp_path / "state.json", state)
    commands = Mock()
    monkeypatch.setattr(cluster, "Commands", commands)
    with pytest.raises(ValueError):
        cluster.cleanup(tmp_path)
    commands.assert_not_called()


def test_cleanup_deletes_only_manifest_resources_and_pins_adr_api(tmp_path, monkeypatch):
    state = make_state()
    pipeline.write(tmp_path / "state.json", state)
    commands = Mock()
    commands.az_json.side_effect = [
        {"id": SUBSCRIPTION, "environmentName": "AzureCloud"},
        [{"id": value} for value in state["resources"].values()],
        [{"id": value} for key, value in state["resources"].items() if key != "instance"],
        [{"id": "/unrelated/resource"}],
    ]
    monkeypatch.setattr(cluster, "Commands", Mock(return_value=commands))
    cluster.cleanup(tmp_path)
    calls = [call.args[0] for call in commands.run.call_args_list]
    deletes = [args for args in calls if args[:3] == ["az", "resource", "delete"]]
    assert len(deletes) == 4
    assert all(args[4] in state["resources"].values() for args in deletes)
    assert all("--api-version" in args for args in deletes if "Microsoft.DeviceRegistry" in args[4])
    assert pipeline.read(tmp_path / "state.json")["cleanup"] == "passed"


def test_cleanup_does_not_stop_after_one_delete_failure(tmp_path, monkeypatch):
    state = make_state()
    pipeline.write(tmp_path / "state.json", state)
    commands = Mock()
    resources = [{"id": value} for key, value in state["resources"].items() if key != "instance"]
    commands.az_json.side_effect = [{"id": SUBSCRIPTION, "environmentName": "AzureCloud"}, resources, resources, []]
    commands.run.side_effect = [subprocess.CalledProcessError(1, ["az"]), None, None, None]
    monkeypatch.setattr(cluster, "Commands", Mock(return_value=commands))
    with pytest.raises(RuntimeError, match="Cleanup had failures"):
        cluster.cleanup(tmp_path)
    assert commands.run.call_count == 4
    assert pipeline.read(tmp_path / "state.json")["cleanup"] == "incomplete"


@pytest.mark.parametrize("stale_reads", [0, 2, 20])
def test_cleanup_waits_boundedly_for_deleted_resources(tmp_path, monkeypatch, stale_reads):
    state = make_state()
    pipeline.write(tmp_path / "state.json", state)
    resources = [{"id": state["resources"]["storage"]}]
    commands = Mock()
    commands.az_json.side_effect = [
        {"id": SUBSCRIPTION, "environmentName": "AzureCloud"}, resources, resources,
        *([resources] * stale_reads), [],
    ]
    sleep = Mock()
    monkeypatch.setattr(cluster, "Commands", Mock(return_value=commands))
    monkeypatch.setattr(cluster.time, "sleep", sleep)
    if stale_reads == 20:
        with pytest.raises(RuntimeError, match="resources remain"):
            cluster.cleanup(tmp_path)
        assert pipeline.read(tmp_path / "state.json")["cleanup"] == "incomplete"
    else:
        cluster.cleanup(tmp_path)
        assert pipeline.read(tmp_path / "state.json")["cleanup"] == "passed"
    assert sleep.call_count == min(stale_reads, 19)
    commands.run.assert_called_once_with(
        ["az", "resource", "delete", "--ids", state["resources"]["storage"]], timeout=180,
    )


def test_environment_drops_control_tokens_and_truthy_false_cleanup(monkeypatch, tmp_path):
    monkeypatch.setenv("idToken", "offline-assertion")
    monkeypatch.setenv("servicePrincipalKey", "offline-secret")
    monkeypatch.setenv("azext_edge_aio_cleanup", "false")
    monkeypatch.setenv("azext_edge_rg", "wrong-rg")
    environment = cluster.test_environment(make_state(), tmp_path)
    assert environment["azext_edge_rg"] == "ops-cli-int-test-rg"
    for name in ("SYSTEM_ACCESSTOKEN", "idToken", "servicePrincipalKey", "azext_edge_aio_cleanup"):
        assert name not in environment


def test_commands_abort_when_auth_process_dies(monkeypatch):
    process = Mock(pid=12345, returncode=None)
    process.poll.return_value = None
    monkeypatch.setattr(cluster.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    # Windows does not expose this Unix API.
    monkeypatch.delattr(cluster.os, "killpg", raising=False)
    monkeypatch.setattr(cluster.os, "killpg", kill, raising=False)
    with pytest.raises(RuntimeError, match="renewal stopped"):
        cluster.Commands(auth=Mock(poll=Mock(return_value=1))).run(["offline-command"])
    kill.assert_called_once_with(12345, cluster.signal.SIGTERM)
    process.wait.assert_called_once()


@pytest.mark.parametrize("failed_waits", [0, 2, 60])
def test_cluster_waits_for_its_registered_ready_node(monkeypatch, tmp_path, failed_waits):
    state = make_state()
    directory, _ = cluster.cluster_paths(state)
    directory.mkdir()
    binary = directory / "k3s"
    binary.write_bytes(b"offline-k3s")
    commands = Mock()
    error = subprocess.CalledProcessError(1, ["kubectl", "wait"])
    commands.run.side_effect = [None] + [error] * failed_waits + [None]
    sleep = Mock()
    copy_config = Mock()
    monkeypatch.setattr(cluster.time, "sleep", sleep)
    monkeypatch.setattr(cluster.subprocess, "run", copy_config)
    monkeypatch.setenv("KUBECONFIG", "before-start")

    if failed_waits == 60:
        with pytest.raises(subprocess.CalledProcessError):
            cluster.start_cluster(commands, state, tmp_path)
        copy_config.assert_not_called()
        assert cluster.os.environ["KUBECONFIG"] == "before-start"
    else:
        cluster.start_cluster(commands, state, tmp_path)
        copy_config.assert_called_once()
        assert cluster.os.environ["KUBECONFIG"] == str(directory / "user-config")

    waits = commands.run.call_args_list[1:]
    assert len(waits) == min(failed_waits + 1, 60)
    assert sleep.call_count == min(failed_waits, 59)
    for call in waits:
        assert call.args[0] == [
            "sudo", "-n", str(binary), "kubectl", "--kubeconfig", str(directory / "config"),
            "wait", "--for=condition=Ready", f"node/{state['cluster']}", "--timeout=5s",
        ]
        assert call.kwargs == {"timeout": 20}
    assert pipeline.read(tmp_path / "state.json")["clusterStarted"] is True


@pytest.mark.parametrize("definition", ["164", "167"])
def test_run_without_admission_still_cleans_after_provision_failure(monkeypatch, tmp_path, definition):
    monkeypatch.setenv("SYSTEM_DEFINITIONID", definition)
    pipeline.write(tmp_path / "state.json", make_state())
    monkeypatch.setattr(cluster.os, "cpu_count", Mock(return_value=1))
    lookup = Mock(side_effect=AssertionError("Unexpected admission lookup"))
    monkeypatch.setattr(auth.requests, "get", lookup)
    identity = Mock(poll=Mock(return_value=None))
    monkeypatch.setattr(cluster, "start_auth", Mock(return_value=identity))
    commands = Mock()
    monkeypatch.setattr(cluster, "Commands", Mock(return_value=commands))
    monkeypatch.setattr(cluster, "check_account", Mock())
    monkeypatch.setattr(cluster, "resource_ids", Mock(return_value=set()))
    monkeypatch.setattr(cluster, "start_cluster", Mock(side_effect=RuntimeError("offline setup failure")))
    cleanup = Mock()
    monkeypatch.setattr(cluster, "cleanup", cleanup)
    with pytest.raises(RuntimeError, match="offline setup failure"):
        cluster.run(tmp_path)
    lookup.assert_not_called()
    cluster.start_cluster.assert_called_once()
    cleanup.assert_called_once_with(tmp_path)
    identity.terminate.assert_called_once()


def test_assertion_request_is_scoped_and_never_redirects(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"oidcToken": "offline-assertion"}
    post = Mock()
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    post.return_value = context
    monkeypatch.setattr(auth.requests, "post", post)
    assert auth.assertion() == "offline-assertion"
    assert post.call_args.kwargs["params"]["serviceConnectionId"] == UUID_VALUE
    assert post.call_args.kwargs["allow_redirects"] is False
    assert "azureiotdevxp" in post.call_args.args[0]


def test_auth_error_does_not_print_assertions(capsys):
    auth.failure(RuntimeError, RuntimeError("offline-secret-assertion"), None)
    stderr = capsys.readouterr().err
    assert "RuntimeError" in stderr and "offline-secret-assertion" not in stderr


def test_auth_start_ignores_stale_readiness_and_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "auth.ready").write_text("stale")
    process = Mock(poll=Mock(return_value=1))
    monkeypatch.setattr(cluster.subprocess, "Popen", Mock(return_value=process))
    with pytest.raises(RuntimeError, match="preflight failed"):
        cluster.start_auth(tmp_path)
    assert not (tmp_path / "auth.ready").exists()
    process.wait.assert_called_once()


def test_auth_shutdown_kills_only_owned_process_if_unresponsive():
    process = Mock(poll=Mock(return_value=None))
    process.wait.side_effect = [subprocess.TimeoutExpired(["auth"], 90), None]
    with pytest.raises(RuntimeError, match="shut down"):
        cluster.stop_auth(process)
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


@pytest.mark.parametrize("mismatch", [None, "id", "tenantId", "name"])
def test_refresh_requires_exact_account_and_preserves_profile(tmp_path, monkeypatch, mismatch):
    from azure.cli.core import _environment, _profile, cloud
    from azure.cli.core.auth import identity, msal_credentials

    account = {
        "id": SUBSCRIPTION, "tenantId": UUID_VALUE, "isDefault": True, "environmentName": "AzureCloud",
        "user": {"name": UUID_VALUE, "type": "servicePrincipal"},
    }
    if mismatch:
        target = account["user"] if mismatch == "name" else account
        target[mismatch] = "22222222-2222-4222-8222-222222222222"
    profile = tmp_path / "azureProfile.json"
    before = json.dumps({"subscriptions": [account]}).encode()
    profile.write_bytes(before)
    monkeypatch.setattr(_environment, "get_config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cloud, "get_active_cloud_name", lambda _: "AzureCloud")
    monkeypatch.setattr(cloud, "get_cloud", lambda *_: SimpleNamespace(
        name="AzureCloud", endpoints=SimpleNamespace(
            active_directory="https://login.microsoftonline.com",
            active_directory_resource_id="https://management.core.windows.net/",
        ),
    ))
    cached_identity = Mock(tenant_id=UUID_VALUE, _msal_app_kwargs={})
    create_identity = Mock(return_value=cached_identity)
    monkeypatch.setattr(_profile, "_create_identity_instance", create_identity)
    service_auth = Mock()
    monkeypatch.setattr(identity.ServicePrincipalAuth, "build_from_credential", Mock(return_value=service_auth))
    credential = Mock()
    monkeypatch.setattr(msal_credentials, "ServicePrincipalCredential", Mock(return_value=credential))
    acquire = Mock(return_value="offline-assertion")
    monkeypatch.setattr(auth, "assertion", acquire)
    if mismatch:
        with pytest.raises(ValueError, match="account does not match"):
            auth.refresh()
        acquire.assert_not_called()
        create_identity.assert_not_called()
    else:
        auth.refresh()
        credential.acquire_token.assert_called_once()
        cached_identity._service_principal_store.save_entry.assert_called_once_with(  # pylint: disable=protected-access
            service_auth.get_entry_to_persist(),
        )
    assert profile.read_bytes() == before


@pytest.mark.parametrize("name", ["azext_edge_rg", "azext_edge_wheel", "azext_edge_skip_init", "SYSTEM_ACCESSTOKEN"])
def test_scenario_cannot_override_execution_contract(name, tmp_path):
    state = make_state()
    state["row"]["scenario"]["env"] = [{"name": name, "value": "override"}]
    with pytest.raises(ValueError, match="override"):
        cluster.test_environment(state, tmp_path)


@pytest.mark.parametrize("mutation", [None, "digest", "origin", "missing", "fragment"])
def test_inventory_recovers_only_the_exact_tox_candidate(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    original = tmp_path / ".tox/.tmp/package/1/azure_iot_ops-2.0.0b1.tar.gz"
    retained = tmp_path / ".tox/.pkg/dist" / original.name
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b"installed candidate archive")
    provenance = {"url": original.as_uri(), "archive_info": {"hashes": {"sha256": pipeline.digest(retained)}}}
    fragment = "#sha256=" + ("0" * 64 if mutation == "fragment" else pipeline.digest(retained))
    if mutation == "digest":
        retained.write_bytes(b"different archive")
    elif mutation == "origin":
        provenance["url"] = (tmp_path / "another.tar.gz").as_uri()
    elif mutation == "missing":
        retained.unlink()
    monkeypatch.setattr(pipeline, "distribution", Mock(return_value=SimpleNamespace(
        read_text=lambda _: json.dumps(provenance))))
    requirements = f"azure-iot-ops @ {original.as_uri()}{fragment}\nshared==1.0\n"
    monkeypatch.setattr(pipeline.subprocess, "check_output", Mock(return_value=requirements))
    output = tmp_path / "dependency-inventory"
    if mutation:
        with pytest.raises(ValueError, match="exact installed candidate"):
            pipeline.inventory(output)
        assert not output.exists()
    else:
        pipeline.inventory(output)
        assert (output / "environment/requirements.txt").read_text() == (
            f"azure-iot-ops @ {retained.as_uri()}{fragment}\nshared==1.0\n"
        )


def test_dependency_inventory_preserves_each_installed_environment(tmp_path, monkeypatch):
    extension = tmp_path / "azure-iot-ops"
    extension.mkdir()
    candidate = "azure-iot-ops @ file:///candidate/azure_iot_ops-2.0.0b1-py3-none-any.whl\n"
    packages = Mock(side_effect=[
        "azure-cli==2.80.0\nshared==1.0\n",
        candidate + "shared==2.0\n",
    ])
    monkeypatch.setattr(pipeline.subprocess, "check_output", packages)
    output = tmp_path / "dependency-inventory"
    pipeline.inventory(output, extension)
    assert (output / "environment/requirements.txt").read_text() == "azure-cli==2.80.0\nshared==1.0\n"
    assert (output / "extension/requirements.txt").read_text() == candidate + "shared==2.0\n"
    assert "--path" not in packages.call_args_list[0].args[0]
    assert packages.call_args_list[1].args[0][-2:] == ["--path", str(extension)]


@pytest.mark.parametrize("extension_packages", ["", "shared==2.0\n"])
def test_dependency_inventory_rejects_missing_installed_extension(tmp_path, monkeypatch, extension_packages):
    extension = tmp_path / "azure-iot-ops"
    extension.mkdir()
    monkeypatch.setattr(pipeline.subprocess, "check_output", Mock(side_effect=[
        "azure-cli==2.80.0\n", extension_packages,
    ]))
    output = tmp_path / "dependency-inventory"
    with pytest.raises(ValueError, match="empty|installed extension is missing"):
        pipeline.inventory(output, extension)
    assert not (output / "extension/requirements.txt").exists()


def test_dependency_inventory_requires_existing_extension_directory(tmp_path, monkeypatch):
    packages = Mock()
    monkeypatch.setattr(pipeline.subprocess, "check_output", packages)
    with pytest.raises(ValueError, match="directory is missing"):
        pipeline.inventory(tmp_path / "dependency-inventory", tmp_path / "missing")
    packages.assert_not_called()


@pytest.mark.parametrize("result", ["", subprocess.CalledProcessError(1, ["pip", "freeze"])])
def test_dependency_inventory_rejects_empty_or_failed_collection(tmp_path, monkeypatch, result):
    packages = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
    monkeypatch.setattr(pipeline.subprocess, "check_output", packages)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        pipeline.inventory(tmp_path / "dependency-inventory")
    assert not (tmp_path / "dependency-inventory").exists()


def test_yaml_exposes_installed_dependencies_even_after_test_failure():
    template = yaml.safe_load((ROOT / ".azure-devops/templates/integration-pipeline.yml").read_text())
    live = template["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    jobs = {stage["stage"]: stage["jobs"][0]["steps"] for stage in live}
    for stage, interpreter in (("Build", "python"), ("Lint", ".tox/lint/bin/python"),
                               ("Unit", ".tox/python/bin/python")):
        step = next(step for step in jobs[stage] if " inventory" in step.get("bash", ""))
        assert f"{interpreter} tools/ado_integration.py inventory" in step["bash"]
        assert f"$(Build.SourcesDirectory)/dependency-inventory/{stage.lower()}" in step["bash"]
        assert step["condition"] == "succeededOrFailed()"
        feed = next(item for item in jobs[stage] if item.get("template") == "release-feed.yml")
        assert jobs[stage].index(feed) > jobs[stage].index(step)
        assert feed["parameters"]["condition"] == step["condition"]
    assert "sysconfig.get_paths()" in step["bash"] and '--extension-dir "$extension"' in step["bash"]
    scenario = jobs["Integration"]
    prepare = next(step for step in scenario if " prepare --output" in step.get("bash", ""))
    assert prepare["bash"].index(" prepare --output") < prepare["bash"].index(" inventory")
    cleanup = next(step for step in scenario if "cleanup --output" in step.get("inputs", {}).get("inlineScript", ""))
    inventory = next(step for step in scenario if step.get("displayName", "").startswith("Refresh installed"))
    assert scenario.index(inventory) > scenario.index(cleanup)
    assert inventory["condition"] == "always()"
    assert '$(Build.SourcesDirectory)/dependency-inventory/scenario' in inventory["bash"]
    assert '--extension-dir "$(Agent.TempDirectory)/azure-cli-extensions/azure-iot-ops"' in inventory["bash"]
    feed = next(step for step in scenario if step.get("template") == "release-feed.yml")
    assert scenario.index(feed) > scenario.index(inventory)
    assert feed["parameters"]["condition"] == "always()"
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-feed.yml").read_text())
    assert template["parameters"][0]["default"] == "succeeded()"
    assert all(step["condition"] == "${{ parameters.condition }}" for step in template["steps"])
    assert template["steps"][0]["inputs"] == {"artifactFeeds": "aziotcli/pip", "onlyAddExtraIndex": False}


def test_yaml_keeps_dry_run_separate_and_reuses_existing_tests():
    value = yaml.safe_load((ROOT / ".azure-devops/integration.yml").read_text())
    assert value["trigger"] == "none" and value["pr"] == "none" and "schedules" not in value
    assert next(param for param in value["parameters"] if param["name"] == "mode")["default"] == "Dry run"
    connection = next(param for param in value["parameters"] if param["name"] == "azureServiceConnection")
    assert connection["default"] == "az-iot-ops-int-sp-ado"
    assert value["extends"]["template"] == "templates/integration-pipeline.yml"
    value = yaml.safe_load((ROOT / ".azure-devops/templates/integration-pipeline.yml").read_text())
    assert value["stages"][0]["stage"] == "Plan"
    live = value["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    assert [stage["stage"] for stage in live] == ["Build", "Lint", "Unit", "Integration", "Qualify"]
    integration = next(stage for stage in live if stage["stage"] == "Integration")
    job = integration["jobs"][0]
    assert job["pool"] == {
        "name": "iotupx-ops-integration",
        "demands": ["ImageOverride -equals iotupx-1espt-ubuntu2404"],
    }
    pool = json.loads((ROOT / ".azure-devops/integration-pool.json").read_text())["resources"][0]
    assert pool["name"] == job["pool"]["name"]
    assert pool["properties"]["sku"]["name"] == "Standard_D8ds_v5"
    assert pool["properties"]["maxPoolSize"] == 1
    assert pool["properties"]["agentProfile"] == {
        "type": "Stateless", "resourcePredictions": [{"00:00:00": 0}],
    }
    assert all("pool" not in stage for stage in live)
    assert all("pool" not in job for stage in live if stage["stage"] != "Integration" for job in stage["jobs"])
    assert job["strategy"]["maxParallel"] == 1
    assert job["${{ else }}"]["timeoutInMinutes"] == "${{ parameters.scenarioTimeoutMinutes }}"
    azure = [step for step in job["steps"] if step.get("task") == "AzureCLI@2"]
    assert len(azure) == 2 and azure[1]["condition"] == "always()"
    assert azure[0]["inputs"]["addSpnToEnvironment"] is True
    assert "continueOnError" not in json.dumps(live)
    assert "SYSTEM_ACCESSTOKEN" in azure[0]["env"]
    assert azure[0]["env"]["${{ else }}"]["OPS_SCENARIO_TIMEOUT_MINUTES"] == "${{ parameters.scenarioTimeoutMinutes }}"
