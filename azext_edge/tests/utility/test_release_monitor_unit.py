# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
AUTOMATION = "a" * 40
SOURCE = "b" * 40


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


def test_health_job_timeout_uses_the_typed_selection_not_a_runtime_variable():
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-monitor-stages.yml").read_text())
    stages = template["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    for stage in stages[:2]:
        configuration = stage["jobs"][0]["parameters"]["configuration"]
        assert configuration["scenarioTimeoutMinutes"] == "${{ parameters.scenarioTimeoutMinutes }}"
    for path in (ROOT / ".azure-devops").glob("release-monitor*.yml"):
        pipeline = yaml.safe_load(path.read_text())
        assert pipeline["stages"][0]["parameters"]["scenarioTimeoutMinutes"] == (
            "${{ parameters.scenarioTimeoutMinutes }}"
        )


@pytest.fixture
def monitor(monkeypatch):
    for key, value in {
        "TESTPYTHONS": "3.13", "TESTMODE": "Integration tests",
        "TESTCHANNELS": "stable", "TESTBASELINES": "{}", "TESTTIMEOUT": "360",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    return importlib.import_module("release_monitor")


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
        assert item["repository"]["properties"] == {"connectedServiceId": "github-connection"}
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
def test_only_proven_unavailable_fairfax_cases_are_explicitly_skipped(adapter, monkeypatch, cloud, source, excluded):
    plugin = importlib.import_module("release_monitor_pytest")
    monkeypatch.setenv("azext_edge_cloud", cloud)
    monkeypatch.setenv("AZEXT_OPS_RELEASE_TEST_SOURCE", source)
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
