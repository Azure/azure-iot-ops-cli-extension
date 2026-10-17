# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Offline contract tests for ops ADO orchestration and fail-closed qualification."""

from datetime import datetime, timezone
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


@pytest.mark.parametrize("hour", [2, 7, 8])
def test_admission_refuses_cleanup_or_github_schedule_window(hour, monkeypatch):
    lookup = Mock()
    monkeypatch.setattr(cluster, "get_json", lookup)
    with pytest.raises(ValueError, match="safe time"):
        cluster.admission(datetime(2026, 10, 17, hour, tzinfo=timezone.utc))
    lookup.assert_not_called()


@pytest.mark.parametrize("workflow", ["int_test.yml", "container_int_test.yml", "cluster_cleanup.yml"])
def test_admission_refuses_active_github_work(workflow, monkeypatch):
    monkeypatch.setattr(cluster, "get_json", Mock(return_value={
        "total_count": 1, "workflow_runs": [{"path": f".github/workflows/{workflow}"}],
    }))
    with pytest.raises(ValueError, match="GitHub"):
        cluster.admission(datetime(2026, 10, 17, 15, tzinfo=timezone.utc))


def test_admission_refuses_other_ado_run(monkeypatch):
    monkeypatch.setattr(cluster, "get_json", Mock(side_effect=[
        *[{"total_count": 0, "workflow_runs": []} for _ in range(5)],
        {"value": [{"id": 123}, {"id": 124}]},
    ]))
    with pytest.raises(ValueError, match="Another ADO"):
        cluster.admission(datetime(2026, 10, 17, 15, tzinfo=timezone.utc))


def test_admission_accepts_idle_window(monkeypatch):
    monkeypatch.setattr(cluster, "get_json", Mock(side_effect=[
        *[{"total_count": 0, "workflow_runs": []} for _ in range(5)], {"value": [{"id": 123}]},
    ]))
    cluster.admission(datetime(2026, 10, 17, 15, tzinfo=timezone.utc))


@pytest.mark.parametrize("hour,allowed", [(1, True), (5, True), (6, False), (8, False)])
def test_quick_run_reserves_timeout_and_cleanup_buffer(hour, allowed, monkeypatch):
    monkeypatch.setenv("OPS_SCENARIO_TIMEOUT_MINUTES", "90")
    lookup = Mock(side_effect=[
        *[{"total_count": 0, "workflow_runs": []} for _ in range(5)], {"value": [{"id": 123}]},
    ])
    monkeypatch.setattr(cluster, "get_json", lookup)
    now = datetime(2026, 10, 17, hour, tzinfo=timezone.utc)
    if allowed:
        cluster.admission(now)
        assert lookup.call_count == 6
    else:
        with pytest.raises(ValueError, match="safe time"):
            cluster.admission(now)
        lookup.assert_not_called()


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
    monkeypatch.setattr(cluster.os, "killpg", kill)
    with pytest.raises(RuntimeError, match="renewal stopped"):
        cluster.Commands(auth=Mock(poll=Mock(return_value=1))).run(["offline-command"])
    kill.assert_called_once_with(12345, cluster.signal.SIGTERM)
    process.wait.assert_called_once()


def test_run_always_cleans_after_provision_failure(monkeypatch, tmp_path):
    pipeline.write(tmp_path / "state.json", make_state())
    monkeypatch.setattr(cluster, "admission", Mock())
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


def test_yaml_keeps_dry_run_separate_and_reuses_existing_tests():
    value = yaml.safe_load((ROOT / ".azure-devops/integration.yml").read_text())
    assert value["trigger"] == "none" and value["pr"] == "none" and "schedules" not in value
    assert next(param for param in value["parameters"] if param["name"] == "mode")["default"] == "Dry run"
    connection = next(param for param in value["parameters"] if param["name"] == "azureServiceConnection")
    assert connection["default"] == "az-iot-ops-int-sp-ado"
    assert value["stages"][0]["stage"] == "Plan"
    live = value["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    assert [stage["stage"] for stage in live] == ["Build", "Lint", "Unit", "Integration", "Qualify"]
    integration = next(stage for stage in live if stage["stage"] == "Integration")
    job = integration["jobs"][0]
    assert job["strategy"]["maxParallel"] == 1
    assert job["timeoutInMinutes"] == "${{ parameters.scenarioTimeoutMinutes }}"
    azure = [step for step in job["steps"] if step.get("task") == "AzureCLI@2"]
    assert len(azure) == 2 and azure[1]["condition"] == "always()"
    assert azure[0]["inputs"]["addSpnToEnvironment"] is True
    assert "continueOnError" not in json.dumps(live)
    assert "SYSTEM_ACCESSTOKEN" in azure[0]["env"]
    assert azure[0]["env"]["OPS_SCENARIO_TIMEOUT_MINUTES"] == "${{ parameters.scenarioTimeoutMinutes }}"
