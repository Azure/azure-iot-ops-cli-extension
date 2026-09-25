# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Offline coverage for channel matrix, pinned wheel isolation and live assertions."""

from copy import deepcopy
from email.message import Message
import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from types import SimpleNamespace
from urllib.request import HTTPHandler, HTTPSHandler, build_opener
from urllib.response import addinfourl
from zipfile import ZipFile

import pytest
import yaml
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.runtime_profiles import (
    RuntimeChannel, RuntimeIdentity, RuntimeProfileCatalog,
)
from azext_edge.tests import runtime_checks
from azext_edge.tests.edge.orchestration.test_runtime_profiles_unit import make_profile
from azext_edge.tests.edge.orchestration.test_runtime_unit import records as runtime_records


records = runtime_records
ROOT = Path(__file__).resolve().parents[3]


def load_tool(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matrix = load_tool("integration_matrix", ".github/actions/build-int-test-matrix/build_matrix.py")
runner = load_tool("integration_runner", "tools/integration_runner.py")


def baseline():
    return {
        "wheel_url": "https://example.invalid/azure_iot_ops-1.0.0-py3-none-any.whl",
        "sha256": "a" * 64, "version": "1.6.0-preview.2", "train": "preview", "create_args": "--yes",
    }


@pytest.mark.parametrize("use_preview", [False, True])
@pytest.mark.parametrize("description", [None, "", "custom description"])
@pytest.mark.parametrize("matches", [False, True])
def test_init_description_assertion_uses_selected_defaults(mocker, use_preview, description, matches):
    from dataclasses import replace
    from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
    from azext_edge.tests.edge.init.int import test_init_int as init_tests
    from azext_edge.tests.helpers import process_additional_args

    profiles = []
    for channel in RuntimeChannel:
        profile = get_runtime_catalog().get(channel)
        blueprint = profile.copy_instance_blueprint()
        blueprint.get_resource_by_key("aioInstance")["properties"]["description"] = f"{channel.value} default"
        profiles.append(replace(profile, instance_blueprint=blueprint))
    catalog = RuntimeProfileCatalog(profiles)
    mocker.patch.object(init_tests, "get_runtime_catalog", return_value=catalog)
    expected = description if description is not None else ("preview default" if use_preview else "stable default")
    actual = expected if matches else "incorrect description"
    command = mocker.patch.object(init_tests, "run", side_effect=[
        {"id": "/cluster"},
        {"value": [{"properties": {"extensionType": init_tests.EXTENSION_TYPE_OPS},
                    "identity": {"principalId": "principal"}}]},
        {"extendedLocation": {"name": "/locations/location"}, "properties": {
            "description": actual, "schemaRegistryRef": {"resourceId": "/registry"},
            "adrNamespaceRef": {"resourceId": "/namespace"},
        }},
        "location cert-manager",
    ])
    roles = mocker.patch.object(init_tests, "assert_role_assignment")
    arguments = process_additional_args("--use-preview --yes" if use_preview else "")
    if description is not None:
        arguments["description"] = description
    arguments.update(instance_name="instance", cluster_name="cluster", resource_group="rg",
                     schema_registry_id="/registry", adr_namespace_id="/namespace")
    if matches:
        init_tests.assert_aio_instance(**arguments)
        assert command.call_count == 4
        roles.assert_called_once()
    else:
        with pytest.raises(AssertionError, match="Unexpected instance description"):
            init_tests.assert_aio_instance(**arguments)
        roles.assert_not_called()


def test_workload_identity_jobs_serialize_through_cleanup():
    config = yaml.safe_load((ROOT / ".github/workflows/int_test.yml").read_text())
    assert "concurrency" not in config
    job = config["jobs"]["int-test"]
    assert "max-parallel" not in job["strategy"]
    assert job["concurrency"] == {
        "group": (
            "${{ matrix.scenario.tox_env == 'python-wlif-int' && "
            "format('iot-ops-wlif-{0}', inputs.resource-group || 'ops-cli-int-test-rg') || "
            "format('iot-ops-int-{0}-{1}-{2}', github.run_id, github.run_attempt, matrix.scenario.name) }}"
        ),
        "cancel-in-progress": False,
        "queue": "max",
    }
    steps = {step.get("name"): step for step in job["steps"]}
    names = list(steps)
    assert (
        names.index("Tox INIT Integration Tests")
        < names.index("${{ matrix.scenario.description }}")
        < names.index("Delete AIO resources")
        < names.index("Delete connected cluster and resources")
    )
    for name in ("Delete AIO resources", "Delete connected cluster and resources"):
        assert steps[name]["if"] == "${{ always() }}"


def test_default_matrix_covers_both_channels_without_invented_baselines():
    scenarios = yaml.safe_load((ROOT / ".github/test-scenarios.yml").read_text())["scenarios"]
    rows = matrix.expand_channels(matrix.process_scenarios(scenarios, ""))
    assert len(rows) == 2 * sum(not scenario.get("requires_baseline") for scenario in scenarios)
    assert len({row["name"] for row in rows}) == len(rows)
    for row in rows:
        assert "--use-preview" not in row["init_args"]
        assert ("--use-preview" in row["create_args"]) == (row["channel"] == "preview")
        assert row["baseline"] is None
        assert not row["requires_baseline"]
    runtime_rows = [row for row in rows if row["tox_env"] == "python-runtime-int"]
    assert len(runtime_rows) == 2
    assert all(not row["parallel"] for row in runtime_rows)


@pytest.mark.parametrize("channels", ["stable", "preview", "stable,preview", "preview,stable", "stable,stable"])
def test_matrix_channel_selection_preserves_scenario_inputs(channels):
    scenarios = matrix.process_scenarios([{
        "name": "trust", "init_args": "--user-trust", "create_args": "--feature opcua.mode=Disabled",
        "parallel": False, "env": [{"SETTING": "value"}],
    }], "trust")
    original = deepcopy(scenarios)
    rows = matrix.expand_channels(scenarios, channels, init_args="--no-progress", create_args="--description testing")
    assert scenarios == original
    assert len(rows) == len(set(channels.split(",")))
    for row in rows:
        assert row["init_args"] == "--user-trust --no-progress"
        assert "--feature opcua.mode=Disabled" in row["create_args"]
        assert "--description testing" in row["create_args"]
        assert not row["parallel"]
        assert row["env"] == [{"name": "SETTING", "value": "value"}]


@pytest.mark.parametrize("channels", ["", "ga", "canary", "stable,other"])
def test_unknown_channels_fail(channels):
    with pytest.raises(ValueError, match="runtime-channels"):
        matrix.expand_channels([], channels)


@pytest.mark.parametrize("arg", ["--use-preview", "--use-preview=false", "--ops-version 1.0.0", "--ops-train stable"])
@pytest.mark.parametrize("position", ["init_args", "create_args"])
def test_matrix_disallows_runtime_override_collisions(arg, position):
    scenarios = matrix.process_scenarios([{"name": "edge"}], "")
    with pytest.raises(ValueError, match="Runtime selection belongs"):
        matrix.expand_channels(scenarios, **{position: arg})
    scenarios[0][position] = arg
    with pytest.raises(ValueError, match="Runtime selection belongs"):
        matrix.expand_channels(scenarios)


def test_upgrade_path_requires_explicit_per_channel_baseline():
    scenarios = matrix.process_scenarios([{"name": "upgrade-path", "requires_baseline": True}], "upgrade-path")
    with pytest.raises(ValueError, match="explicit stable upgrade baseline"):
        matrix.expand_channels(scenarios)
    rows = matrix.expand_channels(scenarios, "preview", {"preview": baseline()})
    assert rows[0]["baseline"] == baseline()
    assert rows[0]["requires_baseline"]


@pytest.mark.parametrize("field,value", [
    ("wheel_url", "http://example.invalid/test.whl"),
    ("wheel_url", "https://user:password@example.invalid/test.whl"),
    ("wheel_url", "https://example.invalid/test.whl?token=redacted"),
    ("wheel_url", "https://example.invalid/source.tar.gz"),
    ("sha256", "not-a-hash"), ("train", "canary"), ("version", ""), ("create_args", []),
])
def test_invalid_baseline_artifacts_fail_before_jobs(field, value):
    definition = {**baseline(), field: value}
    with pytest.raises(ValueError):
        matrix.validate_baseline(definition)


def test_matrix_action_main_serializes_channels(monkeypatch, tmp_path):
    config = tmp_path / "scenarios.yml"
    config.write_text("scenarios:\n  - name: edge\n", encoding="utf-8")
    output = tmp_path / "output"
    for key, value in {
        "TEST_SCENARIO_FILE": str(config), "GITHUB_OUTPUT": str(output), "TEST_SCENARIOS": "edge",
        "RUNTIME_CHANNELS": "stable,preview", "UPGRADE_BASELINES": "{}",
        "RUNTIME_INIT_ARGS": "", "RUNTIME_CREATE_ARGS": "",
    }.items():
        monkeypatch.setenv(key, value)
    matrix.main()
    rows = json.loads(output.read_text().partition("=")[2])
    assert [row["name"] for row in rows] == ["edge-stable", "edge-preview"]


@pytest.fixture
def wheel(tmp_path):
    archive = tmp_path / "azure_iot_ops-1.0.0-py3-none-any.whl"
    target = tmp_path / "extensions" / "azure-iot-ops"
    with ZipFile(archive, "w") as content:
        content.writestr("azext_edge/__init__.py", "VERSION = 'test'\n")
        content.writestr("azext_edge/edge/runtime.py", "IDENTITY = 'candidate'\n")
        content.extractall(target)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return archive, digest, target


def test_wheel_and_installed_bytes_are_verified(wheel):
    archive, digest, target = wheel
    assert runner.verify_wheel(archive, digest) == archive
    runner.verify_installed(archive, target)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        runner.verify_wheel(archive, "0" * 64)
    (target / "azext_edge/edge/runtime.py").write_text("IDENTITY = 'source'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from wheel"):
        runner.verify_installed(archive, target)


def test_missing_installed_file_fails(wheel):
    archive, _, target = wheel
    (target / "azext_edge/edge/runtime.py").unlink()
    with pytest.raises(ValueError, match="file missing"):
        runner.verify_installed(archive, target)


UNSAFE_BASELINE_URLS = [
    "http://example.invalid/test.whl",
    "https:///test.whl",
    "https://user:password@example.invalid/test.whl",
    "https://user@example.invalid/test.whl",
    "https://:password@example.invalid/test.whl",
    "https://@example.invalid/test.whl",
    "https://example.invalid/test.whl?token=redacted",
    "https://example.invalid/test.whl#fragment",
]


@pytest.mark.parametrize("url", UNSAFE_BASELINE_URLS)
@pytest.mark.parametrize("stage", ["initial", "final"])
def test_baseline_rejects_unsafe_urls_before_copy_or_install(mocker, monkeypatch, tmp_path, url, stage):
    definition = baseline()
    if stage == "initial":
        definition["wheel_url"] = url
    mocker.patch.object(runner, "validate_baseline_identity")
    opener = mocker.patch.object(runner, "build_opener").return_value
    response = opener.open.return_value.__enter__.return_value
    response.url = url
    install = mocker.patch.object(runner, "install_wheel")
    monkeypatch.setenv("azext_edge_baseline_extension_dir", "unchanged")
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        runner.prepare_baseline(definition, "preview", tmp_path)
    if stage == "initial":
        opener.open.assert_not_called()
    response.read.assert_not_called()
    install.assert_not_called()
    assert not list(tmp_path.iterdir())
    assert os.environ["azext_edge_baseline_extension_dir"] == "unchanged"


@pytest.fixture
def baseline_http(mocker):
    """Exercise urllib's real redirect chain with an entirely in-memory transport."""
    def configure(locations, payload=b"", code=302):
        requests = []

        class Transport(HTTPSHandler, HTTPHandler):
            def https_open(self, req):
                index = len(requests)
                requests.append(req.full_url)
                headers = Message()
                status = 200
                body = payload
                if index < len(locations):
                    headers["Location"] = locations[index]
                    status, body = code, b""
                response = addinfourl(BytesIO(body), headers, req.full_url, status)
                response.msg = "Redirect" if status != 200 else "OK"
                return response

            http_open = https_open

        mocker.patch.object(runner, "build_opener", side_effect=lambda handler: build_opener(handler, Transport()))
        mocker.patch.object(runner, "validate_baseline_identity")
        return requests

    return configure


# Python 3.10 refuses 308 outright; exercise it on interpreters that follow it.
@pytest.mark.parametrize("code", [
    code for code in (301, 302, 303, 307, 308) if hasattr(runner.HTTPRedirectHandler, f"http_error_{code}")
])
@pytest.mark.parametrize("url", [value for value in UNSAFE_BASELINE_URLS if value != "https:///test.whl"])
def test_baseline_blocks_unsafe_redirect_before_request(baseline_http, mocker, tmp_path, url, code):
    safe_hop = "https://cdn.example.invalid/mirror.whl"
    requests = baseline_http([safe_hop, url], code=code)
    install = mocker.patch.object(runner, "install_wheel")
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        runner.prepare_baseline(baseline(), "preview", tmp_path)
    assert requests == [baseline()["wheel_url"], safe_hop]
    assert not list(tmp_path.iterdir())
    install.assert_not_called()


@pytest.mark.parametrize("locations", [[], ["/mirror.whl"], [
    "https://cdn.example.invalid/mirror.whl", "//other.example.invalid/wheel.whl",
]])
@pytest.mark.parametrize("valid_digest", [True, False])
def test_baseline_safe_download_verifies_digest_before_install(
        baseline_http, wheel, mocker, monkeypatch, tmp_path, locations, valid_digest):
    archive, digest, _ = wheel
    requests = baseline_http(locations, archive.read_bytes())
    definition = {**baseline(), "sha256": digest if valid_digest else "0" * 64}
    work = tmp_path / "download"
    work.mkdir()
    install = mocker.patch.object(runner, "install_wheel")
    monkeypatch.setenv("azext_edge_baseline_extension_dir", "unchanged")
    if valid_digest:
        target = runner.prepare_baseline(definition, "preview", work)
        assert target == work / "baseline-extensions/azure-iot-ops"
        install.assert_called_once_with(work / archive.name, target)
        assert os.environ["azext_edge_baseline_extension_dir"] == str(target.parent)
    else:
        with pytest.raises(ValueError, match="SHA256 mismatch"):
            runner.prepare_baseline(definition, "preview", work)
        install.assert_not_called()
        assert os.environ["azext_edge_baseline_extension_dir"] == "unchanged"
    assert len(requests) == len(locations) + 1
    assert (work / archive.name).read_bytes() == archive.read_bytes()


def test_verification_only_does_not_install_or_authenticate(wheel, mocker, monkeypatch):
    archive, digest, target = wheel
    monkeypatch.setenv("azext_edge_wheel", str(archive))
    monkeypatch.setenv("azext_edge_wheel_sha256", digest)
    execute = mocker.patch.object(runner.subprocess, "run", side_effect=AssertionError("unexpected execution"))
    assert runner.main(["--verify-installed", "--extension-dir", str(target)]) == 0
    execute.assert_not_called()


@pytest.mark.parametrize("target_exists", [False, True])
def test_runner_imports_newly_installed_candidate_in_fresh_process(wheel, tmp_path, target_exists):
    """Exercise real imports after install, including Tox's nonexistent startup PYTHONPATH."""
    archive, digest, _ = wheel
    target = tmp_path / "fresh extensions" / "azure-iot-ops"
    if target_exists:
        target.mkdir(parents=True)
    tests = tmp_path / "test-sources"
    tests.mkdir()
    (tests / "test_example_int.py").write_text("def test_example(): pass\n", encoding="utf-8")
    script = '''
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from zipfile import ZipFile

runner_path, target_path, tests_path, work_path = sys.argv[1:]
target = Path(target_path)
assert "azext_edge" not in sys.modules
assert importlib.util.find_spec("azext_edge") is None
assert str(target) in sys.path_importer_cache
if not target.exists():
    assert sys.path_importer_cache[str(target)] is None
spec = importlib.util.spec_from_file_location("isolated_runner", runner_path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
calls = []

def execute(command, check):
    assert check
    calls.append(command)
    if command[:4] == [sys.executable, "-m", "pip", "install"]:
        assert command[command.index("--target") + 1] == str(target)
        # Replace only the installer transport; run the real install/verification/import path.
        with ZipFile(command[-1]) as wheel:
            wheel.extractall(target)
    else:
        assert command == ["az", "version"]

def extension_info(command, text):
    assert text and command == ["az", "extension", "show", "--name", "azure-iot-ops", "-o", "json"]
    return json.dumps({"path": str(target)})

runner.subprocess = SimpleNamespace(run=execute, check_output=extension_info)
pytest = ModuleType("pytest")

def collect(arguments):
    package = sys.modules["azext_edge"]
    assert Path(package.__file__).resolve() == target / "azext_edge" / "__init__.py"
    assert package.VERSION == "test"
    assert str(target / "azext_edge/tests/test_example_int.py") in arguments
    assert os.environ["PYTHONPATH"] == str(target)
    assert os.environ["AZURE_EXTENSION_DIR"] == str(target.parent)
    assert Path.cwd() == Path(work_path)
    print("candidate-import-verified")
    return 17

pytest.main = collect
sys.modules["pytest"] = pytest
result = runner.main([
    "--extension-dir", str(target), "--tests", tests_path, "--work-dir", work_path,
    "--junit", str(Path(work_path) / "init.xml"),
    "--coverage-config", str(Path(work_path) / ".coveragerc"), "--scenario", "init_scenario_test",
])
assert result == 17
assert len(calls) == 2
'''
    environment = dict(os.environ, PYTHONPATH=str(target), azext_edge_wheel=str(archive),
                       azext_edge_wheel_sha256=digest, azext_edge_upgrade_baseline="null")
    result = subprocess.run(
        [runner.sys.executable, "-S", "-c", script, str(ROOT / "tools/integration_runner.py"),
         str(target), str(tests), str(tmp_path / "work")],
        cwd=tmp_path, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "candidate-import-verified" in result.stdout


def test_runner_isolates_cli_imports_tests_config_and_working_directory(wheel, mocker, monkeypatch, tmp_path):
    archive, digest, target = wheel
    tests = tmp_path / "test-sources"
    tests.mkdir()
    (tests / "test_example_int.py").write_text("def test_example(): pass\n", encoding="utf-8")
    (tests / "test_example_unit.py").write_text("raise AssertionError('not collected')\n", encoding="utf-8")
    monkeypatch.setenv("azext_edge_wheel", str(archive))
    monkeypatch.setenv("azext_edge_wheel_sha256", digest)
    monkeypatch.setenv("azext_edge_upgrade_baseline", "null")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    # Register cleanup before the runner mutates cwd/sys.path/environment.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.sys, "path", list(runner.sys.path))
    monkeypatch.setenv("AZURE_EXTENSION_DIR", "unused")
    monkeypatch.setenv("AZURE_EXTENSION_USE_DYNAMIC_INSTALL", "unused")
    install = mocker.patch.object(runner, "install_wheel")
    package_import = mocker.Mock(return_value=SimpleNamespace(
        __file__=str(target / "azext_edge" / "__init__.py"),
    ))
    # Keep the fake package import local; mock target resolution also uses importlib.
    mocker.patch.object(runner, "importlib", SimpleNamespace(
        import_module=package_import, invalidate_caches=importlib.invalidate_caches,
    ))
    assert importlib.import_module("pytest") is pytest
    mocker.patch.object(runner.subprocess, "run")
    mocker.patch.object(runner.subprocess, "check_output", return_value=json.dumps({"path": str(target)}))
    execute = mocker.patch("pytest.main", return_value=0)
    work = tmp_path / "isolated"
    assert runner.main([
        "--extension-dir", str(target), "--tests", str(tests), "--work-dir", str(work),
        "--junit", str(tmp_path / "junit/results.xml"), "--coverage-config", str(ROOT / ".coveragerc"),
        "--scenario", "edge", "--collect-only",
    ]) == 0
    install.assert_called_once_with(archive, target)
    package_import.assert_called_once_with("azext_edge")

    assert os.getcwd() == str(work)
    assert os.environ["PYTHONPATH"] == str(target)
    assert os.environ["AZURE_EXTENSION_DIR"] == str(target.parent)
    arguments = execute.call_args.args[0]
    assert arguments[arguments.index("-c") + 1] == str(work / "pytest.ini")
    assert str(target / "azext_edge/tests/test_example_int.py") in arguments
    assert not any(arg.endswith("_unit.py") for arg in arguments)
    assert "--collect-only" in arguments
    assert (work / "pytest.ini").read_text() == "[pytest]\njunit_family = xunit1\n"


@pytest.mark.parametrize("version,train,channel,allowed", [
    ("1.6.0-preview.2", "preview", "preview", True),
    ("1.5.6", "stable", "stable", True),
    ("1.5.7", "stable", "stable", False),
    ("1.5.8", "stable", "stable", False),
    ("1.6.0-preview.2", "integration", "preview", False),
    ("1.6.0-preview.2", "preview", "stable", False),
])
def test_baseline_must_be_known_older_and_same_channel(mocker, version, train, channel, allowed):
    catalog = RuntimeProfileCatalog([
        make_profile(RuntimeChannel.STABLE, "1.5.7"), make_profile(RuntimeChannel.PREVIEW, "1.6.0-preview.4"),
    ])
    mocker.patch("azext_edge.edge.providers.orchestration.runtime_catalog.get_runtime_catalog", return_value=catalog)
    definition = {**baseline(), "version": version, "train": train}
    if allowed:
        assert runner.validate_baseline_identity(definition, channel).version == version
    else:
        with pytest.raises((ValueError, ValidationError)):
            runner.validate_baseline_identity(definition, channel)


@pytest.mark.parametrize("channel", list(RuntimeChannel))
def test_live_assertions_use_actual_installed_identity(mocker, records, channel):
    version = "1.5.7" if channel == RuntimeChannel.STABLE else "1.6.0-preview.4"
    profile = make_profile(channel, version, train="integration")
    mocker.patch.object(runtime_checks, "get_runtime_catalog", return_value=RuntimeProfileCatalog([profile]))
    records["extensions"][0]["properties"].update(currentVersion=version, version=version, releaseTrain="integration")
    run = mocker.patch.object(runtime_checks, "run", side_effect=[
        records["instance"], records["custom_location"], records["cluster"], {"value": records["extensions"]},
    ])
    result = runtime_checks.assert_runtime("instance", "rg", channel)
    assert result.identity == RuntimeIdentity(channel, version, "integration")
    assert run.call_count == 4
    assert all("az rest --method get" in call.args[0] for call in run.call_args_list[1:])


@pytest.mark.parametrize("failure", ["wrong-channel", "missing-current-version", "pending", "requested-only"])
def test_live_identity_failures_are_hard_errors(mocker, records, failure):
    profile = make_profile(RuntimeChannel.STABLE, "1.5.7")
    mocker.patch.object(runtime_checks, "get_runtime_catalog", return_value=RuntimeProfileCatalog([profile]))
    props = records["extensions"][0]["properties"]
    if failure == "wrong-channel":
        props.update(currentVersion="1.6.0-preview.4", version="1.6.0-preview.4", releaseTrain="preview")
    elif failure == "missing-current-version":
        del props["currentVersion"]
    elif failure == "pending":
        props["provisioningState"] = "Updating"
    else:
        props["version"] = "1.5.8"
    mocker.patch.object(runtime_checks, "run", side_effect=[
        records["instance"], records["custom_location"], records["cluster"], {"value": records["extensions"]},
    ])
    with pytest.raises((ValidationError, AssertionError)):
        runtime_checks.assert_runtime("instance", "rg", "stable")


@pytest.mark.parametrize("workflow,input_name", [
    ("int_test.yml", "resource-group"),
    ("container_int_test.yml", "resource-group"),
    ("cluster_cleanup.yml", "resource_group"),
])
def test_workflows_default_to_existing_test_resource_group(workflow, input_name):
    source = (ROOT / ".github/workflows" / workflow).read_text()
    config = yaml.load(source, Loader=yaml.BaseLoader)
    for event in ("workflow_call", "workflow_dispatch"):
        input_config = config["on"][event]["inputs"][input_name]
        if event == "workflow_dispatch" or workflow != "cluster_cleanup.yml":
            assert input_config["default"] == "ops-cli-int-test-rg"
    if workflow != "container_int_test.yml":
        assert config["env"]["RESOURCE_GROUP"] == (
            "${{ inputs." + input_name + " || 'ops-cli-int-test-rg' }}"
        )
    assert "centralus" not in source.lower()


def test_workflow_builds_once_and_tox_never_installs_checkout():
    config = yaml.safe_load((ROOT / ".github/workflows/int_test.yml").read_text())
    jobs = config["jobs"]
    assert jobs["int-test"]["needs"] == ["setup", "build-matrix", "build-candidate"]
    assert jobs["build-candidate"]["needs"] == "build-matrix"
    assert jobs["unit-test"]["needs"] == "build-matrix"
    assert jobs["unit-test"]["name"] == "Run linter and unit tests"
    assert any(step.get("run") == "tox r --skip-pkg-install" for step in jobs["unit-test"]["steps"])
    builds = [
        step for job in jobs.values() for step in job.get("steps", []) if "python -m build" in step.get("run", "")
    ]
    assert len(builds) == 1
    assert "matrix.scenario.channel" in jobs["int-test"]["env"]["azext_edge_runtime_channel"]
    tox = (ROOT / "tox.ini").read_text().split("# integration tests", 1)[1].split("# code coverage", 1)[0]
    assert "pip install" not in tox
    assert "integration_runner.py" in tox
    assert "changedir = {envtmpdir}" in tox


def test_container_workflow_builds_once_for_both_channels_and_includes_runner():
    config = yaml.safe_load((ROOT / ".github/workflows/container_int_test.yml").read_text())
    jobs = config["jobs"]
    assert jobs["test"]["needs"] == "build-candidate"
    assert "needs.build-candidate.outputs.matrix" in jobs["test"]["strategy"]["matrix"]["scenario"]
    builds = [(job_name, step) for job_name, job in jobs.items() for step in job.get("steps", [])
              if "python -m build" in step.get("run", "")]
    assert len(builds) == 1 and builds[0][0] == "build-candidate"
    steps = {step.get("name"): step for step in jobs["test"]["steps"]}
    verify = steps["Verify and install the candidate for workflow CLI commands"]["run"]
    assert 'sha256sum --check SHA256SUMS' in verify
    assert '"$azext_edge_wheel_sha256"' in verify
    assert '--verify-installed' in verify
    assert jobs["test"]["env"]["azext_edge_wheel_sha256"] == "${{ needs.build-candidate.outputs.sha256 }}"
    assert jobs["test"]["env"]["azext_edge_runtime_channel"] == "${{ matrix.scenario.channel }}"
    for variable in ("CLUSTER_NAME", "INSTANCE_NAME"):
        assert "matrix.scenario.name" in jobs["test"]["env"][variable]
    scenarios = yaml.safe_load((ROOT / ".github/test-container-scenarios.yml").read_text())["scenarios"]
    rows = matrix.expand_channels(matrix.process_scenarios(scenarios, ""))
    assert [row["name"] for row in rows] == ["container-e2e-stable", "container-e2e-preview"]
    assert [row["create_args"] for row in rows] == ["", "--use-preview --yes"]
    assert all(row["tox_env"] == "python-e2e-int" and not row["init_args"] for row in rows)
    assert "--use-preview" not in steps["Run az iot ops init"]["run"]
    assert steps["Containerized tests"]["env"]["azext_edge_instance"] == "${{ env.INSTANCE_NAME }}"
    assert steps["Setup Cluster Resources"]["with"]["suffix"] == "${{ steps.resources.outputs.suffix }}"
    upload = steps["Upload container results and candidate fingerprint"]
    assert upload["if"] == "${{ always() }}" and upload["with"]["include-hidden-files"]
    assert "SHA256SUMS" in upload["with"]["path"]
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    assert "tools/" not in ignored
    assert "!tools/integration_runner.py" in ignored and "!.coveragerc" in ignored
    assert ".artifacts/" in ignored and "pytest.ini" in ignored and ".venv/" in ignored
    assert '"python-e2e-int"' in (ROOT / "Dockerfile").read_text()


def _find_workflow_bash(platform_name):
    if platform_name == "nt":
        # PATH's bash.exe may be the WSL launcher, not Git for Windows' shell.
        git = shutil.which("git")
        if git:
            for directory in Path(git).resolve().parents:
                for relative in ("usr/bin/bash.exe", "bin/bash.exe"):
                    candidate = directory / relative
                    if candidate.is_file():
                        return str(candidate)
        raise RuntimeError("Workflow shell tests require Git for Windows with Bash; WSL is not used.")
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("Workflow shell tests require Bash on PATH.")
    return bash


@pytest.fixture(scope="module")
def workflow_shell():
    bash = _find_workflow_bash(os.name)

    def run(script, cwd, env):
        environment = dict(env)
        # Make Git's POSIX utilities available without loading interactive profiles.
        bin_dir = Path(bash).parent
        environment["PATH"] = os.pathsep.join([
            str(bin_dir), str(bin_dir.parent / "usr/bin"), environment.get("PATH", ""),
        ])
        environment.pop("BASH_ENV", None)
        environment.pop("ENV", None)
        # stdin avoids Windows command-line quoting and CRLF script-file differences.
        # Binary input also prevents Python's Windows text pipes from restoring CRLF.
        result = subprocess.run(
            [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-s"],
            input=script.replace("\r\n", "\n").encode("utf-8"), cwd=cwd, env=environment,
            capture_output=True, check=False,
        )
        return subprocess.CompletedProcess(
            result.args, result.returncode, result.stdout.decode("utf-8"), result.stderr.decode("utf-8"),
        )

    def directory(path):
        result = run("pwd -P\n", path, os.environ)
        assert result.returncode == 0, result.stdout + result.stderr
        return PurePosixPath(result.stdout.strip())

    return SimpleNamespace(run=run, directory=directory)


@pytest.mark.parametrize("git_relative", ["cmd/git.exe", "mingw64/bin/git.exe"])
@pytest.mark.parametrize("bash_relative", ["usr/bin/bash.exe", "bin/bash.exe"])
def test_workflow_bash_selects_git_for_windows_not_wsl(mocker, tmp_path, git_relative, bash_relative):
    installation = tmp_path / "Program Files/Git"
    git = installation / git_relative
    bash = installation / bash_relative
    for executable in (git, bash):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.touch()
    which = mocker.patch.object(shutil, "which", side_effect=lambda name: {
        "git": str(git), "bash": "C:/Windows/System32/bash.exe",
    }.get(name))
    assert _find_workflow_bash("nt") == str(bash.resolve())
    which.assert_called_once_with("git")


@pytest.mark.parametrize("platform_name", ["nt", "posix"])
def test_workflow_bash_missing_dependency_fails_instead_of_skipping(mocker, platform_name):
    mocker.patch.object(shutil, "which", return_value=None)
    with pytest.raises(RuntimeError, match="require.*Bash"):
        _find_workflow_bash(platform_name)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_workflow_shell_handles_spaces_newlines_and_ignores_profiles(workflow_shell, tmp_path, newline):
    work = tmp_path / "working directory with spaces"
    work.mkdir()
    profile = work / "unexpected-profile.sh"
    profile.write_text("exit 99\n", encoding="utf-8")
    shell_dir = workflow_shell.directory(work)
    environment = dict(os.environ, BASH_ENV=str(profile), ENV=str(profile),
                       OUTPUT=str(shell_dir / "file with spaces"), VALUE="value with spaces")
    script = newline.join(['printf "%s" "$VALUE" > "$OUTPUT"', 'cat "$OUTPUT"', 'exit 17', ''])
    result = workflow_shell.run(script, work, environment)
    assert result.returncode == 17, result.stdout + result.stderr
    assert result.stdout == "value with spaces"
    assert (work / "file with spaces").read_text() == result.stdout


def test_workflow_shell_uses_binary_lf_input(workflow_shell, mocker, tmp_path):
    execute = mocker.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
        [], 17, b"output", b"diagnostic",
    ))
    result = workflow_shell.run("exit 17\r\n", tmp_path, os.environ)
    assert execute.call_args.kwargs["input"] == b"exit 17\n"
    assert not execute.call_args.kwargs.get("text")
    assert "encoding" not in execute.call_args.kwargs
    assert (result.returncode, result.stdout, result.stderr) == (17, "output", "diagnostic")


@pytest.mark.parametrize("channel", ["stable", "preview"])
@pytest.mark.parametrize("build_exit,run_exit", [(0, 0), (0, 17), (23, 0)])
def test_container_shell_passes_candidate_targets_and_preserves_failures(
        workflow_shell, tmp_path, channel, build_exit, run_exit):
    """Execute the actual workflow shell with a fake Docker; never build images or contact Azure."""
    config = yaml.safe_load((ROOT / ".github/workflows/container_int_test.yml").read_text())
    script = next(step["run"] for step in config["jobs"]["test"]["steps"]
                  if step.get("name") == "Containerized tests")
    home = tmp_path / "home"
    (home / ".azure").mkdir(parents=True)
    (home / ".kube").mkdir()
    (home / ".kube/config").touch()
    candidate = tmp_path / "candidate with spaces" / "candidate.whl"
    candidate.parent.mkdir()
    candidate.touch()
    arguments = tmp_path / "docker-args"
    shell_dir = workflow_shell.directory(tmp_path)
    shell_candidate = shell_dir / candidate.relative_to(tmp_path).as_posix()
    environment = dict(os.environ, HOME=str(shell_dir / "home"), DOCKER_ARGS=str(shell_dir / "docker-args"),
                       BUILD_EXIT=str(build_exit), RUN_EXIT=str(run_exit),
                       azext_edge_wheel=str(shell_candidate), azext_edge_wheel_sha256="a" * 64,
                       azext_edge_runtime_channel=channel, azext_edge_skip_init="true",
                       azext_edge_init_redeployment="false", azext_edge_rg="test-rg",
                       azext_edge_cluster="test-cluster", azext_edge_instance="test-instance")
    docker_stub = '''
docker() {
    printf '%s\\0' "$@" >> "$DOCKER_ARGS"
    if [[ "$1" == build ]]; then
        printf 'test-image\\n'
        return "$BUILD_EXIT"
    fi
    return "$RUN_EXIT"
}
'''
    result = workflow_shell.run(docker_stub + script, tmp_path, environment)
    assert result.returncode == (build_exit or run_exit), result.stdout + result.stderr
    args = arguments.read_bytes().decode().split("\0")
    if build_exit:
        assert "run" not in args
        return
    assert "run" in args and "test-image" in args
    assert f"{shell_candidate.parent}:/opt/aio-candidate:ro" in args
    assert f"{shell_dir / 'home/.azure'}:/root/.azure" in args
    assert f"{shell_dir / 'home/.kube/config'}:/root/.kube/config:ro" in args
    for value in (
        "azext_edge_wheel=/opt/aio-candidate/candidate.whl", f"azext_edge_wheel_sha256={'a' * 64}",
        f"azext_edge_runtime_channel={channel}", "azext_edge_instance=test-instance",
        "azext_edge_rg=test-rg", "azext_edge_cluster=test-cluster",
        "azext_edge_junit_path=/integration-results/e2e.xml",
        "azext_edge_coverage_file=/integration-results/.coverage",
    ):
        assert value in args
    assert f"{shell_dir / '.artifacts/container-results'}:/integration-results" in args


@pytest.mark.parametrize("channel", ["stable", "preview"])
def test_container_init_is_shared_and_create_uses_selected_channel(workflow_shell, tmp_path, channel):
    config = yaml.safe_load((ROOT / ".github/workflows/container_int_test.yml").read_text())
    steps = {step.get("name"): step for step in config["jobs"]["test"]["steps"]}
    scenarios = yaml.safe_load((ROOT / ".github/test-container-scenarios.yml").read_text())["scenarios"]
    row = matrix.expand_channels(matrix.process_scenarios(scenarios, ""), channel)[0]
    environment = dict(os.environ, CLUSTER_NAME="test-cluster", RESOURCE_GROUP="test-rg",
                       INSTANCE_NAME="test-instance", SCHEMA_REGISTRY_ID="/test/registry",
                       ADR_NAMESPACE_ID="/test/namespace", CREATE_ARGS=row["create_args"])
    # A shell function captures argv; no real az command can be invoked by these steps.
    stub = "az() { printf '%s\\0' \"$@\"; }\n"
    for step, verb in (("Run az iot ops init", "init"), ("Run az iot ops create", "create")):
        result = workflow_shell.run(stub + steps[step]["run"], tmp_path, environment)
        assert result.returncode == 0, result.stdout + result.stderr
        args = result.stdout.split("\0")
        assert args[:3] == ["iot", "ops", verb]
        assert ("--use-preview" in args) == (verb == "create" and channel == "preview")
        assert ("--yes" in args) == (verb == "create" and channel == "preview")


@pytest.mark.parametrize("missing", ["", "SCHEMA_REGISTRY_ID", "ADR_NAMESPACE_ID", "STORAGE_ID", "all"])
@pytest.mark.parametrize("failed", ["", "SCHEMA_REGISTRY_ID", "ADR_NAMESPACE_ID", "STORAGE_ID"])
def test_container_cleanup_pins_only_adr_and_preserves_failures(workflow_shell, tmp_path, missing, failed):
    config = yaml.safe_load((ROOT / ".github/workflows/container_int_test.yml").read_text())
    steps = {step.get("name"): step for step in config["jobs"]["test"]["steps"]}
    cleanup = steps["Delete schema registry, ADR namespace and storage"]
    provider_root = "/subscriptions/test/resourceGroups/test rg/providers"
    resources = {
        "SCHEMA_REGISTRY_ID": f"{provider_root}/Microsoft.DeviceRegistry/schemaRegistries/sr",
        "ADR_NAMESPACE_ID": f"{provider_root}/Microsoft.DeviceRegistry/namespaces/ns",
        "STORAGE_ID": f"{provider_root}/Microsoft.Storage/storageAccounts/storage",
    }
    resources = {name: "" if missing in (name, "all") else value for name, value in resources.items()}
    environment = dict(os.environ, **resources, FAILED_ID=resources.get(failed, ""))
    stub = '''
az() {
    printf '%s\\0' "$@"
    printf '\\n'
    if [[ "$4" == "$FAILED_ID" ]]; then return 17; fi
    return 0
}
'''
    result = workflow_shell.run(stub + cleanup["run"], tmp_path, environment)
    assert result.returncode == int(bool(resources.get(failed))), result.stdout + result.stderr
    calls = [line.removesuffix("\0").split("\0") for line in result.stdout.splitlines()]
    expected = []
    for name, resource_id in resources.items():
        if resource_id:
            api_args = [] if name == "STORAGE_ID" else ["--api-version", "2026-04-01"]
            expected.append(["resource", "delete", "--id", resource_id, *api_args, "--verbose", "--no-wait"])
    assert calls == expected
    assert cleanup["if"] == "${{ always() }}"
    upload = steps["Upload container results and candidate fingerprint"]
    assert upload["if"] == "${{ always() }}" and upload["with"]["include-hidden-files"]
    assert ".artifacts/container-results/" in upload["with"]["path"]
    assert ".artifacts/candidate/SHA256SUMS" in upload["with"]["path"]


def test_redeployment_reports_are_distinct_and_uploaded_after_all_stages():
    config = yaml.safe_load((ROOT / ".github/workflows/int_test.yml").read_text())
    steps = config["jobs"]["int-test"]["steps"]
    names = [step.get("name") for step in steps]
    init = steps[names.index("Tox INIT Integration Tests")]
    redeploy = steps[names.index("Redeploy cluster via tox")]
    assert init["env"]["azext_edge_junit_path"] == "${{ github.workspace }}/junit/init.xml"
    assert redeploy["env"]["azext_edge_junit_path"] == "${{ github.workspace }}/junit/redeploy.xml"
    for name in ("Upload coverage artifacts", "Upload channel-specific test results and candidate fingerprint"):
        assert names.index(name) > names.index("Delete connected cluster and resources")
        assert names.index(name) > names.index("Redeploy cluster via tox")
        assert steps[names.index(name)]["if"] == "${{ always() }}"
    upload = steps[names.index("Upload channel-specific test results and candidate fingerprint")]["with"]
    assert upload["include-hidden-files"] and "junit/" in upload["path"] and "SHA256SUMS" in upload["path"]
    tox = (ROOT / "tox.ini").read_text()
    assert "--junit {env:azext_edge_junit_path:{toxinidir}/junit/{envname}.xml}" in tox
    assert "COVERAGE_FILE={env:azext_edge_coverage_file:{toxinidir}/.coverage}" in tox


def test_runner_retains_init_report_when_redeployment_fails(wheel, mocker, monkeypatch, tmp_path):
    archive, digest, target = wheel
    tests = tmp_path / "test-sources"
    tests.mkdir()
    (tests / "test_example_int.py").write_text("def test_example(): pass\n", encoding="utf-8")
    for key, value in {"azext_edge_wheel": str(archive), "azext_edge_wheel_sha256": digest,
                       "azext_edge_upgrade_baseline": "null", "PYTHONPATH": "",
                       "AZURE_EXTENSION_DIR": "", "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "no"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.sys, "path", list(runner.sys.path))
    # Simulate installation clearing staged tests on each invocation, without pip/network.
    mocker.patch.object(runner, "install_wheel", side_effect=lambda *_: shutil.rmtree(
        target / "azext_edge/tests", ignore_errors=True,
    ))
    package_import = mocker.Mock(return_value=SimpleNamespace(
        __file__=str(target / "azext_edge/__init__.py"),
    ))
    # Keep the fake package import local; mock target resolution also uses importlib.
    mocker.patch.object(runner, "importlib", SimpleNamespace(
        import_module=package_import, invalidate_caches=importlib.invalidate_caches,
    ))
    assert importlib.import_module("pytest") is pytest
    mocker.patch.object(runner.subprocess, "run")
    mocker.patch.object(runner.subprocess, "check_output", return_value=json.dumps({"path": str(target)}))

    def emit_report(arguments):
        path = Path(next(arg.partition("=")[2] for arg in arguments if arg.startswith("--junitxml=")))
        failures = int(path.stem == "redeploy")
        path.write_text(f'<testsuite failures="{failures}"/>', encoding="utf-8")
        return failures

    mocker.patch("pytest.main", side_effect=emit_report)
    for phase, code in (("init", 0), ("redeploy", 1)):
        assert runner.main([
            "--extension-dir", str(target), "--tests", str(tests), "--work-dir", str(tmp_path / "work"),
            "--junit", str(tmp_path / "junit" / f"{phase}.xml"), "--coverage-config", str(ROOT / ".coveragerc"),
            "--scenario", "init_scenario_test",
        ]) == code
    assert package_import.call_args_list == [mocker.call("azext_edge"), mocker.call("azext_edge")]
    assert (tmp_path / "junit/init.xml").read_text() == '<testsuite failures="0"/>'
    assert (tmp_path / "junit/redeploy.xml").read_text() == '<testsuite failures="1"/>'
