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
        "RELEASE_CREATE_INDEX_PR": "false", "RELEASE_UPLOAD_WHEEL": "false",
        "RELEASE_GITHUB_TOKEN": "offline-placeholder", "RELEASE_CHILD_BUILD_ID": "901",
        "OPS_RELEASE_BUILD_ID": "0",
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
        "sourceCommit": SOURCE, "producer": release.producer(),
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
        "templateParameters": {
            key: item if isinstance(item, str) else json.dumps(item)
            for key, item in release.integration_parameters(value, cohort).items()
        },
    }


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


@pytest.mark.parametrize("mode", ["Plan", "Validate"])
@pytest.mark.parametrize("flag", ["RELEASE_CREATE_INDEX_PR", "RELEASE_UPLOAD_WHEEL"])
def test_nonrelease_modes_cannot_request_publication(candidate, monkeypatch, mode, flag):
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv(flag, "True")
    with pytest.raises(ValueError, match="requires Release"):
        release.release_options()
    release.github.assert_not_called()


def test_release_defaults_to_github_only(candidate, monkeypatch, tmp_path):
    directory, _ = candidate
    monkeypatch.delenv("RELEASE_CREATE_INDEX_PR")
    monkeypatch.delenv("RELEASE_UPLOAD_WHEEL")
    assert release.release_options() == ("Release", False)
    with pytest.raises(ValueError, match="explicit createIndexPr"):
        release.index_pull_request(directory, tmp_path / "receipt", tmp_path / "work", tmp_path / "prepared")
    with pytest.raises(ValueError, match="opt-in"):
        release.upload_wheel(directory, tmp_path / "storage")
    release.github.assert_not_called()


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


@pytest.mark.parametrize("hour,minute,expected", [(10, 0, 0), (23, 0, 0), (0, 1, 32640), (8, 30, 2100)])
def test_queue_waits_across_unsafe_daily_windows(hour, minute, expected):
    assert release.safe_queue_delay(datetime(2026, 10, 27, hour, minute, tzinfo=timezone.utc)) == expected


def test_queue_uses_build_api_and_exact_serialized_parameters(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    monkeypatch.setattr(release, "existing_integration", Mock(return_value=None))
    monkeypatch.setattr(release, "safe_queue_delay", Mock(side_effect=[60, 0]))
    monkeypatch.setattr(release.time, "sleep", Mock())
    network = Mock(side_effect=[{"id": 901}, child(value)])
    monkeypatch.setattr(release, "ado", network)
    assert release.integrate(directory, tmp_path / "record") == "901"
    request = network.call_args_list[0]
    assert request.args == ("build/builds",)
    assert request.kwargs["data"] == {
        "definition": {"id": 164}, "sourceBranch": "refs/heads/dev", "sourceVersion": SOURCE,
        "templateParameters": child(value)["templateParameters"],
    }
    assert release.read(tmp_path / "record")["cohort"] == COHORT
    release.time.sleep.assert_called_once_with(60)


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


@pytest.mark.parametrize("mutation", ["sha", "definition", "scope", "parent", "timeout"])
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
    for name, value in {
        "SYSTEM_DEFINITIONID": "164", "BUILD_BUILDID": "901", "BUILD_SOURCEVERSION": SOURCE,
        "OPS_RELEASE_BUILD_ID": "900", "OPS_RELEASE_INPUT": str(directory), "OPS_MODE": "Integration tests",
        "OPS_SCENARIOS": "edge", "OPS_CHANNELS": "stable", "OPS_PYTHONS": "3.13", "OPS_BASELINES": "{}",
        "OPS_SUBSCRIPTION": release.INTEGRATION_PARAMETERS["subscriptionId"],
        "OPS_RESOURCE_GROUP": release.INTEGRATION_PARAMETERS["resourceGroup"],
        "OPS_CUSTOM_LOCATIONS_OID": release.INTEGRATION_PARAMETERS["customLocationsObjectId"],
        "OPS_SCENARIO_TIMEOUT_MINUTES": "360",
    }.items():
        monkeypatch.setenv(name, value)


def test_consumer_acquires_identical_candidate_without_rebuilding(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    consumer_environment(candidate, monkeypatch)
    monkeypatch.setattr(release, "ado", Mock(side_effect=[parent(), child(value)]))
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


def test_draft_is_promoted_only_after_verified_uploads(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    draft = public_release(value, draft=True)
    draft["assets"] = []
    events = []
    monkeypatch.setattr(release, "tag_commit", Mock(side_effect=[None, None, SOURCE]))
    monkeypatch.setattr(release, "find_release", Mock(return_value=None))

    def github(resource, method="GET", data=None):
        events.append((method, resource, data))
        if method == "PATCH":
            assert len(draft["assets"]) == 2
            draft["draft"] = False
        return draft

    def upload(_url, _token, **kwargs):
        item = next(item for item in (value["wheel"], value["sbom"])
                    if release.hashlib.sha256(kwargs["data"]).hexdigest() == item["sha256"])
        asset = {"name": item["file"], "digest": "sha256:" + item["sha256"]}
        draft["assets"].append(asset)
        return asset

    monkeypatch.setattr(release, "github", github)
    monkeypatch.setattr(release, "api", upload)
    release.publish(directory, tmp_path / "release.json", tmp_path / "publication.json")
    assert [event[0] for event in events] == ["POST", "POST", "PATCH", "GET"]
    assert events[1][2] == {"ref": "refs/tags/v2.0.0b1", "sha": SOURCE}


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


@pytest.mark.parametrize("exists,conflict", [(False, False), (True, False), (True, True)])
def test_storage_verifies_content_and_never_overwrites(candidate, monkeypatch, tmp_path, exists, conflict):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_UPLOAD_WHEEL", "True")
    monkeypatch.setenv("RELEASE_STORAGE_CONTAINER_URL", "https://testaccount.blob.core.windows.net/wheels")
    monkeypatch.setattr(release, "command", Mock(return_value=json.dumps({"exists": exists})))
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if args[3] == "download":
            target = Path(args[args.index("--file") + 1])
            target.write_bytes(b"conflict" if conflict else (directory / value["wheel"]["file"]).read_bytes())

    monkeypatch.setattr(release.subprocess, "run", run)
    if conflict:
        with pytest.raises(ValueError, match="differs"):
            release.upload_wheel(directory, tmp_path / "storage")
    else:
        release.upload_wheel(directory, tmp_path / "storage")
    uploads = [args for args in calls if args[3] == "upload"]
    assert len(uploads) == (0 if exists else 1)
    assert all(args[args.index("--overwrite") + 1] == "false" for args in uploads)


def test_yaml_serial_qualification_requires_all_gates_and_no_default_publication():
    root = yaml.safe_load((ROOT / ".azure-devops/release.yml").read_text(encoding="utf-8"))
    parameters = {item["name"]: item for item in root["parameters"]}
    assert parameters["mode"]["default"] == "Plan"
    assert parameters["createIndexPr"]["default"] is False
    assert parameters["uploadWheel"]["default"] is False
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-stages.yml").read_text(encoding="utf-8"))
    stages = {"Resolve": template["stages"][0]}
    for conditional in template["stages"][1:]:
        stages.update({stage["stage"]: stage for stage in next(iter(conditional.values()))})
    for name in ("Integration", "Publish"):
        for dependency in stages[name]["dependsOn"]:
            assert f"eq(dependencies.{dependency}.result, 'Succeeded')" in stages[name]["condition"]
    strategy = stages["Integration"]["jobs"][0]["strategy"]
    assert strategy["maxParallel"] == 1
    assert "candidate.matrix" in strategy["matrix"]
    job = stages["Publish"]["jobs"][0]
    assert job["templateContext"]["type"] == "releaseJob"
    assert job["templateContext"]["isProduction"] is True
    assert [step["checkout"] for step in job["steps"] if "checkout" in step] == ["none"]
    index = next(step for step in job["steps"] if "${{ if parameters.createIndexPr }}" in step)
    assert " index " in json.dumps(index)
    assert "ReleaseGitHubToken" not in json.dumps(template["stages"][:-1])
    unit = yaml.safe_load((ROOT / ".azure-devops/templates/release-unit.yml").read_text(encoding="utf-8"))
    assert len(unit["jobs"][0]["strategy"]["matrix"]) * len(stages["Unit"]["jobs"]) == 12


def test_manual_and_health_do_not_rebuild_a_release_candidate():
    path = ROOT / ".azure-devops/templates/integration-pipeline.yml"
    template = yaml.safe_load(path.read_text(encoding="utf-8"))
    live = template["stages"][1]["${{ if eq(parameters.mode, 'Integration tests') }}"]
    build = next(stage for stage in live if stage["stage"] == "Build")
    steps = build["jobs"][0]["steps"]
    own = next(step["${{ if eq(parameters.releaseBuildId, 0) }}"]
               for step in steps if "${{ if eq(parameters.releaseBuildId, 0) }}" in step)
    acquired = next(step["${{ if ne(parameters.releaseBuildId, 0) }}"]
                    for step in steps if "${{ if ne(parameters.releaseBuildId, 0) }}" in step)
    assert "python -m build --wheel" in json.dumps(own)
    assert "python -m build" not in json.dumps(acquired)
    assert acquired[0]["inputs"]["pipelineId"] == "${{ parameters.releaseBuildId }}"
    health = yaml.safe_load((ROOT / ".azure-devops/integration-health.yml").read_text(encoding="utf-8"))
    assert "releaseBuildId" not in health.get("parameters", {})
