# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Run integration tests against a hash-verified wheel, never the checkout package.

Only test sources are staged into the installed package (tests are excluded from the
wheel). Both pytest imports and its az subprocesses use this isolated extension root.
The baseline wheel, when supplied, is used exclusively to provision an older runtime.
"""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import ZipFile


def verify_wheel(path, digest):
    path = Path(path).resolve()
    if not path.is_file() or path.suffix != ".whl" or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        raise ValueError("Supply azext_edge_wheel and its azext_edge_wheel_sha256 SHA256 digest.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest.lower():
        raise ValueError(f"Wheel SHA256 mismatch: {path.name}")
    return path


def verify_installed(wheel, target):
    """Check package bytes as well as the artifact hash; a version string is not proof."""
    target = Path(target).resolve()
    with ZipFile(wheel) as archive:
        entries = [name for name in archive.namelist() if name.startswith("azext_edge/") and not name.endswith("/")]
        if "azext_edge/__init__.py" not in entries:
            raise ValueError("Candidate is not an IoT Operations extension wheel.")
        for name in entries:
            destination = (target / name).resolve()
            if not destination.is_relative_to(target) or not destination.is_file():
                raise ValueError(f"Installed candidate file missing: {name}")
            if destination.read_bytes() != archive.read(name):
                raise ValueError(f"Installed candidate differs from wheel: {name}")


def install_wheel(wheel, target, environment_name="extension"):
    target = Path(target).resolve()
    if target.name != "azure-iot-ops":
        raise ValueError("Isolated extension destination must end in azure-iot-ops.")
    if target.exists():
        shutil.rmtree(target)
    environment = dict(os.environ)
    if environment.get("OPS_DEPENDENCY_LOCK"):
        environment["PIP_CONSTRAINT"] = str(
            Path(environment["OPS_DEPENDENCY_LOCK"]) / f"{environment_name}.txt"
        )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--target", str(target), str(wheel)],
        check=True, env=environment,
    )
    verify_installed(wheel, target)


def validate_baseline_identity(baseline, channel):
    from azure.cli.core import get_default_cli
    from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
    from azext_edge.edge.providers.orchestration.runtime_profiles import (
        RuntimeChannel, parse_runtime_version, resolve_runtime_identity, validate_upgrade_boundary,
    )

    catalog = get_runtime_catalog(os.environ.get("azext_edge_cloud") or get_default_cli().cloud.name)
    target = catalog.get(RuntimeChannel(channel)).identity
    source = resolve_runtime_identity(baseline["version"], baseline["train"], catalog.qualification_identities)
    if source.channel != target.channel:
        raise ValueError("Baseline runtime channel does not match this integration job.")
    validate_upgrade_boundary(source, target)
    if parse_runtime_version(source.version) >= parse_runtime_version(target.version):
        raise ValueError("An upgrade-path baseline must be older than the bundled target, not a same-version repair.")
    return source


def validate_baseline_url(value):
    """Apply the same credential-free HTTPS policy to initial URLs and every redirect."""
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.password is not None or url.query or url.fragment):
        raise ValueError("Baseline wheel must use credential-free HTTPS.")
    return url


class BaselineRedirectHandler(HTTPRedirectHandler):
    """Reject unsafe redirect targets before urllib sends the redirected request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_baseline_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def prepare_baseline(baseline, channel, work_dir):
    # This validates reviewed runtime mappings BEFORE downloading or provisioning.
    validate_baseline_identity(baseline, channel)
    url = validate_baseline_url(baseline["wheel_url"])
    wheel = Path(work_dir) / Path(url.path).name
    opener = build_opener(BaselineRedirectHandler())
    with opener.open(baseline["wheel_url"], timeout=60) as response:
        validate_baseline_url(response.url)
        with wheel.open("wb") as output:
            shutil.copyfileobj(response, output)
    verify_wheel(wheel, baseline["sha256"])
    target = Path(work_dir) / "baseline-extensions" / "azure-iot-ops"
    install_wheel(wheel, target, "baseline")
    os.environ["azext_edge_baseline_extension_dir"] = str(target.parent)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension-dir", required=True)
    parser.add_argument("--verify-installed", action="store_true")
    parser.add_argument("--tests")
    parser.add_argument("--work-dir")
    parser.add_argument("--junit")
    parser.add_argument("--coverage-config")
    parser.add_argument("--scenario")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--test-files", help="Comma-separated test file names, run in this order.")
    args, pytest_args = parser.parse_known_args(argv)
    wheel = verify_wheel(os.environ.get("azext_edge_wheel", ""), os.environ.get("azext_edge_wheel_sha256", ""))
    target = Path(args.extension_dir).resolve()
    if args.verify_installed:
        verify_installed(wheel, target)
        return 0
    if not all((args.tests, args.work_dir, args.junit, args.coverage_config, args.scenario)):
        parser.error("Test execution requires --tests, --work-dir, --junit, --coverage-config and --scenario.")
    from azure.cli.core import get_default_cli
    cloud = get_default_cli().cloud.name
    if cloud not in {"AzureCloud", "AzureUSGovernment"}:
        raise ValueError("Ops integration tests require public Azure or Fairfax.")
    if os.environ.get("azext_edge_cloud", cloud) != cloud:
        raise ValueError("Active Azure CLI cloud differs from the integration target.")
    if cloud == "AzureUSGovernment" and os.environ.get("azext_edge_runtime_channel", "stable") != "stable":
        raise ValueError("Fairfax integration tests require stable runtime.")
    tests = Path(args.tests).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    install_wheel(wheel, target)
    if os.environ.get("OPS_DEPENDENCY_LOCK"):
        from integration_dependencies import verify_target
        verify_target("extension", target, wheel)
    shutil.copytree(tests, target / "azext_edge" / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if os.environ.get("AZEXT_TEST_OWNERSHIP"):
        for name in ("owned_resources", "owned_resources_pytest"):
            shutil.copyfile(Path(__file__).with_name(name + ".py"), target / f"azext_edge/tests/_{name}.py")
        pytest_args += ["-p", "azext_edge.tests._owned_resources_pytest"]
    if args.monitor:
        from release_monitor import verify_bundle
        from release_test_compatibility import stage_tests

        manifest = verify_bundle(tests.parents[2])
        if manifest["cloud"] != cloud:
            raise ValueError("Released test compatibility targets a different cloud.")
        stage_tests(target, manifest, work_dir / "test-compatibility.json")
        os.environ["AZEXT_OPS_RELEASE_TEST_SOURCE"] = manifest["testSourceCommit"]
        shutil.copyfile(
            Path(__file__).with_name("release_monitor_pytest.py"),
            target / "azext_edge/tests/_release_monitor.py",
        )
        pytest_args += ["-p", "azext_edge.tests._release_monitor"]
    # The script path is tools/, not the checkout root; cwd and PYTHONPATH cannot
    # point at the source package when pytest imports or az subprocesses start.
    os.chdir(work_dir)
    sys.path.insert(0, str(target))
    os.environ["PYTHONPATH"] = str(target)
    os.environ["AZURE_EXTENSION_DIR"] = str(target.parent)
    os.environ["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"
    # Tox puts target on PYTHONPATH before installation creates it. Python may
    # cache that missing directory; refresh finders before importing the new wheel.
    importlib.invalidate_caches()
    package = importlib.import_module("azext_edge")
    if Path(package.__file__).resolve() != target / "azext_edge" / "__init__.py":
        raise ValueError("Source checkout is shadowing the candidate wheel.")
    baseline = json.loads(os.environ.get("azext_edge_upgrade_baseline", "null"))
    if baseline:
        validate_baseline_identity(baseline, os.environ["azext_edge_runtime_channel"])
        if args.scenario.strip('"') == "init_scenario_test":
            if os.environ.get("OPS_DEPENDENCY_LOCK"):
                baseline_target = Path(os.environ["OPS_BASELINE_EXTENSION"])
                baseline_wheel = verify_wheel(
                    baseline_target.parents[1] / Path(validate_baseline_url(baseline["wheel_url"]).path).name,
                    baseline["sha256"],
                )
                verify_installed(baseline_wheel, baseline_target)
                verify_target("baseline", baseline_target, wheel)
                os.environ["azext_edge_baseline_extension_dir"] = str(baseline_target.parent)
            else:
                prepare_baseline(baseline, os.environ["azext_edge_runtime_channel"], work_dir)
    subprocess.run(["az", "version"], check=True)
    extension = subprocess.check_output(["az", "extension", "show", "--name", "azure-iot-ops", "-o", "json"], text=True)
    if Path(json.loads(extension)["path"]).resolve() != target:
        raise ValueError("az is not using the candidate extension directory.")
    Path(args.junit).parent.mkdir(parents=True, exist_ok=True)
    print(f"Candidate wheel: {wheel.name} SHA256={os.environ['azext_edge_wheel_sha256']}", flush=True)
    # A parent checkout pytest.ini may contain a developer's live cluster env values.
    # Never let automatic root/config discovery override the job's target resources.
    pytest_config = work_dir / "pytest.ini"
    pytest_config.write_text("[pytest]\njunit_family = xunit1\n", encoding="utf-8")
    import pytest

    staged = sorted((target / "azext_edge" / "tests").rglob("*_int.py"))
    integration_files = [str(path) for path in staged]
    if args.test_files:
        by_name = {}
        for path in staged:
            by_name.setdefault(path.name, []).append(str(path))
        names = args.test_files.split(",")
        if len(names) != len(set(names)) or any(len(by_name.get(name, [])) != 1 for name in names):
            raise ValueError("Each selected test file must match exactly one staged integration file.")
        integration_files = [by_name[name][0] for name in names]
    if not integration_files:
        raise ValueError("No integration test files were staged.")
    result = pytest.main([
        "-c", str(pytest_config), "--rootdir", str(work_dir),
        "--randomly-dont-reorganize", "-vv", "-k", "_int.py", "-m", args.scenario.strip('"'),
        "--import-mode=importlib", *integration_files,
        f"--cov={target / 'azext_edge' / 'edge'}", f"--cov-config={args.coverage_config}", "--cov-append",
        "--cov-report=term:skip-covered", "--durations=0", f"--junitxml={args.junit}", *pytest_args,
    ])
    verify_installed(wheel, target)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
