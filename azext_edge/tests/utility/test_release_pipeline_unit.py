# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Offline release publication, cohort ownership and exact-candidate handoff contracts."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError
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
JOB = "44444444-4444-4444-8444-444444444444"
OWNERSHIP_READER = release.publication_ownership


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    for name, value in {
        "SYSTEM_DEFINITIONID": "165", "BUILD_BUILDID": "900", "BUILD_SOURCEVERSION": AUTOMATION,
        "SYSTEM_TEAMPROJECTID": PROJECT, "SYSTEM_JOBATTEMPT": "1", "BUILD_SOURCEBRANCH": "refs/heads/dev",
        "SYSTEM_JOBID": JOB,
        "BUILD_REPOSITORY_NAME": release.REPOSITORY, "RELEASE_SOURCE_BRANCH": "dev",
        "RELEASE_SOURCE_COMMIT": SOURCE, "RELEASE_MODE": "Release",
        "RELEASE_CREATE_INDEX_PR": "false", "RELEASE_SKIP_INTEGRATION_TESTS": "false",
        "RELEASE_UPLOAD_WHEEL_TO_BLOB": "false",
        "RELEASE_GITHUB_TOKEN": "offline-placeholder", "RELEASE_CHILD_BUILD_ID": "901",
        "OPS_RELEASE_BUILD_ID": "0", "RELEASE_REGION": "westus2",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(release, "ado", Mock(side_effect=AssertionError("Unexpected ADO request")))
    monkeypatch.setattr(release, "github", Mock(side_effect=AssertionError("Unexpected GitHub request")))
    ownership = Mock(return_value=None)
    monkeypatch.setattr(release, "publication_ownership", ownership)
    # Never emit a real ADO attachment command from a test, including under ADO CI.
    monkeypatch.setattr(release, "attach_publication_receipt", Mock(
        side_effect=lambda path: setattr(ownership, "return_value", release.read(path)),
    ))
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


def child(value):
    return {
        "id": 901, "definition": {"id": 164}, "project": {"id": PROJECT},
        "repository": {"id": release.REPOSITORY, "type": "GitHub"},
        "sourceBranch": value["sourceBranch"], "sourceVersion": SOURCE,
        "status": "completed", "result": "succeeded",
        "parameters": json.dumps({"ReleaseCandidateBuildId": value["producer"]["build"]}),
        "templateParameters": {
            key: item if isinstance(item, str) else json.dumps(item)
            for key, item in release.integration_parameters(value).items() if key != "releaseBuildId"
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


def test_one_child_request_covers_every_release_cohort(candidate):
    _, value = candidate
    build = child(value)
    scenarios = json.loads(build["templateParameters"]["testScenarios"])
    assert scenarios == list(dict.fromkeys(item["selection"] for item in value["cohorts"].values()))
    assert json.loads(build["templateParameters"]["runtimeChannels"]) == ["Stable", "Preview"]
    root = yaml.safe_load((ROOT / ".azure-devops/integration.yml").read_text(encoding="utf-8"))
    choices = next(item["values"] for item in root["parameters"] if item["name"] == "testScenarios")
    assert set(scenarios) <= set(choices)
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


def owned_release(value, release_id=10):
    release.publication_ownership.return_value = release.ownership_record(value, release_id, JOB)


@pytest.mark.parametrize("value", [
    "refs/tags/v1", "refs/pull/1/head", "dev;echo bad", "dev\n", "../dev", "dev//test", "dev.lock", "-dev",
    "", None, 1, "topic/.hidden", "topic.lock/next", "topic@{1}", "topic~1", "topic:next",
    "topic[1]", "topic\\next", "topic\x7f", "refs/heads/", "/topic",
])
def test_invalid_source_branches(value):
    with pytest.raises(ValueError):
        release.branch(value)


@pytest.mark.parametrize("value", [
    "dev", "release/1.1.1-preview", "_next/2027+beta", "users/test/fix#123", "releases/\u6d4b\u8bd5", "@",
])
def test_source_branch_names_follow_git_syntax_without_release_naming_rules(value):
    subprocess.run(["git", "check-ref-format", "--branch", value], check=True, capture_output=True)
    expected = "refs/heads/" + value
    assert release.branch(value) == expected
    assert release.branch(expected) == expected


@pytest.mark.parametrize("mode", ["Validate", "Draft"])
def test_nonrelease_modes_cannot_request_index_submission(candidate, monkeypatch, mode):
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv("RELEASE_CREATE_INDEX_PR", "True")
    with pytest.raises(ValueError, match="requires Release"):
        release.release_options()
    release.github.assert_not_called()


def test_release_defaults_to_validate_and_rejects_removed_plan(candidate, monkeypatch):
    monkeypatch.delenv("RELEASE_MODE")
    monkeypatch.delenv("RELEASE_UPLOAD_WHEEL_TO_BLOB")
    assert release.release_options() == ("Validate", False)
    assert release.upload_wheel_to_blob() is False
    for mode in ("Validate", "Draft", "Release"):
        monkeypatch.setenv("RELEASE_MODE", mode)
        assert release.release_options() == (mode, False)
    for mode in ("Plan", "Upload wheel only", "upload wheel only", "Upload", "", "$(mode)"):
        monkeypatch.setenv("RELEASE_MODE", mode)
        with pytest.raises(ValueError, match="Invalid release mode"):
            release.release_options()


@pytest.fixture
def storage(candidate, monkeypatch):
    monkeypatch.setenv("RELEASE_MODE", "Validate")
    monkeypatch.setenv("RELEASE_UPLOAD_WHEEL_TO_BLOB", "true")
    directory, value = candidate
    value["uploadWheelToBlob"] = True
    release.write(directory / "candidate.json", value)
    monkeypatch.delenv("RELEASE_GITHUB_TOKEN")
    monkeypatch.setattr(release.subprocess, "run", Mock(return_value=Mock(
        returncode=0, stdout='{"accessToken":"secret-offline-storage-token"}',
    )))
    monkeypatch.setattr(release.time, "sleep", Mock())
    return candidate


def blob_response(body=b"", status=200, length=None):
    response = MagicMock(status=status, headers={"Content-Length": str(len(body) if length is None else length)})
    response.read1.side_effect = BytesIO(body).read1
    response.__enter__.return_value = response
    return response


def blob_transport(monkeypatch, responses):
    transport = Mock()
    transport.open.side_effect = responses
    monkeypatch.setattr(release, "build_opener", Mock(return_value=transport))
    return transport.open


def blob_error(code):
    return HTTPError(release.BLOB_CONTAINER + "wheel.whl", code, "offline error", {}, None)


@pytest.mark.parametrize("skipped", [False, True])
@pytest.mark.parametrize("mode", ["Validate", "Draft", "Release"])
@pytest.mark.parametrize("source", ["dev", "release/2027-preview", "users/test/next", "_next/2027+beta"])
def test_blob_upload_only_exact_candidate_with_receipt_and_no_github(
        storage, monkeypatch, tmp_path, capsys, skipped, mode, source):
    directory, value = storage
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv("RELEASE_SOURCE_BRANCH", source)
    value["sourceBranch"] = release.branch(source)
    if skipped:
        monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", "true")
        value.update(skipIntegrationTests=True, cohorts={})
    release.write(directory / "candidate.json", value)
    data = (directory / value["wheel"]["file"]).read_bytes()
    opened = blob_transport(monkeypatch, [blob_error(404), blob_response(status=201), blob_response(data)])
    receipt = tmp_path / "receipt.json"
    result = release.upload_wheel(directory, receipt)
    assert release.read(receipt) == result
    assert result == {
        "mode": mode, "status": "uploaded",
        "wheelUrl": release.BLOB_CONTAINER + value["wheel"]["file"],
        "sha256": value["wheel"]["sha256"], "length": len(data), "candidate": value,
    }
    requests = [call.args[0] for call in opened.call_args_list]
    assert [request.method for request in requests] == ["GET", "PUT", "GET"]
    assert all(request.full_url == result["wheelUrl"] for request in requests)
    assert requests[1].data == data
    assert requests[1].get_header("If-none-match") == "*"
    assert requests[1].get_header("X-ms-blob-type") == "BlockBlob"
    assert all(request.get_header("Authorization") == "Bearer secret-offline-storage-token" for request in requests)
    assert all(call.kwargs == {"timeout": 60} for call in opened.call_args_list)
    assert all(isinstance(call.args[0], release.NoRedirect) for call in release.build_opener.call_args_list)
    auth = release.subprocess.run.call_args
    assert auth.args[0] == [
        "az", "account", "get-access-token", "--resource", "https://storage.azure.com/",
        "--output", "json", "--only-show-errors",
    ]
    assert auth.kwargs == {"capture_output": True, "text": True, "timeout": 60, "check": False}
    assert "secret-offline-storage-token" not in capsys.readouterr().out + receipt.read_text()
    release.github.assert_not_called()
    release.ado.assert_not_called()


@pytest.mark.parametrize("content", ["identical", "different", "shorter"])
def test_blob_existing_content_is_verified_without_overwrite(storage, monkeypatch, tmp_path, content):
    directory, value = storage
    data = (directory / value["wheel"]["file"]).read_bytes()
    existing = data if content == "identical" else b"x" * (len(data) - (content == "shorter"))
    opened = blob_transport(monkeypatch, [blob_response(existing)])
    receipt = tmp_path / "receipt.json"
    if content == "identical":
        assert release.upload_wheel(directory, receipt)["status"] == "already-present"
    else:
        with pytest.raises(release.BlobUploadError, match="refusing overwrite"):
            release.upload_wheel(directory, receipt)
        assert not receipt.exists()
    assert [call.args[0].method for call in opened.call_args_list] == ["GET"]


@pytest.mark.parametrize("code", [409, 412])
@pytest.mark.parametrize("content", ["identical", "different", "missing"])
def test_blob_create_race_verifies_bytes_with_bounded_reads(storage, monkeypatch, tmp_path, code, content):
    directory, value = storage
    data = (directory / value["wheel"]["file"]).read_bytes()
    final = [blob_error(404)] * 2 if content == "missing" else [
        blob_response(data if content == "identical" else b"x" * len(data)),
    ]
    opened = blob_transport(monkeypatch, [blob_error(404), blob_error(code), blob_error(404)] + final)
    receipt = tmp_path / "receipt.json"
    if content == "identical":
        assert release.upload_wheel(directory, receipt)["status"] == "already-present"
    else:
        with pytest.raises((ValueError, RuntimeError), match="refusing overwrite|bounded reads"):
            release.upload_wheel(directory, receipt)
        assert not receipt.exists()
    methods = [call.args[0].method for call in opened.call_args_list]
    assert methods.count("PUT") == 1
    assert methods.count("GET") <= 4
    assert release.time.sleep.call_count == (2 if content == "missing" else 1)


@pytest.mark.parametrize("name,value", [
    ("BUILD_SOURCEBRANCH", "refs/heads/feature/upload"),
    ("BUILD_SOURCEBRANCH", "refs/pull/42/merge"),
    ("RELEASE_SOURCE_BRANCH", "refs/tags/v1"),
    ("BUILD_REPOSITORY_NAME", "another/repo"),
    ("RELEASE_MODE", "Upload wheel only"), ("RELEASE_MODE", "Plan"),
    ("RELEASE_UPLOAD_WHEEL_TO_BLOB", "false"),
])
def test_blob_production_guard_precedes_authentication(storage, monkeypatch, tmp_path, capsys, name, value):
    monkeypatch.setenv(name, value)
    receipt = tmp_path / "receipt.json"
    verifier = Mock(side_effect=AssertionError("Guard must run before candidate validation"))
    monkeypatch.setattr(release, "verify_candidate", verifier)
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(storage[0]), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert "task.logissue type=error;code=RELEASE_CANDIDATE_INVALID" in output
    assert "Upload validation failed:" in receipt.with_suffix(".md").read_text()
    assert not receipt.exists()
    verifier.assert_not_called()
    release.subprocess.run.assert_not_called()
    release.github.assert_not_called()


@pytest.mark.parametrize("name,value", [
    ("BUILD_SOURCEBRANCH", "refs/pull/42/merge"),
    ("RELEASE_SOURCE_BRANCH", "refs/pull/42/head"), ("BUILD_REPOSITORY_NAME", "another/repo"),
])
def test_blob_resolve_rejects_invalid_context_before_checkout(storage, monkeypatch, tmp_path, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        release.checkout(tmp_path / "source", resolving=True)
    release.subprocess.run.assert_not_called()


@pytest.mark.parametrize("mode,upload", [("Validate", False), ("Validate", True), ("Draft", True), ("Release", False)])
def test_resolve_freezes_any_upstream_branch_and_rejects_nonexistent_branches(
        candidate, monkeypatch, tmp_path, capsys, mode, upload):
    source = "_next/2027+beta"
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv("RELEASE_UPLOAD_WHEEL_TO_BLOB", str(upload))
    monkeypatch.setenv("RELEASE_SOURCE_BRANCH", source)
    repository = tmp_path / "source-repository"
    subprocess.run(["git", "init", "--quiet", "--initial-branch=" + source, str(repository)], check=True)
    for relative in (
        ".azure-devops/templates/integration-pipeline.yml", ".azure-devops/integration.yml",
        "tools/ado_integration.py", "tools/release_pipeline.py", ".github/test-scenarios.yml",
    ):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ReleaseCandidateBuildId clusterRegion\n", encoding="utf-8")
    (repository / "azext_edge").mkdir()
    (repository / "azext_edge/constants.py").write_text('VERSION = "2.11.2"\n', encoding="utf-8")
    profiles = repository / "azext_edge/edge/providers/orchestration"
    profiles.mkdir(parents=True)
    for suffix, runtime, train in [("", "1.4.99", "stable"), ("_preview", "1.6.0-preview.60", "preview")]:
        (profiles / f"template{suffix}.py").write_text(
            repr({"VERSIONS": {"iotOperations": runtime}, "TRAINS": {"iotOperations": train}}), encoding="utf-8")
    monkeypatch.setattr(release, "source_cohorts", Mock(return_value=candidate[1]["cohorts"]))
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    commit_command = [
        "git", "-c", "user.name=Release Test", "-c", "user.email=release-test@example.invalid",
        "commit", "--quiet", "-m",
        "Test release source\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
    ]
    subprocess.run(commit_command, cwd=repository, check=True)
    initial = release.command(["git", "rev-parse", "HEAD"], repository)
    subprocess.run(["git", "tag", "tag-only"], cwd=repository, check=True)
    original_run = subprocess.run
    fetches = []

    def local_run(args, **kwargs):
        if args[:4] == ["git", "remote", "add", "origin"]:
            assert args[4] == "https://github.com/Azure/azure-iot-ops-cli-extension.git"
            args = args[:4] + [repository.as_uri()]
        if args[:2] == ["git", "fetch"]:
            fetches.append(args[-1])
        return original_run(args, check=kwargs.pop("check", False), **kwargs)

    monkeypatch.setattr(release.subprocess, "run", local_run)
    assert release.checkout(tmp_path / "resolve", resolving=True) == initial
    output = capsys.readouterr().out
    assert f"##vso[task.setvariable variable=commit;isOutput=true]{initial}" in output
    assert (
        "##vso[build.updatebuildnumber]ops-900 (2.11.2) (edge, insecure-listener, rpsaas +7) (westus2)"
        f" (runtime 1.4.99, 1.6.0-preview.60) (stable, preview) ({mode.lower()})"
    ) in output.splitlines()
    (repository / "tools/release_pipeline.py").write_text("new tip\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(commit_command, cwd=repository, check=True)
    monkeypatch.setenv("RELEASE_SOURCE_COMMIT", initial)
    downstream = tmp_path / "downstream"
    assert release.checkout(downstream) == initial
    assert (downstream / "tools/release_pipeline.py").read_text() == "ReleaseCandidateBuildId clusterRegion\n"
    for missing in ("missing-branch", "tag-only"):
        monkeypatch.setenv("RELEASE_SOURCE_BRANCH", missing)
        with pytest.raises(subprocess.CalledProcessError):
            release.checkout(tmp_path / missing, resolving=True)
    assert fetches == ["refs/heads/" + source, initial, "refs/heads/missing-branch", "refs/heads/tag-only"]
    release.github.assert_not_called()
    release.ado.assert_not_called()


@pytest.mark.parametrize("value", ["", "yes", "1", "$(uploadWheelToBlob)"])
def test_blob_upload_option_rejects_invalid_values_before_side_effects(storage, monkeypatch, tmp_path, value):
    monkeypatch.setenv("RELEASE_UPLOAD_WHEEL_TO_BLOB", value)
    with pytest.raises(ValueError, match="uploadWheelToBlob"):
        release.release_options()
    with pytest.raises(release.BlobUploadError, match="uploadWheelToBlob"):
        release.upload_wheel(storage[0], tmp_path / "receipt.json")
    release.subprocess.run.assert_not_called()
    release.github.assert_not_called()


@pytest.mark.parametrize("upload", [False, "true", 1])
def test_blob_upload_intent_is_bound_to_candidate(storage, tmp_path, upload):
    directory, value = storage
    value["uploadWheelToBlob"] = upload
    release.write(directory / "candidate.json", value)
    with pytest.raises(release.BlobUploadError, match="Blob upload option"):
        release.upload_wheel(directory, tmp_path / "blob-upload.json")
    release.subprocess.run.assert_not_called()


@pytest.mark.parametrize("mutation", ["wheel", "source", "waiver", "size"])
def test_blob_rejects_unqualified_candidate_before_authentication(storage, monkeypatch, tmp_path, mutation):
    directory, value = storage
    if mutation == "wheel":
        (directory / value["wheel"]["file"]).write_bytes(b"changed")
    elif mutation == "source":
        monkeypatch.setenv("RELEASE_SOURCE_COMMIT", "c" * 40)
    elif mutation == "waiver":
        monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", "true")
    else:
        monkeypatch.setattr(release, "MAX_BLOB_BYTES", 1)
    with pytest.raises(release.BlobUploadError):
        release.upload_wheel(directory, tmp_path / "receipt.json")
    release.subprocess.run.assert_not_called()


@pytest.mark.parametrize("phase", ["get", "put", "verify"])
@pytest.mark.parametrize("code", [301, 307, 401, 403, 500])
def test_blob_http_failures_never_publish_receipt(storage, monkeypatch, tmp_path, phase, code):
    responses = [] if phase == "get" else [blob_error(404)]
    if phase == "verify":
        responses.append(blob_response(status=201))
    opened = blob_transport(monkeypatch, responses + [blob_error(code)])
    receipt = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError, match=f"HTTP {code}"):
        release.upload_wheel(storage[0], receipt)
    assert not receipt.exists()
    assert opened.call_count == len(responses) + 1


@pytest.mark.parametrize("error", [URLError("secret-offline-storage-token"), TimeoutError("secret")])
def test_blob_network_errors_are_explicit_and_do_not_leak_tokens(storage, monkeypatch, tmp_path, error):
    blob_transport(monkeypatch, [error])
    with pytest.raises(RuntimeError, match="Blob network request failed") as caught:
        release.upload_wheel(storage[0], tmp_path / "receipt.json")
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("suffix", ["?sig=secret", "#fragment", "/other.whl"])
def test_blob_destination_rejects_query_fragment_or_nested_path(monkeypatch, suffix):
    opened = blob_transport(monkeypatch, [])
    with pytest.raises(ValueError, match="Unapproved Blob"):
        release.blob_request(release.BLOB_CONTAINER + "wheel.whl" + suffix, "token", size=1)
    opened.assert_not_called()


@pytest.mark.parametrize("url", [
    "http://azedgecli.blob.core.windows.net/drop/wheel.whl",
    "https://other.blob.core.windows.net/drop/wheel.whl",
    "https://azedgecli.blob.core.windows.net/other/wheel.whl",
    "https://user@azedgecli.blob.core.windows.net/drop/wheel.whl",
    "https://azedgecli.blob.core.windows.net/drop/a%2Fb.whl",
])
def test_blob_destination_is_fixed_without_relaxing_generic_api(monkeypatch, url):
    opened = blob_transport(monkeypatch, [])
    with pytest.raises(ValueError, match="Unapproved Blob"):
        release.blob_request(url, "token", size=1)
    with pytest.raises(ValueError, match="Unapproved API"):
        release.api(release.BLOB_CONTAINER + "wheel.whl", "token")
    opened.assert_not_called()


@pytest.mark.parametrize("body", [b"too long", b"x"])
def test_blob_download_rejects_truncated_or_oversized_content(monkeypatch, body):
    blob_transport(monkeypatch, [blob_response(body, length=4)])
    with pytest.raises(release.BlobUploadError, match="length"):
        release.blob_request(release.BLOB_CONTAINER + "wheel.whl", "token", size=4)


def test_blob_download_deadline_is_bounded(monkeypatch):
    blob_transport(monkeypatch, [blob_response(b"data")])
    monkeypatch.setattr(release.time, "monotonic", Mock(side_effect=[0, 121]))
    with pytest.raises(RuntimeError, match="download deadline"):
        release.blob_request(release.BLOB_CONTAINER + "wheel.whl", "token", size=4)


def test_blob_readback_mismatch_after_creation_never_publishes_receipt(storage, monkeypatch, tmp_path):
    directory, value = storage
    size = (directory / value["wheel"]["file"]).stat().st_size
    opened = blob_transport(monkeypatch, [
        blob_error(404), blob_response(status=201), blob_response(b"x" * size),
    ])
    receipt = tmp_path / "receipt.json"
    with pytest.raises(release.BlobUploadError, match="Upload was accepted") as caught:
        release.upload_wheel(directory, receipt)
    assert caught.value.code == "RELEASE_BLOB_UNVERIFIED"
    assert not receipt.exists()
    assert [call.args[0].method for call in opened.call_args_list] == ["GET", "PUT", "GET"]


@pytest.mark.parametrize("response", [
    Mock(returncode=1, stdout="secret", stderr="secret"),
    Mock(returncode=0, stdout="secret"),
    Mock(returncode=0, stdout='{"accessToken":"secret\\ninvalid"}'),
    Mock(returncode=0, stdout='{"accessToken":null}'),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
])
def test_blob_authentication_errors_are_sanitized(storage, monkeypatch, tmp_path, capsys, response):
    monkeypatch.setattr(release.subprocess, "run", Mock(side_effect=[response]))
    with pytest.raises(RuntimeError, match="Storage authentication failed") as caught:
        release.upload_wheel(storage[0], tmp_path / "receipt.json")
    assert "secret" not in str(caught.value) + capsys.readouterr().out


def test_upload_preparation_freezes_standalone_tooling_without_index_generation(storage, tmp_path):
    tooling = tmp_path / "frozen"
    release.prepare_upload(storage[0], tooling)
    assert [path.name for path in tooling.iterdir()] == ["release_pipeline.py"]
    assert (tooling / "release_pipeline.py").read_bytes() == (ROOT / "tools/release_pipeline.py").read_bytes()
    release.subprocess.run.assert_not_called()
    release.github.assert_not_called()


@pytest.mark.parametrize("scenario,code", [
    ("uploaded", None), ("identical", None), ("race-identical", None),
    ("different", "RELEASE_BLOB_CONFLICT"), ("shorter", "RELEASE_BLOB_CONFLICT"),
    ("race-different", "RELEASE_BLOB_CONFLICT"), ("missing", "RELEASE_BLOB_UNVERIFIED"),
    ("auth", "RELEASE_BLOB_AUTH"), ("network-after-put", "RELEASE_BLOB_UNVERIFIED"),
    ("post-create-different", "RELEASE_BLOB_UNVERIFIED"), ("post-create-shorter", "RELEASE_BLOB_UNVERIFIED"),
])
def test_blob_main_reports_links_outcome_and_recovery(storage, monkeypatch, tmp_path, capsys, scenario, code):
    directory, value = storage
    wheel = value["wheel"]
    data = (directory / wheel["file"]).read_bytes()
    different = b"x" * len(data)
    responses = {
        "uploaded": [blob_error(404), blob_response(status=201), blob_response(data)],
        "identical": [blob_response(data)],
        "race-identical": [blob_error(404), blob_error(412), blob_response(data)],
        "different": [blob_response(different)],
        "shorter": [blob_response(different[:-1])],
        "race-different": [blob_error(404), blob_error(409), blob_response(different)],
        "missing": [blob_error(404), blob_response(status=201)] + [blob_error(404)] * 3,
        "auth": [blob_error(403)],
        "network-after-put": [blob_error(404), blob_response(status=201), URLError("secret-offline-storage-token")],
        "post-create-different": [blob_error(404), blob_response(status=201), blob_response(different)],
        "post-create-shorter": [blob_error(404), blob_response(status=201), blob_response(different[:-1])],
    }
    blob_transport(monkeypatch, responses[scenario])
    receipt = tmp_path / "publication" / "blob-upload.json"
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    if code:
        with pytest.raises(SystemExit) as caught:
            release.main()
        assert caught.value.code == 1
        assert not receipt.exists()
    else:
        release.main()
        assert release.read(receipt)["status"] == ("uploaded" if scenario == "uploaded" else "already-present")
    output = capsys.readouterr().out
    summary = receipt.with_suffix(".md").read_text()
    url = release.BLOB_CONTAINER + wheel["file"]
    assert url in output and f"]({url})" in summary
    assert wheel["sha256"] in output and wheel["sha256"] in summary
    assert "Candidate artifact (release-candidate)" in output
    assert "_build/results?buildId=900&view=artifacts" in summary
    assert f"##vso[task.uploadsummary]{receipt.with_suffix('.md')}" in output
    assert "secret-offline-storage-token" not in output + summary
    assert "Traceback" not in output
    if code:
        assert f"##vso[task.logissue type=error;code={code}]" in output
        assert "cannot proceed to release or index publication" in summary
        if code == "RELEASE_BLOB_CONFLICT":
            assert "Existing wheel" in summary and "bump the extension version" in summary
            assert "original pipeline run" in summary and "approved wheel artifact" in summary
            assert "was not overwritten" in summary
            assert f"Existing: {len(data) - (scenario == 'shorter')} bytes" in output
            if scenario == "shorter":
                assert "not computed: size differs" in summary
            else:
                assert release.hashlib.sha256(different).hexdigest() in summary
        elif code == "RELEASE_BLOB_AUTH":
            assert "sc-cli-release-storage" in summary
        else:
            assert "contents not verified" in output
            if scenario.startswith("post-create-"):
                assert "Upload was accepted" in summary and "Observed blob:" in summary
                assert "Existing wheel" not in summary and "RELEASE_BLOB_CONFLICT" not in output
                assert "Investigate the unexpected stored content" in summary
                assert "A retry cannot repair different bytes" in summary
            else:
                assert "blob may already exist" in summary
    else:
        assert "task.logissue type=error" not in output
        expected = ("Wheel uploaded and verified." if scenario == "uploaded"
                    else "Identical wheel already exists; upload skipped.")
        assert expected in output and expected in summary
    release.github.assert_not_called()
    release.ado.assert_not_called()


@pytest.mark.parametrize("mutation,reason", [
    ("wheel", "Candidate asset digest mismatch."),
    ("source", "Configure RELEASE_SOURCE_COMMIT explicitly"),
    ("waiver", "Candidate integration waiver does not match this release run or consumer."),
    ("missing", "A required candidate artifact file is missing or unreadable."),
    ("zip", "The candidate wheel is not a valid ZIP archive."),
])
def test_blob_main_reports_invalid_candidate_without_authentication(
    storage, monkeypatch, tmp_path, capsys, mutation, reason,
):
    directory, value = storage
    if mutation in {"wheel", "zip"}:
        (directory / value["wheel"]["file"]).write_bytes(b"changed")
        if mutation == "zip":
            value["wheel"]["sha256"] = release.digest(directory / value["wheel"]["file"])
            release.write(directory / "candidate.json", value)
    elif mutation == "source":
        monkeypatch.setenv("RELEASE_SOURCE_COMMIT", "$(sourceCommit)")
    elif mutation == "waiver":
        value["skipIntegrationTests"] = True
        release.write(directory / "candidate.json", value)
    else:
        (directory / "candidate.json").unlink()
    receipt = tmp_path / "blob-upload.json"
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert "RELEASE_CANDIDATE_INVALID" in output
    summary = receipt.with_suffix(".md").read_text()
    assert reason in output and reason.replace("_", r"\_") in summary
    assert "pipeline variables" in output and "release-candidate manifest" in output
    assert "Candidate artifact (release-candidate)" in summary
    assert not receipt.exists()
    release.subprocess.run.assert_not_called()


@pytest.mark.parametrize("path,bad_value,reason", [
    ((), {}, "field 'schema'"), ((), [], "must be a JSON object"),
    ((), "private-manifest-value", "must be a JSON object"),
    (("wheel",), None, "field 'wheel'"), (("wheel",), {}, "field 'file'"),
    (("wheel", "file"), None, "field 'file'"), (("wheel", "sha256"), [], "field 'sha256'"),
    (("wheel", "version"), 1, "field 'version'"), (("sbom",), {}, "field 'file'"),
    (("sbom", "file"), {}, "field 'file'"), (("sbom", "sha256"), None, "field 'sha256'"),
    (("producer",), [], "field 'producer'"), (("cohorts",), [], "cohort inventory"),
    (("region",), None, "field 'region'"), (("cohorts", COHORT), [], "must be a JSON object"),
    (("cohorts", COHORT), {}, "field 'row'"), (("cohorts", COHORT, "selection"), None, "field 'selection'"),
    (("cohorts", COHORT, "row"), [], "field 'row'"),
    (("cohorts", COHORT, "row", "scenario"), None, "field 'scenario'"),
    (("cohorts", COHORT, "row", "scenario", "channel"), [], "field 'channel'"),
])
def test_blob_main_reports_malformed_manifest_without_authentication(
    storage, monkeypatch, tmp_path, capsys, path, bad_value, reason,
):
    directory, manifest = storage
    if path:
        parent = manifest
        for field in path[:-1]:
            parent = parent[field]
        parent[path[-1]] = bad_value
    else:
        manifest = bad_value
    release.write(directory / "candidate.json", manifest)
    receipt = tmp_path / "blob-upload.json"
    opened = blob_transport(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    summary = receipt.with_suffix(".md").read_text()
    assert reason in output and reason in summary
    assert "task.logissue type=error;code=RELEASE_CANDIDATE_INVALID" in output
    assert "pipeline variables" in summary and "release-candidate manifest" in summary
    assert "private-manifest-value" not in output + summary
    assert not receipt.exists()
    release.subprocess.run.assert_not_called()
    opened.assert_not_called()
    release.github.assert_not_called()


@pytest.mark.parametrize("attribute,value,reason", [
    ("flag_bits", 1, "Encrypted wheel METADATA is not supported."),
    ("compress_type", 99, "Wheel METADATA uses unsupported ZIP features or compression."),
    ("compress_type", release.zipfile.ZIP_DEFLATED, "Wheel METADATA contains corrupt DEFLATE data."),
])
def test_blob_main_reports_unreadable_wheel_metadata(storage, monkeypatch, tmp_path, capsys, attribute, value, reason):
    getinfo = ZipFile.getinfo

    def unreadable_metadata(archive, name):
        info = getinfo(archive, name)
        if name.endswith(".dist-info/METADATA"):
            setattr(info, attribute, value)
        return info

    monkeypatch.setattr(ZipFile, "getinfo", unreadable_metadata)
    receipt = tmp_path / "blob-upload.json"
    opened = blob_transport(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(storage[0]), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    summary = receipt.with_suffix(".md").read_text()
    assert release.ado_escape(reason) in output and reason in summary
    assert "task.logissue type=error;code=RELEASE_CANDIDATE_INVALID" in output
    assert "Candidate artifact (release-candidate)" in summary
    assert not receipt.exists()
    release.subprocess.run.assert_not_called()
    opened.assert_not_called()


def test_blob_main_reports_unsupported_zip_version(storage, monkeypatch, tmp_path, capsys):
    directory, manifest = storage
    wheel = directory / manifest["wheel"]["file"]
    data = bytearray(wheel.read_bytes())
    entry = data.index(b"PK\x01\x02")
    data[entry + 6:entry + 8] = (64).to_bytes(2, "little")
    wheel.write_bytes(data)
    manifest["wheel"]["sha256"] = release.digest(wheel)
    release.write(directory / "candidate.json", manifest)
    receipt = tmp_path / "blob-upload.json"
    opened = blob_transport(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    reason = "Wheel archive uses unsupported ZIP features."
    assert reason in output and reason in receipt.with_suffix(".md").read_text()
    assert "task.logissue type=error;code=RELEASE_CANDIDATE_INVALID" in output
    assert not receipt.exists()
    release.subprocess.run.assert_not_called()
    opened.assert_not_called()


@pytest.mark.parametrize("fault,reason", [
    ("sbom-name", "Invalid candidate asset identity."),
    ("manifest-directory", "A required candidate artifact file is missing or unreadable."),
    ("wheel-removed", "Candidate wheel could not be read before upload."),
])
def test_blob_main_reports_candidate_file_errors(storage, monkeypatch, tmp_path, capsys, fault, reason):
    directory, manifest = storage
    if fault == "sbom-name":
        manifest["sbom"]["file"] = ".."
        release.write(directory / "candidate.json", manifest)
    elif fault == "manifest-directory":
        (directory / "candidate.json").unlink()
        (directory / "candidate.json").mkdir()
    else:
        monkeypatch.setattr(release, "verify_candidate", Mock(return_value=manifest))
        (directory / manifest["wheel"]["file"]).unlink()
    receipt = tmp_path / "blob-upload.json"
    opened = blob_transport(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert reason in output and "task.logissue type=error;code=RELEASE_CANDIDATE_INVALID" in output
    assert not receipt.exists()
    release.subprocess.run.assert_not_called()
    opened.assert_not_called()


def test_blob_main_reports_receipt_save_failure_after_verified_upload(storage, monkeypatch, tmp_path, capsys):
    directory, manifest = storage
    blob_transport(monkeypatch, [blob_response((directory / manifest["wheel"]["file"]).read_bytes())])
    (tmp_path / "blocked").write_text("not a directory")
    receipt = tmp_path / "blocked" / "blob-upload.json"
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert "task.logissue type=error;code=RELEASE_BLOB_RECEIPT" in output
    assert "Verified wheel: " in output and "rerun this upload job" in output
    assert "Could not write the Blob upload summary" in output


@pytest.mark.parametrize("paths", [
    {"--record": "blob-upload.json"}, {"--directory": "candidate"},
    {"--directory": "candidate", "--record": ""}, {"--directory": "candidate", "--record": "."},
    {"--directory": "candidate", "--record": "/"},
])
def test_blob_main_requires_upload_paths(storage, monkeypatch, capsys, paths):
    monkeypatch.chdir(storage[0].parent)
    monkeypatch.setattr(sys, "argv", ["release_pipeline.py", "upload", *[v for item in paths.items() for v in item]])
    opened = blob_transport(monkeypatch, [])
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 2
    assert "upload requires --directory and --record" in capsys.readouterr().err
    release.subprocess.run.assert_not_called()
    opened.assert_not_called()


def test_wheel_metadata_parses_headers_only(storage, tmp_path):
    directory, manifest = storage
    source = directory / manifest["wheel"]["file"]
    wheel = tmp_path / source.name
    nested = "".join(f'Content-Type: multipart/mixed; boundary="b{i}"\n\n--b{i}\n' for i in range(1200))
    with ZipFile(source) as original, ZipFile(wheel, "w") as rebuilt:
        for name in original.namelist():
            data = original.read(name)
            rebuilt.writestr(name, data + nested.encode() if name.endswith(".dist-info/METADATA") else data)
    assert release.wheel_metadata(wheel) == manifest["wheel"]["version"]


def test_blob_main_preserves_unexpected_reader_error(storage, monkeypatch, tmp_path):
    monkeypatch.setattr(ZipFile, "read", Mock(side_effect=RuntimeError("unexpected reader defect")))
    receipt = tmp_path / "blob-upload.json"
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(storage[0]), "--record", str(receipt),
    ])
    with pytest.raises(RuntimeError, match="unexpected reader defect"):
        release.main()
    assert not receipt.exists()
    assert not receipt.with_suffix(".md").exists()
    release.subprocess.run.assert_not_called()


@pytest.mark.parametrize("length", [None, "invalid-secret-header", "9" * 5000])
def test_blob_invalid_content_length_is_unverified_not_conflict(monkeypatch, length):
    response = blob_response(b"x")
    response.headers = {} if length is None else {"Content-Length": length}
    blob_transport(monkeypatch, [response])
    with pytest.raises(release.BlobUploadError) as caught:
        release.blob_request(release.BLOB_CONTAINER + "wheel.whl", "token", size=4)
    assert caught.value.code == "RELEASE_BLOB_UNVERIFIED"
    assert "secret" not in str(caught.value)


def test_blob_summary_write_failure_preserves_primary_error(storage, monkeypatch, tmp_path, capsys):
    directory, value = storage
    size = (directory / value["wheel"]["file"]).stat().st_size
    blob_transport(monkeypatch, [blob_response(b"x" * size)])
    receipt = tmp_path / "blob-upload.json"
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    monkeypatch.setattr(Path, "write_text", Mock(side_effect=OSError("offline disk error")))
    with pytest.raises(SystemExit) as caught:
        release.main()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert "code=RELEASE_BLOB_CONFLICT" in output
    assert "Could not write the Blob upload summary" in output
    assert "task.uploadsummary" not in output
    assert not receipt.exists()


def test_blob_summary_write_failure_keeps_verified_upload_successful(storage, monkeypatch, tmp_path, capsys):
    directory, value = storage
    data = (directory / value["wheel"]["file"]).read_bytes()
    blob_transport(monkeypatch, [blob_response(data)])
    receipt = tmp_path / "blob-upload.json"
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(directory), "--record", str(receipt),
    ])
    receipt.with_suffix(".md").mkdir()
    release.main()
    output = capsys.readouterr().out
    assert release.read(receipt)["status"] == "already-present"
    assert "Identical wheel already exists" in output
    assert "Could not write the Blob upload summary" in output
    assert "task.uploadsummary" not in output


@pytest.mark.parametrize("error_type", [AssertionError, KeyError, TypeError, RuntimeError, NotImplementedError])
def test_blob_main_does_not_hide_unexpected_errors(storage, monkeypatch, tmp_path, error_type):
    monkeypatch.setattr(release, "verify_candidate", Mock(side_effect=error_type("unexpected defect")))
    monkeypatch.setattr(sys, "argv", [
        "release_pipeline.py", "upload", "--directory", str(storage[0]), "--record", str(tmp_path / "receipt.json"),
    ])
    with pytest.raises(error_type, match="unexpected defect"):
        release.main()
    release.subprocess.run.assert_not_called()


def test_blob_summary_escapes_attachment_path_and_preserves_encoded_wheel_link(storage, tmp_path, capsys):
    wheel = {**storage[1]["wheel"], "file": "wheel+local.whl"}
    result = {"candidate": {"wheel": wheel}, "length": 4, "status": "already-present"}
    receipt = tmp_path / "upload];%.json"
    release.report_blob_upload(receipt, result=result)
    output = capsys.readouterr().out
    assert "upload%5D%3B%AZP25.md" in output
    assert "##vso[task.uploadsummary]" + str(receipt.with_suffix(".md")) not in output
    url = release.BLOB_CONTAINER + "wheel%2Blocal.whl"
    assert f"Verified wheel: {url}" in output
    assert f"[Verified wheel]({url})" in receipt.with_suffix(".md").read_text()


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
    ("BUILD_SOURCEBRANCH", "refs/heads/feature/work"), ("RELEASE_SOURCE_BRANCH", "refs/tags/v1"),
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


def test_pre_shard_source_keeps_unsharded_cohorts(tmp_path):
    for path in (".github/test-scenarios.yml", ".github/actions/build-int-test-matrix/build_matrix.py"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text((ROOT / path).read_text(encoding="utf-8"), encoding="utf-8")
    matrix = tmp_path / ".github/actions/build-int-test-matrix/build_matrix.py"
    matrix.write_text(matrix.read_text(encoding="utf-8").split("\ndef shard_rows(")[0], encoding="utf-8")
    config = tmp_path / ".github/test-scenarios.yml"
    config.write_text(config.read_text(encoding="utf-8").split("    # ADO runs each shard")[0], encoding="utf-8")
    cohorts = release.source_cohorts(tmp_path)
    assert {"trustbundle_stable_py313", "trustbundle_preview_py313", COHORT} <= set(cohorts)
    assert not any("shard" in key for key in cohorts)


@pytest.mark.parametrize("version,already_versioned", [
    ("2.11.1", False), ("2.0.0b1", False), ("2.0.0b1", True),
])
@pytest.mark.parametrize("skipped", [False, True])
@pytest.mark.parametrize("upload", [False, True])
@pytest.mark.parametrize("mode", ["Validate", "Draft", "Release"])
def test_candidate_creation_updates_title_from_wheel_once(
        candidate, tmp_path, monkeypatch, capsys, version, already_versioned, skipped, upload, mode):
    _, value = candidate
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", str(skipped))
    monkeypatch.setenv("RELEASE_UPLOAD_WHEEL_TO_BLOB", str(upload))
    monkeypatch.setenv("RELEASE_MODE", mode)
    title = "aio-release-20261104.1"
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
        for suffix, runtime, train in [("", "1.4.99", "stable"), ("_preview", "1.6.0-preview.60", "preview")]:
            archive.writestr(
                f"azext_edge/edge/providers/orchestration/template{suffix}.py",
                repr({"VERSIONS": {"iotOperations": runtime}, "TRAINS": {"iotOperations": train}}),
            )
    monkeypatch.setattr(release, "command", Mock(return_value=SOURCE))
    monkeypatch.setattr(release.subprocess, "run", Mock())
    monkeypatch.setattr(release, "source_cohorts", Mock(return_value=value["cohorts"]))
    output = tmp_path / "generated"
    generated = release.create_candidate(source, output)
    lines = capsys.readouterr().out.splitlines()
    expected = f"ops-900 ({version})"
    if not skipped:
        expected += (
            " (edge, insecure-listener, rpsaas +7) (westus2)"
            " (runtime 1.4.99, 1.6.0-preview.60) (stable, preview)"
        )
    assert lines[0] == f"##vso[build.updatebuildnumber]{expected} ({mode.lower()})"
    assert not any("variable=matrix" in line for line in lines)
    assert generated["skipIntegrationTests"] is skipped
    assert generated["uploadWheelToBlob"] is upload
    if skipped:
        release.source_cohorts.assert_not_called()
    assert generated["wheel"]["version"] == version
    assert generated["producer"] == value["producer"]
    assert release.verify_candidate(output) == generated


@pytest.mark.parametrize("mutation", [
    "source", "producer", "wheel", "sbom", "cohort", "shard", "shard-name", "shard-int", "shard-list", "extra",
])
def test_invalid_candidate_rejected(candidate, mutation):
    directory, value = candidate
    if mutation == "shard":
        value["cohorts"].pop("trustbundle_preview_trust_py313")
    elif mutation == "shard-name":
        value["cohorts"]["trustbundle_preview_trust_py313"]["row"]["scenario"]["shard"] = "other"
    elif mutation in {"shard-int", "shard-list"}:
        value["cohorts"]["trustbundle_preview_trust_py313"]["row"]["scenario"]["shard"] = (
            1 if mutation == "shard-int" else []
        )
    elif mutation == "source":
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
    assert release.read(tmp_path / "record") == {"id": "901", "producer": value["producer"]}
    assert network.call_count == 2
    assert network.call_args_list[1].args == ("build/builds/901",)
    release.time.sleep.assert_not_called()


def test_retry_reattaches_to_the_owned_child(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    monkeypatch.setenv("SYSTEM_JOBATTEMPT", "2")
    other = child(value)
    other["parameters"] = json.dumps({"ReleaseCandidateBuildId": "899"})
    builds = [other, child(value)]
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


def test_duplicate_owned_child_is_rejected(candidate, monkeypatch):
    value = candidate[1]
    monkeypatch.setattr(release, "ado", Mock(side_effect=[parent(), {"value": [child(value), child(value)]}]))
    with pytest.raises(ValueError, match="Multiple children"):
        release.existing_integration(value)


def test_owned_per_cohort_child_is_rejected(candidate, monkeypatch):
    value = candidate[1]
    build = child(value)
    build["templateParameters"].update(testScenarios='["edge"]', runtimeChannels='["Stable"]')
    monkeypatch.setattr(release, "ado", Mock(side_effect=[parent(), {"value": [build]}]))
    with pytest.raises(ValueError, match="unexpected release request"):
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


def test_cancel_cannot_target_another_release(candidate, tmp_path):
    directory, value = candidate
    release.write(tmp_path / "record", {"id": "901", "producer": dict(value["producer"], build="899")})
    with pytest.raises(ValueError, match="another release"):
        release.cancel_integration(tmp_path / "record", directory)
    release.ado.assert_not_called()


def consumer_environment(candidate, monkeypatch):
    directory, _ = candidate
    profile = release.read(ROOT / ".azure-devops/release-monitors.json")["clouds"]["public"]["variables"]
    for name, value in {
        "SYSTEM_DEFINITIONID": "164", "BUILD_BUILDID": "901", "BUILD_SOURCEVERSION": SOURCE,
        "OPS_RELEASE_BUILD_ID": "900", "OPS_RELEASE_INPUT": str(directory), "OPS_MODE": "Integration tests",
        "OPS_SCENARIOS": ",".join(dict.fromkeys(item["selection"] for item in candidate[1]["cohorts"].values())),
        "OPS_CHANNELS": "stable,preview", "OPS_PYTHONS": "3.13", "OPS_BASELINES": "{}",
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
@pytest.mark.parametrize("upload", [False, True])
@pytest.mark.parametrize("source", ["dev", "release/2027-preview", "_next/2027+beta"])
def test_consumer_acquires_identical_candidate_without_rebuilding(
        candidate, monkeypatch, tmp_path, mode, upload, source):
    directory, value = candidate
    value["uploadWheelToBlob"] = upload
    value["sourceBranch"] = release.branch(source)
    release.write(directory / "candidate.json", value)
    consumer_environment(candidate, monkeypatch)
    monkeypatch.setenv("BUILD_SOURCEBRANCH", value["sourceBranch"])
    producer = parent()
    producer["templateParameters"]["mode"] = mode
    producer["templateParameters"]["sourceBranch"] = source
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
    monkeypatch.delenv("OPS_UNIT_COVERAGE")
    seeded = integration.read(tmp_path / f"ops-attempt-{COHORT}-1/receipt.json")
    rows = integration.read(tmp_path / "plan/plan.json")["rows"]
    assert rows == integration.release_rows(wheel_dir)
    for row in rows:
        attempt = tmp_path / f"ops-attempt-{row['key']}-1"
        phases = integration.expected_phases(row)
        integration.write(attempt / "receipt.json", dict(
            seeded, row=row["key"], sha256=value["wheel"]["sha256"], phases=dict.fromkeys(phases, "passed"),
        ))
        for phase in phases:
            (attempt / "junit").mkdir(exist_ok=True)
            (attempt / "junit" / f"{phase}.xml").write_text('<testsuite><testcase name="passed"/></testsuite>')
        (attempt / "coverage.dat").write_bytes(b"offline coverage")
    integration.gate(tmp_path / "ops-qualification-1")
    proof = integration.read(tmp_path / "ops-qualification-1/qualification.json")
    assert proof["coverageScope"] == "selected ops scenarios"
    assert not (tmp_path / "ops-qualification-1/coverage/.coverage.unit").exists()
    monkeypatch.setenv("SYSTEM_DEFINITIONID", "165")
    monkeypatch.setenv("BUILD_BUILDID", "900")
    monkeypatch.setenv("BUILD_SOURCEVERSION", AUTOMATION)
    monkeypatch.setattr(release, "ado", Mock(return_value=child(value)))
    release.verify_integration_artifacts(directory, tmp_path)
    partial = dict(proof, scenarios=proof["scenarios"][1:])
    integration.write(tmp_path / "ops-qualification-2/qualification.json", partial)
    with pytest.raises(ValueError, match="Incomplete release cohort"):
        release.verify_integration_artifacts(directory, tmp_path)
    shutil.rmtree(tmp_path / "ops-qualification-2")
    (wheel_dir / value["wheel"]["file"]).write_bytes(b"rebuilt")
    with pytest.raises(ValueError, match="exact candidate"):
        release.verify_integration_artifacts(directory, tmp_path)


def test_publication_without_index_credentials_reuses_exact_release(candidate, monkeypatch, tmp_path):
    directory, value = candidate
    owned_release(value)
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
@pytest.mark.parametrize("upload_blob", [False, True])
@pytest.mark.parametrize("source", ["dev", "release/2027-preview", "users/test/next"])
def test_draft_is_promoted_only_after_verified_uploads(
        candidate, monkeypatch, tmp_path, mode, skipped, upload_blob, source):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_MODE", mode)
    monkeypatch.setenv("RELEASE_SKIP_INTEGRATION_TESTS", str(skipped))
    monkeypatch.setenv("RELEASE_UPLOAD_WHEEL_TO_BLOB", str(upload_blob))
    monkeypatch.setenv("RELEASE_SOURCE_BRANCH", source)
    value["sourceBranch"] = release.branch(source)
    value["uploadWheelToBlob"] = upload_blob
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
        release.attach_publication_receipt.assert_called_once()
        assert release.read(release.attach_publication_receipt.call_args.args[0]) == (
            release.ownership_record(value, draft["id"], JOB)
        )
        item = next(item for item in (value["wheel"], value["sbom"])
                    if release.hashlib.sha256(kwargs["data"]).hexdigest() == item["sha256"])
        asset = {"name": item["file"], "digest": "sha256:" + item["sha256"]}
        draft["assets"].append(asset)
        return asset

    monkeypatch.setattr(release, "github", github)
    monkeypatch.setattr(release, "api", upload)
    blob_receipt = tmp_path / "blob-upload.json"
    if upload_blob:
        monkeypatch.setattr(release, "storage_token", Mock(return_value="offline-storage-token"))
        monkeypatch.setattr(release, "blob_request", Mock(return_value={
            "status": 200, "sha256": value["wheel"]["sha256"],
            "length": (directory / value["wheel"]["file"]).stat().st_size,
        }))
        assert release.upload_wheel(directory, blob_receipt)["status"] == "already-present"
        assert not events
    result = release.publish(directory, tmp_path / "release.json", tmp_path / "publication.json")
    assert blob_receipt.exists() is upload_blob
    if upload_blob:
        assert release.read(blob_receipt)["candidate"] == release.read(tmp_path / "release.json")["candidate"]
        assert release.read(blob_receipt)["status"] == "already-present"
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
    owned_release(candidate[1])
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
    owned_release(value)
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


@pytest.mark.parametrize("change", [
    {"draft": False}, {"target_commitish": "f" * 40}, {"assets": []}, {"tag_name": "v9.9.9"},
])
def test_draft_requires_fresh_identity_and_asset_verification(candidate, tmp_path, monkeypatch, change):
    monkeypatch.setenv("RELEASE_MODE", "Draft")
    owned_release(candidate[1])
    staged = public_release(candidate[1], draft=True)
    monkeypatch.setattr(release, "find_release", Mock(return_value=staged))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=None))
    network = Mock(return_value={**staged, **change})
    monkeypatch.setattr(release, "github", network)
    with pytest.raises(ValueError):
        release.publish(candidate[0], tmp_path / "receipt", tmp_path / "publication.json")
    assert not (tmp_path / "receipt").exists()
    assert all("method" not in call.kwargs for call in network.call_args_list)


@pytest.mark.parametrize("conflict", ["tag", "release-tag", "digest", "missing"])
def test_publication_never_overwrites_conflicting_assets(candidate, monkeypatch, tmp_path, conflict):
    owned_release(candidate[1])
    published = public_release(candidate[1])
    if conflict == "digest":
        published["assets"][0]["digest"] = "sha256:wrong"
    elif conflict == "missing":
        published["assets"] = []
    elif conflict == "release-tag":
        published["tag_name"] = "v9.9.9"
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=AUTOMATION if conflict == "tag" else SOURCE))
    monkeypatch.setattr(release, "find_release", Mock(return_value=published))
    with pytest.raises(ValueError):
        release.publish(candidate[0], tmp_path / "receipt", tmp_path / "publication.json")
    release.github.assert_not_called()


@pytest.mark.parametrize("mode,draft", [("Draft", True), ("Release", True), ("Release", False)])
@pytest.mark.parametrize("assets", [0, 1, 2])
def test_new_run_cannot_adopt_an_existing_version_even_when_assets_match(
        candidate, tmp_path, monkeypatch, mode, draft, assets):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_MODE", mode)
    existing = public_release(value, draft=draft)
    existing["assets"] = existing["assets"][:assets]
    monkeypatch.setattr(release, "find_release", Mock(return_value=existing))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=None if draft else SOURCE))
    writes = Mock(side_effect=AssertionError("No API writes permitted"))
    monkeypatch.setattr(release, "api", writes)
    with pytest.raises(ValueError, match="another run or ownership is unknown") as error:
        release.publish(directory, tmp_path / "receipt.json", tmp_path / "publication.json")
    assert f"https://github.com/{release.REPOSITORY}/releases/tag/v{value['wheel']['version']}" in str(error.value)
    release.github.assert_not_called()
    release.attach_publication_receipt.assert_not_called()
    writes.assert_not_called()


@pytest.mark.parametrize("assets", [0, 1, 2])
def test_original_run_can_resume_partial_draft_without_replacing_assets(
        candidate, tmp_path, monkeypatch, assets):
    directory, value = candidate
    monkeypatch.setenv("RELEASE_MODE", "Draft")
    owned_release(value)
    staged = public_release(value, draft=True)
    staged["assets"] = staged["assets"][:assets]
    monkeypatch.setattr(release, "find_release", Mock(return_value=staged))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=None))
    monkeypatch.setattr(release, "github", Mock(return_value=staged))

    def upload(_url, _token, **kwargs):
        item = next(item for item in (value["wheel"], value["sbom"])
                    if release.hashlib.sha256(kwargs["data"]).hexdigest() == item["sha256"])
        asset = {"name": item["file"], "digest": "sha256:" + item["sha256"]}
        staged["assets"].append(asset)
        return asset

    transport = Mock(side_effect=upload)
    monkeypatch.setattr(release, "api", transport)
    assert release.publish(directory, tmp_path / "receipt.json", tmp_path / "publication.json")["draft"]
    assert transport.call_count == 2 - assets
    assert all("method" not in call.kwargs for call in release.github.call_args_list)
    release.attach_publication_receipt.assert_not_called()


@pytest.mark.parametrize("existing", [None, 11])
def test_owned_release_cannot_be_replaced_or_silently_recreated(candidate, tmp_path, monkeypatch, existing):
    owned_release(candidate[1])
    found = {**public_release(candidate[1], draft=True), "id": existing} if existing else None
    monkeypatch.setattr(release, "find_release", Mock(return_value=found))
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=None))
    with pytest.raises(ValueError, match="no longer present|another run"):
        release.publish(candidate[0], tmp_path / "receipt.json", tmp_path / "publication.json")
    release.github.assert_not_called()
    release.attach_publication_receipt.assert_not_called()


def test_existing_matching_tag_without_release_is_not_a_duplicate(candidate, tmp_path, monkeypatch):
    directory, value = candidate
    staged = public_release(value, draft=True)
    staged["assets"] = []
    monkeypatch.setattr(release, "tag_commit", Mock(return_value=SOURCE))
    monkeypatch.setattr(release, "find_release", Mock(return_value=None))

    def github(resource, method="GET", data=None):
        assert not resource.endswith("/git/refs")
        if method in ("POST", "PATCH"):
            staged.update(data)
        return staged

    def upload(_url, _token, **kwargs):
        item = next(item for item in (value["wheel"], value["sbom"])
                    if release.hashlib.sha256(kwargs["data"]).hexdigest() == item["sha256"])
        asset = {"name": item["file"], "digest": "sha256:" + item["sha256"]}
        staged["assets"].append(asset)
        return asset

    monkeypatch.setattr(release, "github", Mock(side_effect=github))
    monkeypatch.setattr(release, "api", Mock(side_effect=upload))
    assert release.publish(directory, tmp_path / "receipt.json", tmp_path / "publication.json")["draft"] is False
    release.attach_publication_receipt.assert_called_once()


def ownership_timeline(start, attempt):
    ids = [str(release.UUID(int=value)) for value in range(start, start + 5)]
    timeline, stage, phase, job, task = ids
    return {
        "id": timeline, "records": [
            {"id": stage, "type": "Stage", "identifier": "Publish", "previousAttempts": []},
            {"id": phase, "type": "Phase", "parentId": stage},
            {"id": job, "type": "Job", "identifier": release.PUBLICATION_JOB,
             "parentId": phase, "attempt": attempt, "state": "completed", "previousAttempts": []},
            {"id": task, "type": "Task", "name": release.PUBLICATION_TASK, "parentId": job},
        ],
    }


@pytest.mark.parametrize("history", ["current", "job-retry", "stage-retry"])
@pytest.mark.parametrize("problem", [
    None, "missing", "foreign-producer", "candidate", "wrong-task", "wrong-stage",
    "foreign-build", "conflicting-receipts", "previous-active", "foreign-task",
])
def test_ownership_receipts_are_bound_to_this_run_and_protected_task(
        candidate, monkeypatch, history, problem):
    value = candidate[1]
    current, previous = ownership_timeline(1, 2), ownership_timeline(20, 1)
    current_job, current_task = current["records"][2:]
    current_job["state"] = "inProgress"
    monkeypatch.setenv("SYSTEM_JOBID", current_job["id"])
    monkeypatch.setenv("SYSTEM_JOBATTEMPT", "2")
    if history == "job-retry":
        current_job["previousAttempts"] = [{
            "timelineId": previous["id"], "recordId": previous["records"][2]["id"], "attempt": 1,
        }]
    elif history == "stage-retry":
        current["records"][0]["previousAttempts"] = [{
            "timelineId": previous["id"], "recordId": previous["records"][0]["id"], "attempt": 1,
        }]
    origin = current if history == "current" else previous
    origin_job, origin_task = origin["records"][2:]
    evidence = release.ownership_record(deepcopy(value), 10, origin_job["id"])
    if problem == "foreign-producer":
        evidence["candidate"]["producer"]["build"] = "899"
    elif problem == "candidate":
        evidence["candidate"]["wheel"]["sha256"] = "d" * 64
    elif problem == "wrong-task":
        origin_task["name"] = "Untrusted qualification output"
    elif problem == "wrong-stage":
        origin["records"][0]["identifier"] = "Unit"
    elif problem == "previous-active":
        previous["records"][2]["state"] = "inProgress"

    def attachment_path(timeline, task):
        return (f"build/builds/900/{timeline['id']}/{task['id']}/attachments/"
                f"{release.OWNERSHIP_ATTACHMENT}/{release.OWNERSHIP_FILE}")

    attachments = {} if problem == "missing" else {attachment_path(origin, origin_task): evidence}
    if problem == "foreign-task":
        foreign = ownership_timeline(40, 1)
        foreign["records"][0]["identifier"] = "Unit"
        foreign["records"][2]["identifier"] = "Unit.Unit.__default"
        origin["records"].extend(foreign["records"])
        attachments = {attachment_path(origin, foreign["records"][3]): evidence}
    if problem == "conflicting-receipts":
        current_job["previousAttempts"] = [{
            "timelineId": previous["id"], "recordId": previous["records"][2]["id"], "attempt": 1,
        }]
        attachments[attachment_path(current, current_task)] = release.ownership_record(value, 10, current_job["id"])
        attachments[attachment_path(previous, previous["records"][3])] = release.ownership_record(
            value, 11, previous["records"][2]["id"],
        )

    def ado(resource, **kwargs):
        if resource == "build/builds/900":
            return {
                "id": 899 if problem == "foreign-build" else 900,
                "definition": {"id": int(value["producer"]["definition"])},
                "project": {"id": PROJECT}, "repository": {"id": release.REPOSITORY, "type": "GitHub"},
                "sourceVersion": AUTOMATION, "sourceBranch": "refs/heads/dev",
            }
        if resource == "build/builds/900/timeline":
            return current
        if resource == f"build/builds/900/timeline/{previous['id']}":
            return previous
        assert resource.endswith("/" + release.OWNERSHIP_FILE) and kwargs == {"missing": True}
        return deepcopy(attachments.get(resource))

    network = Mock(side_effect=ado)
    monkeypatch.setattr(release, "ado", network)
    if (problem in ("foreign-producer", "candidate", "wrong-stage", "foreign-build", "conflicting-receipts")
            or problem == "wrong-task" and history == "current"
            or problem == "previous-active" and history != "current"):
        with pytest.raises(ValueError):
            OWNERSHIP_READER(value)
    elif problem in ("missing", "wrong-task", "foreign-task"):
        assert OWNERSHIP_READER(value) is None
    else:
        assert OWNERSHIP_READER(value) == evidence
    assert all("method" not in call.kwargs for call in network.call_args_list)
    release.github.assert_not_called()
    release.attach_publication_receipt.assert_not_called()


def test_ownership_attachment_file_is_never_overwritten(candidate, tmp_path):
    directory, value = candidate
    receipt = tmp_path / "receipt.json"
    release.retain_publication_ownership(value, 10, receipt)
    path = release.attach_publication_receipt.call_args.args[0]
    original = path.read_bytes()
    release.attach_publication_receipt.reset_mock()
    with pytest.raises(ValueError, match="different evidence"):
        release.retain_publication_ownership(value, 11, receipt)
    assert path.read_bytes() == original
    assert path not in directory.iterdir()
    release.attach_publication_receipt.assert_not_called()


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
    assert root["name"] == "ops-$(Build.BuildId)"
    assert root["appendCommitMessageToRunName"] is False
    parameters = {item["name"]: item for item in root["parameters"]}
    order = [item["name"] for item in root["parameters"]]
    region_index = order.index("clusterRegion")
    assert order[region_index + 1:region_index + 4] == [
        "uploadWheelToBlob", "skipIntegrationTests", "createIndexPr",
    ]
    assert parameters["mode"]["default"] == "Validate"
    assert parameters["createIndexPr"]["default"] is False
    assert parameters["uploadWheelToBlob"]["default"] is False
    assert parameters["skipIntegrationTests"]["default"] is False
    assert parameters["mode"]["values"] == ["Validate", "Draft", "Release"]
    assert root["variables"]["RELEASE_SKIP_INTEGRATION_TESTS"] == "${{ parameters.skipIntegrationTests }}"
    assert root["variables"]["RELEASE_UPLOAD_WHEEL_TO_BLOB"] == "${{ parameters.uploadWheelToBlob }}"
    assert root["extends"]["parameters"]["stages"][0]["parameters"]["uploadWheelToBlob"] == (
        "${{ parameters.uploadWheelToBlob }}"
    )
    template = yaml.safe_load((ROOT / ".azure-devops/templates/release-stages.yml").read_text(encoding="utf-8"))
    stages = {"Resolve": template["stages"][0]}
    for conditional in template["stages"][1:]:
        stages.update({stage["stage"]: stage for stage in next(iter(conditional.values()))})
    for name in ("Integration", "Upload", "Publish"):
        for dependency in stages[name]["dependsOn"]:
            if isinstance(dependency, dict):
                continue
            assert f"eq(dependencies.{dependency}.result, 'Succeeded')" in stages[name]["condition"]
    job, = stages["Integration"]["jobs"]
    assert "$(" not in job["displayName"]
    assert "strategy" not in job
    assert job["templateContext"]["outputs"][0]["artifact"] == "release-integration-$(System.JobAttempt)"
    assert "cohort" not in json.dumps(job).lower()
    assert stages["Unit"]["dependsOn"] == "Resolve"
    assert stages["Integration"]["dependsOn"] == ["Resolve", "Build", "Security", "CommandLint", "IndexCompatibility"]
    assert "dependencies.Unit" not in stages["Integration"]["condition"]
    assert stages["Publish"]["dependsOn"] == [
        "Resolve", "Build", "Unit", "Security", "CommandLint", "IndexCompatibility",
        {"${{ if not(parameters.skipIntegrationTests) }}": ["Integration"]},
    ]
    assert list(template["stages"][-3]) == ["${{ if not(parameters.skipIntegrationTests) }}"]
    assert list(template["stages"][-2]) == [
        "${{ if and(eq(parameters.mode, 'Validate'), parameters.uploadWheelToBlob) }}"
    ]
    assert list(template["stages"][-1]) == ["${{ if in(parameters.mode, 'Draft', 'Release') }}"]
    assert "or(${{ parameters.skipIntegrationTests }}, eq(dependencies.Integration.result, 'Succeeded'))" in (
        stages["Publish"]["condition"]
    )
    access = next(step for step in stages["Resolve"]["jobs"][0]["steps"]
                  if "${{ if not(parameters.skipIntegrationTests) }}" in step)
    assert " release_pipeline.py access" in json.dumps(access).replace("tools/", "")
    assert "ReleaseStorageServiceConnection" not in json.dumps(template)
    assert "Upload wheel only" not in json.dumps(template)
    assert "eq(dependencies.Unit.result, 'Succeeded')" in stages["Publish"]["condition"]
    job = stages["Publish"]["jobs"][0]
    assert job["templateContext"]["type"] == "releaseJob"
    assert job["templateContext"]["isProduction"] is True
    assert [step["checkout"] for step in job["steps"] if "checkout" in step] == ["none"]
    index = next(step for step in job["steps"] if "${{ if parameters.createIndexPr }}" in step)
    assert " index " in json.dumps(index)
    assert "ReleaseGitHubToken" not in json.dumps(template["stages"][:-1])
    assert "aziotops_release_publish" not in json.dumps(template["stages"][:-1])
    assert stages["Publish"]["variables"][0] == {"group": "aziotops_release_publish"}
    assert "Plan" not in json.dumps(root) + json.dumps(template)
    template_mode = next(item for item in template["parameters"] if item["name"] == "mode")
    assert template_mode["default"] == "Validate"
    assert template_mode["values"] == parameters["mode"]["values"]
    assert stages["Upload"]["dependsOn"] == stages["Publish"]["dependsOn"]
    assert "eq(variables['Build.SourceBranch'], 'refs/heads/dev')" in stages["Upload"]["condition"]
    assert "eq(variables['Build.Repository.Name'], 'Azure/azure-iot-ops-cli-extension')" in (
        stages["Upload"]["condition"]
    )
    assert "or(${{ parameters.skipIntegrationTests }}, eq(dependencies.Integration.result, 'Succeeded'))" in (
        stages["Upload"]["condition"]
    )
    upload = stages["Upload"]["jobs"][0]
    assert upload["templateContext"] == job["templateContext"]
    assert [step["checkout"] for step in upload["steps"] if "checkout" in step] == ["none"]
    assert "ManualValidation" not in json.dumps(upload)
    upload_steps = yaml.safe_load((ROOT / ".azure-devops/templates/release-upload.yml").read_text())["steps"]
    assert upload["steps"][-1] == {
        "template": "release-upload.yml", "parameters": {
            "mode": "${{ parameters.mode }}", "sourceBranch": "${{ parameters.sourceBranch }}",
            "uploadWheelToBlob": "${{ parameters.uploadWheelToBlob }}",
        },
    }
    upload_index = next(i for i, step in enumerate(job["steps"]) if "${{ if parameters.uploadWheelToBlob }}" in step)
    assert job["steps"][upload_index]["${{ if parameters.uploadWheelToBlob }}"] == [upload["steps"][-1]]
    assert job["steps"][upload_index + 1]["displayName"] == "Stage draft or publish release"
    assert job["steps"][upload_index + 1].get("condition", "succeeded()") == "succeeded()"
    storage = upload_steps[0]
    assert storage["inputs"]["azureSubscription"] == "sc-cli-release-storage"
    assert "release-tooling/release_pipeline.py" in storage["inputs"]["inlineScript"]
    assert '" upload ' in storage["inputs"]["inlineScript"]
    assert "RELEASE_GITHUB_TOKEN" not in storage["env"]
    assert storage["env"]["RELEASE_UPLOAD_WHEEL_TO_BLOB"] == "${{ parameters.uploadWheelToBlob }}"
    assert "blob-upload.json" in storage["inputs"]["inlineScript"]
    assert storage.get("condition", "succeeded()") == "succeeded()"
    assert not storage.get("continueOnError", False)
    for release_job in (upload, job):
        assert "outputs" not in release_job["templateContext"]
    for steps, filename in ((upload_steps, "blob-upload.json"), (job["steps"], "release.json")):
        receipt = next(step for step in steps if "task.uploadfile" in step.get("bash", ""))
        assert receipt["env"]["RELEASE_RECEIPT"] == "$(Agent.TempDirectory)/publication/" + filename
        assert 'if [ ! -s "$RELEASE_RECEIPT" ]' in receipt["bash"]
        assert "task.logissue type=error" in receipt["bash"] and "exit 1" in receipt["bash"]
        assert receipt.get("condition", "succeeded()") == "succeeded()"
    assert next(i for i, step in enumerate(job["steps"]) if "task.uploadfile" in step.get("bash", "")) < next(
        i for i, step in enumerate(job["steps"]) if "${{ if parameters.createIndexPr }}" in step
    )
    preparation = next(step for step in stages["Build"]["jobs"][0]["steps"]
                       if "${{ if and(eq(parameters.mode, 'Validate'), parameters.uploadWheelToBlob) }}" in step)
    assert "prepare-upload" in json.dumps(preparation)
    assert "pip install" not in json.dumps(preparation)
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
    stages = template["stages"][1]["${{ if in(parameters.mode, 'Validate', 'Draft', 'Release') }}"]
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
