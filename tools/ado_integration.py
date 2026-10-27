# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Plan and qualify ADO ops integration runs without accessing Azure."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
from uuid import UUID, uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

import yaml

import release_pipeline as release


ROOT = Path(__file__).resolve().parents[1]
PYTHONS = {"3.10", "3.11", "3.12", "3.13"}


def required(name):
    value = os.environ.get(name, "").strip()
    if not value or "$(" in value or "\n" in value or "\r" in value:
        raise ValueError(f"Configure {name} explicitly.")
    return value


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def producer():
    value = {key: required(name) for key, name in (
        ("pipeline", "SYSTEM_DEFINITIONID"), ("build", "BUILD_BUILDID"), ("commit", "BUILD_SOURCEVERSION"),
    )}
    if not all(re.fullmatch(r"[1-9][0-9]*", value[key]) for key in ("pipeline", "build")):
        raise ValueError("Producer IDs must be positive integers.")
    if not re.fullmatch(r"[0-9a-f]{40}", value["commit"]):
        raise ValueError("An immutable source commit is required.")
    return value


def output_variable(name, value):
    escaped = str(value).replace("%", "%AZP25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"##vso[task.setvariable variable={name};isOutput=true]{escaped}", flush=True)


def scenario_timeout():
    value = required("OPS_SCENARIO_TIMEOUT_MINUTES")
    if value not in {"90", "180", "360"}:
        raise ValueError("Scenario timeout must be 90, 180 or 360 minutes.")
    return int(value)


def release_build_id():
    value = os.environ.get("OPS_RELEASE_BUILD_ID", "0")
    if value != "0":
        release.identifier(value)
        if producer()["pipeline"] != "164" or os.environ.get("OPS_HEALTH_HISTORY"):
            raise ValueError("Only manual pipeline 164 can consume a release candidate, never Health.")
    return value


def plan(output):
    parent = release_build_id()
    if parent != "0" and required("OPS_MODE") != "Integration tests":
        raise ValueError("A release candidate requires live integration, not a dry run.")
    health = None
    if os.environ.get("OPS_HEALTH_HISTORY"):
        from integration_health import resolve
        health = resolve(required("OPS_HEALTH_HISTORY"))
    matrix_tools = runpy.run_path(str(ROOT / ".github/actions/build-int-test-matrix/build_matrix.py"))
    config = yaml.safe_load((ROOT / ".github/test-scenarios.yml").read_text(encoding="utf-8"))["scenarios"]
    selection = required("OPS_SCENARIOS").split(",")
    if "Default scenarios" in selection and selection != ["Default scenarios"]:
        raise ValueError("Select Default scenarios alone, or select individual scenarios.")
    if selection != ["Default scenarios"] and set(selection) - {item["name"] for item in config}:
        raise ValueError("Unknown ops scenario selection.")
    if len(selection) != len(set(selection)):
        raise ValueError("Duplicate scenario selection.")
    versions = required("OPS_PYTHONS").split(",")
    if set(versions) - PYTHONS or len(versions) != len(set(versions)):
        raise ValueError("Select distinct supported Python versions.")
    group = required("OPS_RESOURCE_GROUP")
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", group) or group.endswith("."):
        raise ValueError("Invalid resource group name.")
    scenarios = matrix_tools["process_scenarios"](
        config, "" if selection == ["Default scenarios"] else ",".join(selection),
    )
    baselines = json.loads(required("OPS_BASELINES"))
    if not isinstance(baselines, dict):
        raise ValueError("Upgrade baselines must be a JSON object.")
    scenarios = matrix_tools["expand_channels"](
        scenarios, required("OPS_CHANNELS"), baselines,
    )
    rows = []
    for scenario in scenarios:
        for version in versions:
            rows.append({
                "key": f"{scenario['name'].replace('-', '_')}_py{version.replace('.', '')}",
                "python": version, "scenario": scenario,
            })
    if not rows:
        raise ValueError("The integration matrix is empty.")
    if health and len(rows) > 40:
        raise ValueError("Select at most 40 combinations per run.")
    value = {
        "schema": 1, "producer": producer(), "rows": rows,
        "subscription": str(UUID(required("OPS_SUBSCRIPTION"))), "resourceGroup": group,
        "customLocationsObjectId": str(UUID(required("OPS_CUSTOM_LOCATIONS_OID"))),
        "scenarioTimeoutMinutes": scenario_timeout(),
        "qualification": "selected scenarios only; not release qualification",
    }
    if health:
        value["health"] = health
        value["locations"] = {key: health["profile"][key] for key in
                              ("clusterRegion", "resourceRegion", "namespaceRegion")}
    if parent != "0":
        value["releaseBuildId"] = parent
    write(output / "plan.json", value)
    print(json.dumps(value, indent=2))
    output_variable("matrix", json.dumps({
        row["key"]: {"row": row["key"], "python": row["python"], "scenarioTimeoutMinutes": scenario_timeout()}
        for row in rows
    }))
    output_variable("artifact", f"ops-plan-{required('SYSTEM_JOBATTEMPT')}")


def candidate(output):
    if release_build_id() != "0":
        raise ValueError("A release candidate must be acquired from 165, never rebuilt.")
    wheels = list(output.glob("*.whl"))
    if len(wheels) != 1 or not re.fullmatch(r"azure_iot_ops-[A-Za-z0-9_.+!-]+\.whl", wheels[0].name):
        raise ValueError("Build must produce exactly one azure-iot-ops wheel.")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual != producer()["commit"]:
        raise ValueError("Checkout does not match the producer commit.")
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT, check=True)
    value = {
        "schema": 1, "producer": producer(),
        "wheel": {"file": wheels[0].name, "sha256": digest(wheels[0])},
    }
    write(output / "candidate.json", value)
    output_variable("digest", value["wheel"]["sha256"])
    output_variable("artifact", f"ops-wheel-{required('SYSTEM_JOBATTEMPT')}")


def acquire(output):
    parent_id = release_build_id()
    if parent_id == "0":
        raise ValueError("A trusted release producer is required.")
    source = Path(required("OPS_RELEASE_INPUT"))
    parent = release.ado(f"build/builds/{parent_id}")
    parameters = parent.get("templateParameters", {})
    if isinstance(parameters, str):
        parameters = json.loads(parameters)
    if (parent["definition"]["id"] != 165 or parent["repository"]["id"] != release.REPOSITORY
            or parent["repository"]["type"] != "GitHub"
            or parent["project"]["id"].lower() != required("SYSTEM_TEAMPROJECTID").lower()
            or parameters.get("mode") not in {"Validate", "Release"}
            or release.branch(parameters["sourceBranch"]) != required("BUILD_SOURCEBRANCH")
            or parent.get("result") not in (None, "succeeded")):
        raise ValueError("Untrusted, failed, or nonqualifying release producer.")
    value = release.verify_candidate(
        source, expected_producer={"definition": "165", "build": parent_id,
                                   "commit": release.commit(parent["sourceVersion"])},
        source_branch=required("BUILD_SOURCEBRANCH"), source_commit=producer()["commit"],
    )
    if value["cohorts"] != release.source_cohorts(ROOT):
        raise ValueError("Release cohort inventory differs from the pinned integration source.")
    child = release.ado(f"build/builds/{producer()['build']}")
    matches = []
    for key in value["cohorts"]:
        try:
            release.validate_integration(child, value, key)
            matches.append(key)
        except ValueError:
            continue
    if len(matches) != 1:
        raise ValueError("Child parameters do not identify exactly one declared release cohort.")
    output.mkdir(parents=True, exist_ok=False)
    for name in ("candidate.json", "SBOM.zip", value["wheel"]["file"]):
        shutil.copyfile(source / name, output / name)
    write(output / "handoff.json", {
        "consumer": producer(), "cohort": matches[0], "candidateSha256": digest(output / "candidate.json"),
    })
    verified_candidate(output, value["wheel"]["sha256"])
    output_variable("digest", value["wheel"]["sha256"])
    output_variable("artifact", f"ops-wheel-{required('SYSTEM_JOBATTEMPT')}")


def verified_candidate(directory, expected_digest):
    value = read(directory / "candidate.json")
    parent = release_build_id()
    if parent != "0":
        release.verify_candidate(
            directory, expected_producer={"definition": "165", "build": parent,
                                          "commit": release.commit(value["producer"]["commit"])},
            source_branch=required("BUILD_SOURCEBRANCH"), source_commit=producer()["commit"], consumer=producer(),
        )
        if value["wheel"]["sha256"] != expected_digest:
            raise ValueError("Release candidate digest mismatch.")
        return directory / value["wheel"]["file"]
    if value.get("schema") != 1 or value.get("producer") != producer():
        raise ValueError("Candidate producer does not match this run and source.")
    name = value["wheel"]["file"]
    if not re.fullmatch(r"azure_iot_ops-[A-Za-z0-9_.+!-]+\.whl", name):
        raise ValueError("Invalid candidate wheel filename.")
    wheel = directory / name
    if wheel.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise ValueError("Invalid candidate identity.")
    if value["wheel"]["sha256"] != expected_digest or digest(wheel) != expected_digest:
        raise ValueError("Candidate digest mismatch.")
    with ZipFile(wheel) as archive:
        if "azext_edge/__init__.py" not in archive.namelist():
            raise ValueError("Candidate does not contain the ops extension.")
    return wheel


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    value = read(required("OPS_PLAN"))
    if value["producer"] != producer():
        raise ValueError("Execution plan belongs to another source or run.")
    row = next((item for item in value["rows"] if item["key"] == required("OPS_ROW")), None)
    if row is None or row["python"] != f"{sys.version_info.major}.{sys.version_info.minor}":
        raise ValueError("Selected row or Python does not match the plan.")
    wheel = verified_candidate(Path(required("OPS_CANDIDATE")), required("OPS_CANDIDATE_DIGEST"))
    if release_build_id() != "0":
        directory = Path(required("OPS_CANDIDATE"))
        release_candidate = read(directory / "candidate.json")
        handoff = read(directory / "handoff.json")
        if (value.get("releaseBuildId") != release_build_id()
                or value["rows"] != [release_candidate["cohorts"][handoff["cohort"]]["row"]]):
            raise ValueError("Execution plan does not match the exact release cohort.")
    suffix = uuid4().hex[:11]
    prefix = f"/subscriptions/{value['subscription']}/resourceGroups/{value['resourceGroup']}/providers"
    cluster, storage = f"opado{suffix}", f"initstore{suffix}"
    registry, namespace = f"init-registry{suffix}", f"init-adr-{suffix}"
    state = {
        "schema": 1, "producer": producer(), "row": row, "attempt": int(required("SYSTEM_JOBATTEMPT")),
        "subscription": value["subscription"], "resourceGroup": value["resourceGroup"],
        "customLocationsObjectId": value["customLocationsObjectId"], "suffix": suffix,
        "cluster": cluster, "instance": f"inst{suffix}", "wheel": str(wheel.resolve()), "sha256": digest(wheel),
        "resources": {
            "cluster": f"{prefix}/Microsoft.Kubernetes/connectedClusters/{cluster}",
            "instance": f"{prefix}/Microsoft.IoTOperations/instances/inst{suffix}",
            "storage": f"{prefix}/Microsoft.Storage/storageAccounts/{storage}",
            "registry": f"{prefix}/Microsoft.DeviceRegistry/schemaRegistries/{registry}",
            "namespace": f"{prefix}/Microsoft.DeviceRegistry/namespaces/{namespace}",
        },
        "ownershipChecked": False, "phases": {}, "cleanup": "not-started", "status": "incomplete",
    }
    if value.get("health"):
        state["health"] = value["health"]
        state["locations"] = value["locations"]
    write(output / "state.json", state)
    extension_root = Path(required("AZURE_EXTENSION_DIR")).resolve()
    subprocess.run(["az", "extension", "add", "--source", str(wheel), "--yes"], check=True)
    runner = runpy.run_path(str(ROOT / "tools/integration_runner.py"))
    runner["verify_installed"](wheel, extension_root / "azure-iot-ops")
    if row["scenario"]["baseline"]:
        subprocess.run([
            sys.executable, "-c",
            "import json, runpy, sys; "
            "runpy.run_path(sys.argv[1])['validate_baseline_identity'](json.loads(sys.argv[2]), sys.argv[3])",
            str(ROOT / "tools/integration_runner.py"), json.dumps(row["scenario"]["baseline"]),
            row["scenario"]["channel"],
        ], cwd=output, env={**os.environ, "PYTHONPATH": str(extension_root / "azure-iot-ops")}, check=True)


def expected_phases(row):
    phases = ["init", "smoke"]
    if row["scenario"]["tox_env"]:
        phases.append("scenario")
    if row["scenario"]["test_redeploy"]:
        phases.append("redeploy")
    return phases


def junit_results(path):
    cases = list(ElementTree.parse(path).getroot().iter("testcase"))
    if not cases or any(case.find("failure") is not None or case.find("error") is not None for case in cases):
        raise ValueError(f"Failed or empty test results: {Path(path).name}")
    passed = sum(case.find("skipped") is None for case in cases)
    if not passed:
        raise ValueError(f"All cases were skipped: {Path(path).name}")
    return {"passed": passed, "skipped": len(cases) - passed, "total": len(cases)}


def report(output):
    if not (output / "state.json").is_file():
        write(output / "receipt.json", {"status": "incomplete", "producer": producer()})
        raise ValueError("Scenario setup did not produce execution state.")
    state = read(output / "state.json")
    phases = expected_phases(state["row"])
    success = state["status"] == "passed" and state["cleanup"] == "passed"
    success = success and all(state["phases"].get(phase) == "passed" for phase in phases)
    value = {
        "schema": 1, "producer": state["producer"], "row": state["row"]["key"],
        "attempt": state["attempt"], "sha256": state["sha256"], "phases": state["phases"],
        "cleanup": state["cleanup"], "status": "passed" if success else "incomplete",
        "createdAt": datetime.now(timezone.utc).isoformat(), "releaseQualified": False,
    }
    if state.get("health"):
        value["health"] = state["health"]
        value["locations"] = state.get("observedLocations", {})
        success = success and value["locations"] == expected_locations(state["locations"])
        value["status"] = "passed" if success else "incomplete"
    write(output / "receipt.json", value)
    if not success:
        raise ValueError("Scenario failed, was interrupted, or did not finish cleanup.")


def expected_locations(locations):
    return {
        "cluster": locations["clusterRegion"], "instance": locations["clusterRegion"],
        "storage": locations["resourceRegion"], "registry": locations["resourceRegion"],
        "namespace": locations["namespaceRegion"],
    }


def gate(output):
    value = read(required("OPS_PLAN"))
    if value["producer"] != producer():
        raise ValueError("Qualification plan does not match this run.")
    parent = release_build_id()
    release_candidate = None
    if parent != value.get("releaseBuildId", "0"):
        raise ValueError("Qualification plan has a different release producer.")
    if parent != "0":
        candidate_directory = Path(required("OPS_CANDIDATE"))
        verified_candidate(candidate_directory, required("OPS_CANDIDATE_DIGEST"))
        release_candidate = read(candidate_directory / "candidate.json")
        handoff = read(candidate_directory / "handoff.json")
        if value["rows"] != [release_candidate["cohorts"][handoff["cohort"]]["row"]]:
            raise ValueError("Selected integration rows differ from the release cohort.")
    history = Path(required("OPS_HISTORY"))
    verified = []
    output.mkdir(parents=True, exist_ok=False)
    coverage = output / "coverage"
    coverage.mkdir()
    unit_coverage = Path(required("OPS_UNIT_COVERAGE"))
    if not unit_coverage.is_file():
        raise ValueError("Missing unit coverage.")
    shutil.copyfile(unit_coverage, coverage / ".coverage.unit")
    for row in value["rows"]:
        receipts = []
        for path in history.glob(f"ops-attempt-{row['key']}-*/receipt.json"):
            receipt = read(path)
            attempt = path.parent.name.removeprefix(f"ops-attempt-{row['key']}-")
            if not attempt.isdigit() or receipt.get("attempt") != int(attempt):
                raise ValueError("Invalid scenario attempt identity.")
            receipts.append((int(attempt), path, receipt))
        if not receipts:
            raise ValueError(f"Missing scenario evidence: {row['key']}")
        _, path, receipt = max(receipts, key=lambda entry: entry[0])
        if (receipt.get("producer") != producer() or receipt.get("row") != row["key"]
                or receipt.get("sha256") != required("OPS_CANDIDATE_DIGEST")
                or receipt.get("status") != "passed" or receipt.get("cleanup") != "passed"
                or any(receipt.get("phases", {}).get(phase) != "passed" for phase in expected_phases(row))):
            raise ValueError(f"Unqualified latest scenario attempt: {row['key']}")
        if value.get("health") and (receipt.get("health") != value["health"]
                                    or receipt.get("locations") != expected_locations(value["locations"])):
            raise ValueError("Health profile or observed regional coverage differs from the plan.")
        for phase in expected_phases(row):
            junit_results(path.parent / "junit" / f"{phase}.xml")
        source = path.parent / "coverage.dat"
        if not source.is_file():
            raise ValueError(f"Missing scenario coverage: {row['key']}")
        shutil.copyfile(source, coverage / f".coverage.{row['key']}")
        verified.append(receipt)
    subprocess.run([sys.executable, "-m", "coverage", "combine", str(coverage)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "coverage", "xml", "-o", str(output / "coverage.xml")], cwd=ROOT, check=True)
    qualification = {
        "schema": 1, "producer": producer(), "sha256": required("OPS_CANDIDATE_DIGEST"),
        "scope": "selected ops scenarios", "scenarios": verified, "releaseQualified": False,
        "coverageScope": "unit tests plus selected ops scenarios",
    }
    if release_candidate:
        qualification["releaseCandidate"] = release_candidate
    write(output / "qualification.json", qualification)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["plan", "candidate", "acquire", "prepare", "report", "gate"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    globals()[args.operation](args.output.resolve())


if __name__ == "__main__":
    main()
