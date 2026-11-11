# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Offline release publication, cohort ownership and exact-candidate handoff contracts."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

import pytest
import yaml

from azext_edge.tests.utility.test_ado_integration_unit import seed_gate


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
try:
    release = importlib.import_module("release_pipeline")
    integration = importlib.import_module("ado_integration")
finally:
    sys.path.pop(0)

PROJECT = "9c543948-e573-4146-832a-bf16b1531204"
SOURCE = "a" * 40
AUTOMATION = "b" * 40
COHORT = "edge_stable_py313"


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    for name, value in {
        "SYSTEM_DEFINITIONID": "165", "BUILD_BUILDID": "900", "BUILD_SOURCEVERSION": AUTOMATION,
        "SYSTEM_TEAMPROJECTID": PROJECT, "SYSTEM_JOBATTEMPT": "1", "BUILD_SOURCEBRANCH": "refs/heads/dev",
        "BUILD_REPOSITORY_NAME": release.REPOSITORY, "RELEASE_SOURCE_BRANCH": "dev",
        "RELEASE_SOURCE_COMMIT": SOURCE, "RELEASE_COHORT": COHORT, "RELEASE_MODE": "Release",
        "RELEASE_CREATE_INDEX_PR": "false", "RELEASE_SKIP_INTEGRATION_TESTS": "false",
        "RELEASE_GITHUB_TOKEN": "offline-placeholder", "RELEASE_CHILD_BUILD_ID": "901",
        "OPS_RELEASE_BUILD_ID": "0", "RELEASE_REGION": "westus2",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(release, "ado", Mock(side_effect=AssertionError("Unexpected ADO request")))
    monkeypatch.setattr(release, "github", Mock(side_effect=AssertionError("Unexpected GitHub request")))
    directory = tmp_path / "candidate"
    directory.mkdir()
    wheel = directory / "azure_iot_ops-2.0.0b1-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("azext_edge/__init__.py", "")
        archive.writestr("azure_iot_ops-2.0.0b1.dist-info/METADATA", "Name: azure-iot-ops\nVersion: 2.0.0b1\n")
    with ZipFile(directory / "SBOM.zip", "w") as archive:
        archive.writestr("_manifest/manifest.spdx.json", '{"spdxVersion":"SPDX-2.2"}')
    value = {
        "schema": 1, "repository": release.REPOSITORY, "sourceBranch": "refs/heads/dev",
        "sourceCommit": SOURCE, "producer": release.producer(), "region": "westus2",
        "wheel": {"file": wheel.name, "sha256": release.digest(wheel), "version": "2.0.0b1"},
        "sbom": {"file": "SBOM.zip", "sha256": release.digest(directory / "SBOM.zip")},
        "cohorts": release.source_cohorts(ROOT),
    }
    release.write(directory / "candidate.json", value)
    release.write(tmp_path / "publication.json", {
        "candidate": value, "prerelease": True, "indexEntry": {
            "filename": wheel.name, "sha256Digest": value["wheel"]["sha256"],
            "downloadUrl": f"https://github.com/{release.REPOSITORY}/releases/download/v2.0.0b1/{wheel.name}",
            "metadata": {"version": "2.0.0b1"},
        },
    })
    return directory, value


def child(value, cohort=COHORT):
    return {
        "id": 901, "definition": {"id": 164}, "project": {"id": PROJECT},
        "repository": {"id": release.REPOSITORY, "type": "GitHub"},
        "sourceBranch": value["sourceBranch"], "sourceVersion": SOURCE,
        "status": "completed", "result": "succeeded",
        "parameters": json.dumps({"ReleaseCandidateBuildId": value["producer"]["build"]}),
        "templateParameters": {
            key: item if isinstance(item, str) else json.dumps(item)
            for key, item in release.integration_parameters(value, cohort).items() if key != "releaseBuildId"
        },
    }


def test_release_region_is_frozen_and_child_drift_is_rejected(candidate, monkeypatch):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_REGION", "eastus")
    with pytest.raises(ValueError, match="Candidate region"):
        release.verify_candidate(directory)
    value["region"] = "eastus"
    release.write(directory / "candidate.json", value)
    assert release.verify_candidate(directory)["region"] == "eastus"
    build = child(value)
    assert build["templateParameters"]["clusterRegion"] == "East US"
    assert build["templateParameters"]["cloud"] == "Public"
    release.validate_integration(build, value)
    build["templateParameters"]["clusterRegion"] = "West US 2"
    with pytest.raises(ValueError, match="exact release"):
        release.validate_integration(build, value)


def test_candidate_verifier_remains_standalone_for_publication(candidate, tmp_path):
    directory, _ = candidate
    script = tmp_path / "release_pipeline.py"
    script.write_bytes((ROOT / "tools/release_pipeline.py").read_bytes())
    subprocess.run(
        [sys.executable, "-I", "-S", str(script), "verify", "--directory", str(directory)],
        check=True, capture_output=True, text=True,
    )


def parent():
    return {
        "id": 900, "definition": {"id": 165}, "project": {"id": PROJECT},
        "repository": {"id": release.REPOSITORY, "type": "GitHub"},
        "sourceVersion": AUTOMATION, "queueTime": "2026-10-27T00:00:00Z",
        "templateParameters": {"mode": "Validate", "sourceBranch": "dev"},
    }


def public_release(value, draft=False):
    return {
        "id": 10, "tag_name": "v2.0.0b1", "target_commitish": SOURCE, "draft": draft, "prerelease": True,
        "assets": [{"name": item["file"], "digest": "sha256:" + item["sha256"]}
                   for item in (value["wheel"], value["sbom"])],
    }


@pytest.mark.parametrize("mode", ["Plan", "Validate", "Draft"])
def test_nonrelease_modes_cannot_request_index_submission(candidate, monkeypatch, mode):
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv("RELEASE_CREATE_INDEX_PR", "True")
    with pytest.raises(ValueError, match="requires Release"):
        release.release_options()
    release.github.assert_not_called()


def test_release_defaults_to_github_only(candidate, monkeypatch, tmp_path):
    directory, _ = candidate
    monkeypatch.delenv("RELEASE_CREATE_INDEX_PR")
    assert release.release_options() == ("Release", False)
    with pytest.raises(ValueError, match="explicit createIndexPr"):
        release.index_pull_request(directory, tmp_path / "receipt", tmp_path / "work", tmp_path / "prepared")
    release.github.assert_not_called()


@pytest.mark.parametrize("value", ["", "yes", "1", "$(skipIntegrationTests)"])
def test_invalid_waiver_is_not_silently_disabled(candidate, monkeypatch, value):
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", value)
    with pytest.raises(ValueError, match="explicit boolean"):
        release.release_options()


def test_waiver_is_bound_to_candidate_and_prevents_child_execution(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", "true")
    with pytest.raises(ValueError, match="waiver"):
        release.verify_candidate(directory)
    value.update(skipIntegrationTests=True, cohorts={})
    release.write(directory / "candidate.json", value)
    assert release.verify_candidate(directory) == value
    with pytest.raises(ValueError, match="waived"):
        release.integrate(directory, tmp_path / "receipt")
    release.ado.assert_not_called()
    with pytest.raises(ValueError, match="waiver"):
        release.verify_candidate(directory, expected_producer=value["producer"])
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", "false")
    with pytest.raises(ValueError, match="waiver"):
        release.verify_candidate(directory)


@pytest.mark.parametrize("skipped", [False, True])
def test_waived_source_does_not_require_integration_protocol(candidate, tmp_path, monkeypatch, skipped):
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", str(skipped))
    monkeypatch.setenv("RELEASE_MODE", "Draft")
    monkeypatch.setattr(release.subprocess, "run", Mock())
    monkeypatch.setattr(release, "command", Mock(return_value=SOURCE))
    if skipped:
        assert release.checkout(tmp_path / "source", resolving=True) == SOURCE
    else:
        with pytest.raises(ValueError, match="prerequisites"):
            release.checkout(tmp_path / "source", resolving=True)


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize("folder,token", [
    ("\\", f"{PROJECT}/164"),
    ("\\official", f"{PROJECT}/official/164"),
    ("\\official\\release checks", f"{PROJECT}/official/release checks/164"),
])
def test_access_probe_uses_job_token_without_queuing(candidate, monkeypatch, allowed, folder, token):
    monkeypatch.setenv("SYSTEM_ACCESSTOKEN", "offline-job-token")
    monkeypatch.setattr(release, "ado", Mock(return_value={"path": folder}))
    request = Mock(return_value={"count": 1, "value": [allowed]})
    monkeypatch.setattr(release, "api", request)
    if allowed:
        release.check_access()
    else:
        with pytest.raises(ValueError, match="Build Service"):
            release.check_access()
    assert len(request.call_args_list) == 4
    assert all("/_apis/permissions/" in call.args[0] and call.args[1] == "offline-job-token"
               and call.args[0].endswith("api-version=7.1")
               and not call.kwargs for call in request.call_args_list)
    assert all(parse_qs(urlsplit(call.args[0]).query)["tokens"] == [token]
               for call in request.call_args_list)
    release.ado.assert_called_once_with("build/definitions/164")


@pytest.mark.parametrize("response", [
    False, True, {}, {"count": 1, "value": ["true"]}, {"count": 0, "value": []},
    {"count": 2, "value": [True, True]},
])
def test_access_probe_rejects_ambiguous_permission_responses(candidate, monkeypatch, response):
    monkeypatch.setenv("SYSTEM_ACCESSTOKEN", "offline-job-token")
    monkeypatch.setattr(release, "ado", Mock(return_value={"path": "\\official"}))
    monkeypatch.setattr(release, "api", Mock(return_value=response))
    with pytest.raises(ValueError, match="Unexpected build-permission response"):
        release.check_access()


@pytest.mark.parametrize("name,value", [
    ("BUILD_SOURCEBRANCH", "refs/heads/feature/work"), ("RELEASE_SOURCE_BRANCH", "feature/work"),
    ("BUILD_REPOSITORY_NAME", "another/repo"), ("RELEASE_MODE", "Validate"),
])
def test_publication_rejects_nonproduction_context(candidate, monkeypatch, tmp_path, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        release.publish(candidate[0], tmp_path / "receipt", tmp_path / "publication.json")
    release.github.assert_not_called()


def test_candidate_inventory_is_full_default_channel_matrix(candidate):
    directory, value = candidate
    assert release.verify_candidate(directory) == value
    config = yaml.safe_load((ROOT / ".github/test-scenarios.yml").read_text(encoding="utf-8"))["scenarios"]
    defaults = {item["name"] for item in config if not item.get("manual_only") and not item.get("requires_baseline")}
    assert {(item["selection"], item["row"]["scenario"]["channel"]) for item in value["cohorts"].values()} == {
        (name, channel) for name in defaults for channel in ("stable", "preview")
    }


@pytest.mark.parametrize("version,already_versioned", [
    ("2.11.1", False), ("2.0.0b1", False), ("2.0.0b1", True),
])
@pytest.mark.parametrize("skipped", [False, True])
def test_candidate_creation_updates_title_from_wheel_once(
        candidate, tmp_path, monkeypatch, capsys, version, already_versioned, skipped):
    _, value = candidate
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", str(skipped))
    title = "ops-release-20261104.1"
    versioned_title = f"{title} ({version})"
    monkeypatch.setenv("BUILD_BUILDNUMBER", versioned_title if already_versioned else title)
    source = tmp_path / "source"
    dist = source / "dist"
    manifest = dist / "_manifest/spdx_2.2/manifest.spdx.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"spdxVersion":"SPDX-2.2"}', encoding="utf-8")
    filename = f"azure_iot_ops-{version}-py3-none-any.whl"
    with ZipFile(dist / filename, "w") as archive:
        archive.writestr("azext_edge/__init__.py", "")
        archive.writestr(f"azure_iot_ops-{version}.dist-info/METADATA",
                         f"Name: azure-iot-ops\nVersion: {version}\n")
    monkeypatch.setattr(release, "command", Mock(return_value=SOURCE))
    monkeypatch.setattr(release.subprocess, "run", Mock())
    monkeypatch.setattr(release, "source_cohorts", Mock(return_value=value["cohorts"]))
    output = tmp_path / "generated"
    generated = release.create_candidate(source, output)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"##vso[build.updatebuildnumber]{versioned_title}"
    assert set(json.loads(lines[-1].split("]", 1)[1])) == (set() if skipped else set(value["cohorts"]))
    assert generated["skipIntegrationTests"] is skipped
    if skipped:
        release.source_cohorts.assert_not_called()
    assert generated["wheel"]["version"] == version
    assert generated["producer"] == value["producer"]
    assert release.verify_candidate(output) == generated


@pytest.mark.parametrize("mutation", ["source", "producer", "wheel", "sbom", "cohort", "extra"])
def test_invalid_candidate_rejected(candidate, mutation):
    directory, value = candidate
    if mutation == "source":
        value["sourceCommit"] = AUTOMATION
    elif mutation == "producer":
        value["producer"]["build"] = "899"
    elif mutation in {"wheel", "sbom"}:
        (directory / value[mutation]["file"]).write_bytes(b"altered")
    elif mutation == "cohort":
        value["cohorts"].pop(COHORT)
    else:
        (directory / "extra.whl").write_bytes(b"unexpected")
    release.write(directory / "candidate.json", value)
    with pytest.raises(ValueError):
        release.verify_candidate(directory)


@pytest.mark.parametrize("hour", [8, 9])
def test_queue_uses_exact_parameters_without_waiting_for_cleanup(candidate, monkeypatch, tmp_path, hour):
    directory, value = candidate
    monkeypatch.setattr(release, "existing_integration", Mock(return_value=None))
    monkeypatch.setattr(
        release, "datetime", Mock(now=Mock(return_value=datetime(2026, 10, 29, hour, tzinfo=timezone.utc))),
        raising=False,
    )
    monkeypatch.setattr(release.time, "sleep", Mock(side_effect=AssertionError("Unexpected admission wait")))
    network = Mock(side_effect=[{"id": 901}, child(value)])
    monkeypatch.setattr(release, "ado", network)
    assert release.integrate(directory, tmp_path / "record") == "901"
    request = network.call_args_list[0]
    assert request.args == ("build/builds",)
    assert request.kwargs["data"] == {
        "definition": {"id": 164}, "sourceBranch": "refs/heads/dev", "sourceVersion": SOURCE,
        "parameters": json.dumps({"ReleaseCandidateBuildId": "900"}),
        "templateParameters": child(value)["templateParameters"],
    }
    assert release.read(tmp_path / "record")["cohort"] == COHORT
    assert network.call_count == 2
    assert network.call_args_list[1].args == ("build/builds/901",)
    release.time.sleep.assert_not_called()


def test_retry_finds_only_its_own_cohort(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    monkeypatch.setenv("SYSTEM_JOBATTEMPT", "2")
    builds = [child(value, "edge_preview_py313"), child(value)]
    network = Mock(side_effect=[parent(), {"value": builds}, child(value)])
    monkeypatch.setattr(release, "ado", network)
    assert release.integrate(directory, tmp_path / "record") == "901"
    assert all("method" not in call.kwargs for call in network.call_args_list)


def test_uncertain_retry_never_requeues(candidate, monkeypatch, tmp_path):
    monkeypatch.setenv("SYSTEM_JOBATTEMPT", "2")
    monkeypatch.setattr(release, "existing_integration", Mock(return_value=None))
    with pytest.raises(ValueError, match="uncertain"):
        release.integrate(candidate[0], tmp_path / "record")
    release.ado.assert_not_called()


def test_duplicate_owned_cohort_is_rejected(candidate, monkeypatch):
    value = candidate[1]
    monkeypatch.setattr(release, "ado", Mock(side_effect=[parent(), {"value": [child(value), child(value)]}]))
    with pytest.raises(ValueError, match="Multiple children"):
        release.existing_integration(value)


@pytest.mark.parametrize("mutation", ["sha", "definition", "scope", "parent", "timeout", "region"])
def test_child_must_match_exact_request(candidate, mutation):
    value = candidate[1]
    build = child(value)
    if mutation == "sha":
        build["sourceVersion"] = AUTOMATION
    elif mutation == "definition":
        build["definition"]["id"] = 167
    elif mutation == "scope":
        build["templateParameters"]["runtimeChannels"] = '["preview"]'
    elif mutation == "parent":
        build["templateParameters"]["releaseBuildId"] = "899"
    elif mutation == "region":
        build["templateParameters"]["clusterRegion"] = "eastus2"
    else:
        build["templateParameters"]["scenarioTimeoutMinutes"] = "90"
    with pytest.raises(ValueError):
        release.validate_integration(build, value)


@pytest.mark.parametrize("result", ["failed", "canceled", "partiallySucceeded", "skipped"])
def test_non_succeeded_child_blocks_release(candidate, monkeypatch, tmp_path, result):
    build = child(candidate[1])
    build["result"] = result
    monkeypatch.setattr(release, "existing_integration", Mock(return_value=build))
    monkeypatch.setattr(release, "ado", Mock(return_value=build))
    with pytest.raises(RuntimeError, match="finished"):
        release.integrate(candidate[0], tmp_path / "record")


def test_cancel_cannot_target_another_cohort(candidate, tmp_path):
    directory, value = candidate
    release.write(tmp_path / "record", {
        "id": "901", "producer": value["producer"], "cohort": "edge_preview_py313",
    })
    with pytest.raises(ValueError, match="another release"):
        release.cancel_integration(tmp_path / "record", directory)
    release.ado.assert_not_called()


def consumer_environment(candidate, monkeypatch):
    directory, _ = candidate
    profile = release.read(ROOT / ".azure-devops/release-monitors.json")["clouds"]["public"]["variables"]
    for name, value in {
        "SYSTEM_DEFINITIONID": "164", "BUILD_BUILDID": "901", "BUILD_SOURCEVERSION": SOURCE,
        "OPS_RELEASE_BUILD_ID": "900", "OPS_RELEASE_INPUT": str(directory), "OPS_MODE": "Integration tests",
        "OPS_SCENARIOS": "edge", "OPS_CHANNELS": "stable", "OPS_PYTHONS": "3.13", "OPS_BASELINES": "{}",
        "OPS_SUBSCRIPTION": profile["MonitorSubscription"],
        "OPS_RESOURCE_GROUP": profile["MonitorResourceGroup"],
        "OPS_CLUSTER_REGION": profile["MonitorRegion"],
        "OPS_CUSTOM_LOCATIONS_OID": profile["MonitorCustomLocationsObjectId"],
        "OPS_SCENARIO_TIMEOUT_MINUTES": "360",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("variables", [
    None, "[]", "invalid-json", {}, {"ReleaseCandidateBuildId": "899"},
    {"ReleaseCandidateBuildId": "0900"}, {"ReleaseCandidateBuildId": True},
])
def test_internal_candidate_identity_fails_closed(candidate, variables):
    _, value = candidate
    build = child(value)
    build["parameters"] = variables
    with pytest.raises(ValueError):
        release.validate_integration(build, value)


@pytest.mark.parametrize("mode", ["Validate", "Draft", "Release"])
def test_consumer_acquires_identical_candidate_without_rebuilding(candidate, monkeypatch, tmp_path, mode):
    directory, value = candidate
    consumer_environment(candidate, monkeypatch)
    producer = parent()
    producer["templateParameters"]["mode"] = mode
    monkeypatch.setattr(release, "ado", Mock(side_effect=[producer, child(value)]))
    run = Mock(side_effect=AssertionError("Handoff must not rebuild or execute packages"))
    monkeypatch.setattr(integration.subprocess, "run", run)
    output = tmp_path / "consumer"
    integration.acquire(output)
    for name in ("candidate.json", "SBOM.zip", value["wheel"]["file"]):
        assert (output / name).read_bytes() == (directory / name).read_bytes()
    assert integration.verified_candidate(output, value["wheel"]["sha256"]) == output / value["wheel"]["file"]
    with pytest.raises(ValueError, match="never rebuilt"):
        integration.candidate(output)
    run.assert_not_called()


@pytest.mark.parametrize("mutation", ["parent", "repository", "mode", "source", "inventory", "child", "digest"])
def test_handoff_rejects_untrusted_or_mismatched_producer(candidate, monkeypatch, tmp_path, mutation):
    directory, value = candidate
    consumer_environment(candidate, monkeypatch)
    producer = parent()
    build = child(value)
    if mutation == "parent":
        producer["definition"]["id"] = 161
    elif mutation == "repository":
        producer["repository"]["id"] = "other/repo"
    elif mutation == "mode":
        producer["templateParameters"]["mode"] = "Plan"
    elif mutation == "source":
        producer["sourceVersion"] = "c" * 40
    elif mutation == "inventory":
        value["cohorts"].pop("edge_preview_py313")
        value["cohorts"].pop(COHORT)
        release.write(directory / "candidate.json", value)
    elif mutation == "child":
        build["templateParameters"]["releaseBuildId"] = "899"
    else:
        (directory / value["wheel"]["file"]).write_bytes(b"rebuilt")
    monkeypatch.setattr(release, "ado", Mock(side_effect=[producer, build]))
    with pytest.raises(ValueError):
        integration.acquire(tmp_path / "consumer")
    assert not (tmp_path / "consumer").exists()


@pytest.mark.parametrize("mode", ["health", "dry"])
def test_health_and_dry_run_cannot_consume_release(candidate, monkeypatch, tmp_path, mode):
    consumer_environment(candidate, monkeypatch)
    if mode == "health":
        monkeypatch.setenv("SYSTEM_DEFINITIONID", "167")
    else:
        monkeypatch.setenv("OPS_MODE", "Dry run")
    with pytest.raises(ValueError):
        integration.plan(tmp_path / "plan")


def test_qualification_preserves_provenance_and_parent_reverifies_bytes(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    consumer_environment(candidate, monkeypatch)
    monkeypatch.setattr(release, "ado", Mock(side_effect=[parent(), child(value)]))
    wheel_dir = tmp_path / "ops-wheel-1"
    integration.acquire(wheel_dir)
    seed_gate(tmp_path, monkeypatch)
    integration.plan(tmp_path / "plan")
    monkeypatch.setenv("OPS_PLAN", str(tmp_path / "plan/plan.json"))
    monkeypatch.setenv("OPS_CANDIDATE", str(wheel_dir))
    monkeypatch.setenv("OPS_CANDIDATE_DIGEST", value["wheel"]["sha256"])
    receipt = tmp_path / f"ops-attempt-{COHORT}-1/receipt.json"
    evidence = integration.read(receipt)
    evidence["sha256"] = value["wheel"]["sha256"]
    integration.write(receipt, evidence)
    integration.gate(tmp_path / "ops-qualification-1")
    monkeypatch.setenv("SYSTEM_DEFINITIONID", "165")
    monkeypatch.setenv("BUILD_BUILDID", "900")
    monkeypatch.setenv("BUILD_SOURCEVERSION", AUTOMATION)
    monkeypatch.setattr(release, "ado", Mock(return_value=child(value)))
    release.verify_integration_artifacts(directory, tmp_path)
    (wheel_dir / value["wheel"]["file"]).write_bytes(b"rebuilt")
    with pytest.raises(ValueError, match="exact candidate"):
        release.verify_integration_artifacts(directory, tmp_path)


def test_publication_without_index_credentials_reuses_exact_release(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    monkeypatch.delenv("INDEX_FORK_REPOSITORY", raising=False)
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=SOURCE))
    monkeypatch.setattr(release, "find_release", Mock(return_value=public_release(value)))
    network = Mock(return_value=public_release(value))
    monkeypatch.setattr(release, "github", network)
    result = release.publish(directory, tmp_path / "release.json", tmp_path / "publication.json")
    assert result["candidate"] == value
    assert all("method" not in call.kwargs for call in network.call_args_list)


@pytest.mark.parametrize("mode", ["Draft", "Release"])
@pytest.mark.parametrize("skipped", [False, True])
def test_draft_is_promoted_only_after_verified_uploads(candidate, monkeypatch, tmp_path, mode, skipped):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", str(skipped))
    if skipped:
        value.update(skipIntegrationTests=True, cohorts={})
        release.write(directory / "candidate.json", value)
        prepared = release.read(tmp_path / "publication.json")
        prepared["candidate"] = value
        release.write(tmp_path / "publication.json", prepared)
    draft = public_release(value, draft=True)
    draft["assets"] = []
    events = []
    monkeypatch.setattr(release, "tag_commit", Mock(side_effect=[None, None, SOURCE]))
    monkeypatch.setattr(release, "find_release", Mock(return_value=None))

    def github(resource, method="GET", data=None):
        events.append((method, resource, data))
        if method == "PATCH":
            assert len(draft["assets"]) == 2
            draft.update(data)
        if method == "POST" and resource.endswith("/releases"):
            draft.update(data)
        return draft

    def upload(_url, _token, **kwargs):
        item = next(item for item in (value["wheel"], value["sbom"])
                    if release.hashlib.sha256(kwargs["data"]).hexdigest() == item["sha256"])
        asset = {"name": item["file"], "digest": "sha256:" + item["sha256"]}
        draft["assets"].append(asset)
        return asset

    monkeypatch.setattr(release, "github", github)
    monkeypatch.setattr(release, "api", upload)
    result = release.publish(directory, tmp_path / "release.json", tmp_path / "publication.json")
    assert ("Integration tests skipped" in draft["body"]) is skipped
    if mode == "Draft":
        assert [event[0] for event in events] == ["POST", "GET"]
        assert result["draft"] is True
        assert draft["draft"] is True
        assert "wheelUrl" not in result
        monkeypatch.setattr(release, "find_release", Mock(return_value=draft))
        monkeypatch.setattr(release, "tag_commit", Mock(return_value=None))
        monkeypatch.setattr(release, "api", Mock(side_effect=AssertionError("Unexpected duplicate upload")))
        events.clear()
        assert release.publish(directory, tmp_path / "retry.json", tmp_path / "publication.json") == result
        assert [event[0] for event in events] == ["GET"]
    else:
        assert [event[0] for event in events] == ["POST", "POST", "PATCH", "GET"]
        assert events[1][2] == {"ref": "refs/tags/v2.0.0b1", "sha": SOURCE}
        assert result["draft"] is False


@pytest.mark.parametrize("mode", ["Draft", "Release"])
def test_bad_upload_never_promotes_draft(candidate, tmp_path, monkeypatch, mode):
    monkeypatch.setenv("RELEASE_MODE", mode)
    draft = public_release(candidate[1], draft=True)
    draft["assets"] = []
    monkeypatch.setattr(release, "find_release", Mock(return_value=draft))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=None))
    monkeypatch.setattr(release, "api", Mock(return_value={"digest": "sha256:wrong"}))
    with pytest.raises(ValueError, match="remains a draft"):
        release.publish(candidate[0], tmp_path / "release.json", tmp_path / "publication.json")
    release.github.assert_not_called()


def test_draft_mode_rejects_already_public_release(candidate, tmp_path, monkeypatch):
    monkeypatch.setenv("RELEASE_MODE", "Draft")
    monkeypatch.setattr(release, "find_release", Mock(return_value=public_release(candidate[1])))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=SOURCE))
    with pytest.raises(ValueError, match="already published"):
        release.publish(candidate[0], tmp_path / "receipt", tmp_path / "publication.json")
    release.github.assert_not_called()


@pytest.mark.parametrize("draft", [False, True])
def test_waiver_updates_existing_draft_notes_but_never_public_notes(candidate, tmp_path, monkeypatch, draft):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_MODE", "Draft" if draft else "Release")
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", "true")
    value.update(skipIntegrationTests=True, cohorts={})
    release.write(directory / "candidate.json", value)
    prepared = release.read(tmp_path / "publication.json")
    prepared["candidate"] = value
    release.write(tmp_path / "publication.json", prepared)
    staged = public_release(value, draft=draft)
    staged["body"] = "Existing notes."
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=SOURCE))
    monkeypatch.setattr(release, "find_release", Mock(return_value=staged))

    def github(_resource, method="GET", data=None):
        if method == "PATCH":
            assert set(data) == {"body"}
            staged.update(data)
        return staged

    network = Mock(side_effect=github)
    monkeypatch.setattr(release, "github", network)
    if draft:
        result = release.publish(directory, tmp_path / "receipt", tmp_path / "publication.json")
        assert result["draft"] is True
        assert staged["body"] == "Integration tests skipped by release waiver.\n\nExisting notes."
        assert [call.kwargs.get("method", "GET") for call in network.call_args_list] == ["PATCH", "GET"]
    else:
        with pytest.raises(ValueError, match="refusing to edit"):
            release.publish(directory, tmp_path / "receipt", tmp_path / "publication.json")
        network.assert_not_called()


@pytest.mark.parametrize("change", [{"draft": False}, {"target_commitish": "f" * 40}, {"assets": []}])
def test_draft_requires_fresh_identity_and_asset_verification(candidate, tmp_path, monkeypatch, change):
    monkeypatch.setenv("RELEASE_MODE", "Draft")
    staged = public_release(candidate[1], draft=True)
    monkeypatch.setattr(release, "find_release", Mock(return_value=staged))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=None))
    network = Mock(return_value={**staged, **change})
    monkeypatch.setattr(release, "github", network)
    with pytest.raises(ValueError):
        release.publish(candidate[0], tmp_path / "receipt", tmp_path / "publication.json")
    assert not (tmp_path / "receipt").exists()
    assert all("method" not in call.kwargs for call in network.call_args_list)


@pytest.mark.parametrize("conflict", ["tag", "digest", "missing"])
def test_publication_never_overwrites_conflicting_assets(candidate, monkeypatch, tmp_path, conflict):
    published = public_release(candidate[1])
    if conflict == "digest":
        published["assets"][0]["digest"] = "sha256:wrong"
    elif conflict == "missing":
        published["assets"] = []
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=AUTOMATION if conflict == "tag" else SOURCE))
    monkeypatch.setattr(release, "find_release", Mock(return_value=published))
    with pytest.raises(ValueError):
        release.publish(candidate[0], tmp_path / "receipt", tmp_path / "publication.json")
    release.github.assert_not_called()


def test_index_rejects_draft_before_fork_access(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_CREATE_INDEX_PR", "True")
    prepared = release.read(tmp_path / "publication.json")
    release.write(tmp_path / "receipt", {
        "candidate": value, "wheelUrl": prepared["indexEntry"]["downloadUrl"], "tag": "v2.0.0b1", "release": 10,
    })
    monkeypatch.setattr(release, "find_release", Mock(return_value=public_release(value, draft=True)))
    with pytest.raises(ValueError, match="public release"):
        release.index_pull_request(directory, tmp_path / "receipt", tmp_path / "index", tmp_path / "publication.json")
    release.github.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
def test_index_append_preserves_unrelated_entries_and_supports_first_ops_release(existing):
    before = {"extensions": {"other": [{"metadata": {"version": "1.0"}}]}}
    if existing:
        before["extensions"]["azure-iot-ops"] = [{"metadata": {"version": "1.0"}}]
    after = deepcopy(before)
    entry = {"metadata": {"version": "2.0"}}
    after["extensions"].setdefault("azure-iot-ops", []).append(entry)
    release.verify_index_change(before, after, entry)
    after["extensions"]["other"] = []
    with pytest.raises(ValueError):
        release.verify_index_change(before, after, entry)


@pytest.mark.parametrize("dependency_failure", [False, True])
def test_unit_dependency_versions_are_logged_before_checking(monkeypatch, tmp_path, dependency_failure):
    env = {"PIP_INDEX_URL": "authenticated-test-feed"}
    failure = release.subprocess.CalledProcessError(1, ["pip", "check"])
    run = Mock(side_effect=[None, failure if dependency_failure else None])
    constraints = Mock(return_value="azure-core>=1.30\n")
    monkeypatch.setattr(release, "feed_environment", Mock(return_value=env))
    monkeypatch.setattr(release.subprocess, "run", run)
    monkeypatch.setattr(release.subprocess, "check_output", constraints)
    directory = tmp_path / "inventory"
    if dependency_failure:
        with pytest.raises(release.subprocess.CalledProcessError) as caught:
            release.unit_dependencies(tmp_path / "source", directory)
        assert caught.value is failure
        constraints.assert_not_called()
        assert not directory.exists()
    else:
        release.unit_dependencies(tmp_path / "source", directory)
        assert (directory / "cli-constraints.txt").read_text() == "azure-core>=1.30\n"
    assert [call.args[0][1:] for call in run.call_args_list] == [
        ["-m", "pip", "list", "--format=json"], ["-m", "pip", "check"],
    ]
    assert all(call.kwargs == {"env": env, "check": True} for call in run.call_args_list)


def test_yaml_parallel_qualification_requires_all_gates_and_no_default_publication():
    root = yaml.safe_load((ROOT / ".azure-devops/release.yml").read_text(encoding="utf-8"))
    parameters = {item["name"]: item for item in root["parameters"]}
    assert parameters["mode"]["default"] == "Plan"
    assert parameters["createIndexPr"]["default"] is False
    assert "uploadWheel" not in parameters
    assert parameters["skipIntegrationTests"]["default"] is False
    assert parameters["mode"]["values"] == ["Plan", "Validate", "Draft", "Release"]
    assert root["variables"]["RELEASE_SKIP_INTEGRATION_TESTS"] == "${{ parameters.skipIntegrationTests }}"
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-stages.yml").read_text(encoding="utf-8"))
    stages = {"Resolve": template["stages"][0]}
    for conditional in template["stages"][1:]:
        stages.update({stage["stage"]: stage for stage in next(iter(conditional.values()))})
    for name in ("Integration", "Publish"):
        for dependency in stages[name]["dependsOn"]:
            if isinstance(dependency, dict):
                continue
            assert f"eq(dependencies.{dependency}.result, 'Succeeded')" in stages[name]["condition"]
    assert "$(" not in stages["Integration"]["jobs"][0]["displayName"]
    strategy = stages["Integration"]["jobs"][0]["strategy"]
    assert strategy["maxParallel"] == 0
    assert stages["Unit"]["dependsOn"] == "Resolve"
    assert stages["Integration"]["dependsOn"] == ["Resolve", "Build", "Security", "CommandLint", "IndexCompatibility"]
    assert "dependencies.Unit" not in stages["Integration"]["condition"]
    assert stages["Publish"]["dependsOn"] == [
        "Resolve", "Build", "Unit", "Security", "CommandLint", "IndexCompatibility",
        {"${{ if not(parameters.skipIntegrationTests) }}": ["Integration"]},
    ]
    assert list(template["stages"][-2]) == [
        "${{ if and(ne(parameters.mode, 'Plan'), not(parameters.skipIntegrationTests)) }}"
    ]
    assert list(template["stages"][-1]) == ["${{ if in(parameters.mode, 'Draft', 'Release') }}"]
    assert "or(${{ parameters.skipIntegrationTests }}, eq(dependencies.Integration.result, 'Succeeded'))" in (
        stages["Publish"]["condition"]
    )
    access = next(step for step in stages["Resolve"]["jobs"][0]["steps"]
                  if "${{ if not(parameters.skipIntegrationTests) }}" in step)
    assert " release_pipeline.py access" in json.dumps(access).replace("tools/", "")
    assert "ReleaseStorageServiceConnection" not in json.dumps(template)
    assert "uploadWheel" not in json.dumps(template)
    assert "eq(dependencies.Unit.result, 'Succeeded')" in stages["Publish"]["condition"]
    assert "candidate.matrix" in strategy["matrix"]
    job = stages["Publish"]["jobs"][0]
    assert job["templateContext"]["type"] == "releaseJob"
    assert job["templateContext"]["isProduction"] is True
    assert [step["checkout"] for step in job["steps"] if "checkout" in step] == ["none"]
    index = next(step for step in job["steps"] if "${{ if parameters.createIndexPr }}" in step)
    assert " index " in json.dumps(index)
    assert "ReleaseGitHubToken" not in json.dumps(template["stages"][:-1])
    unit = yaml.safe_load((ROOT / ".azure-devops/templates/release-unit.yml").read_text(encoding="utf-8"))
    assert "$(" not in unit["jobs"][0]["displayName"]
    matrix = unit["jobs"][0]["strategy"]["matrix"]
    assert all(name == "py" + leg["python"].replace(".", "") for name, leg in matrix.items())
    assert len(matrix) * len(stages["Unit"]["jobs"]) == 12
    lint = next(step["bash"] for step in stages["CommandLint"]["jobs"][0]["steps"] if "bash" in step)
    assert lint.index("cp .pylintrc pylintrc") < lint.index("azdev linter ")
    assert "--min-severity medium" in lint
    compatibility = next(step["bash"] for step in stages["IndexCompatibility"]["jobs"][0]["steps"] if "bash" in step)
    assert compatibility.index('cd "$COMPAT_ROOT/azure-cli-extensions"') < compatibility.index("azdev linter ")
    assert "--min-severity medium" in compatibility
    assert "cp .pylintrc" not in compatibility and "cp linter_exclusions.yml" not in compatibility


def test_security_stages_verified_engine_before_scanning_without_reducing_coverage():
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-stages.yml").read_text(encoding="utf-8"))
    stages = template["stages"][1]["${{ if ne(parameters.mode, 'Plan') }}"]
    steps = next(stage for stage in stages if stage["stage"] == "Security")["jobs"][0]["steps"]
    bootstrap = next(step for step in steps if step.get("name") == "stageMsdo")
    scanner = next(step for step in steps if step.get("task") == "MicrosoftSecurityDevOps@1")
    assert steps.index(bootstrap) < steps.index(scanner)
    assert bootstrap["env"] == {"SYSTEM_ACCESSTOKEN": "$(System.AccessToken)"}
    script = bootstrap["pwsh"]
    assert "https://pkgs.dev.azure.com/azureiotdevxp/aziotcli/_packaging/pip/nuget/v3/flat2" in script
    assert "api.nuget.org" not in script and "PreserveAuthorizationOnRedirect" not in script
    assert script.index("Get-FileHash") < script.index("Expand-Archive") < script.index("task.setvariable")
    assert scanner["env"]["MSDO_FILEPATH"] == "$(stageMsdo.directory)/guardian.cmd"
    assert scanner["env"]["MSDO_VERSION"] == "$(stageMsdo.version)"
    assert scanner["env"]["BUILD_SOURCEVERSION"] == "$(sourceCommit)"
    assert scanner["inputs"] == {
        "break": True, "publish": True, "artifactName": "release-security-$(System.JobAttempt)",
    }


def test_manual_and_health_do_not_rebuild_a_release_candidate():
    path = ROOT / ".azure-devops/templates/integration-pipeline.yml"
    template = yaml.safe_load(path.read_text(encoding="utf-8"))
    live = template["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    build = next(stage for stage in live if stage["stage"] == "Build")
    steps = build["jobs"][0]["steps"]
    own = [step for step in steps if "eq(variables['releaseBuildId'], '0')" in str(step)]
    acquired = [step for step in steps if "ne(variables['releaseBuildId'], '0')" in str(step)]
    assert "python -m build --wheel" in json.dumps(own)
    assert "python -m build" not in json.dumps(acquired)
    assert acquired[0]["inputs"]["pipelineId"] == "${{ parameters.releaseBuildId }}"
    prepare = next(step for step in steps if step.get("name") == "candidate")
    assert "candidate --output dist" in prepare["bash"]
    assert "ado_integration.py acquire --output dist" in prepare["bash"]
    names = [step["name"] for step in steps if "name" in step]
    assert len(names) == len(set(names))
    health = yaml.safe_load((ROOT / ".azure-devops/integration-health.yml").read_text(encoding="utf-8"))
    assert "releaseBuildId" not in health.get("parameters", {})
