# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import hashlib
import importlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import tarfile
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
AUTOMATION = "a" * 40
SOURCE = "b" * 40


@pytest.fixture
def branch(monkeypatch, monitor):
    monkeypatch.setenv("BUILD_BUILDID", "123")
    monkeypatch.setenv("SYSTEM_DEFINITIONID", "200")
    monkeypatch.setenv("BUILD_SOURCEVERSION", AUTOMATION)
    return importlib.import_module("branch_health")


def branch_selection(branch, monitor, mocker, tmp_path, cloud="public", track="ga"):
    mocker.patch.object(branch.subprocess, "run", return_value=Mock(stdout=f"{SOURCE}\trefs/heads/dev\n"))
    mocker.patch.object(monitor, "download", return_value=b'VERSION = "2.12.0b1"\n')
    runtime = profile("1.5.45", cloud)
    if track == "preview":
        runtime = {**runtime, "train": "preview", "template": monitor.TEMPLATE.format("_preview")}
    mocker.patch.object(monitor, "runtime_profile", return_value=runtime)
    return branch.resolve(tmp_path / "history", cloud, track, AUTOMATION, 1)


@pytest.mark.parametrize("cloud,track", [("public", "ga"), ("fairfax", "ga"), ("public", "preview")])
def test_branch_selection_records_product_and_automation_and_never_reresolves(
        branch, monitor, mocker, tmp_path, cloud, track):
    selected = branch_selection(branch, monitor, mocker, tmp_path, cloud, track)
    assert selected["source"] == {"branch": "refs/heads/dev", "commit": SOURCE, "version": "2.12.0b1"}
    assert selected["testSourceCommit"] == SOURCE != selected["automationCommit"] == AUTOMATION
    assert set(selected["runtimes"]) == {"preview" if track == "preview" else "stable"}
    saved = tmp_path / "history/branch-selection-1-1/manifest.json"
    monitor.write_json(saved, selected)
    branch.subprocess.run.side_effect = AssertionError("A retry must never look up moving dev")
    assert branch.resolve(saved.parents[1], cloud, track, AUTOMATION, 2) == selected


@pytest.mark.parametrize("failure", ["missing", "source", "cloud", "automation", "run", "fairfax-preview"])
def test_branch_selection_rejects_retry_identity_drift(branch, monitor, mocker, tmp_path, monkeypatch, failure):
    selected = branch_selection(branch, monitor, mocker, tmp_path)
    if failure == "source":
        selected["source"]["commit"] = "c" * 40
    if failure == "automation":
        selected["automationCommit"] = "c" * 40
    if failure == "run":
        monkeypatch.setenv("BUILD_BUILDID", "124")
    if failure != "missing":
        monitor.write_json(tmp_path / "history/branch-selection-1-1/manifest.json", selected)
    cloud = "fairfax" if failure in {"cloud", "fairfax-preview"} else "public"
    track = "preview" if failure == "fairfax-preview" else "ga"
    with pytest.raises(ValueError):
        branch.resolve(tmp_path / "history", cloud, track, AUTOMATION, 2)


def test_branch_build_retry_reuses_original_bytes_and_rejects_tampering(branch, monitor, mocker, tmp_path):
    selected = branch_selection(branch, monitor, mocker, tmp_path)
    source = tmp_path / "input"
    product = source / "source/azext_edge"
    product.mkdir(parents=True)
    (product / "__init__.py").write_text("# original product\n")
    template = source / "source" / selected["runtime"]["template"]
    template.parent.mkdir(parents=True)
    template.write_text("P = {'VERSIONS': {'iotOperations': '1.5.45'}, 'TRAINS': {'iotOperations': 'stable'}}\n")
    compat = importlib.import_module("release_test_compatibility")
    scenarios = source / "source/.github/test-scenarios.yml"
    scenarios.parent.mkdir(parents=True)
    scenarios.write_text("scenarios: []\n")
    tests = product / "tests/conftest.py"
    tests.parent.mkdir()
    tests.write_text("# selected tests\n")
    monitor.write_json(source / "source.json", {
        "commit": SOURCE, "files": monitor.source_files(source / "source"),
    })
    selected["sourceSha256"] = hashlib.sha256((source / "source.json").read_bytes()).hexdigest()
    selected["testCompatibility"] = compat.source_compatibility(
        selected, source / "source", monitor.source_files(source / "source"),
    )
    monitor.write_json(source / "manifest.json", selected)
    built = tmp_path / "history/branch-wheel-1-1"
    mocker.patch.object(branch.shutil, "copytree", wraps=branch.shutil.copytree)
    build_calls = []

    def build_wheel(arguments, cwd, check):
        assert check and (cwd / "azext_edge/__init__.py").read_text() == "# original product\n"
        assert cwd != ROOT
        build_calls.append(arguments)
        with ZipFile(built / "azure_iot_ops-2.12.0b1-py3-none-any.whl", "w") as archive:
            for path in product.rglob("*.py"):
                if "tests" not in path.relative_to(product).parts:
                    archive.write(path, path.relative_to(source / "source"))
            archive.writestr(
                "azure_iot_ops-2.12.0b1.dist-info/METADATA", "Name: azure-iot-ops\nVersion: 2.12.0b1\n",
            )

    branch.subprocess.run.side_effect = build_wheel
    first = branch.build(source, tmp_path / "history", built, 1)
    assert len(build_calls) == 1
    original = (built / first["wheel"]["name"]).read_bytes()
    branch.subprocess.run.side_effect = AssertionError("Retry must not rebuild")
    restored = tmp_path / "retry"
    assert branch.build(source, tmp_path / "history", restored, 2) == first
    assert (restored / first["wheel"]["name"]).read_bytes() == original
    (built / first["wheel"]["name"]).write_bytes(original + b"drift")
    with pytest.raises(ValueError, match="SHA256"):
        branch.build(source, tmp_path / "history", tmp_path / "rejected", 3)


def test_branch_build_requires_the_original_artifact_on_retry(branch, monitor, mocker, tmp_path):
    mocker.patch.object(monitor, "verify_bundle", return_value={})
    with pytest.raises(ValueError, match="cannot rebuild"):
        branch.build(tmp_path / "source", tmp_path / "history", tmp_path / "output", 2)


def test_branch_adapter_plans_the_selected_tests_not_the_automation_checkout(
        branch, adapter, monitor, mocker, tmp_path):
    manifest = branch_selection(branch, monitor, mocker, tmp_path)
    mocker.patch.object(adapter, "bundle_manifest", return_value=manifest)

    def plan(output, scenario_source):
        assert scenario_source == tmp_path / "source"
        monitor.write_json(output / "plan.json", {"producer": "automation"})

    mocker.patch.object(adapter.native, "plan", side_effect=plan)
    mocker.patch.object(adapter.native, "candidate", side_effect=lambda output: monitor.write_json(
        output / "candidate.json", {"producer": "automation"},
    ))
    adapter.plan(tmp_path)
    for name in ("plan", "candidate"):
        assert monitor.read_json(tmp_path / f"{name}.json")["monitor"] == manifest


def test_fixed_branch_wrappers_cannot_override_source_cloud_or_runtime():
    config = json.loads((ROOT / ".azure-devops/branch-health.json").read_text())
    assert len(config["definitions"]) == 3
    assert config["folder"] == "\\official\\branch-health"
    for definition in config["definitions"]:
        pipeline = yaml.safe_load((ROOT / definition["yaml"]).read_text())
        assert {item["name"] for item in pipeline["parameters"]} <= {"mode", "pythonVersions", "clusterRegion"}
        parameters = pipeline["stages"][0]["parameters"]
        assert (parameters["cloud"], parameters["track"]) == (definition["cloud"], definition["track"])
        assert bool(pipeline["schedules"]) == (definition["cloud"] == "public")
        assert "Runtime" not in definition["name"]
    template = yaml.safe_load((ROOT / ".azure-devops/templates/branch-health-stages.yml").read_text())
    live = template["stages"][-1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    for stage in live:
        assert {"Build", "Lint", "Unit"} <= set(stage["dependsOn"])
    integration = live[0]["jobs"][0]["parameters"]
    assert integration["monitor"] and integration["monitorKind"] == "branch"


def test_health_pipeline_runs_only_the_selected_mode():
    pipeline = yaml.safe_load(
        (ROOT / ".azure-devops/templates/release-monitor-stages.yml").read_text(encoding="utf-8")
    )
    stages = {
        stage["stage"]: stage for stage in [
            pipeline["stages"][0], *pipeline["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"],
        ]
    }
    assert set(stages) == {"Prepare", "Integration", "TrustBundle", "Results"}
    steps = stages["Prepare"]["jobs"][0]["steps"]
    assert any("release_monitor_adapter.py plan" in step.get("bash", "") for step in steps)
    assert stages["Results"]["dependsOn"] == ["Prepare", "Integration", "TrustBundle"]
    assert "runIntegration" not in str(pipeline)


def test_daily_health_schedules_are_public_dev_only_and_fairfax_stays_held():
    schedules = {
        "release-monitor.yml": "0 0 * * *", "release-monitor-v2.yml": "0 8 * * *",
        "release-monitor-v3.yml": "0 16 * * *", "release-monitor-preview.yml": "0 20 * * *",
        "branch-health.yml": "0 4 * * *", "branch-health-preview.yml": "0 12 * * *",
    }
    for filename, cron in schedules.items():
        pipeline = yaml.safe_load((ROOT / ".azure-devops" / filename).read_text())
        schedule, = pipeline["schedules"]
        assert schedule["cron"] == cron
        assert schedule["branches"] == {"include": ["dev"]}
        assert schedule["always"] is True and "batch" not in schedule
        parameters = {parameter["name"]: parameter for parameter in pipeline["parameters"]}
        assert parameters["mode"]["default"] == "Integration tests"
        assert parameters["pythonVersions"]["default"] == ["3.13"]
    for filename in (
        "release-monitor-fairfax.yml", "release-monitor-fairfax-v2.yml", "release-monitor-fairfax-v3.yml",
        "release-monitor-fairfax-preview.yml", "branch-health-fairfax.yml",
    ):
        assert yaml.safe_load((ROOT / ".azure-devops" / filename).read_text())["schedules"] == []


@pytest.mark.parametrize("filename,script", [
    ("release-monitor-stages.yml", "release_monitor.py"),
    ("branch-health-stages.yml", "branch_health.py"),
])
def test_health_schedule_preflight_receives_job_token_before_artifacts(filename, script):
    template = yaml.safe_load((ROOT / ".azure-devops/templates" / filename).read_text())
    steps = template["stages"][0]["jobs"][0]["steps"]
    resolve = next(step for step in steps if script + " resolve " in step.get("bash", ""))
    assert resolve["env"]["SYSTEM_ACCESSTOKEN"] == "$(System.AccessToken)"
    assert not resolve.get("continueOnError")
    assert steps.index(resolve) < next(index for index, step in enumerate(steps) if "publish" in step)


def test_public_test_connection_is_consistent_across_current_ado_profiles():
    config = json.loads((ROOT / ".azure-devops/release-monitors.json").read_text())
    connection = config["clouds"]["public"]["variables"]["AzureServiceConnection"]
    assert connection == "sc-iot-ops-cli-public-it"
    profile = yaml.safe_load((ROOT / ".azure-devops/templates/integration-profile.yml").read_text())
    public = next(item["${{ if eq(parameters.cloud, 'public') }}"] for item in profile["variables"]
                  if "${{ if eq(parameters.cloud, 'public') }}" in item)
    assert next(item["value"] for item in public if item["name"] == "TestAzureServiceConnection") == connection
    integration = yaml.safe_load((ROOT / ".azure-devops/templates/integration-pipeline.yml").read_text())
    assert next(item["default"] for item in integration["parameters"]
                if item["name"] == "azureServiceConnection") == connection


def test_health_job_timeout_uses_the_typed_selection_not_a_runtime_variable():
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-monitor-stages.yml").read_text())
    stages = template["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    for stage in stages[:2]:
        configuration = stage["jobs"][0]["parameters"]["configuration"]
        assert configuration["scenarioTimeoutMinutes"] == "${{ parameters.scenarioTimeoutMinutes }}"
    trust_stage = stages[1]
    assert trust_stage["stage"] == "TrustBundle"
    assert trust_stage["lockBehavior"] == "sequential"
    assert trust_stage["jobs"][0]["parameters"]["maxParallel"] == 1
    lock_job, = trust_stage["jobs"][1]["${{ if eq(parameters.cloud, 'public') }}"]
    assert lock_job["deployment"] == "TrustBundleLock"
    assert lock_job["dependsOn"] == "Scenario"
    assert lock_job["condition"] == "always()"
    assert lock_job["environment"] == "ops-wlif-a386d5ea-ea90-441a-8263-d816368c84a1-ops-cli-int-test-rg"
    for path in (ROOT / ".azure-devops").glob("release-monitor*.yml"):
        pipeline = yaml.safe_load(path.read_text())
        stage_params = pipeline["stages"][0]["parameters"]
        assert stage_params["cloud"] == "${{ lower(parameters.cloud) }}"
        assert stage_params["scenarioTimeoutMinutes"] == (
            "${{ parameters.scenarioTimeoutMinutes }}"
        )


@pytest.fixture
def monitor(monkeypatch):
    for key, value in {
        "TESTPYTHONS": "3.13", "TESTMODE": "Integration tests",
        "TESTCHANNELS": "stable", "TESTBASELINES": "{}", "TESTTIMEOUT": "360",
        "BUILD_REASON": "Manual",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    return importlib.import_module("release_monitor")


@pytest.fixture
def scheduled(monitor, monkeypatch):
    for key, value in {
        "BUILD_REASON": "Schedule", "BUILD_BUILDID": "123", "SYSTEM_DEFINITIONID": "200",
        "SYSTEM_ACCESSTOKEN": "offline-schedule-token",
        "SYSTEM_STAGEATTEMPT": "1", "SYSTEM_JOBATTEMPT": "1",
    }.items():
        monkeypatch.setenv(key, value)
    helper = importlib.import_module("ado_schedule")
    api = Mock(return_value={
        "count": 1, "value": [{"id": 123, "definition": {"id": 200}, "status": "inProgress"}],
    })
    monkeypatch.setattr(importlib.import_module("release_pipeline"), "api", api)
    return helper, api


@pytest.mark.parametrize("reason", ["Manual", "PullRequest", "IndividualCI", ""])
def test_manual_health_runs_do_not_query_scheduled_overlap(scheduled, monkeypatch, reason):
    helper, api = scheduled
    monkeypatch.setenv("BUILD_REASON", reason)
    monkeypatch.delenv("SYSTEM_ACCESSTOKEN")
    monkeypatch.delenv("SYSTEM_STAGEATTEMPT")
    monkeypatch.delenv("SYSTEM_JOBATTEMPT")
    helper.check_scheduled_overlap()
    api.assert_not_called()


def test_scheduled_preflight_scopes_active_build_lookup_and_allows_newer_runs(scheduled):
    helper, api = scheduled
    api.return_value["value"].append({"id": 124, "definition": {"id": 200}, "status": "notStarted"})
    api.return_value["count"] = 2
    helper.check_scheduled_overlap()
    api.assert_called_once()
    url, token = api.call_args.args
    assert token == "offline-schedule-token"
    assert url.startswith("https://dev.azure.com/azureiotdevxp/aziotcli/_apis/build/builds?")
    query = parse_qs(urlsplit(url).query)
    assert query["definitions"] == ["200"]
    assert set(query["statusFilter"][0].split(",")) == {"inProgress", "notStarted", "postponed", "cancelling"}
    assert query["queryOrder"] == ["queueTimeAscending"]
    assert query["$top"] == ["1000"] and query["api-version"] == ["7.1"]
    assert not api.call_args.kwargs


@pytest.mark.parametrize("status", ["inProgress", "notStarted", "postponed", "cancelling"])
def test_scheduled_preflight_refuses_every_older_active_build_status(scheduled, status, capsys):
    helper, api = scheduled
    api.return_value["value"].insert(0, {"id": 122, "definition": {"id": 200}, "status": status})
    api.return_value["count"] = 2
    with pytest.raises(RuntimeError, match="older active build\\(s\\) 122"):
        helper.check_scheduled_overlap()
    assert "passed" not in capsys.readouterr().out


@pytest.mark.parametrize("attempt", ["SYSTEM_STAGEATTEMPT", "SYSTEM_JOBATTEMPT"])
@pytest.mark.parametrize("status", ["inProgress", "notStarted", "postponed", "cancelling"])
def test_scheduled_retry_refuses_newer_active_build(scheduled, monkeypatch, attempt, status):
    helper, api = scheduled
    monkeypatch.setenv(attempt, "2")
    api.return_value["value"].append({"id": 124, "definition": {"id": 200}, "status": status})
    api.return_value["count"] = 2
    with pytest.raises(RuntimeError, match="other active build\\(s\\) 124"):
        helper.check_scheduled_overlap()


@pytest.mark.parametrize("attempt", ["SYSTEM_STAGEATTEMPT", "SYSTEM_JOBATTEMPT"])
def test_scheduled_retry_allows_only_the_current_build(scheduled, monkeypatch, attempt):
    helper, api = scheduled
    monkeypatch.setenv(attempt, "2")
    helper.check_scheduled_overlap()
    api.assert_called_once()


@pytest.mark.parametrize("attempt", ["SYSTEM_STAGEATTEMPT", "SYSTEM_JOBATTEMPT"])
@pytest.mark.parametrize("value", [None, "0", "-1", "$(System.JobAttempt)"])
def test_scheduled_guard_rejects_missing_or_invalid_attempts(scheduled, monkeypatch, attempt, value):
    helper, api = scheduled
    if value is None:
        monkeypatch.delenv(attempt)
    else:
        monkeypatch.setenv(attempt, value)
    with pytest.raises(ValueError):
        helper.check_scheduled_overlap()
    api.assert_not_called()


def test_standalone_provisioning_check_uses_retry_policy(scheduled, monkeypatch):
    _, api = scheduled
    monkeypatch.setenv("SYSTEM_STAGEATTEMPT", "2")
    api.return_value["value"].append({"id": 124, "definition": {"id": 200}, "status": "inProgress"})
    api.return_value["count"] = 2
    with pytest.raises(RuntimeError, match="other active build\\(s\\) 124"):
        runpy.run_path(str(ROOT / "tools/ado_schedule.py"), run_name="__main__")


def test_health_scenario_retries_recheck_before_provisioning_without_gating_cleanup():
    template = yaml.safe_load((ROOT / ".azure-devops/templates/integration-scenario.yml").read_text())
    steps = template["jobs"][0]["steps"]
    run_index = next(index for index, step in enumerate(steps) if step.get("name") == "runScenario")
    conditional = steps[run_index - 1]
    assert list(conditional) == ["${{ if parameters.monitor }}"]
    guard, = conditional["${{ if parameters.monitor }}"]
    assert guard["bash"] == "python tools/ado_schedule.py"
    assert guard["workingDirectory"] == "$(Build.SourcesDirectory)"
    assert guard["env"] == {"SYSTEM_ACCESSTOKEN": "$(System.AccessToken)"}
    assert "condition" not in guard and "continueOnError" not in guard
    assert steps[run_index].get("condition", "succeeded()") == "succeeded()"
    proof = next(step for step in steps if step.get("name") == "cleanupProof")
    cleanup = next(step for step in steps if step.get("displayName") == "Clean up")
    assert proof["condition"] == "always()"
    assert cleanup["condition"] == "and(always(), or(canceled(), ne(variables['cleanupProof.complete'], 'true')))"


@pytest.mark.parametrize("failure", [
    "empty", "limit", "missing-current", "wrong-definition", "unknown-status", "missing-id",
    "duplicate", "count", "not-list",
])
def test_scheduled_preflight_fails_closed_on_ambiguous_evidence(scheduled, failure):
    helper, api = scheduled
    result = api.return_value
    if failure == "empty":
        result.update(count=0, value=[])
    elif failure == "limit":
        result.update(count=1000, value=result["value"] * 1000)
    elif failure == "missing-current":
        result["value"][0]["id"] = 124
    elif failure == "wrong-definition":
        result["value"][0]["definition"]["id"] = 201
    elif failure == "unknown-status":
        result["value"][0]["status"] = "unknown"
    elif failure == "missing-id":
        result["value"][0].pop("id")
    elif failure == "duplicate":
        result.update(count=2, value=result["value"] * 2)
    elif failure == "count":
        result["count"] = True
    else:
        result["value"] = {}
    with pytest.raises(ValueError):
        helper.check_scheduled_overlap()


@pytest.mark.parametrize("failure", ["api", "token"])
def test_scheduled_preflight_fails_closed_on_lookup_or_authentication_failure(scheduled, monkeypatch, failure):
    helper, api = scheduled
    if failure == "api":
        api.side_effect = RuntimeError("GET API request failed with HTTP 403")
    else:
        monkeypatch.delenv("SYSTEM_ACCESSTOKEN")
    with pytest.raises((RuntimeError, ValueError)):
        helper.check_scheduled_overlap()


@pytest.mark.parametrize("kind", ["release", "branch"])
def test_scheduled_preflight_blocks_both_resolvers_before_recording_selection(
        branch, monitor, scheduled, monkeypatch, tmp_path, kind):
    _, api = scheduled
    api.side_effect = RuntimeError("Scheduled lookup unavailable")
    monkeypatch.setenv("SYSTEM_JOBATTEMPT", "1")
    selection = Mock()
    owner = monitor if kind == "release" else branch
    monkeypatch.setattr(owner, "resolve", selection)
    output = tmp_path / "manifest.json"
    arguments = ["resolve", "--output", str(output)]
    if kind == "release":
        arguments += ["--extension", "azure-iot-ops", "--cloud", "public", "--track", "1.5",
                      "--automation-commit", AUTOMATION]
    with pytest.raises(RuntimeError, match="Scheduled lookup unavailable"):
        owner.main(arguments)
    selection.assert_not_called()
    assert not output.exists()


@pytest.fixture
def adapter(monkeypatch, monitor):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    return importlib.import_module("release_monitor_adapter")


def release(version):
    name = f"azure_iot_ops-{version}-py3-none-any.whl"
    return {
        "id": 123, "tag_name": f"v{version}", "draft": False, "prerelease": False,
        "assets": [{
            "name": name, "digest": "sha256:" + "d" * 64,
            "browser_download_url": (
                f"https://github.com/Azure/azure-iot-ops-cli-extension/releases/download/v{version}/{name}"
            ),
        }],
    }


def profile(version, cloud="public"):
    return {
        "version": version, "milestone": ".".join(version.split(".")[:2]), "train": "stable",
        "template": "azext_edge/edge/providers/orchestration/template"
        + ("_fairfax" if cloud == "fairfax" else "") + ".py",
    }


@pytest.fixture
def releases(monitor, mocker):
    versions = {"2.11.1": "1.5.45", "2.11.0": "1.5.41", "2.10.0": "1.4.112", "2.9.0": "1.4.73", "2.7.0": "1.3.137"}
    commits = {f"v{version}": f"{index:040x}" for index, version in enumerate(versions, 1)}
    by_commit = {commits[f"v{version}"]: runtime for version, runtime in versions.items()}
    mocker.patch.object(monitor, "tag_commit", side_effect=lambda _, tag: commits[tag])
    mocker.patch.object(
        monitor, "runtime_profile",
        side_effect=lambda _, source, cloud: profile("1.5.46" if cloud == "fairfax" else by_commit[source], cloud),
    )
    return [release(version) for version in versions]


@pytest.fixture
def manifest(monitor, releases):
    return {**monitor.resolve("azure-iot-ops", "public", "1.5", AUTOMATION, releases), "slot": "v1"}


@pytest.mark.parametrize("override", [None, "region", "services", "cloud", "version"])
def test_health_overrides_preserve_selection_and_retry_identity(
        monitor, releases, monkeypatch, override):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    cloud = "fairfax" if override == "cloud" else "public"
    slot = "v2" if override == "version" else "v1"
    manifest = {
        **monitor.resolve("azure-iot-ops", cloud, config["tracks"][slot], AUTOMATION, releases), "slot": slot,
    }
    selected = next(item["variables"] for item in monitor.configurations(config)
                    if item["variables"]["MonitorCloud"] == cloud and item["variables"]["MonitorTrack"] == slot)
    monkeypatch.setenv("MONITORCLOUD", "public")
    monkeypatch.setenv("MONITORTRACK", "v1")
    for key, value in selected.items():
        monkeypatch.setenv("TEST" + key.removeprefix("Monitor").upper(), value)
    monkeypatch.setenv("TESTSERVICES", "edge" if override == "services" else "Default scenarios")
    if override == "region":
        monkeypatch.setenv("TESTREGION", "eastus")
    monitor.bind_profile(manifest, config)
    if override:
        assert monitor.run_title(manifest, "123").endswith("-manual")
    monkeypatch.setenv("TESTREGION", "westus3")
    with pytest.raises(ValueError, match="changed between attempts"):
        monitor.bind_profile(manifest, config)
    monkeypatch.setenv("TESTAZURESERVICECONNECTION", "unreviewed-connection")
    with pytest.raises(ValueError, match="reviewed cloud profile"):
        monitor.bind_profile(manifest, config)


def test_distinct_milestones_use_latest_cli_patch_and_cloud_profile(monitor, releases):
    latest = monitor.resolve("azure-iot-ops", "fairfax", "1.5", AUTOMATION, releases)
    previous = monitor.resolve("azure-iot-ops", "public", "1.4", AUTOMATION, releases)
    oldest = monitor.resolve("azure-iot-ops", "public", "1.3", AUTOMATION, releases)
    assert latest["release"]["version"] == "2.11.1"
    assert latest["runtime"]["version"] == "1.5.46"
    assert previous["release"]["version"] == "2.10.0"
    assert oldest["release"]["version"] == "2.7.0"
    with pytest.raises(ValueError, match="matching published release"):
        monitor.resolve("azure-iot-ops", "public", "1.2", AUTOMATION, releases)


def test_new_release_does_not_invalidate_explicitly_supported_milestone(monitor, releases, mocker):
    original_commit = monitor.tag_commit.side_effect
    original_profile = monitor.runtime_profile.side_effect
    mocker.patch.object(
        monitor, "tag_commit",
        side_effect=lambda repository, tag: SOURCE if tag == "v2.12.0" else original_commit(repository, tag),
    )
    mocker.patch.object(
        monitor, "runtime_profile",
        side_effect=lambda repository, source, cloud: (
            profile("1.6.1") if source == SOURCE else original_profile(repository, source, cloud)
        ),
    )
    result = monitor.resolve("azure-iot-ops", "public", "1.3", AUTOMATION, [release("2.12.0"), *releases])
    assert result["release"]["version"] == "2.7.0"


def test_nonstable_public_runtime_is_skipped_but_ambiguous_metadata_is_not(monitor, releases, mocker, capsys):
    original_commit = monitor.tag_commit.side_effect
    original_profile = monitor.runtime_profile.side_effect
    mocker.patch.object(
        monitor, "tag_commit",
        side_effect=lambda repository, tag: SOURCE if tag == "v2.12.0" else original_commit(repository, tag),
    )

    def runtime(repository, source, cloud):
        if source == SOURCE:
            raise monitor.NonStableRuntime("Bundled runtime uses the preview train.")
        return original_profile(repository, source, cloud)

    mocker.patch.object(monitor, "runtime_profile", side_effect=runtime)
    values = [release("2.12.0"), *releases]
    result = monitor.resolve("azure-iot-ops", "public", "1.5", AUTOMATION, values)
    assert result["release"]["version"] == "2.11.1"
    assert "Skipping published CLI v2.12.0" in capsys.readouterr().err
    mocker.patch.object(monitor, "runtime_profile", side_effect=ValueError("ambiguous profile"))
    with pytest.raises(ValueError, match="ambiguous"):
        monitor.resolve("azure-iot-ops", "public", "1.5", AUTOMATION, values)


def test_missing_fairfax_profile_stays_blocked_and_mooncake_is_rejected(monitor, releases, mocker):
    public = monitor.runtime_profile.side_effect
    mocker.patch.object(
        monitor, "runtime_profile",
        side_effect=lambda repository, source, cloud: None if cloud == "fairfax" else public(repository, source, cloud),
    )
    result = monitor.resolve("azure-iot-ops", "fairfax", "1.4", AUTOMATION, releases)
    assert result["runtime"] is None
    assert result["blockers"]
    monitor.validate_manifest(result)
    with pytest.raises(ValueError, match="not supported"):
        monitor.resolve("azure-iot-ops", "mooncake", "1.5", AUTOMATION, releases)


def test_runtime_metadata_is_parsed_without_executing_release_code(monitor):
    source = (
        "raise RuntimeError('release code must not execute')\n"
        "blueprint = {'VERSIONS': {'iotOperations': '1.5.45'}, 'TRAINS': {'iotOperations': 'stable'}}\n"
    )
    assert monitor.parse_runtime_profile(source, "public") == profile("1.5.45")
    with pytest.raises(ValueError, match="stable bundled"):
        monitor.parse_runtime_profile(source.replace("'stable'", "'integration'"), "public")


def test_retry_retains_selection_and_rejects_missing_or_changed_history(monitor, manifest, tmp_path, mocker):
    monitor.write_json(tmp_path / "release-selection-1/manifest.json", manifest)
    discovery = mocker.patch.object(monitor, "resolve")
    assert monitor.frozen_manifest(tmp_path, "azure-iot-ops", "public", "1.5", AUTOMATION, 2) == manifest
    discovery.assert_not_called()
    with pytest.raises(ValueError, match="requested slot"):
        monitor.frozen_manifest(tmp_path, "azure-iot-ops", "public", "1.5", AUTOMATION, 2, slot="v2")
    with pytest.raises(ValueError, match="cannot rediscover"):
        monitor.frozen_manifest(tmp_path / "missing", "azure-iot-ops", "public", "1.5", AUTOMATION, 2)
    changed = deepcopy(manifest)
    changed["release"]["id"] = 456
    monitor.write_json(tmp_path / "release-selection-2/manifest.json", changed)
    with pytest.raises(ValueError, match="changed between attempts"):
        monitor.frozen_manifest(tmp_path, "azure-iot-ops", "public", "1.5", AUTOMATION, 3)


@pytest.mark.parametrize("url", [
    "http://github.com/Azure/release.whl", "https://github.com.evil.example/release.whl",
    "https://user:password@github.com/Azure/release.whl", "file:///tmp/release.whl",
])
def test_download_url_boundary(monitor, url):
    with pytest.raises(ValueError, match="approved"):
        monitor.validate_url(url)


@pytest.fixture
def bundle(monitor, manifest, tmp_path):
    path = tmp_path / manifest["wheel"]["name"]
    package = "VERSION = '2.11.1'\n"
    template = "blueprint = {'VERSIONS': {'iotOperations': '1.5.45'}, 'TRAINS': {'iotOperations': 'stable'}}\n"
    with ZipFile(path, "w") as archive:
        archive.writestr("azext_edge/__init__.py", package)
        archive.writestr(manifest["runtime"]["template"], template)
        archive.writestr("azure_iot_ops-2.11.1.dist-info/METADATA", "Name: azure-iot-ops\nVersion: 2.11.1\n")
    manifest["wheel"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    source = tmp_path / "source"
    (source / "azext_edge").mkdir(parents=True)
    (source / "azext_edge/__init__.py").write_bytes(package.encode("utf-8"))
    runtime = source / manifest["runtime"]["template"]
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(template.encode("utf-8"))
    (source / "azext_edge/tests").mkdir()
    (source / "azext_edge/tests/test_case_int.py").write_text("def test_case():\n    assert True\n", encoding="utf-8")
    monitor.write_json(tmp_path / "source.json", {
        "commit": manifest["testSourceCommit"], "files": monitor.source_files(source),
    })
    manifest["sourceSha256"] = hashlib.sha256((tmp_path / "source.json").read_bytes()).hexdigest()
    monitor.write_json(tmp_path / "manifest.json", manifest)
    return tmp_path, manifest


def test_bundle_verification_survives_artifact_git_exclusion_and_rejects_changed_tests(monitor, bundle):
    directory, manifest = bundle
    assert monitor.verify_bundle(directory) == manifest
    (directory / "source/azext_edge/tests/test_case_int.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="test source"):
        monitor.verify_bundle(directory)


def test_bundle_rejects_tampered_wheel_and_wrong_target(monitor, bundle):
    directory, manifest = bundle
    with pytest.raises(ValueError, match="requested cloudKey"):
        monitor.verify_bundle(directory, cloud="fairfax")
    wheel = directory / manifest["wheel"]["name"]
    wheel.write_bytes(wheel.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SHA256"):
        monitor.verify_bundle(directory)


def test_bundle_rejects_runtime_metadata_different_from_the_published_wheel(monitor, bundle):
    directory, manifest = bundle
    manifest["runtime"]["version"] = "1.5.46"
    monitor.write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match="Wheel runtime differs"):
        monitor.verify_bundle(directory)


def test_definition_binding_rejects_scope_overrides(monitor, monkeypatch):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    item = monitor.configurations(config)[0]
    monkeypatch.setenv("BUILD_DEFINITIONNAME", item["name"])
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", monitor.REPOSITORIES[config["extension"]])
    for key, value in item["variables"].items():
        monkeypatch.setenv(key.upper(), value)
    monitor.check_definition(config, config["extension"], "public", item["variables"]["MonitorTrack"])
    monkeypatch.setenv("MONITORRESOURCEGROUP", "another-resource-group")
    with pytest.raises(ValueError, match="reviewed monitor configuration"):
        monitor.check_definition(config, config["extension"], "public", item["variables"]["MonitorTrack"])


def test_support_rotation_preserves_definition_names_variables_and_resource_groups(monitor):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    original = monitor.configurations(config)
    config["tracks"] = {"v1": "1.6", "v2": "1.5", "v3": "1.4"}
    assert monitor.configurations(config) == original


@pytest.mark.parametrize("tracks", [
    {"v1": "1.3", "v2": "1.4", "v3": "1.5"},
    {"v1": "1.5", "v2": "1.4", "v3": "1.4"},
    {"v1": "1.5", "v2": "1.4"},
])
def test_invalid_support_roster_is_rejected(monitor, tracks):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    config["tracks"] = tracks
    with pytest.raises(ValueError, match="AIO"):
        monitor.configurations(config)


@pytest.mark.parametrize("milestone", ["1.5", "1.6"])
def test_configured_slot_resolves_its_milestone_and_labels_the_actual_versions(
        monitor, manifest, monkeypatch, mocker, tmp_path, capsys, milestone):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    if milestone == "1.6":
        config["tracks"] = {"v1": "1.6", "v2": "1.5", "v3": "1.4"}
    configuration = tmp_path / "release-monitors.json"
    monitor.write_json(configuration, config)
    manifest["track"] = milestone
    manifest["runtime"] = profile(f"{milestone}.45")
    manifest["runtimes"]["stable"] = manifest["runtime"]
    item = monitor.configurations(config)[0]
    monkeypatch.setenv("BUILD_DEFINITIONNAME", item["name"])
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", monitor.REPOSITORIES[config["extension"]])
    monkeypatch.setenv("BUILD_BUILDID", "123")
    for key, value in item["variables"].items():
        monkeypatch.setenv(key.upper(), value)
        monkeypatch.setenv("TEST" + key.removeprefix("Monitor").upper(), value)
    monkeypatch.setenv("TESTSERVICES", "Default scenarios")
    discovery = mocker.patch.object(monitor, "resolve", return_value=manifest)
    output = tmp_path / "manifest.json"
    monitor.main([
        "resolve", "--configuration", str(configuration), "--extension", "azure-iot-ops",
        "--cloud", "public", "--track", "v1", "--automation-commit", AUTOMATION, "--output", str(output),
    ])
    discovery.assert_called_once_with("azure-iot-ops", "public", milestone, AUTOMATION)
    assert monitor.read_json(output)["slot"] == "v1"
    title = f"aio-health-public-{milestone}-cli2.11.1-runtime{milestone}.45-b123"
    assert f"##vso[build.updatebuildnumber]{title}" in capsys.readouterr().out


def test_dedicated_preview_uses_v1_cli_and_freezes_preview_on_retry(
        monitor, manifest, monkeypatch, mocker, tmp_path, capsys):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    item = next(item for item in monitor.configurations(config)
                if item["variables"]["MonitorCloud"] == "public" and item["variables"]["MonitorTrack"] == "preview")
    monkeypatch.setenv("BUILD_DEFINITIONNAME", item["name"])
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", monitor.REPOSITORIES[config["extension"]])
    monkeypatch.setenv("BUILD_BUILDID", "123")
    for key, value in item["variables"].items():
        monkeypatch.setenv(key.upper(), value)
        monkeypatch.setenv("TEST" + key.removeprefix("Monitor").upper(), value)
    monkeypatch.setenv("TESTSERVICES", "Default scenarios")
    monkeypatch.setenv("TESTCHANNELS", "preview")
    preview = monitor.parse_runtime_profile(
        "{'VERSIONS': {'iotOperations': '1.6.0-preview.60'}, 'TRAINS': {'iotOperations': 'preview'}}",
        "public", "preview",
    )
    discovery = mocker.patch.object(monitor, "resolve", return_value=manifest)
    runtime = mocker.patch.object(monitor, "runtime_profile", return_value=preview)
    output = tmp_path / "manifest.json"
    arguments = [
        "resolve", "--configuration", str(ROOT / ".azure-devops/release-monitors.json"),
        "--extension", "azure-iot-ops", "--cloud", "public", "--track", "preview",
        "--automation-commit", AUTOMATION, "--output", str(output),
    ]
    monitor.main(arguments)
    frozen = monitor.read_json(output)
    assert frozen["slot"] == "preview"
    assert frozen["profile"]["configured"] == frozen["profile"]["selected"]
    assert frozen["profile"]["selected"]["channels"] == ["preview"]
    assert frozen["runtimes"]["preview"] == preview
    title = "aio-health-public-preview-cli2.11.1-runtime1.6.0-preview.60-b123"
    assert f"##vso[build.updatebuildnumber]{title}" in capsys.readouterr().out
    monitor.write_json(tmp_path / "release-selection-1/manifest.json", frozen)
    monitor.main([*arguments, "--history", str(tmp_path), "--attempt", "2"])
    assert monitor.read_json(output) == frozen
    discovery.assert_called_once_with("azure-iot-ops", "public", config["tracks"]["v1"], AUTOMATION)
    runtime.assert_called_once_with(frozen["repository"], frozen["testSourceCommit"], "public", "preview")


@pytest.mark.parametrize("channels", ["stable", "stable,preview", ""])
def test_dedicated_preview_rejects_nonpreview_selection(monitor, manifest, monkeypatch, mocker, channels):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    manifest["slot"] = "preview"
    selected = next(item["variables"] for item in monitor.configurations(config)
                    if item["variables"]["MonitorCloud"] == "public"
                    and item["variables"]["MonitorTrack"] == "preview")
    for key, value in selected.items():
        monkeypatch.setenv(key.upper(), value)
        monkeypatch.setenv("TEST" + key.removeprefix("Monitor").upper(), value)
    monkeypatch.setenv("TESTSERVICES", "Default scenarios")
    monkeypatch.setenv("TESTCHANNELS", channels)
    runtime = mocker.patch.object(monitor, "runtime_profile")
    with pytest.raises(ValueError, match="requires only the preview runtime channel"):
        monitor.bind_profile(manifest, config)
    runtime.assert_not_called()
    with pytest.raises(ValueError, match="no frozen preview runtime"):
        monitor.run_title(manifest, "123")


def test_fairfax_preview_definition_is_blocked_before_discovery(monitor, monkeypatch, mocker, tmp_path):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    item = next(item for item in monitor.configurations(config)
                if item["variables"]["MonitorCloud"] == "fairfax" and item["variables"]["MonitorTrack"] == "preview")
    monkeypatch.setenv("BUILD_DEFINITIONNAME", item["name"])
    for key, value in item["variables"].items():
        monkeypatch.setenv(key.upper(), value)
    discovery = mocker.patch.object(monitor, "resolve")
    with pytest.raises(ValueError, match="fairfax preview is unsupported"):
        monitor.main([
            "resolve", "--configuration", str(ROOT / ".azure-devops/release-monitors.json"),
            "--extension", "azure-iot-ops", "--cloud", "fairfax", "--track", "preview",
            "--automation-commit", AUTOMATION, "--output", str(tmp_path / "manifest.json"),
        ])
    discovery.assert_not_called()


def test_definition_generation_cannot_enable_runs_or_copy_secrets(monitor):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    repository = monitor.REPOSITORIES[config["extension"]]
    baseline = {
        "queue": {"id": 1},
        "repository": {
            "id": repository, "name": repository, "type": "GitHub", "url": f"https://github.com/{repository}",
            "properties": {"connectedServiceId": "github-connection", "unrelated": "do-not-copy"},
        },
        "variables": {"Secret": {"isSecret": True, "value": "do-not-copy"}},
        "triggers": [{"triggerType": "schedule"}],
    }
    definitions = monitor.definitions(config, baseline, "refs/heads/monitor-test")
    assert len(definitions) == 8
    for item in definitions:
        preview = item["variables"]["MonitorTrack"]["value"] == "preview"
        assert item["queueStatus"] == "disabled" and item["triggers"] == []
        assert "Secret" not in item["variables"]
        assert item["repository"]["properties"] == {
            "connectedServiceId": "github-connection", "reportBuildStatus": "false",
        }
        assert all(not value["allowOverride"] for value in item["variables"].values())
        pipeline = yaml.safe_load((ROOT / item["process"]["yamlFilename"]).read_text(encoding="utf-8"))
        parameters = {parameter["name"]: parameter for parameter in pipeline["parameters"]}
        common = yaml.safe_load((ROOT / ".azure-devops/integration.yml").read_text())["parameters"]
        assert list(parameters) == [p["name"] for p in common]
        for expected in common:
            if preview and expected["name"] == "runtimeChannels":
                expected = {**expected, "values": ["Preview"]}
            actual = parameters[expected["name"]]
            assert {k: v for k, v in actual.items() if k != "default"} == {
                k: v for k, v in expected.items() if k != "default"
            }
        assert parameters["cloud"]["default"] == item["variables"]["MonitorCloud"]["value"].capitalize()
        profile = next(value for value in pipeline["variables"] if "template" in value)
        assert profile["parameters"]["version"] == item["variables"]["MonitorTrack"]["value"]
        assert parameters["clusterRegion"]["default"] == "West US 2"
        assert parameters["testScenarios"]["default"] == ["Default scenarios"]
        assert parameters["runtimeChannels"]["default"] == ["Preview" if preview else "Stable"]
        channels = next(value for value in pipeline["variables"] if value.get("name") == "TestChannels")
        assert channels["value"] == "${{ lower(join(',', parameters.runtimeChannels)) }}"
    with pytest.raises(ValueError, match="GitHub definition"):
        monitor.definitions(config, baseline, "refs/heads/../other")


@pytest.fixture
def state(adapter, manifest, monkeypatch, tmp_path):
    for key, value in {
        "BUILD_SOURCEVERSION": AUTOMATION, "SYSTEM_DEFINITIONID": "200", "BUILD_BUILDID": "100",
        "MONITOR_CLOUD": "public", "MONITOR_TRACK": "v1", "OPS_MONITOR_BUNDLE": str(tmp_path),
        "OPS_CANDIDATE_DIGEST": manifest["wheel"]["sha256"],
        "OPS_RESOURCE_GROUP": "group",
    }.items():
        monkeypatch.setenv(key, value)
    return {
        "monitor": manifest, "cloud": "AzureCloud", "sha256": manifest["wheel"]["sha256"],
        "wheel": str(tmp_path / manifest["wheel"]["name"]), "resources": {"cluster": "/cluster"},
        "row": {"key": "edge", "scenario": {"channel": "stable", "tox_env": "", "test_redeploy": False}},
        "producer": adapter.native.producer(), "suffix": "a" * 11,
        "resourceGroup": "group",
    }


def test_cleanup_identity_does_not_depend_on_source_files(adapter, state, monkeypatch):
    adapter.validate_state(state)
    with pytest.raises(ValueError, match="missing the frozen release identity"):
        adapter.validate_state({key: value for key, value in state.items() if key != "monitor"})
    monkeypatch.setenv("MONITOR_TRACK", "v2")
    with pytest.raises(ValueError, match="requested track"):
        adapter.validate_state(state)


@pytest.mark.parametrize("slot", ["v1", "preview"])
def test_preview_channel_freezes_its_exact_deployment_version(
        monitor, adapter, state, monkeypatch, mocker, tmp_path, slot):
    preview = monitor.parse_runtime_profile(
        "{'VERSIONS': {'iotOperations': '1.6.0-preview.60'}, 'TRAINS': {'iotOperations': 'preview'}}",
        "public", "preview",
    )
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    state["monitor"]["slot"] = slot
    monkeypatch.setenv("MONITOR_TRACK", slot)
    selected = next(item["variables"] for item in monitor.configurations(config)
                    if item["variables"]["MonitorCloud"] == "public" and item["variables"]["MonitorTrack"] == slot)
    for key, value in selected.items():
        monkeypatch.setenv(key.upper(), value)
        monkeypatch.setenv("TEST" + key.removeprefix("Monitor").upper(), value)
    monkeypatch.setenv("TESTSERVICES", "edge")
    monkeypatch.setenv("TESTCHANNELS", "preview")
    resolve = mocker.patch.object(monitor, "runtime_profile", return_value=preview)
    monitor.bind_profile(state["monitor"], config)
    assert state["monitor"]["runtimes"]["preview"]["version"] == "1.6.0-preview.60"
    monitor.bind_profile(state["monitor"], config)
    resolve.assert_called_once_with(
        state["monitor"]["repository"], state["monitor"]["testSourceCommit"], "public", "preview",
    )
    if slot == "preview":
        with pytest.raises(ValueError, match="execution state differs"):
            adapter.validate_state(state)
    state["row"]["scenario"]["channel"] = "preview"
    adapter.validate_state(state)
    commands = Mock()
    commands.az_json.side_effect = [
        {"name": "AzureCloud", "endpoints": {"resourceManager": "https://management.azure.com/"}},
        {"value": [{"properties": {
            "extensionType": "microsoft.iotoperations", "version": "1.6.0-preview.60", "releaseTrain": "preview",
        }}]},
    ]
    adapter.verify_runtime(commands, state, tmp_path)
    assert state["observedRuntime"] == {"version": "1.6.0-preview.60", "train": "preview"}


@pytest.mark.parametrize("version,cloud", [
    ("1.5.45", "AzureCloud"), ("1.5.46", "AzureCloud"), ("1.5.45", "AzureUSGovernment"),
])
def test_runtime_observation_is_exact_and_cloud_bound(adapter, state, version, cloud, tmp_path):
    commands = Mock()
    commands.az_json.side_effect = [
        {"name": cloud, "endpoints": {"resourceManager": "https://management.azure.com/"}},
        {"value": [{"properties": {
            "extensionType": "microsoft.iotoperations", "version": version, "releaseTrain": "stable",
        }}]},
    ]
    if version != "1.5.45" or cloud != "AzureCloud":
        with pytest.raises(ValueError, match="runtime|cloud"):
            adapter.verify_runtime(commands, state, tmp_path)
        assert "observedRuntime" not in state
    else:
        adapter.verify_runtime(commands, state, tmp_path)
        assert adapter.native.read(tmp_path / "state.json")["observedRuntime"] == {
            "version": "1.5.45", "train": "stable",
        }


@pytest.mark.parametrize("failure", [None, "identity", "scenario"])
def test_monitor_gate_retains_failure_evidence_without_masking_rejection(
        adapter, state, tmp_path, mocker, monkeypatch, failure):
    native = adapter.native
    mocker.patch.object(adapter, "bundle_manifest", return_value=state["monitor"])
    monkeypatch.setenv("OPS_RELEASE_BUILD_ID", "0")
    monkeypatch.setenv("OPS_HISTORY", str(tmp_path / "history"))
    value = {
        "rows": [state["row"]], "cloud": state["cloud"], "monitor": state["monitor"],
        "producer": native.producer(),
    }
    if failure == "identity":
        value["monitor"] = {}
    native.write(tmp_path / "plan.json", value)
    evidence = mocker.patch.object(native, "scenario_evidence", return_value=[(None, None, {"status": "passed"})])
    if failure == "scenario":
        evidence.side_effect = ValueError("Unqualified latest scenario attempt")
    output = tmp_path / "results"
    native.write(output / "monitor-results.json", {"status": "passed", "scenarios": ["stale"]})
    if failure:
        with pytest.raises(ValueError, match="standalone|Unqualified"):
            adapter.gate(output)
    else:
        adapter.gate(output)
    result = native.read(output / "monitor-results.json")
    assert result["releaseQualified"] is False
    if failure:
        assert result["status"] == "incomplete" and "scenarios" not in result
        assert result["phase"] == ("release-identity" if failure == "identity" else "scenario-evidence")
    else:
        assert result["status"] == "passed" and result["scenarios"] == [{"status": "passed"}]


def test_monitor_aggregate_rejects_missing_latest_or_wrong_kind_evidence(adapter, state, tmp_path):
    native = adapter.native
    value = {
        "rows": [state["row"]], "cloud": state["cloud"], "monitor": state["monitor"],
        "subscription": "subscription", "resourceGroup": "group",
    }
    receipt = {
        "producer": native.producer(), "row": "edge", "attempt": 1, "sha256": state["sha256"],
        "cloud": "AzureCloud", "status": "passed", "cleanup": "passed",
        "phases": {"init": "passed", "smoke": "passed"}, "monitor": state["monitor"],
        "observedRuntime": {"version": "1.5.45", "train": "stable"},
        "subscription": "subscription", "resourceGroup": state["resourceGroup"], "releaseQualified": False,
        "resourceSuffix": state["suffix"],
    }
    directory = tmp_path / "ops-attempt-edge-1"
    native.write(directory / "receipt.json", receipt)
    (directory / "junit").mkdir()
    for phase in ("init", "smoke"):
        (directory / "junit" / f"{phase}.xml").write_text(
            "<testsuite><testcase name='passed'/></testsuite>", encoding="utf-8",
        )
    assert len(list(native.scenario_evidence(value, tmp_path))) == 1
    ordinary = {key: item for key, item in value.items() if key != "monitor"}
    with pytest.raises(ValueError, match="execution kind"):
        list(native.scenario_evidence(ordinary, tmp_path))
    (tmp_path / "ops-attempt-edge-2").mkdir()
    with pytest.raises(ValueError, match="Missing scenario receipt"):
        list(native.scenario_evidence(value, tmp_path))
    native.write(directory / "receipt.json", {key: item for key, item in receipt.items() if key != "monitor"})
    assert len(list(native.scenario_evidence(ordinary, tmp_path))) == 1


@pytest.mark.parametrize("slot", ["v2", "v3"])
def test_unsupported_fairfax_slots_cannot_reach_release_acquisition(monitor, monkeypatch, slot):
    config = monitor.read_json(ROOT / ".azure-devops/release-monitors.json")
    item = next(item for item in monitor.configurations(config)
                if item["variables"]["MonitorCloud"] == "fairfax" and item["variables"]["MonitorTrack"] == slot)
    monkeypatch.setenv("BUILD_DEFINITIONNAME", item["name"])
    with pytest.raises(ValueError, match="unsupported"):
        monitor.check_definition(config, "azure-iot-ops", "fairfax", slot)


def test_monitor_rejects_dynamic_or_foreign_resource_groups(adapter, state):
    adapter.validate_state(state)
    for group in ("group-100-" + state["suffix"], "foreign-group"):
        with pytest.raises(ValueError, match="execution state differs"):
            adapter.validate_state({**state, "resourceGroup": group})


def test_fairfax_released_test_catalog_is_bound_without_changing_product(adapter, monkeypatch, mocker):
    plugin = importlib.import_module("release_monitor_pytest")
    catalog = Mock(return_value="fairfax-profile")
    checks = Mock(get_runtime_catalog=catalog)
    mocker.patch.object(plugin.importlib, "import_module", return_value=checks)
    monkeypatch.setenv("azext_edge_cloud", "AzureUSGovernment")
    plugin.pytest_configure()
    assert checks.get_runtime_catalog() == "fairfax-profile"
    catalog.assert_called_once_with("AzureUSGovernment")
    with pytest.raises(ValueError, match="different cloud"):
        checks.get_runtime_catalog("AzureCloud")


@pytest.mark.parametrize("tamper", [None, "baseline", "replacement", "manifest"])
def test_reviewed_test_compatibility_is_explicit_and_never_changes_product(
        adapter, monkeypatch, tmp_path, tamper):
    compat = importlib.import_module("release_test_compatibility")
    name = "edge/orchestration/test_runtime_channels_int.py"
    original, corrected = b"original test\n", b"cloud-correct test\n"
    automation, target = tmp_path / "automation", tmp_path / "installed"
    replacement = automation / compat.PREFIX / name
    staged = target / compat.PREFIX / name
    replacement.parent.mkdir(parents=True)
    staged.parent.mkdir(parents=True)
    replacement.write_bytes(corrected)
    staged.write_bytes(original)
    product = target / "azext_edge/__init__.py"
    product.write_bytes(b"published product\n")
    monkeypatch.setattr(compat, "ROOT", automation)
    monkeypatch.setattr(compat, "BASE_FILES", {name: hashlib.sha256(original).hexdigest()})
    monkeypatch.setattr(compat, "REMOVAL_FILES", {})
    manifest = {
        "extension": "azure-iot-ops", "cloud": "AzureUSGovernment",
        "testSourceCommit": compat.FAIRFAX_TEST_SOURCE, "automationCommit": AUTOMATION,
    }
    manifest["testCompatibility"] = compat.compatibility(manifest)
    if tamper == "baseline":
        staged.write_bytes(b"unreviewed released test\n")
    elif tamper == "replacement":
        replacement.write_bytes(b"unreviewed automation test\n")
    elif tamper == "manifest":
        manifest["testCompatibility"]["exclusions"] = {}
    receipt = tmp_path / "test-compatibility.json"
    if tamper:
        with pytest.raises(ValueError, match="baseline|manifest"):
            compat.stage_tests(target, manifest, receipt)
        assert not receipt.exists()
    else:
        compat.stage_tests(target, manifest, receipt)
        assert staged.read_bytes() == corrected
        assert json.loads(receipt.read_text()) == manifest["testCompatibility"]
    assert product.read_bytes() == b"published product\n"


@pytest.mark.parametrize("tamper", [None, "baseline", "function"])
def test_frozen_certificate_tests_get_only_the_reviewed_read_wait(adapter, monkeypatch, tmp_path, tamper):
    compat = importlib.import_module("release_test_compatibility")
    target = tmp_path / "installed"
    originals = {
        compat.OPCUA_PREFIX + "helpers.py":
            "def assert_ssc_secret_not_exists(*args):\n    pass\n",
        compat.OPCUA_PREFIX + "test_opcua_certs_trust_int.py":
            "def test_trust():\n    assert_ssc_secret_not_exists(\n        ssc_name=NAME,\n    )\n",
        compat.OPCUA_PREFIX + "test_opcua_certs_client_int.py":
            "def test_client():\n    for certificate in certificates:\n        assert_ssc_secret_not_exists(\n"
            "            ssc_name=NAME,\n        )\n",
    }
    for name, content in originals.items():
        path = target / compat.PREFIX / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    monkeypatch.setattr(compat, "REMOVAL_FILES", {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content in originals.items()
    })
    manifest = {
        "extension": "azure-iot-ops", "cloud": "AzureCloud",
        "testSourceCommit": compat.FAIRFAX_TEST_SOURCE, "automationCommit": AUTOMATION,
    }
    manifest["testCompatibility"] = compat.compatibility(manifest)
    assert manifest["testCompatibility"]["files"] == []
    assert manifest["testCompatibility"]["exclusions"] == {}
    product = target / "azext_edge/__init__.py"
    product.write_text("unchanged product\n")
    receipt = tmp_path / "receipt.json"
    if tamper == "baseline":
        (target / compat.PREFIX / next(iter(originals))).write_text("unexpected source\n")
    elif tamper == "function":
        manifest["testCompatibility"]["secretSyncRemoval"]["functionSha256"] = "0" * 64
    if tamper:
        with pytest.raises(ValueError, match="baseline|manifest"):
            compat.stage_tests(target, manifest, receipt)
        assert not receipt.exists()
    else:
        compat.stage_tests(target, manifest, receipt)
        for name, content in originals.items():
            staged = (target / compat.PREFIX / name).read_text()
            if name.endswith("/helpers.py"):
                assert staged == compat.removal_function() + "\n"
            else:
                assert staged.replace(" " * (12 if "client" in name else 8)
                                      + "instance_name=instance_name,\n", "") == content
        assert json.loads(receipt.read_text()) == manifest["testCompatibility"]
    assert product.read_text() == "unchanged product\n"


@pytest.mark.parametrize("cloud,source,excluded", [
    ("AzureUSGovernment", "40ca69187cb8a04e1ea92f5d759c3f4a0a1c868a", True),
    ("AzureCloud", "40ca69187cb8a04e1ea92f5d759c3f4a0a1c868a", False),
    ("AzureUSGovernment", "c" * 40, False),
])
def test_only_proven_unavailable_fairfax_cases_are_explicitly_skipped(
        adapter, monkeypatch, tmp_path, cloud, source, excluded):
    plugin = importlib.import_module("release_monitor_pytest")
    monkeypatch.setenv("azext_edge_cloud", cloud)
    monkeypatch.setenv("AZEXT_OPS_RELEASE_TEST_SOURCE", source)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "schema": 1, "baseTestSourceCommit": source, "exclusions": plugin.exclusions_for(cloud, source),
    }))
    monkeypatch.setenv(plugin.TEST_COMPATIBILITY_ENV, str(receipt))
    monkeypatch.setenv("AZEXT_OPS_TEST_KIND", "release")
    items = [
        Mock(path=Path("/installed/azext_edge/tests") / path, originalname=name)
        for path, name in [
            ("edge/adr/test_asset_lifecycle_int.py", "test_asset_lifecycle"),
            ("edge/adr/test_namespaces_int.py", "test_namespace_lifecycle"),
            ("edge/orchestration/test_secretsync_int.py", "test_secretsync"),
        ]
    ]
    plugin.pytest_collection_modifyitems(items)
    assert items[0].add_marker.call_count == int(excluded)
    if excluded:
        assert "2026-04-01" in items[0].add_marker.call_args.args[0].kwargs["reason"]
    items[1].add_marker.assert_not_called()
    items[2].add_marker.assert_not_called()


def test_monitor_pytest_requires_staged_receipt_instead_of_commit_lookup(adapter, monkeypatch):
    plugin = importlib.import_module("release_monitor_pytest")
    monkeypatch.delenv(plugin.TEST_COMPATIBILITY_ENV, raising=False)
    monkeypatch.setenv("azext_edge_cloud", "AzureUSGovernment")
    monkeypatch.setenv("AZEXT_OPS_RELEASE_TEST_SOURCE", plugin.FAIRFAX_TEST_SOURCE)
    with pytest.raises(ValueError, match="staged.*receipt"):
        plugin.pytest_collection_modifyitems([])


def test_release_pytest_rejects_receipt_exclusions_outside_exact_release_rule(adapter, monkeypatch, tmp_path):
    plugin = importlib.import_module("release_monitor_pytest")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "schema": 1, "baseTestSourceCommit": SOURCE, "exclusions": plugin.FAIRFAX_EXCLUSIONS,
    }))
    monkeypatch.setenv(plugin.TEST_COMPATIBILITY_ENV, str(receipt))
    monkeypatch.setenv("AZEXT_OPS_TEST_KIND", "release")
    monkeypatch.setenv("azext_edge_cloud", "AzureUSGovernment")
    monkeypatch.setenv("AZEXT_OPS_RELEASE_TEST_SOURCE", SOURCE)
    with pytest.raises(ValueError, match="reviewed release"):
        plugin.pytest_collection_modifyitems([])


@pytest.fixture
def branch_compatibility_source(adapter, monkeypatch, tmp_path):
    compat = importlib.import_module("release_test_compatibility")
    if subprocess.run(["git", "cat-file", "-e", compat.FAIRFAX_TEST_SOURCE], cwd=ROOT, capture_output=True,
                      check=False).returncode:
        pytest.skip("Reviewed compatibility baseline is unavailable in this shallow checkout.")
    source = tmp_path / "source"
    archived = subprocess.check_output([
        "git", "archive", compat.FAIRFAX_TEST_SOURCE,
        "azext_edge/tests", ".github/test-scenarios.yml", "azext_edge/edge/util/az_client.py",
    ], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archived)) as archive:
        for item in archive:
            if item.isfile() and not item.name.endswith("_unit.py"):
                destination = source / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.extractfile(item).read())
    (source / "azext_edge/__init__.py").write_bytes(b"unchanged product\n")
    monkeypatch.setenv(compat.TEST_COMPATIBILITY_ENV, "")
    monkeypatch.setenv("AZEXT_OPS_TEST_KIND", "")
    monkeypatch.setenv("BUILD_SOURCEVERSION", AUTOMATION)
    monkeypatch.setenv("AZEXT_OPS_RELEASE_TEST_SOURCE", SOURCE)
    monkeypatch.setenv("azext_edge_cloud", "AzureUSGovernment")
    manifest = {
        "extension": "azure-iot-ops", "kind": "branch", "cloud": "AzureUSGovernment",
        "testSourceCommit": SOURCE, "automationCommit": AUTOMATION, "sourceSha256": "d" * 64,
    }
    return compat, source, manifest


@pytest.mark.parametrize("change", ["none", "one-fixture", "fixed-fixtures", "unit-only", "scenario"])
@pytest.mark.parametrize("cloud", ["AzureCloud", "AzureUSGovernment"])
def test_branch_fairfax_compatibility_uses_reviewed_bytes_not_whole_commit(
        branch_compatibility_source, monitor, monkeypatch, tmp_path, change, cloud):
    compat, source, manifest = branch_compatibility_source
    manifest["cloud"] = cloud
    monkeypatch.setenv("azext_edge_cloud", cloud)
    if change == "fixed-fixtures":
        for name in [*compat.BASE_FILES, *compat.REMOVAL_FILES]:
            (source / compat.PREFIX / name).write_bytes((ROOT / compat.PREFIX / name).read_bytes())
    elif change == "one-fixture":
        path = source / compat.PREFIX / next(iter(compat.BASE_FILES))
        path.write_text(path.read_text() + "\n# source-owned fixture change\n")
    elif change == "unit-only":
        (source / compat.PREFIX / "test_new_unit.py").write_text("# unrelated unit tests\n")
    elif change == "scenario":
        path = source / ".github/test-scenarios.yml"
        path.write_text(path.read_text() + "\n# selected scenario change\n")
    original = monitor.source_files(source)
    manifest["testCompatibility"] = compat.source_compatibility(manifest, source, original)
    plan = manifest["testCompatibility"]
    tier_a = change in {"none", "unit-only"}
    fairfax = cloud == "AzureUSGovernment"
    if tier_a:
        assert plan["baseTestSourceCommit"] == compat.FAIRFAX_TEST_SOURCE != SOURCE
        assert plan["sourceTreeSha256"] == compat.REVIEWED_TEST_TREE
        assert len(plan["files"]) == (4 if fairfax else 0)
        assert len(plan["secretSyncRemoval"]["files"]) == 4
    elif fairfax:
        assert plan["files"] == [] and plan["secretSyncRemoval"] is None
        assert plan["sourceTreeSha256"] != compat.REVIEWED_TEST_TREE
    else:
        assert plan is None
    target = tmp_path / "installed"
    shutil.copytree(source, target)
    receipt = tmp_path / "compatibility.json"
    compat.stage_tests(target, manifest, receipt)
    assert json.loads(receipt.read_text()) == plan
    assert monitor.source_files(source) == original
    assert (target / "azext_edge/__init__.py").read_bytes() == b"unchanged product\n"
    expected_changes = {
        item["path"] for item in (plan or {}).get("files", [])
        + ((plan or {}).get("secretSyncRemoval") or {"files": []})["files"]
    }
    assert {name for name, value in monitor.source_files(target).items() if original[name] != value} == expected_changes
    plugin = importlib.import_module("release_monitor_pytest")
    monkeypatch.setattr(plugin, "__file__", str(target / "azext_edge/tests/_release_monitor.py"))
    items = [
        Mock(path=target / compat.PREFIX / path, originalname=name)
        for path, name in (entry.split("::") for entry in compat.FAIRFAX_EXCLUSIONS)
    ]
    unaffected = Mock(path=target / compat.PREFIX / "edge/adr/test_namespaces_int.py",
                      originalname="test_namespace_lifecycle")
    plugin.pytest_collection_modifyitems([*items, unaffected])
    assert all(item.add_marker.call_count == int(fairfax) for item in items)
    unaffected.add_marker.assert_not_called()


@pytest.mark.parametrize("drift", ["api", "missing-api", "excluded-file"])
def test_branch_fairfax_rejects_unknown_api_or_test_drift_before_patching(
        branch_compatibility_source, monitor, drift):
    compat, source, manifest = branch_compatibility_source
    api = source / "azext_edge/edge/util/az_client.py"
    if drift == "api":
        api.write_text(api.read_text().replace(
            "DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION = DeviceRegistryMgmtApiVersion.V20260401",
            "DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION = '2027-01-01'",
        ))
    elif drift == "missing-api":
        api.unlink()
    else:
        path = source / next(iter(compat.FAIRFAX_EXCLUSION_FILES))
        path.write_text(path.read_text() + "\n# revised exclusion case\n")
    with pytest.raises(ValueError, match="re-review"):
        compat.source_compatibility(manifest, source, monitor.source_files(source))


@pytest.mark.parametrize("tamper", ["source", "receipt", "installed-exclusion", "missing"])
def test_branch_fairfax_rechecks_proof_before_patching_and_skipping(
        branch_compatibility_source, monitor, monkeypatch, tmp_path, tamper):
    compat, source, manifest = branch_compatibility_source
    manifest["testCompatibility"] = compat.source_compatibility(manifest, source, monitor.source_files(source))
    receipt = tmp_path / "compatibility.json"
    if tamper in {"source", "missing"}:
        path = source / next(iter(compat.FAIRFAX_EXCLUSION_FILES))
        if tamper == "source":
            path.write_bytes(b"unreviewed tests\n")
        elif tamper == "missing":
            path.unlink()
        with pytest.raises(ValueError):
            compat.stage_tests(source, manifest, receipt)
        assert not receipt.exists()
        return
    compat.stage_tests(source, manifest, receipt)
    if tamper == "receipt":
        plan = json.loads(receipt.read_text())
        plan["exclusions"]["edge/adr/test_namespaces_int.py::test_namespace_lifecycle"] = "unreviewed skip"
        receipt.write_text(json.dumps(plan))
    else:
        (source / next(iter(compat.FAIRFAX_EXCLUSION_FILES))).write_text("unreviewed skipped test\n")
    plugin = importlib.import_module("release_monitor_pytest")
    monkeypatch.setattr(plugin, "__file__", str(source / "azext_edge/tests/_release_monitor.py"))
    item = Mock(path=source / compat.PREFIX / "edge/adr/test_asset_lifecycle_int.py",
                originalname="test_asset_lifecycle")
    with pytest.raises(ValueError, match="exclusions"):
        plugin.pytest_collection_modifyitems([item])
    item.add_marker.assert_not_called()


def test_branch_compatibility_never_targets_product_bytes(branch_compatibility_source, monitor, tmp_path):
    compat, source, manifest = branch_compatibility_source
    manifest["testCompatibility"] = compat.source_compatibility(manifest, source, monitor.source_files(source))
    manifest["testCompatibility"]["files"] = [{
        "path": "azext_edge/__init__.py", "baseSha256": compat.digest(source / "azext_edge/__init__.py"),
        "sha256": "a" * 64,
    }]
    with pytest.raises(ValueError, match="never product"):
        compat.stage_tests(source, manifest, tmp_path / "receipt.json")
    assert (source / "azext_edge/__init__.py").read_bytes() == b"unchanged product\n"


@pytest.mark.parametrize("tamper", [None, "plan", "source"])
def test_branch_acquisition_binds_compatibility_to_its_frozen_source_inventory(
        branch_compatibility_source, branch, monitor, mocker, tmp_path, tamper):
    compat, source, _ = branch_compatibility_source
    manifest = branch_selection(branch, monitor, mocker, tmp_path, cloud="fairfax")
    assert "testCompatibility" not in manifest

    def checkout(arguments, **_):
        destination = Path(arguments[2])
        if arguments[3] == "init":
            (destination / ".git").mkdir()
        if arguments[3] == "checkout":
            shutil.copytree(source, destination, dirs_exist_ok=True)

    mocker.patch.object(branch.subprocess, "run", side_effect=checkout)
    mocker.patch.object(branch.subprocess, "check_output", return_value=SOURCE + "\n")
    bundle = tmp_path / "bundle"
    branch.acquire(manifest, bundle)
    acquired = monitor.verify_bundle(bundle, require_wheel=False)
    plan = acquired["testCompatibility"]
    assert plan["sourceTreeSha256"] == compat.REVIEWED_TEST_TREE
    assert plan["baseTestSourceCommit"] == compat.FAIRFAX_TEST_SOURCE != SOURCE
    assert plan["exclusions"] == compat.FAIRFAX_EXCLUSIONS
    if tamper == "plan":
        acquired["testCompatibility"]["files"] = []
        monitor.write_json(bundle / "manifest.json", acquired)
    elif tamper == "source":
        path = bundle / "source" / compat.PREFIX / next(iter(compat.BASE_FILES))
        path.write_text(path.read_text() + "\n# bundle drift\n")
    if tamper:
        with pytest.raises(ValueError, match="source|Source"):
            monitor.verify_bundle(bundle, require_wheel=False)


@pytest.mark.parametrize("source", [
    "0b555d6e535f7e212db7aa8b79436d652507e96b",
    "16e6e1d64ffe266970596d0b66cf8ff464b8c85a",
])
def test_legacy_public_releases_stage_adr_metadata_and_optional_metrics_agent_only(
    adapter, monkeypatch, tmp_path, source
):
    compat = importlib.import_module("release_test_compatibility")
    plugin = importlib.import_module("release_monitor_pytest")
    target = tmp_path / "installed"
    conftest_src = (
        "def shared_device(require_namespace_init_session, tracked_resources):\n"
        "    result = run(\n"
        '        f"az iot ops ns device create --name {device_name} "\n'
        '        f"--instance {instance_name} -g {resource_group}"\n'
        "    )\n"
        "    return result\n"
    )
    ns_devices_src = (
        "def test_namespace_device_lifecycle_operations():\n"
        "    result = run(\n"
        '        f"az iot ops ns device create --name {device_name} "\n'
        '        f"--instance {instance_name} -g {resource_group}"\n'
        "    )\n\n"
        "def test_generalized_inbound_endpoint_lifecycle():\n"
        "    result = run(\n"
        '        f"az iot ops ns device create --name {device_name} "\n'
        '        f"--instance {instance_name} -g {resource_group}"\n'
        "    )\n"
    )
    mgmt_src = (
        "def mgmt_actions_setup():\n"
        '    run(f"az iot ops ns device create -n {device_name} {common}")\n'
    )
    bundle_helper_src = (
        "def _clean_up_folders(walk_result, arc_namespace):\n"
        "    if arc_namespace:\n"
        '        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, arc_namespace, "arcagents"))\n'
        '        assert level_2["folders"] == [agent[0] for agent in ARC_AGENTS], '
        'f"Mismatch; folders: [{level_2[\'folders\']}]"\n'
        '        assert not level_2["files"]\n\n'
        "def get_file_map(walk_result):\n"
        "    num_additional_services = len(ARC_AGENTS)\n"
        "    if arc_namespace:\n"
        "        for agent, _ in ARC_AGENTS:\n"
        '            agent_path = path.join(BASE_ZIP_PATH, arc_namespace, "arcagents", agent)\n'
        '            file_map["arc"][agent] = convert_file_names(walk_result[agent_path]["files"])\n'
    )
    arcagents_test_src = (
        "def test_create_bundle_arcagents():\n"
        "    for agent, has_service in ARC_AGENTS:\n"
        "        file_map = agents_file_map[agent]\n"
        "        assert file_map\n"
    )
    auto_test_src = (
        "def test_create_bundle():\n"
        "    actual_walk_result = len(expected_services) + int(is_billing_included) + len(ARC_AGENTS)\n"
        "    assert len(walk_result) == actual_walk_result\n"
    )
    is_v2 = source == compat.PUBLIC_V2_TEST_SOURCE
    files = {
        "edge/adr/conftest.py": ("adr_shared_device_metadata", conftest_src),
        "edge/adr/test_namespace_devices_int.py": ("adr_generalized_endpoint_device_metadata", ns_devices_src),
        **(
            {"edge/orchestration/test_mgmt_actions_int.py": ("adr_mgmt_actions_device_metadata", mgmt_src)}
            if is_v2
            else {
                "edge/support/create_bundle_int/helpers.py": ("optional_arc_metrics_agent_helper", bundle_helper_src),
                "edge/support/create_bundle_int/test_arcagents_int.py": (
                    "optional_arc_metrics_agent_test",
                    arcagents_test_src,
                ),
                "edge/support/create_bundle_int/test_auto_int.py": (
                    "optional_arc_metrics_agent_auto_test",
                    auto_test_src,
                ),
            }
        ),
    }
    patched_registry = dict(compat.SOURCE_PATCHES)
    patched_registry[("AzureCloud", source)] = [
        {"path": rel_path, "kind": kind, "baseSha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
        for rel_path, (kind, content) in files.items()
    ]
    monkeypatch.setattr(compat, "SOURCE_PATCHES", patched_registry)
    for rel_path, (_kind, content) in files.items():
        full = target / compat.PREFIX / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content.encode("utf-8"))

    manifest = {
        "extension": "azure-iot-ops",
        "cloud": "AzureCloud",
        "testSourceCommit": source,
        "automationCommit": AUTOMATION,
    }
    manifest["testCompatibility"] = compat.compatibility(manifest)
    receipt = tmp_path / "receipt.json"
    compat.stage_tests(target, manifest, receipt)

    assert "--manufacturer Contoso" in (target / compat.PREFIX / "edge/adr/conftest.py").read_text(encoding="utf-8")
    staged_ns_devices = (target / compat.PREFIX / "edge/adr/test_namespace_devices_int.py").read_text(encoding="utf-8")
    assert staged_ns_devices.count("--manufacturer Contoso") == 1
    untouched_lifecycle = (
        "def test_namespace_device_lifecycle_operations():\n"
        "    result = run(\n"
        '        f"az iot ops ns device create --name {device_name} "\n'
        '        f"--instance {instance_name} -g {resource_group}"\n'
        "    )"
    )
    assert untouched_lifecycle in staged_ns_devices
    if is_v2:
        assert "--manufacturer Contoso" in (
            target / compat.PREFIX / "edge/orchestration/test_mgmt_actions_int.py"
        ).read_text(encoding="utf-8")
    else:
        assert 'agent == "metrics-agent"' in (
            target / compat.PREFIX / "edge/support/create_bundle_int/helpers.py"
        ).read_text(encoding="utf-8")
        assert 'agent == "metrics-agent"' in (
            target / compat.PREFIX / "edge/support/create_bundle_int/test_arcagents_int.py"
        ).read_text(encoding="utf-8")
        assert "missing_metrics" in (
            target / compat.PREFIX / "edge/support/create_bundle_int/test_auto_int.py"
        ).read_text(encoding="utf-8")

    monkeypatch.setenv("azext_edge_cloud", "AzureCloud")
    monkeypatch.setenv("AZEXT_OPS_RELEASE_TEST_SOURCE", source)
    items = [
        Mock(path=Path("/installed/azext_edge/tests") / path, originalname=name)
        for path, name in [
            ("edge/adr/test_namespace_devices_int.py", "test_namespace_device_lifecycle_operations"),
            ("edge/adr/test_namespace_devices_int.py", "test_generalized_inbound_endpoint_lifecycle"),
        ]
    ]
    plugin.pytest_collection_modifyitems(items)
    assert items[0].add_marker.call_count == 1
    assert "PR #941" in items[0].add_marker.call_args.args[0].kwargs["reason"]
    items[1].add_marker.assert_not_called()


def test_source_patches_match_real_frozen_git_blobs_and_tolerate_missing_metrics_agent(adapter):
    import os
    import subprocess

    compat = importlib.import_module("release_test_compatibility")
    for (_cloud, commit), entries in compat.SOURCE_PATCHES.items():
        check = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=compat.ROOT,
            capture_output=True,
            check=False,
        )
        if check.returncode != 0:
            pytest.skip(f"Frozen commit {commit} not present in shallow clone.")
        for entry in entries:
            blob = subprocess.check_output(
                ["git", "show", f"{commit}:{compat.PREFIX}{entry['path']}"],
                cwd=compat.ROOT,
            )
            assert hashlib.sha256(blob).hexdigest() == entry["baseSha256"]
            patched = compat.apply_source_patch(blob.decode("utf-8"), entry["kind"]).decode("utf-8")
            if entry["kind"] == "optional_arc_metrics_agent_helper":
                assert "expected_arc_folders" in patched
                namespace = {
                    "path": os.path,
                    "BASE_ZIP_PATH": "root",
                    "ARC_AGENTS": [("connect-agent", False), ("metrics-agent", False), ("config-agent", True)],
                }
                tree = compat.ast.parse(patched)
                fn_node = next(
                    item for item in tree.body
                    if isinstance(item, compat.ast.FunctionDef) and item.name == "_clean_up_folders"
                )
                # Verify patched _clean_up_folders Arc folder assertion passes without metrics-agent
                arc_if = next(
                    stmt for stmt in fn_node.body
                    if isinstance(stmt, compat.ast.If) and compat.ast.unparse(stmt.test) == "arc_namespace"
                )
                mod = compat.ast.Module(body=[arc_if], type_ignores=[])
                arc_key = os.path.join("root", "azure-arc", "arcagents")
                namespace.update({
                    "arc_namespace": "azure-arc",
                    "walk_result": {
                        arc_key: {"folders": ["connect-agent", "config-agent"], "files": []}
                    },
                })
                exec(compile(mod, "<patched_clean_up_folders>", "exec"), namespace)
                namespace.update({
                    "walk_result": {
                        arc_key: {"folders": ["connect-agent"], "files": []}
                    },
                })
                with pytest.raises(AssertionError, match="Mismatch"):
                    exec(compile(mod, "<patched_clean_up_folders>", "exec"), namespace)
            elif entry["kind"] == "optional_arc_metrics_agent_auto_test":
                assert "missing_metrics" in patched

    check = subprocess.run(
        ["git", "cat-file", "-e", f"{compat.FAIRFAX_TEST_SOURCE}^{{commit}}"],
        cwd=compat.ROOT,
        capture_output=True,
        check=False,
    )
    if check.returncode == 0:
        for rel_path, expected_sha in compat.BASE_FILES.items():
            blob = subprocess.check_output(
                ["git", "show", f"{compat.FAIRFAX_TEST_SOURCE}:{compat.PREFIX}{rel_path}"],
                cwd=compat.ROOT,
            )
            assert hashlib.sha256(blob).hexdigest() == expected_sha
