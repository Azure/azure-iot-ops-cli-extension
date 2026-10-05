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
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import ZIP_DEFLATED, ZipFile


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


def install_wheel(wheel, target):
    target = Path(target).resolve()
    if target.name != "azure-iot-ops":
        raise ValueError("Isolated extension destination must end in azure-iot-ops.")
    if target.exists():
        shutil.rmtree(target)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--target", str(target), str(wheel)],
        check=True,
    )
    verify_installed(wheel, target)


def validate_baseline_identity(baseline, channel):
    from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
    from azext_edge.edge.providers.orchestration.runtime_profiles import (
        RuntimeChannel, parse_runtime_version, resolve_runtime_identity, validate_upgrade_boundary,
    )

    catalog = get_runtime_catalog()
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
    install_wheel(wheel, target)
    os.environ["azext_edge_baseline_extension_dir"] = str(target.parent)
    return target


def schema_resource_summary(resource):
    metadata = resource.get("metadata", {})
    status = resource.get("status", {})
    return {
        "kind": resource.get("kind"),
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "nameLabel": metadata.get("labels", {}).get("app.kubernetes.io/name"),
        "phase": status.get("phase"),
        "readyReplicas": status.get("readyReplicas"),
        "containers": [{"name": container.get("name"), "ready": container.get("ready")}
                       for container in status.get("containerStatuses", [])],
    }


def capture_schema_inventory(directory, phase):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    report = {"phase": phase, "resources": []}
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods,statefulsets,deployments,services,configmaps,pvc", "-A", "-o", "json",
             "--request-timeout=30s"], capture_output=True, text=True, timeout=45, check=False,
        )
        report["returncode"] = result.returncode
        if result.returncode == 0:
            report["resources"] = [schema_resource_summary(resource)
                                   for resource in json.loads(result.stdout).get("items", [])]
    except Exception as error:
        report["errorType"] = type(error).__name__
    (directory / f"inventory-{phase}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def capture_schema_bundle(directory):
    import yaml

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    report = {}
    try:
        with TemporaryDirectory(prefix="aio-schema-diagnostics-") as temporary:
            result = subprocess.run(
                ["az", "iot", "ops", "support", "create-bundle", "--ops-service", "schemaregistry",
                 "--bundle-dir", temporary, "--bundle-name", "schema-diagnostics", "--debug"],
                capture_output=True, text=True, timeout=180, check=False,
            )
            report["returncode"] = result.returncode
            report["failedCollectors"] = sorted(set(re.findall(
                r"Unable to process schemaregistry ([a-z]+):", result.stderr,
            )))
            report["errorTypes"] = sorted(set(re.findall(
                r"\b([A-Za-z]{1,40}Error|ApiException)\b", result.stderr,
            )))
            report["httpStatuses"] = sorted(set(re.findall(r"HTTP/[0-9.]+\" ([45][0-9]{2})\b", result.stderr)))
            report["schemaPodCounts"] = re.findall(
                r"Detected (\d+) pods with label '[^'\r\n]*"
                r"(?:aio-edge-registry|microsoft-iotoperations-schemas)[^'\r\n]*'",
                result.stderr,
            )
            bundle = Path(temporary) / "schema-diagnostics.zip"
            if bundle.exists():
                destination_path = directory / "schema-bundle-sanitized.zip"
                with ZipFile(bundle) as source, ZipFile(destination_path, "w", compression=ZIP_DEFLATED) as destination:
                    manifest = []
                    for entry in source.infolist():
                        parts = entry.filename.split("/")
                        if (len(parts) != 3 or parts[1] != "schemaregistry"
                                or any(part in ("", ".", "..") for part in parts)):
                            continue
                        manifest.append({"name": entry.filename, "size": entry.file_size})
                        if entry.filename.endswith(".yaml"):
                            resource = yaml.safe_load(source.read(entry))
                            if isinstance(resource, dict):
                                destination.writestr(
                                    entry.filename, json.dumps(schema_resource_summary(resource), indent=2),
                                )
                    destination.writestr("manifest.json", json.dumps(manifest, indent=2))
                    report["schemaFiles"] = len(manifest)
    except Exception as error:
        report["errorType"] = type(error).__name__
    (directory / "collection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def run_with_schema_diagnostics(execute, directory):
    def capture(operation, *arguments):
        try:
            operation(directory, *arguments)
        except Exception as error:
            print(f"Schema diagnostics unavailable: {type(error).__name__}", flush=True)

    capture(capture_schema_inventory, "before")
    result = None
    try:
        result = execute()
        return result
    finally:
        capture(capture_schema_inventory, "after")
        if result != 0:
            capture(capture_schema_bundle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension-dir", required=True)
    parser.add_argument("--verify-installed", action="store_true")
    parser.add_argument("--tests")
    parser.add_argument("--work-dir")
    parser.add_argument("--junit")
    parser.add_argument("--coverage-config")
    parser.add_argument("--scenario")
    args, pytest_args = parser.parse_known_args(argv)
    wheel = verify_wheel(os.environ.get("azext_edge_wheel", ""), os.environ.get("azext_edge_wheel_sha256", ""))
    target = Path(args.extension_dir).resolve()
    if args.verify_installed:
        verify_installed(wheel, target)
        return 0
    if not all((args.tests, args.work_dir, args.junit, args.coverage_config, args.scenario)):
        parser.error("Test execution requires --tests, --work-dir, --junit, --coverage-config and --scenario.")
    tests = Path(args.tests).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    install_wheel(wheel, target)
    shutil.copytree(tests, target / "azext_edge" / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
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

    integration_files = sorted(str(path) for path in (target / "azext_edge" / "tests").rglob("*_int.py"))
    if not integration_files:
        raise ValueError("No integration test files were staged.")
    arguments = [
        "-c", str(pytest_config), "--rootdir", str(work_dir),
        "--randomly-dont-reorganize", "-vv", "-k", "_int.py", "-m", args.scenario.strip('"'),
        "--import-mode=importlib", *integration_files,
        f"--cov={target / 'azext_edge' / 'edge'}", f"--cov-config={args.coverage_config}", "--cov-append",
        "--cov-report=term:skip-covered", "--durations=0", f"--junitxml={args.junit}", *pytest_args,
    ]
    if args.scenario.strip('"') == "edge" and not {"--collect-only", "--co"}.intersection(pytest_args):
        result = run_with_schema_diagnostics(
            lambda: pytest.main(arguments), Path(args.junit).parent / "schema-diagnostics",
        )
    else:
        result = pytest.main(arguments)
    verify_installed(wheel, target)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
