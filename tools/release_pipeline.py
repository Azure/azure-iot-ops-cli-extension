# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Release orchestration with immutable candidates and explicit external publication."""

import argparse
import base64
from datetime import datetime, timedelta, timezone
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


REPOSITORY = "Azure/azure-iot-ops-cli-extension"
INDEX_REPOSITORY = "Azure/azure-cli-extensions"
ADO = "https://dev.azure.com/azureiotdevxp/aziotcli/_apis"
PERMISSIONS = "https://dev.azure.com/azureiotdevxp/_apis/permissions"
FEED = "https://pkgs.dev.azure.com/azureiotdevxp/aziotcli/_packaging/pip/pypi/simple/"
INTEGRATION_PARAMETERS = {
    "mode": "Integration tests", "pythonVersions": ["3.13"], "upgradeBaselines": "{}",
    "scenarioTimeoutMinutes": 360, "azureServiceConnection": "az-iot-ops-int-sp-ado",
    "subscriptionId": "a386d5ea-ea90-441a-8263-d816368c84a1",
    "resourceGroup": "ops-cli-int-test-rg",
    "customLocationsObjectId": "51dfe1e8-70c6-4de5-a08e-e18aff23d815",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def environment(name):
    value = os.environ.get(name, "").strip()
    if not value or "$(" in value or "\n" in value or "\r" in value:
        raise ValueError(f"Configure {name} explicitly; unresolved pipeline variables are not allowed.")
    return value


def identifier(value):
    if not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("Expected a positive build or pipeline ID.")
    return str(value)


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected an immutable, lowercase 40-character commit SHA.")
    return value


def branch(value):
    value = value.removeprefix("refs/heads/")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", value)
            or any(part in value for part in ("..", "//", "@{"))
            or value.endswith(("/", ".", ".lock"))):
        raise ValueError("Source must be a safe branch name, not a tag or revision expression.")
    return f"refs/heads/{value}"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def api(url, token, method="GET", data=None, missing=False, content_type="application/json"):
    if not url.startswith((ADO + "/", PERMISSIONS + "/", "https://api.github.com/", "https://uploads.github.com/")):
        raise ValueError("Unapproved API destination.")
    payload = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
    request = Request(url, data=payload, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": content_type,
        "Accept": "application/json", "User-Agent": "azure-iot-ops-release",
    })
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            result = response.read()
            return json.loads(result) if result else None
    except HTTPError as error:
        if missing and error.code == 404:
            return None
        raise RuntimeError(f"{method} API request failed with HTTP {error.code}; no automatic write retry.") from None


def ado(resource, **kwargs):
    separator = "&" if "?" in resource else "?"
    return api(f"{ADO}/{resource}{separator}api-version=7.1", environment("SYSTEM_ACCESSTOKEN"), **kwargs)


def github(resource, **kwargs):
    return api(f"https://api.github.com/{resource}", environment("RELEASE_GITHUB_TOKEN"), **kwargs)


def check_access():
    query = urlencode({"tokens": environment("SYSTEM_TEAMPROJECTID") + "/164",
                       "alwaysAllowAdministrators": "false", "api-version": "7.1"})
    granted = {}
    for name, bit in (("View builds", 1), ("Queue builds", 128), ("Stop builds", 512),
                      ("View build pipeline", 1024)):
        response = api(f"{PERMISSIONS}/33344d9c-fc72-4d6f-aba5-fa317101a7e9/{bit}?{query}",
                       environment("SYSTEM_ACCESSTOKEN"))
        if (not isinstance(response, dict) or response.get("count") != 1
                or not isinstance(response.get("value"), list) or len(response["value"]) != 1
                or type(response["value"][0]) is not bool):
            raise ValueError("Unexpected build-permission response; authorization could not be established.")
        granted[name] = response["value"][0]
    print(json.dumps({"pipeline": 164, "jobTokenPermissions": granted}, indent=2), flush=True)
    if not all(granted.values()):
        raise ValueError("The release Build Service needs scoped View/Queue/Stop permissions on pipeline 164.")


def checkout(destination, resolving=False):
    if resolving:
        if environment("RELEASE_MODE") == "Release":
            automation_allowed()
            if branch(environment("RELEASE_SOURCE_BRANCH")) != "refs/heads/dev":
                raise ValueError("Ops publication requires the protected dev source branch.")
    source_branch = branch(environment("RELEASE_SOURCE_BRANCH"))
    source_commit = None if resolving else commit(environment("RELEASE_SOURCE_COMMIT"))
    if destination.exists():
        raise ValueError("The source destination must be a new, isolated directory.")
    subprocess.run(["git", "init", "--quiet", str(destination)], check=True)
    subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPOSITORY}.git"],
                   cwd=destination, check=True)
    fetch = ["git", "fetch", "--quiet", "--filter=blob:none", "--depth=1", "origin"]
    subprocess.run(fetch + [source_branch if resolving else source_commit], cwd=destination, check=True)
    tip = commit(command(["git", "rev-parse", "FETCH_HEAD"], destination))
    selected = source_commit or tip
    subprocess.run(["git", "checkout", "--quiet", "--detach", selected], cwd=destination, check=True)
    if command(["git", "rev-parse", "HEAD"], destination) != selected:
        raise ValueError("Source checkout did not match the resolved commit.")
    if resolving:
        for relative in (
            ".azure-devops/templates/integration-pipeline.yml", "tools/ado_integration.py",
            "tools/release_pipeline.py", ".github/test-scenarios.yml",
        ):
            if not (destination / relative).is_file():
                raise ValueError(f"Source branch needs the migration/index-check prerequisites: {relative}")
        integration = (destination / ".azure-devops/integration.yml").read_text(encoding="utf-8")
        if "releaseBuildId" not in integration:
            raise ValueError("The selected source does not support pipeline 164's release-candidate handoff.")
        print(f"##vso[task.setvariable variable=commit;isOutput=true]{selected}", flush=True)
    return selected


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 1024 * 1024:
            raise ValueError("Expected one bounded wheel METADATA document.")
        value = Parser().parsestr(archive.read(names[0]).decode("utf-8"))
        if value.get("Name", "").lower().replace("_", "-") != "azure-iot-ops":
            raise ValueError("Only the azure-iot-ops distribution may be released.")
        version = value.get("Version", "")
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+!]*", version):
            raise ValueError("Wheel version is missing or unsafe.")
        if "azext_edge/__init__.py" not in archive.namelist():
            raise ValueError("Wheel does not contain the Ops extension.")
    return version


def producer():
    return {
        "definition": identifier(environment("SYSTEM_DEFINITIONID")),
        "build": identifier(environment("BUILD_BUILDID")),
        "commit": commit(environment("BUILD_SOURCEVERSION")),
    }


def feed_environment():
    authenticated = os.environ.get("PIP_INDEX_URL", "")
    try:
        uri = urlsplit(authenticated)
        port = uri.port
    except ValueError:
        raise ValueError("PipAuthenticate did not provide a valid authenticated feed URL.") from None
    expected = urlsplit(FEED)
    if (uri.scheme != expected.scheme or uri.hostname != expected.hostname
            or uri.path.rstrip("/") != expected.path.rstrip("/")
            or not uri.username or not uri.password or port not in (None, 443)
            or uri.query or uri.fragment or any(char.isspace() for char in authenticated)):
        raise ValueError("PipAuthenticate must authenticate exactly the configured aziotcli/pip feed.")
    result = {key: value for key, value in os.environ.items() if not key.startswith("PIP_")}
    result.update(
        PIP_INDEX_URL=authenticated, PIP_CONFIG_FILE=os.devnull, PIP_EXTRA_INDEX_URL="",
        PIP_KEYRING_PROVIDER="disabled", PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_NO_CACHE_DIR="1",
    )
    return result


def configure_feed():
    configured = feed_environment()
    for key in sorted(set(os.environ) | set(configured)):
        if key.startswith("PIP_") and key != "PIP_INDEX_URL":
            if not re.fullmatch(r"PIP_[A-Z0-9_]+", key):
                raise ValueError("Invalid inherited pip configuration variable name.")
            print(f"##vso[task.setvariable variable={key}]{configured.get(key, '')}", flush=True)
    print("Using only the authenticated aziotcli/pip feed; alternate indexes and pip configuration are disabled.")


def build_candidate(source, work_dir):
    build_env = feed_environment()

    def run(args):
        subprocess.run(args, cwd=source, env=build_env, check=True)

    run([sys.executable, "-m", "pip", "install", "-r", "dev_requirements.txt", "PyYAML"])
    run([sys.executable, "-m", "build", "--wheel"])
    wheels = list((source / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Build must produce exactly one wheel.")
    wheel = wheels[0]
    venv = work_dir / "sbom-venv"
    run([sys.executable, "-m", "venv", str(venv)])
    python = str(venv / "bin/python")
    run([python, "-m", "pip", "install", str(wheel)])
    requirements = source / "dist/requirements.txt"
    requirements.write_text(subprocess.check_output(
        [python, "-m", "pip", "freeze"], cwd=source, env=build_env, text=True), encoding="utf-8")
    tool = work_dir / "sbom-tool"
    subprocess.run([
        "curl", "--fail", "--location", "--proto", "=https", "--tlsv1.2",
        "https://github.com/microsoft/sbom-tool/releases/download/v4.1.5/sbom-tool-linux-x64",
        "--output", str(tool),
    ], check=True)
    if digest(tool) != "bf5d4f99bc98c119d549d08fc02ae92598a7a42772f17317c01031a92632e05b":
        raise ValueError("SBOM tool digest does not match the pinned release.")
    tool.chmod(0o700)
    run([str(tool), "generate", "-b", "dist", "-bc", "dist", "-pn", "Azure IoT Operations CLI Extension",
         "-pv", wheel_metadata(wheel), "-ps", "Microsoft"])
    requirements.unlink()


def source_cohorts(source):
    import yaml

    config = yaml.safe_load((source / ".github/test-scenarios.yml").read_text(encoding="utf-8"))["scenarios"]
    matrix = runpy.run_path(str(source / ".github/actions/build-int-test-matrix/build_matrix.py"))
    selected = matrix["process_scenarios"](config, "")
    rows = matrix["expand_channels"](selected, "stable,preview", {})
    return {
        f"{row['name'].replace('-', '_')}_py313": {
            "selection": row["name"].removesuffix("-" + row["channel"]),
            "row": {"key": f"{row['name'].replace('-', '_')}_py313", "python": "3.13", "scenario": row},
        } for row in rows
    }


def integration_parameters(candidate, cohort=None):
    key = cohort or environment("RELEASE_COHORT")
    selection = candidate["cohorts"][key]
    return dict(INTEGRATION_PARAMETERS, releaseBuildId=candidate["producer"]["build"],
                testScenarios=[selection["selection"]], runtimeChannels=[selection["row"]["scenario"]["channel"]])


def create_candidate(source, directory):
    wheels = list((source / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Build must produce exactly one wheel.")
    wheel = wheels[0]
    source_commit = commit(environment("RELEASE_SOURCE_COMMIT"))
    if command(["git", "rev-parse", "HEAD"], source) != source_commit:
        raise ValueError("Build checkout no longer matches the selected source.")
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=source, check=True)
    manifests = list((source / "dist/_manifest").rglob("*.spdx.json"))
    if not manifests:
        raise ValueError("SBOM generation did not produce an SPDX manifest.")
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(wheel, directory / wheel.name)
    with zipfile.ZipFile(directory / "SBOM.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((source / "dist/_manifest").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source / "dist"))
    value = {
        "schema": 1, "repository": REPOSITORY,
        "sourceBranch": branch(environment("RELEASE_SOURCE_BRANCH")), "sourceCommit": source_commit,
        "producer": producer(),
        "wheel": {"file": wheel.name, "sha256": digest(wheel), "version": wheel_metadata(wheel)},
        "sbom": {"file": "SBOM.zip", "sha256": digest(directory / "SBOM.zip")},
        "cohorts": source_cohorts(source),
    }
    write(directory / "candidate.json", value)
    verify_candidate(directory)
    print("##vso[task.setvariable variable=matrix;isOutput=true]" + json.dumps({
        key: {"cohort": key} for key in value["cohorts"]
    }), flush=True)
    return value


def verify_candidate(directory, *, expected_producer=None, source_branch=None, source_commit=None, consumer=None):
    value = read(directory / "candidate.json")
    if (type(value["schema"]) is not int or value["schema"] != 1 or value["repository"] != REPOSITORY
            or value["producer"] != (expected_producer or producer())
            or value["sourceBranch"] != branch(source_branch or environment("RELEASE_SOURCE_BRANCH"))
            or value["sourceCommit"] != commit(source_commit or environment("RELEASE_SOURCE_COMMIT"))):
        raise ValueError("Candidate provenance does not match this release run and source.")
    cohorts = value["cohorts"]
    if not isinstance(cohorts, dict) or not cohorts:
        raise ValueError("Missing full release cohort inventory.")
    selections = set()
    for key, cohort in cohorts.items():
        row = cohort["row"]
        name, channel = cohort["selection"], row["scenario"]["channel"]
        if (not re.fullmatch(r"[a-z][a-z0-9-]*", name) or channel not in {"stable", "preview"}
                or key != f"{name.replace('-', '_')}_{channel}_py313" or row["key"] != key
                or row["python"] != "3.13" or row["scenario"]["name"] != f"{name}-{channel}"):
            raise ValueError("Invalid release cohort inventory.")
        selections.add(name)
    if len(cohorts) != len(selections) * 2:
        raise ValueError("Every release scenario must cover stable and preview.")
    wheel = value["wheel"]
    if not re.fullmatch(r"azure_iot_ops-[A-Za-z0-9_.+!-]+\.whl", wheel["file"]):
        raise ValueError("Unsafe candidate wheel name.")
    governance = directory / "_manifest"
    if governance.exists() or governance.is_symlink():
        if (governance.is_symlink() or not governance.is_dir() or any(
                path.is_symlink() or path.suffix.lower() == ".whl" or not (path.is_file() or path.is_dir())
                for path in governance.rglob("*"))):
            raise ValueError("Unsafe governed artifact metadata.")
    files = [path for path in directory.iterdir() if path.name != "_manifest"]
    expected_files = {wheel["file"], "candidate.json", "SBOM.zip"}
    if consumer is not None:
        expected_files.add("handoff.json")
        handoff = read(directory / "handoff.json")
        if (handoff["cohort"] not in cohorts or handoff != {
                "consumer": consumer, "cohort": handoff["cohort"],
                "candidateSha256": digest(directory / "candidate.json")}):
            raise ValueError("Candidate handoff does not match this consumer.")
    if (directory.is_symlink() or {path.name for path in files} != expected_files
            or any(path.is_symlink() or not path.is_file() for path in files)):
        raise ValueError("Expected only declared candidate assets as regular files.")
    for item in (wheel, value["sbom"]):
        if Path(item["file"]).name != item["file"] or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Invalid candidate asset identity.")
        if digest(directory / item["file"]) != item["sha256"]:
            raise ValueError("Candidate asset digest mismatch.")
    if value["sbom"]["file"] != "SBOM.zip" or wheel_metadata(directory / wheel["file"]) != wheel["version"]:
        raise ValueError("Candidate metadata mismatch.")
    return value


def validate_integration(build, candidate, cohort=None):
    parameters = build.get("templateParameters")
    if isinstance(parameters, str):
        parameters = json.loads(parameters)
    parameters = dict(parameters)
    for key in ("testScenarios", "runtimeChannels", "pythonVersions"):
        if isinstance(parameters.get(key), str):
            parameters[key] = json.loads(parameters[key])
    parameters["releaseBuildId"] = identifier(parameters.get("releaseBuildId"))
    parameters["scenarioTimeoutMinutes"] = int(parameters["scenarioTimeoutMinutes"])
    expected = integration_parameters(candidate, cohort)
    repository = build["repository"]
    if (build["definition"]["id"] != 164 or repository.get("id") != REPOSITORY
            or repository.get("type") != "GitHub" or repository.get("name") not in (None, REPOSITORY)
            or build["project"]["id"].lower() != environment("SYSTEM_TEAMPROJECTID").lower()
            or build["sourceVersion"] != candidate["sourceCommit"]
            or build["sourceBranch"] != candidate["sourceBranch"] or parameters != expected):
        raise ValueError("Pipeline 164 run does not match the exact release qualification request.")


def existing_integration(candidate) -> dict | None:
    parent = ado(f"build/builds/{candidate['producer']['build']}")
    if (str(parent["definition"]["id"]) != candidate["producer"]["definition"]
            or parent["sourceVersion"] != candidate["producer"]["commit"]):
        raise ValueError("Release producer metadata mismatch.")
    query = urlencode({
        "definitions": 164, "branchName": candidate["sourceBranch"], "minTime": parent["queueTime"],
        "queryOrder": "queueTimeAscending", "$top": 1000,
    })
    builds = ado("build/builds?" + query)["value"]
    if len(builds) >= 1000:
        raise ValueError("Too many child builds to prove unique ownership; inspect pipeline 164 before retrying.")
    matches = []
    for build in builds:
        parameters = build.get("templateParameters", {})
        if isinstance(parameters, str):
            parameters = json.loads(parameters)
        if str(parameters.get("releaseBuildId", "")) == candidate["producer"]["build"]:
            scopes = []
            for key in candidate["cohorts"]:
                try:
                    validate_integration(build, candidate, key)
                    scopes.append(key)
                except ValueError:
                    continue
            if len(scopes) != 1:
                raise ValueError("An owned child has an unexpected release cohort or source.")
            if scopes[0] == environment("RELEASE_COHORT"):
                matches.append(build)
    if len(matches) > 1:
        raise ValueError("Multiple children reference this release; resolve the duplicate cohorts before proceeding.")
    return matches[0] if matches else None


def cancel_integration(record, directory):
    candidate = verify_candidate(directory)
    if not record.exists():
        existing = existing_integration(candidate)
        if existing is None:
            print("No child of this release was found; no cancellation request was sent.", flush=True)
            return
        run = {"id": identifier(existing.get("id")), "producer": candidate["producer"],
               "cohort": environment("RELEASE_COHORT")}
    else:
        run = read(record)
    if run["producer"] != candidate["producer"] or run["cohort"] != environment("RELEASE_COHORT"):
        raise ValueError("Refusing to cancel a child owned by another release.")
    build = ado(f"build/builds/{identifier(run['id'])}")
    validate_integration(build, candidate)
    if build["status"] != "completed":
        ado(f"build/builds/{run['id']}", method="PATCH", data={"status": "cancelling"})
        print(f"Requested cancellation of pipeline 164 build {run['id']}.", flush=True)


def safe_queue_delay(now=None):
    now = now or datetime.now(timezone.utc)
    if now.hour == 9 and now.minute < 5:
        return (now.replace(minute=5, second=0, microsecond=0) - now).total_seconds()
    # Queue only with the child's six-hour budget, cleanup hour and startup margin.
    for hour in (8, 9):
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)
        if scheduled - now < timedelta(hours=8):
            resume = scheduled.replace(hour=9, minute=5)
            return max(0, (resume - now).total_seconds())
    return 0


def integrate(directory, record, timeout=25200):
    candidate = verify_candidate(directory)
    payload = {
        "definition": {"id": 164}, "sourceBranch": candidate["sourceBranch"],
        "sourceVersion": candidate["sourceCommit"],
        "templateParameters": {
            key: value if isinstance(value, str) else json.dumps(value)
            for key, value in integration_parameters(candidate).items()
        },
    }
    run = existing_integration(candidate)
    if run is None:
        if int(os.environ.get("SYSTEM_JOBATTEMPT", "1")) != 1:
            raise ValueError("No child found on a retried job; do not risk requeuing an uncertain prior request.")
        delay = safe_queue_delay()
        if delay:
            print("Waiting without Azure resources until the next safe Ops qualification window.", flush=True)
            while delay > 0:
                time.sleep(min(60, delay))
                delay = safe_queue_delay()
        run = ado("build/builds", method="POST", data=payload)
    run_id = identifier(run["id"])
    write(record, {"id": run_id, "producer": candidate["producer"], "cohort": environment("RELEASE_COHORT")})
    print(f"##vso[task.setvariable variable=integrationBuildId]{run_id}", flush=True)
    print(f"Integration: https://dev.azure.com/azureiotdevxp/aziotcli/_build/results?buildId={run_id}", flush=True)

    def interrupted(_signum, _frame):
        cancel_integration(record, directory)
        raise SystemExit(130)

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    deadline = time.monotonic() + timeout
    try:
        while True:
            build = ado(f"build/builds/{run_id}")
            validate_integration(build, candidate)
            if build["status"] == "completed":
                if build["result"] != "succeeded":
                    raise RuntimeError(f"Pipeline 164 build {run_id} finished with {build['result']}.")
                return run_id
            if time.monotonic() >= deadline:
                cancel_integration(record, directory)
                raise TimeoutError(f"Pipeline 164 build {run_id} exceeded the release wait budget.")
            time.sleep(30)
    except (ValueError, RuntimeError, OSError, KeyError):
        cancel_integration(record, directory)
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def verify_integration_artifacts(directory, artifacts):
    candidate = verify_candidate(directory)
    key = environment("RELEASE_COHORT")
    child = ado(f"build/builds/{identifier(environment('RELEASE_CHILD_BUILD_ID'))}")
    validate_integration(child, candidate)
    if child["status"] != "completed" or child["result"] != "succeeded":
        raise ValueError("The exact child must succeed before evidence verification.")
    consumer = {"pipeline": "164", "build": str(child["id"]), "commit": candidate["sourceCommit"]}
    manifests = list(artifacts.glob("ops-wheel-*/candidate.json"))
    if not manifests:
        raise ValueError("Integration candidate evidence is missing.")
    for path in manifests:
        wheel = path.parent / candidate["wheel"]["file"]
        handoff = read(path.parent / "handoff.json")
        if (read(path) != candidate or digest(wheel) != candidate["wheel"]["sha256"]
                or digest(path.parent / "SBOM.zip") != candidate["sbom"]["sha256"]
                or handoff != {"consumer": consumer, "cohort": key, "candidateSha256": digest(path)}):
            raise ValueError("Integration did not retain the exact candidate and consumer binding.")
    qualifications = list(artifacts.glob("ops-qualification-*/qualification.json"))
    if not qualifications:
        raise ValueError("Integration qualification evidence is missing.")
    latest = max(qualifications, key=lambda path: int(path.parent.name.removeprefix("ops-qualification-")))
    proof = read(latest)
    rows = proof["scenarios"]
    expected_phases = {"init", "smoke"}
    scenario = candidate["cohorts"][key]["row"]["scenario"]
    if scenario["tox_env"]:
        expected_phases.add("scenario")
    if scenario["test_redeploy"]:
        expected_phases.add("redeploy")
    if (proof.get("producer") != consumer or proof.get("sha256") != candidate["wheel"]["sha256"]
            or proof.get("releaseCandidate") != candidate
            or len(rows) != 1 or rows[0].get("row") != key
            or rows[0].get("producer") != consumer or rows[0].get("sha256") != candidate["wheel"]["sha256"]
            or rows[0].get("cleanup") != "passed" or rows[0].get("status") != "passed"
            or any(rows[0].get("phases", {}).get(phase) != "passed" for phase in expected_phases)):
        raise ValueError("Incomplete release cohort evidence or cleanup.")
    print(f"Qualified {key} against wheel SHA-256 {candidate['wheel']['sha256']}.", flush=True)


def automation_allowed():
    if environment("BUILD_SOURCEBRANCH") != "refs/heads/dev":
        raise ValueError("Publication requires the reviewed release automation on dev, not a feature branch.")
    if environment("BUILD_REPOSITORY_NAME") != REPOSITORY:
        raise ValueError("Publication is only allowed from the upstream repository.")


def release_options():
    mode = environment("RELEASE_MODE")
    index = os.environ.get("RELEASE_CREATE_INDEX_PR", "false").lower()
    if mode not in {"Plan", "Validate", "Release"} or index not in {"true", "false"}:
        raise ValueError("Invalid release mode or createIndexPr option.")
    if index == "true" and mode != "Release":
        raise ValueError("createIndexPr requires Release mode and a public GitHub release.")
    upload = os.environ.get("RELEASE_UPLOAD_WHEEL", "false").lower()
    if upload not in {"true", "false"} or upload == "true" and mode != "Release":
        raise ValueError("uploadWheel requires Release mode and an explicit boolean option.")
    return mode, index == "true"


def publication_allowed():
    if release_options()[0] != "Release":
        raise ValueError("Publication requires explicit Release mode.")
    automation_allowed()
    if branch(environment("RELEASE_SOURCE_BRANCH")) != "refs/heads/dev":
        raise ValueError("Ops publication requires the protected dev source branch.")
    environment("RELEASE_GITHUB_TOKEN")


def tag_commit(tag):
    value = github(f"repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}", missing=True)
    if value is None:
        return None
    obj = value["object"]
    for _ in range(5):
        if obj["type"] == "commit":
            return commit(obj["sha"])
        if obj["type"] != "tag":
            break
        obj = github(f"repos/{REPOSITORY}/git/tags/{obj['sha']}")["object"]
    raise ValueError("Release tag does not resolve to a commit.")


def find_release(tag):
    value = github(f"repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}", missing=True)
    if value is not None:
        return value
    page = 1
    while True:
        values = github(f"repos/{REPOSITORY}/releases?per_page=100&page={page}")
        matches = [item for item in values if item["tag_name"] == tag]
        if len(matches) > 1:
            raise ValueError("Multiple drafts exist for the same version.")
        if matches:
            return matches[0]
        if len(values) < 100:
            return None
        page += 1


def verify_public_assets(release, candidate):
    if release["draft"]:
        raise ValueError("The qualified release is not public.")
    for asset in (candidate["wheel"], candidate["sbom"]):
        matches = [item for item in release["assets"] if item["name"] == asset["file"]]
        if len(matches) != 1 or matches[0].get("digest") != "sha256:" + asset["sha256"]:
            raise ValueError("Public release assets do not match the qualified candidate.")


def github_contents(repository, ref):
    contents = github(f"repos/{repository}/contents/src/index.json?" + urlencode({"ref": ref}))
    if contents.get("encoding") != "base64":
        contents = github(f"repos/{repository}/git/blobs/{contents['sha']}")
    if contents.get("encoding") != "base64":
        raise ValueError("GitHub did not return base64 index content.")
    return base64.b64decode(contents["content"], validate=False)


def verify_index_change(before, after, entry):
    prior = before["extensions"].get("azure-iot-ops", [])
    normalized = json.loads(json.dumps(after))
    if "azure-iot-ops" in before["extensions"]:
        normalized["extensions"]["azure-iot-ops"] = prior
    else:
        normalized["extensions"].pop("azure-iot-ops", None)
    if (normalized != before or after["extensions"]["azure-iot-ops"] != prior + [entry]):
        raise ValueError("Index update changed more than the verified candidate entry.")


def verify_existing_index_branch(fork, ref, contents, entry):
    comparison = github(
        f"repos/{INDEX_REPOSITORY}/compare/main...{quote(fork.split('/')[0] + ':' + ref, safe='')}")
    commits = comparison.get("commits", [])
    if (len(commits) != 1 or comparison.get("ahead_by") != 1
            or [item["filename"] for item in comparison.get("files", [])] != ["src/index.json"]
            or len(commits[0]["parents"]) != 1
            or commits[0]["parents"][0]["sha"] != comparison["merge_base_commit"]["sha"]):
        raise ValueError("Existing index branch has unrelated commits or files; refusing to overwrite it.")
    before = json.loads(github_contents(INDEX_REPOSITORY, comparison["merge_base_commit"]["sha"]))
    verify_index_change(before, json.loads(contents), entry)


def index_metadata(wheel, destination):
    if Path(environment("VIRTUAL_ENV")).resolve() != Path(sys.prefix).resolve():
        raise ValueError("Index metadata generation requires the activated tooling virtual environment.")
    from importlib import import_module
    from importlib.metadata import version

    if version("azdev") != "0.2.13":
        raise ValueError("Index metadata generation requires azdev 0.2.13.")
    destination.mkdir(parents=True, exist_ok=False)
    return import_module("azdev.operations.extensions.util").get_ext_metadata(
        str(destination), str(wheel), "azure-iot-ops",
    )


def prepare_publication(directory, tooling, work_dir):
    from packaging.version import Version

    candidate = verify_candidate(directory)
    version = Version(candidate["wheel"]["version"])
    if str(version) != candidate["wheel"]["version"]:
        raise ValueError("The wheel version must already be normalized.")
    wheel = candidate["wheel"]
    entry = {
        "downloadUrl": f"https://github.com/{REPOSITORY}/releases/download/v{version}/{wheel['file']}",
        "sha256Digest": wheel["sha256"], "filename": wheel["file"],
        "metadata": index_metadata(directory / wheel["file"], work_dir / "index-metadata"),
    }
    tooling.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), tooling / "release_pipeline.py")
    prepared = tooling / "publication.json"
    write(prepared, {"candidate": candidate, "indexEntry": entry, "prerelease": version.is_prerelease})
    verify_publication_inputs(directory, prepared)


def verify_publication_inputs(directory, prepared):
    candidate = verify_candidate(directory)
    value = read(prepared)
    entry = value["indexEntry"]
    wheel = candidate["wheel"]
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/v{wheel['version']}/{wheel['file']}"
    if (value["candidate"] != candidate or type(value["prerelease"]) is not bool
            or set(entry) != {"downloadUrl", "sha256Digest", "filename", "metadata"}
            or entry["filename"] != wheel["file"] or entry["sha256Digest"] != wheel["sha256"]
            or entry["downloadUrl"] != expected_url or entry["metadata"].get("version") != wheel["version"]):
        raise ValueError("Prepared publication metadata does not match the qualified candidate.")
    return candidate, value


def publish(directory, receipt, prepared):
    publication_allowed()
    candidate, preparation = verify_publication_inputs(directory, prepared)
    version = candidate["wheel"]["version"]
    tag = f"v{version}"
    existing_tag = tag_commit(tag)
    if existing_tag is not None and existing_tag != candidate["sourceCommit"]:
        raise ValueError("Existing release tag points to another commit; it will not be moved.")
    release = find_release(tag)
    if release is None:
        release = github(f"repos/{REPOSITORY}/releases", method="POST", data={
            "tag_name": tag, "target_commitish": candidate["sourceCommit"],
            "name": f"azure-iot-ops {version}", "draft": True,
            "prerelease": preparation["prerelease"], "generate_release_notes": True,
        })
    if (release["target_commitish"] != candidate["sourceCommit"] and existing_tag != candidate["sourceCommit"]
            or release["prerelease"] != preparation["prerelease"]):
        raise ValueError("Existing release has different source or prerelease metadata.")
    for asset in (candidate["wheel"], candidate["sbom"]):
        matches = [item for item in release["assets"] if item["name"] == asset["file"]]
        if len(matches) > 1:
            raise ValueError("Duplicate release assets.")
        if matches:
            if matches[0].get("digest") != "sha256:" + asset["sha256"]:
                raise ValueError("Existing asset differs or has no verifiable digest; refusing overwrite.")
        else:
            if not release["draft"]:
                raise ValueError("Published release is incomplete; refusing to mutate its assets.")
            uploaded = api(
                f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release['id']}/assets?"
                + urlencode({"name": asset["file"]}), environment("RELEASE_GITHUB_TOKEN"),
                method="POST", data=(directory / asset["file"]).read_bytes(),
                content_type="application/octet-stream",
            )
            if uploaded.get("digest") != "sha256:" + asset["sha256"]:
                raise ValueError("Uploaded release asset digest mismatch; release remains a draft.")
    if release["draft"]:
        current_tag = tag_commit(tag)
        if current_tag is None:
            github(f"repos/{REPOSITORY}/git/refs", method="POST",
                   data={"ref": f"refs/tags/{tag}", "sha": candidate["sourceCommit"]})
        elif current_tag != candidate["sourceCommit"]:
            raise ValueError("Tag changed during staging; release remains a draft.")
        github(f"repos/{REPOSITORY}/releases/{release['id']}", method="PATCH", data={"draft": False})
    verify_public_assets(github(f"repos/{REPOSITORY}/releases/{release['id']}"), candidate)
    if tag_commit(tag) != candidate["sourceCommit"]:
        raise ValueError("Published tag no longer matches the qualified commit.")
    wheel_url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{candidate['wheel']['file']}"
    result = {"release": release["id"], "tag": tag, "wheelUrl": wheel_url, "candidate": candidate}
    write(receipt, result)
    print(f"Published https://github.com/{REPOSITORY}/releases/tag/{tag}", flush=True)
    return result


def index_pull_request(directory, receipt, work_dir, prepared):
    publication_allowed()
    if not release_options()[1]:
        raise ValueError("Index submission requires explicit createIndexPr opt-in.")
    candidate, preparation = verify_publication_inputs(directory, prepared)
    publication = read(receipt)
    if publication["candidate"] != candidate:
        raise ValueError("Publication receipt belongs to a different candidate.")
    expected_url = (f"https://github.com/{REPOSITORY}/releases/download/"
                    f"v{candidate['wheel']['version']}/{candidate['wheel']['file']}")
    if publication["wheelUrl"] != expected_url:
        raise ValueError("Index URL differs from the qualified release.")
    release = find_release(publication["tag"])
    if (release is None or release["draft"] or release["id"] != publication["release"]
            or tag_commit(publication["tag"]) != candidate["sourceCommit"]):
        raise ValueError("A public release of the qualified commit is required before index submission.")
    verify_public_assets(release, candidate)
    fork = environment("INDEX_FORK_REPOSITORY")
    if not re.fullmatch(r"[A-Za-z0-9-]+/azure-cli-extensions", fork) or fork == INDEX_REPOSITORY:
        raise ValueError("Configure an approved automation fork, not the upstream index repository.")
    fork_info = github(f"repos/{fork}")
    if not fork_info.get("fork") or fork_info.get("parent", {}).get("full_name") != INDEX_REPOSITORY:
        raise ValueError("The configured repository is not a fork of the official index.")
    work_dir.mkdir(parents=True, exist_ok=True)
    source_sha = commit(github(f"repos/{INDEX_REPOSITORY}/git/ref/heads/main")["object"]["sha"])
    before = json.loads(github_contents(INDEX_REPOSITORY, source_sha))
    prior = before["extensions"].get("azure-iot-ops", [])
    same_version = [entry for entry in prior if entry["metadata"]["version"] == candidate["wheel"]["version"]]
    if same_version:
        if (len(same_version) != 1 or same_version[0]["sha256Digest"] != candidate["wheel"]["sha256"]
                or same_version[0]["downloadUrl"] != expected_url):
            raise ValueError("The index already contains conflicting metadata for this version.")
        print("The exact candidate is already indexed; no duplicate PR was created.")
        return {"status": "already-indexed"}
    after = json.loads(json.dumps(before))
    added = preparation["indexEntry"]
    after["extensions"].setdefault("azure-iot-ops", []).append(added)
    verify_index_change(before, after, added)
    if (added["metadata"]["version"] != candidate["wheel"]["version"]
            or added["sha256Digest"] != candidate["wheel"]["sha256"]
            or added["filename"] != candidate["wheel"]["file"] or added["downloadUrl"] != expected_url):
        raise ValueError("Index update changed more than the verified candidate entry.")
    index_path = work_dir / "index.json"
    index_path.write_text(json.dumps(after, indent=4, sort_keys=True), encoding="utf-8")
    release_branch = f"release/azure-iot-ops-{candidate['wheel']['version']}"
    ref = github(f"repos/{fork}/git/ref/heads/{quote(release_branch, safe='')}", missing=True)
    encoded = base64.b64encode(index_path.read_bytes()).decode()
    if ref:
        contents = github_contents(fork, release_branch)
        if ref["object"]["sha"] != source_sha:
            verify_existing_index_branch(fork, release_branch, contents, added)
        elif contents != index_path.read_bytes():
            old = github(f"repos/{fork}/contents/src/index.json?" + urlencode({"ref": release_branch}))
            github(f"repos/{fork}/contents/src/index.json", method="PUT", data={
                "message": f"Update azure-iot-ops to {candidate['wheel']['version']}",
                "content": encoded, "sha": old["sha"], "branch": release_branch,
            })
    else:
        github(f"repos/{fork}/git/refs", method="POST",
               data={"ref": f"refs/heads/{release_branch}", "sha": source_sha})
        old = github(f"repos/{fork}/contents/src/index.json?" + urlencode({"ref": release_branch}))
        github(f"repos/{fork}/contents/src/index.json", method="PUT", data={
            "message": f"Update azure-iot-ops to {candidate['wheel']['version']}",
            "content": encoded, "sha": old["sha"], "branch": release_branch,
        })
    head = f"{fork.split('/')[0]}:{release_branch}"
    existing = github(f"repos/{INDEX_REPOSITORY}/pulls?" + urlencode({"head": head, "base": "main", "state": "open"}))
    if len(existing) > 1:
        raise ValueError("Multiple open index PRs reference the release branch.")
    result = existing[0] if existing else github(f"repos/{INDEX_REPOSITORY}/pulls", method="POST", data={
        "title": f"[azure-iot-ops] Update to {candidate['wheel']['version']}", "head": head, "base": "main",
        "body": (f"Release: https://github.com/{REPOSITORY}/releases/tag/{publication['tag']}\n\n"
                 f"Source: `{candidate['sourceCommit']}`\n\nWheel SHA-256: `{candidate['wheel']['sha256']}`\n\n"
                 "Qualified by the Azure IoT Operations CLI ADO release pipeline. Index-team review is required; "
                 "this automation does not merge the PR."),
    })
    print(f"Index review required: {result['html_url']}", flush=True)
    return {"status": "review-required", "url": result["html_url"]}


def upload_wheel(directory, work_dir):
    if release_options()[0] != "Release" or os.environ.get("RELEASE_UPLOAD_WHEEL", "").lower() != "true":
        raise ValueError("Storage upload requires explicit Release mode and uploadWheel opt-in.")
    automation_allowed()
    if branch(environment("RELEASE_SOURCE_BRANCH")) != "refs/heads/dev":
        raise ValueError("Ops publication requires the protected dev source branch.")
    candidate = verify_candidate(directory)
    url = urlsplit(environment("RELEASE_STORAGE_CONTAINER_URL"))
    if (url.scheme != "https" or not re.fullmatch(r"[a-z0-9]{3,24}\.blob\.core\.windows\.net", url.netloc)
            or not re.fullmatch(r"/[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", url.path)
            or url.query or url.fragment):
        raise ValueError("Configure an approved public-Azure container URL without embedded credentials.")
    account = url.hostname.split(".")[0]
    wheel = candidate["wheel"]
    common = ["--auth-mode", "login", "--account-name", account, "--container-name", url.path[1:],
              "--name", wheel["file"], "--only-show-errors"]
    exists = json.loads(command(["az", "storage", "blob", "exists", *common, "--output", "json"]))["exists"]
    if type(exists) is not bool:
        raise ValueError("Storage did not return a boolean existence result.")
    work_dir.mkdir(parents=True, exist_ok=False)
    if not exists:
        subprocess.run(["az", "storage", "blob", "upload", *common, "--file", str(directory / wheel["file"]),
                        "--overwrite", "false", "--output", "none"], check=True)
    downloaded = work_dir / wheel["file"]
    subprocess.run(["az", "storage", "blob", "download", *common, "--file", str(downloaded),
                    "--output", "none"], check=True)
    if digest(downloaded) != wheel["sha256"]:
        raise ValueError("Stored wheel differs from the qualified candidate; no overwrite was attempted.")
    print(f"Verified storage wheel {wheel['file']} with SHA-256 {wheel['sha256']}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=[
        "access", "options", "plan", "resolve", "checkout", "build", "candidate", "verify", "integrate", "cancel",
        "verify-integration", "feed-environment", "prepare-publication", "publish", "index", "upload",
    ])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--prepared", type=Path)
    args = parser.parse_args()
    if args.operation == "access":
        check_access()
    elif args.operation == "options":
        mode, create_index_pr = release_options()
        print(json.dumps({"mode": mode, "createIndexPr": create_index_pr}))
    elif args.operation == "plan":
        print(json.dumps({
            "sourceBranch": branch(environment("RELEASE_SOURCE_BRANCH")),
            "mode": "Plan only; governed onboarding; no qualification, release, tag, or index PR.",
            "integrationPipeline": 164, "unitMatrix": "Python 3.10-3.13 on Ubuntu, Windows and macOS",
        }, indent=2))
    elif args.operation in ("resolve", "checkout"):
        checkout(args.source, resolving=args.operation == "resolve")
    elif args.operation == "candidate":
        create_candidate(args.source, args.directory)
    elif args.operation == "build":
        build_candidate(args.source, args.work_dir)
    elif args.operation == "feed-environment":
        configure_feed()
    elif args.operation == "prepare-publication":
        prepare_publication(args.directory, args.prepared, args.work_dir)
    elif args.operation == "verify":
        verify_candidate(args.directory)
    elif args.operation == "integrate":
        integrate(args.directory, args.record)
    elif args.operation == "cancel":
        cancel_integration(args.record, args.directory)
    elif args.operation == "verify-integration":
        verify_integration_artifacts(args.directory, args.work_dir)
    elif args.operation == "publish":
        publish(args.directory, args.record, args.prepared)
    elif args.operation == "upload":
        upload_wheel(args.directory, args.work_dir)
    elif args.operation == "index":
        result = index_pull_request(args.directory, args.record, args.work_dir, args.prepared)
        write(args.work_dir / "index-pr.json", result)


if __name__ == "__main__":
    main()
