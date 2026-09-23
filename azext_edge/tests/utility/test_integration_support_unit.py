# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Offline coverage for channel matrix, pinned wheel isolation and live assertions."""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
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


def test_live_data_scenario_uses_both_channels_serially():
    scenarios = yaml.safe_load((ROOT / ".github/test-scenarios.yml").read_text())["scenarios"]
    rows = matrix.expand_channels(matrix.process_scenarios(scenarios, "livedata"))
    assert [row["name"] for row in rows] == ["livedata-stable", "livedata-preview"]
    assert all(row["tox_env"] == "python-livedata-int" and not row["parallel"] for row in rows)
    assert [row["create_args"] for row in rows] == ["", "--use-preview --yes"]
    assert all(not row["init_args"] and row["baseline"] is None for row in rows)


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


def test_verification_only_does_not_install_or_authenticate(wheel, mocker, monkeypatch):
    archive, digest, target = wheel
    monkeypatch.setenv("azext_edge_wheel", str(archive))
    monkeypatch.setenv("azext_edge_wheel_sha256", digest)
    execute = mocker.patch.object(runner.subprocess, "run", side_effect=AssertionError("unexpected execution"))
    assert runner.main(["--verify-installed", "--extension-dir", str(target)]) == 0
    execute.assert_not_called()


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
    mocker.patch.object(runner, "importlib", SimpleNamespace(import_module=package_import))
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


def test_workflow_builds_once_and_tox_never_installs_checkout():
    config = yaml.safe_load((ROOT / ".github/workflows/int_test.yml").read_text())
    jobs = config["jobs"]
    assert "build-candidate" in jobs["int-test"]["needs"]
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


@pytest.mark.parametrize("channel", ["stable", "preview"])
@pytest.mark.parametrize("build_exit,run_exit", [(0, 0), (0, 17), (23, 0)])
def test_container_shell_passes_candidate_targets_and_preserves_failures(tmp_path, channel, build_exit, run_exit):
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
    environment = dict(os.environ, HOME=str(home), DOCKER_ARGS=str(arguments), BUILD_EXIT=str(build_exit),
                       RUN_EXIT=str(run_exit), azext_edge_wheel=str(candidate), azext_edge_wheel_sha256="a" * 64,
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
    result = subprocess.run(["bash", "-c", docker_stub + script], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, check=False)
    assert result.returncode == (build_exit or run_exit), result.stderr
    args = arguments.read_bytes().decode().split("\0")
    if build_exit:
        assert "run" not in args
        return
    assert "run" in args and "test-image" in args
    assert f"{candidate.parent}:/opt/aio-candidate:ro" in args
    for value in (
        "azext_edge_wheel=/opt/aio-candidate/candidate.whl", f"azext_edge_wheel_sha256={'a' * 64}",
        f"azext_edge_runtime_channel={channel}", "azext_edge_instance=test-instance",
        "azext_edge_rg=test-rg", "azext_edge_cluster=test-cluster",
        "azext_edge_junit_path=/integration-results/e2e.xml",
        "azext_edge_coverage_file=/integration-results/.coverage",
    ):
        assert value in args
    assert f"{tmp_path / '.artifacts/container-results'}:/integration-results" in args


@pytest.mark.parametrize("channel", ["stable", "preview"])
def test_container_init_is_shared_and_create_uses_selected_channel(tmp_path, channel):
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
        result = subprocess.run(["bash", "-e", "-c", stub + steps[step]["run"]], cwd=tmp_path,
                                env=environment, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        args = result.stdout.split("\0")
        assert args[:3] == ["iot", "ops", verb]
        assert ("--use-preview" in args) == (verb == "create" and channel == "preview")
        assert ("--yes" in args) == (verb == "create" and channel == "preview")


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
    mocker.patch.object(runner, "importlib", SimpleNamespace(import_module=package_import))
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
