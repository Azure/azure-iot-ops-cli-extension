# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Release orchestration with immutable candidates and explicit external publication."""

import argparse
import base64
from email.parser import Parser
from email.utils import formatdate
import hashlib
from http.client import HTTPException
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
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID
import zipfile
import zlib


REPOSITORY = "Azure/azure-iot-ops-cli-extension"
INDEX_REPOSITORY = "Azure/azure-cli-extensions"
ADO = "https://dev.azure.com/azureiotdevxp/aziotcli/_apis"
PERMISSIONS = "https://dev.azure.com/azureiotdevxp/_apis/permissions"
FEED = "https://pkgs.dev.azure.com/azureiotdevxp/aziotcli/_packaging/pip/pypi/simple/"
BLOB_CONTAINER = "https://azedgecli.blob.core.windows.net/drop/"
MAX_BLOB_BYTES = 256 * 1024 * 1024
PUBLICATION_JOB = "Publish.Publish.__default"
PUBLICATION_TASK = "Stage draft or publish release"
OWNERSHIP_ATTACHMENT = "azure-cli.release-ownership"
OWNERSHIP_FILE = "release-ownership.json"
INTEGRATION_PARAMETERS = {
    "mode": "Integration tests", "pythonVersions": ["3.13"], "upgradeBaselines": "{}",
    "scenarioTimeoutMinutes": 360, "cloud": "Public",
}
CLUSTER_REGIONS = {
    "eastus": "East US", "eastus2": "East US 2", "westus": "West US", "westus2": "West US 2",
    "westus3": "West US 3", "southcentralus": "South Central US", "westeurope": "West Europe",
    "northeurope": "North Europe", "germanywestcentral": "Germany West Central",
}


def validate_cluster_region(value, cloud="AzureCloud"):
    allowed = {"usgovvirginia"} if cloud == "AzureUSGovernment" else CLUSTER_REGIONS
    if cloud not in {"AzureCloud", "AzureUSGovernment"} or not isinstance(value, str) or value not in allowed:
        raise ValueError("Select a supported Arc/AIO cluster region.")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BlobUploadError(RuntimeError):
    def __init__(self, code, message, *, existing=None):
        super().__init__(message)
        self.code = code
        self.existing = existing
        self.wheel = None
        self.size = None


def ado_escape(value):
    return (str(value).replace("%", "%AZP25").replace("\r", "%0D").replace("\n", "%0A")
            .replace(";", "%3B").replace("]", "%5D"))


def report_blob_upload(receipt, *, result=None, error=None):
    wheel = result["candidate"]["wheel"] if result else error.wheel
    size = result["length"] if result else error.size
    if result:
        message = ("Wheel uploaded and verified." if result["status"] == "uploaded"
                   else "Identical wheel already exists; upload skipped.")
        lines = [message]
    else:
        message = str(error)
        lines = [f"{error.code}: {message}", "This job cannot proceed to release or index publication."]
    if wheel:
        label = "Existing wheel" if error and error.code == "RELEASE_BLOB_CONFLICT" else (
            "Verified wheel" if result else "Target location (contents not verified)")
        url = BLOB_CONTAINER + quote(wheel["file"], safe="")
        lines += [f"{label}: {url}", f"Candidate: {size} bytes; SHA-256 {wheel['sha256']}"]
    build = os.environ.get("BUILD_BUILDID", "")
    if re.fullmatch(r"[1-9][0-9]*", build):
        artifact_url = f"{ADO.removesuffix('/_apis')}/_build/results?buildId={build}&view=artifacts"
        lines.append(f"Candidate artifact (release-candidate): {artifact_url}")
    if error:
        if error.existing is not None:
            label = "Existing" if error.code == "RELEASE_BLOB_CONFLICT" else "Observed blob"
            lines.append(
                f"{label}: {error.existing['length']} bytes; SHA-256 "
                + error.existing.get("sha256", "not computed: size differs from the candidate.")
            )
        if error.code == "RELEASE_BLOB_CONFLICT":
            lines += [
                "The existing blob was not overwritten; refusing overwrite.",
                "For changed content, bump the extension version and build again.",
                "For a retry, rerun the upload/publish job in the original pipeline run "
                "to reuse its approved wheel artifact. "
                "Rebuilding the same version may produce different bytes.",
            ]
        elif error.code == "RELEASE_BLOB_AUTH":
            lines.append(
                "Check authentication and Blob data permissions for service connection sc-cli-release-storage.")
        elif error.code == "RELEASE_CANDIDATE_INVALID":
            lines.append("Check the specific validation reason above, this run's pipeline variables, "
                         "and the release-candidate manifest; do not change Blob storage.")
        elif error.existing is not None:
            lines.append("Investigate the unexpected stored content before retrying. "
                         "A retry cannot repair different bytes; never delete or overwrite the blob.")
        else:
            lines.append("The blob may already exist. Retry the upload/publish job in the original pipeline run "
                         "with its approved wheel artifact; never overwrite it.")
    for line in lines:
        print(line, flush=True)
    if error:
        print(f"##vso[task.logissue type=error;code={error.code}]{ado_escape(message)}", flush=True)
    summary = Path(receipt).with_suffix(".md")
    try:
        summary.parent.mkdir(parents=True, exist_ok=True)
        markdown = []
        for line in lines:
            if ": https://" in line:
                label, url = line.split(": ", 1)
                markdown.append(f"- [{label}]({url})")
            else:
                markdown.append("- " + re.sub(r"([\\`*_{}\[\]<>()!|])", r"\\\1", line))
        summary.write_text("## Wheel Blob upload\n\n" + "\n\n".join(markdown) + "\n", encoding="utf-8")
    except OSError:
        if not error:
            raise
        print("##vso[task.logissue type=warning]Could not write the Blob upload summary; see the error above.",
              flush=True)
    else:
        print(f"##vso[task.uploadsummary]{ado_escape(summary.resolve())}", flush=True)


def environment(name):
    value = os.environ.get(name, "").strip()
    if not value or "$(" in value or "\n" in value or "\r" in value:
        raise ValueError(f"Configure {name} explicitly; unresolved pipeline variables are not allowed.")
    return value


def skip_integration_tests():
    value = os.environ.get("RELEASE_SKIP_INTEGRATION_TESTS", "false").lower()
    if value not in {"true", "false"}:
        raise ValueError("skipIntegrationTests must be an explicit boolean.")
    return value == "true"


def upload_wheel_to_blob():
    value = os.environ.get("RELEASE_UPLOAD_WHEEL_TO_BLOB", "false").lower()
    if value not in {"true", "false"}:
        raise ValueError("uploadWheelToBlob must be an explicit boolean.")
    return value == "true"


def identifier(value):
    if not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("Expected a positive build or pipeline ID.")
    return str(value)


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected an immutable, lowercase 40-character commit SHA.")
    return value


def branch(value):
    if not isinstance(value, str) or value.startswith("refs/") and not value.startswith("refs/heads/"):
        raise ValueError("Source must be a safe branch name, not a tag or revision expression.")
    value = value.removeprefix("refs/heads/")
    if (not value or value.startswith("-") or value.endswith(".")
            or any(ord(char) < 33 or ord(char) == 127 or char in "~^:?*[\\" for char in value)
            or any(part in value for part in ("..", "@{"))
            or any(not part or part.startswith(".") or part.endswith(".lock") for part in value.split("/"))):
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
    definition = ado("build/definitions/164")
    folder = definition["path"].replace("\\", "/").strip("/")
    token = "/".join(part for part in (environment("SYSTEM_TEAMPROJECTID"), folder, "164") if part)
    query = urlencode({"tokens": token,
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
        if release_options()[0] in {"Draft", "Release"} or upload_wheel_to_blob():
            automation_allowed()
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
        prerequisites = () if skip_integration_tests() else (
            ".azure-devops/templates/integration-pipeline.yml", "tools/ado_integration.py",
            "tools/release_pipeline.py", ".github/test-scenarios.yml",
        )
        for relative in prerequisites:
            if not (destination / relative).is_file():
                raise ValueError(f"Source branch needs the migration/index-check prerequisites: {relative}")
        if not skip_integration_tests():
            integration = (destination / ".azure-devops/integration.yml").read_text(encoding="utf-8")
            if "ReleaseCandidateBuildId" not in integration:
                raise ValueError("The selected source does not support pipeline 164's release-candidate handoff.")
            if "clusterRegion" not in integration:
                raise ValueError("The selected source does not support explicit integration cluster regions.")
        print(f"##vso[task.setvariable variable=commit;isOutput=true]{selected}", flush=True)
        # Early title from source; Record candidate re-sets it from the built wheel.
        constants = destination / "azext_edge/constants.py"
        version = constants.is_file() and re.search(
            r'^VERSION = "([^"]+)"$', constants.read_text(encoding="utf-8"), re.MULTILINE)
        if version:
            cohorts = {} if skip_integration_tests() else source_cohorts(destination)
            channels = [item["row"]["scenario"]["channel"] for item in cohorts.values()]
            naming = runpy.run_path(str(Path(__file__).with_name("pipeline_title.py")))
            runtimes = naming["source_runtimes"](destination, channels) if channels else ()
            print(f"##vso[build.updatebuildnumber]{release_title(version.group(1), cohorts, runtimes)}", flush=True)
    return selected


def release_title(version, cohorts, runtimes):
    naming = runpy.run_path(str(Path(__file__).with_name("pipeline_title.py")))
    return naming["format_title"](
        "ops", identifier(environment("BUILD_BUILDID")), version,
        scopes=[item["selection"] for item in cohorts.values()],
        regions=[environment("RELEASE_REGION")] if cohorts else (),
        runtimes=runtimes, channels=[item["row"]["scenario"]["channel"] for item in cohorts.values()],
        action=release_options()[0].lower(),
    )


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 1024 * 1024:
            raise ValueError("Expected one bounded wheel METADATA document.")
        if archive.getinfo(names[0]).flag_bits & 1:
            raise ValueError("Encrypted wheel METADATA is not supported.")
        try:
            metadata = archive.read(names[0])
        except NotImplementedError as error:
            raise ValueError("Wheel METADATA uses unsupported ZIP features or compression.") from error
        except zlib.error as error:
            raise ValueError("Wheel METADATA contains corrupt DEFLATE data.") from error
        value = Parser().parsestr(metadata.decode("utf-8"))
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


def unit_dependencies(source, directory, check=False):
    venv = source / ".tox/python"
    python = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    env = feed_environment()
    if not check:
        subprocess.run([python, "-m", "pip", "list", "--format=json"], env=env, check=True)
        subprocess.run([python, "-m", "pip", "check"], env=env, check=True)
        constraints = subprocess.check_output([
            python, "-c",
            "from importlib.metadata import requires\nfrom packaging.requirements import Requirement\n"
            "for name in ('azure-cli', 'azure-cli-core'):\n"
            "    for value in requires(name):\n"
            "        requirement = Requirement(value)\n"
            "        requirement.extras.clear()\n"
            "        print(requirement)\n",
        ], env=env, text=True)
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "cli-constraints.txt"
        path.write_text(constraints, encoding="utf-8")
        print(f"##vso[task.setvariable variable=PIP_CONSTRAINT]{path.resolve()}", flush=True)
        return
    site = Path(subprocess.check_output(
        [python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], text=True).strip())
    target = site / "azure-cli-extensions/azure-iot-ops"
    if not target.is_dir():
        raise ValueError("The tested extension dependency directory is missing.")
    env["PYTHONPATH"] = str(target)
    subprocess.run([python, "-m", "pip", "check"], env=env, check=True)
    requirements = subprocess.check_output(
        [python, "-m", "pip", "freeze", "--path", str(target)], env=env, text=True)
    if not re.search(r"(?m)^azure-iot-ops(?:==| @ )", requirements):
        raise ValueError("The tested extension is missing from its dependency inventory.")
    (directory / "requirements.txt").write_text(requirements, encoding="utf-8")


def build_candidate(source, work_dir, inventory=None):
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
    run([python, "-m", "pip", "check"])
    inventory = inventory or work_dir / "runtime-inventory"
    inventory.mkdir(parents=True, exist_ok=False)
    requirements = inventory / "requirements.txt"
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
    run([str(tool), "generate", "-b", "dist", "-bc", str(inventory), "-pn", "Azure IoT Operations CLI Extension",
         "-pv", wheel_metadata(wheel), "-ps", "Microsoft"])


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


def verify_runtime_inventory(source, inventory):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    manifest = read(source / "dist/_manifest/spdx_2.2/manifest.spdx.json")
    packages = {(canonicalize_name(p["name"]), p.get("versionInfo")) for p in manifest["packages"]}
    expected = set()
    for line in (inventory / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.url:
            if canonicalize_name(requirement.name) != "azure-iot-ops":
                raise ValueError("Unexpected direct-URL runtime dependency.")
            continue
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==":
            raise ValueError("Runtime dependency inventory must contain exact installed versions.")
        expected.add((canonicalize_name(requirement.name), pins[0].version))
    if not expected or not expected.issubset(packages):
        raise ValueError("SBOM omitted installed runtime dependencies.")
    package_ids = {p["SPDXID"] for p in manifest["packages"] if p["SPDXID"] != "SPDXRef-RootPackage"}
    if not any(r["relationshipType"] == "DEPENDS_ON" and r["spdxElementId"] in package_ids
               and r["relatedSpdxElement"] in package_ids for r in manifest["relationships"]):
        raise ValueError("SBOM has no resolved dependency graph; source-only fallback is not sufficient.")


def integration_parameters(candidate):
    scenarios = list(dict.fromkeys(item["selection"] for item in candidate["cohorts"].values()))
    return dict(INTEGRATION_PARAMETERS, clusterRegion=CLUSTER_REGIONS[candidate["region"]],
                releaseBuildId=candidate["producer"]["build"],
                testScenarios=scenarios, runtimeChannels=["Stable", "Preview"])


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
        "region": environment("RELEASE_REGION"),
        "wheel": {"file": wheel.name, "sha256": digest(wheel), "version": wheel_metadata(wheel)},
        "sbom": {"file": "SBOM.zip", "sha256": digest(directory / "SBOM.zip")},
        "skipIntegrationTests": skip_integration_tests(),
        "uploadWheelToBlob": upload_wheel_to_blob(),
        "cohorts": {} if skip_integration_tests() else source_cohorts(source),
    }
    write(directory / "candidate.json", value)
    verify_candidate(directory)
    naming = runpy.run_path(str(Path(__file__).with_name("pipeline_title.py")))
    channels = [item["row"]["scenario"]["channel"] for item in value["cohorts"].values()]
    runtimes = naming["wheel_runtimes"](wheel, channels) if channels else ()
    title = release_title(value["wheel"]["version"], value["cohorts"], runtimes)
    print(f"##vso[build.updatebuildnumber]{title}", flush=True)
    return value


def validate_manifest_fields(value, fields, context):
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object.")
    for field, expected_type in fields.items():
        if type(value.get(field)) is not expected_type:
            raise ValueError(f"{context} field '{field}' is missing or has an invalid type.")


def verify_candidate(directory, *, expected_producer=None, source_branch=None, source_commit=None, consumer=None):
    value = read(directory / "candidate.json")
    validate_manifest_fields(value, {
        "schema": int, "repository": str, "producer": dict, "sourceBranch": str,
        "sourceCommit": str, "region": str, "wheel": dict, "sbom": dict,
    }, "Candidate manifest")
    validate_manifest_fields(value["wheel"], {"file": str, "sha256": str, "version": str}, "Candidate wheel")
    validate_manifest_fields(value["sbom"], {"file": str, "sha256": str}, "Candidate SBOM")
    if (type(value["schema"]) is not int or value["schema"] != 1 or value["repository"] != REPOSITORY
            or value["producer"] != (expected_producer or producer())
            or value["sourceBranch"] != branch(source_branch or environment("RELEASE_SOURCE_BRANCH"))
            or value["sourceCommit"] != commit(source_commit or environment("RELEASE_SOURCE_COMMIT"))):
        raise ValueError("Candidate provenance does not match this release run and source.")
    skipped = value.get("skipIntegrationTests", False)
    expected_skip = False if expected_producer is not None or consumer is not None else skip_integration_tests()
    if type(skipped) is not bool or skipped != expected_skip:
        raise ValueError("Candidate integration waiver does not match this release run or consumer.")
    upload = value.get("uploadWheelToBlob", False)
    if (type(upload) is not bool or expected_producer is None and consumer is None
            and upload != upload_wheel_to_blob()):
        raise ValueError("Candidate Blob upload option does not match this release run.")
    validate_cluster_region(value["region"])
    if expected_producer is None and consumer is None and value["region"] != environment("RELEASE_REGION"):
        raise ValueError("Candidate region differs from this release run.")
    cohorts = value.get("cohorts")
    if not isinstance(cohorts, dict) or (bool(cohorts) == skipped):
        raise ValueError("Missing full release cohort inventory.")
    selections = set()
    for key, cohort in cohorts.items():
        validate_manifest_fields(cohort, {"row": dict, "selection": str}, "Candidate cohort")
        row = cohort["row"]
        validate_manifest_fields(row, {"scenario": dict, "key": str, "python": str}, "Candidate cohort row")
        validate_manifest_fields(row["scenario"], {"channel": str, "name": str}, "Candidate cohort scenario")
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
        if handoff != {"consumer": consumer, "candidateSha256": digest(directory / "candidate.json")}:
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


def queued_release_build_id(build):
    variables = build.get("parameters")
    if variables is None:
        return "0"
    if isinstance(variables, str):
        variables = json.loads(variables)
    if not isinstance(variables, dict):
        raise ValueError("Invalid queued integration variables.")
    value = str(variables.get("ReleaseCandidateBuildId", "0"))
    if not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ValueError("Invalid queued release candidate ID.")
    return value


def validate_integration(build, candidate):
    parameters = build.get("templateParameters")
    if isinstance(parameters, str):
        parameters = json.loads(parameters)
    parameters = dict(parameters)
    if "releaseBuildId" in parameters:
        raise ValueError("Release candidate identity must come from the internal queue variable.")
    for key in ("testScenarios", "runtimeChannels", "pythonVersions"):
        if isinstance(parameters.get(key), str):
            parameters[key] = json.loads(parameters[key])
    parameters["releaseBuildId"] = identifier(queued_release_build_id(build))
    parameters["scenarioTimeoutMinutes"] = int(parameters["scenarioTimeoutMinutes"])
    expected = integration_parameters(candidate)
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
    matches = [build for build in builds if queued_release_build_id(build) == candidate["producer"]["build"]]
    for build in matches:
        try:
            validate_integration(build, candidate)
        except ValueError as error:
            raise ValueError("An owned child has an unexpected release request or source.") from error
    if len(matches) > 1:
        raise ValueError("Multiple children reference this release; resolve the duplicates before proceeding.")
    return matches[0] if matches else None


def cancel_integration(record, directory):
    candidate = verify_candidate(directory)
    if not record.exists():
        existing = existing_integration(candidate)
        if existing is None:
            print("No child of this release was found; no cancellation request was sent.", flush=True)
            return
        run = {"id": identifier(existing.get("id")), "producer": candidate["producer"]}
    else:
        run = read(record)
    if run["producer"] != candidate["producer"]:
        raise ValueError("Refusing to cancel a child owned by another release.")
    build = ado(f"build/builds/{identifier(run['id'])}")
    validate_integration(build, candidate)
    if build["status"] != "completed":
        ado(f"build/builds/{run['id']}", method="PATCH", data={"status": "cancelling"})
        print(f"Requested cancellation of pipeline 164 build {run['id']}.", flush=True)


def integrate(directory, record, timeout=25200):
    if skip_integration_tests():
        raise ValueError("Integration tests were waived; no child may be queued or qualified.")
    candidate = verify_candidate(directory)
    payload = {
        "definition": {"id": 164}, "sourceBranch": candidate["sourceBranch"],
        "sourceVersion": candidate["sourceCommit"],
        "parameters": json.dumps({"ReleaseCandidateBuildId": candidate["producer"]["build"]}),
        "templateParameters": {
            key: value if isinstance(value, str) else json.dumps(value)
            for key, value in integration_parameters(candidate).items() if key != "releaseBuildId"
        },
    }
    run = existing_integration(candidate)
    if run is None:
        if int(os.environ.get("SYSTEM_JOBATTEMPT", "1")) != 1:
            raise ValueError("No child found on a retried job; do not risk requeuing an uncertain prior request.")
        run = ado("build/builds", method="POST", data=payload)
    run_id = identifier(run["id"])
    write(record, {"id": run_id, "producer": candidate["producer"]})
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
                or handoff != {"consumer": consumer, "candidateSha256": digest(path)}):
            raise ValueError("Integration did not retain the exact candidate and consumer binding.")
    qualifications = list(artifacts.glob("ops-qualification-*/qualification.json"))
    if not qualifications:
        raise ValueError("Integration qualification evidence is missing.")
    latest = max(qualifications, key=lambda path: int(path.parent.name.removeprefix("ops-qualification-")))
    proof = read(latest)
    rows = proof["scenarios"]
    if (proof.get("producer") != consumer or proof.get("sha256") != candidate["wheel"]["sha256"]
            or proof.get("releaseCandidate") != candidate
            or sorted(str(row.get("row")) for row in rows) != sorted(candidate["cohorts"])):
        raise ValueError("Incomplete release cohort evidence or cleanup.")
    for row in rows:
        scenario = candidate["cohorts"][row["row"]]["row"]["scenario"]
        expected_phases = {"init", "smoke"}
        if scenario["tox_env"]:
            expected_phases.add("scenario")
        if scenario["test_redeploy"]:
            expected_phases.add("redeploy")
        if (row.get("producer") != consumer or row.get("sha256") != candidate["wheel"]["sha256"]
                or row.get("cleanup") != "passed" or row.get("status") != "passed"
                or any(row.get("phases", {}).get(phase) != "passed" for phase in expected_phases)):
            raise ValueError("Incomplete release cohort evidence or cleanup.")
    print(f"Qualified {len(rows)} cohorts against wheel SHA-256 {candidate['wheel']['sha256']}.", flush=True)


def automation_allowed():
    branch(environment("RELEASE_SOURCE_BRANCH"))
    if environment("BUILD_SOURCEBRANCH") != "refs/heads/dev":
        raise ValueError("Publication requires the reviewed release automation on dev, not a feature branch.")
    if environment("BUILD_REPOSITORY_NAME") != REPOSITORY:
        raise ValueError("Publication is only allowed from the upstream repository.")


def release_options():
    mode = os.environ.get("RELEASE_MODE", "Validate")
    index = os.environ.get("RELEASE_CREATE_INDEX_PR", "false").lower()
    skip_integration_tests()
    upload_wheel_to_blob()
    if mode not in {"Validate", "Draft", "Release"} or index not in {"true", "false"}:
        raise ValueError("Invalid release mode or createIndexPr option.")
    if index == "true" and mode != "Release":
        raise ValueError("createIndexPr requires Release mode and a public GitHub release.")
    return mode, index == "true"


def publication_allowed(*, draft=False, upload=False):
    mode, _ = release_options()
    if upload:
        if not upload_wheel_to_blob():
            raise ValueError("Blob upload requires explicit uploadWheelToBlob opt-in.")
    else:
        expected = "Draft" if draft else "Release"
        if mode != expected:
            raise ValueError(f"Publication requires explicit {expected} mode.")
    automation_allowed()
    if not upload:
        environment("RELEASE_GITHUB_TOKEN")


def storage_token():
    try:
        result = subprocess.run([
            "az", "account", "get-access-token", "--resource", "https://storage.azure.com/",
            "--output", "json", "--only-show-errors",
        ], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise BlobUploadError(
            "RELEASE_BLOB_AUTH", "Storage authentication failed: Azure CLI could not obtain a token.") from None
    if result.returncode:
        raise BlobUploadError(
            "RELEASE_BLOB_AUTH", "Storage authentication failed: check the approved WIF service connection.")
    try:
        token = json.loads(result.stdout)["accessToken"]
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BlobUploadError("RELEASE_BLOB_AUTH",
                              "Storage authentication failed: Azure CLI returned an invalid token response.") from None
    return token


def blob_request(url, token, *, size, data=None):
    filename = unquote(urlsplit(url).path.removeprefix("/drop/"))
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]*\.whl", filename)
            or url != BLOB_CONTAINER + quote(filename, safe="")):
        raise ValueError("Unapproved Blob destination; only the fixed drop container is allowed.")
    if not 0 < size <= MAX_BLOB_BYTES or data is not None and len(data) != size:
        raise ValueError("Candidate wheel exceeds the bounded Blob size or has changed length.")
    method = "GET" if data is None else "PUT"
    headers = {
        "Authorization": f"Bearer {token}", "x-ms-version": "2023-11-03",
        "x-ms-date": formatdate(usegmt=True),
    }
    if data is not None:
        headers.update({
            "If-None-Match": "*", "x-ms-blob-type": "BlockBlob",
            "Content-Type": "application/octet-stream", "Content-Length": str(size),
        })
    request = Request(url, method=method, data=data, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            if response.status != (200 if data is None else 201):
                raise BlobUploadError(
                    "RELEASE_BLOB_UNVERIFIED", f"{method} Blob request returned unexpected HTTP {response.status}.")
            if data is not None:
                return {"status": 201}
            if response.headers.get("Content-Length") != str(size):
                length = response.headers.get("Content-Length", "")
                if not re.fullmatch(r"[0-9]{1,20}", length):
                    raise BlobUploadError(
                        "RELEASE_BLOB_UNVERIFIED", "Blob response is missing a valid content length.")
                raise BlobUploadError(
                    "RELEASE_BLOB_CONFLICT",
                    "This wheel filename already exists with different content; refusing overwrite.",
                    existing={"length": int(length)},
                )
            actual = hashlib.sha256()
            length = 0
            deadline = time.monotonic() + 120
            while True:
                if time.monotonic() > deadline:
                    raise BlobUploadError(
                        "RELEASE_BLOB_UNVERIFIED", "Blob verification exceeded its download deadline.")
                chunk = response.read1(min(64 * 1024, size - length + 1))
                if not chunk:
                    break
                length += len(chunk)
                if length > size:
                    raise BlobUploadError(
                        "RELEASE_BLOB_UNVERIFIED", "Blob download exceeds the candidate length; contents not verified.")
                actual.update(chunk)
            if length != size:
                raise BlobUploadError(
                    "RELEASE_BLOB_UNVERIFIED", "Blob download is incomplete; candidate length verification failed.")
            return {"status": 200, "sha256": actual.hexdigest(), "length": length}
    except HTTPError as error:
        error.close()
        if (method == "GET" and error.code == 404 or method == "PUT" and error.code in {409, 412}):
            return {"status": error.code}
        reason = "authorization failed" if error.code in {401, 403} else "request failed"
        raise BlobUploadError(
            "RELEASE_BLOB_AUTH" if error.code in {401, 403} else "RELEASE_BLOB_UNVERIFIED",
            f"{method} Blob {reason} with HTTP {error.code}; no automatic write retry.",
        ) from None
    except (URLError, OSError, HTTPException):
        raise BlobUploadError(
            "RELEASE_BLOB_UNVERIFIED",
            f"{method} Blob network request failed; contents not verified; no automatic write retry.",
        ) from None


def prepare_upload(directory, tooling):
    verify_candidate(directory)
    tooling.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), tooling / "release_pipeline.py")


def upload_wheel(directory, receipt):
    try:
        publication_allowed(upload=True)
        candidate = verify_candidate(directory)
    except ValueError as error:
        raise BlobUploadError("RELEASE_CANDIDATE_INVALID", f"Upload validation failed: {error}") from None
    except FileNotFoundError:
        raise BlobUploadError("RELEASE_CANDIDATE_INVALID", "A required candidate artifact file is missing.") from None
    except zipfile.BadZipFile:
        raise BlobUploadError(
            "RELEASE_CANDIDATE_INVALID", "The candidate wheel is not a valid ZIP archive."
        ) from None
    wheel = candidate["wheel"]
    path = directory / wheel["file"]
    size = path.stat().st_size
    if not 0 < size <= MAX_BLOB_BYTES:
        raise BlobUploadError("RELEASE_CANDIDATE_INVALID", "Candidate wheel exceeds the bounded Blob size.")
    data = path.read_bytes()
    if len(data) != size or hashlib.sha256(data).hexdigest() != wheel["sha256"]:
        raise BlobUploadError("RELEASE_CANDIDATE_INVALID", "Candidate wheel changed before upload.")
    url = BLOB_CONTAINER + quote(wheel["file"], safe="")
    status = "already-present"
    try:
        token = storage_token()
        observed = blob_request(url, token, size=size)
        if observed["status"] == 404:
            created = blob_request(url, token, size=size, data=data)
            status = "uploaded" if created["status"] == 201 else "already-present"
            for attempt in range(3):
                observed = blob_request(url, token, size=size)
                if observed["status"] != 404:
                    break
                if attempt < 2:
                    time.sleep(attempt + 1)
        if observed["status"] != 200:
            raise BlobUploadError(
                "RELEASE_BLOB_UNVERIFIED",
                "Blob create or create-race could not be verified after three bounded reads.")
        if observed["sha256"] != wheel["sha256"] or observed["length"] != size:
            raise BlobUploadError(
                "RELEASE_BLOB_CONFLICT",
                "This wheel filename already exists with different content; refusing overwrite.", existing=observed)
    except BlobUploadError as error:
        if status == "uploaded" and error.code == "RELEASE_BLOB_CONFLICT":
            error = BlobUploadError(
                "RELEASE_BLOB_UNVERIFIED",
                "Upload was accepted, but the stored wheel differs from the candidate on read-back.",
                existing=error.existing,
            )
        error.wheel, error.size = wheel, size
        raise error from None
    result = {
        "mode": release_options()[0], "status": status, "wheelUrl": url,
        "sha256": wheel["sha256"], "length": size, "candidate": candidate,
    }
    write(receipt, result)
    return result


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


def timeline_guid(value):
    if not isinstance(value, str) or str(UUID(value)) != value.lower():
        raise ValueError("Expected a canonical ADO timeline or record ID.")
    return value.lower()


def ownership_record(candidate, release_id, job_id):
    return {
        "schema": 1, "candidate": candidate, "release": int(identifier(release_id)),
        "tag": f"v{candidate['wheel']['version']}", "job": timeline_guid(job_id),
    }


def previous_publication_records(build_id, record, kind, timelines):
    pending = []
    for reference in record.get("previousAttempts", []):
        timeline_id = timeline_guid(reference["timelineId"])
        if timeline_id not in timelines:
            if len(timelines) >= 100:
                raise ValueError("Publication retry history exceeds the bounded ownership inventory.")
            timelines[timeline_id] = ado(f"build/builds/{build_id}/timeline/{timeline_id}")
            if timeline_guid(timelines[timeline_id]["id"]) != timeline_id:
                raise ValueError("Publication retry timeline identity changed.")
        pending.append((timelines[timeline_id], timeline_guid(reference["recordId"]), kind))
    return pending


def publication_ownership(candidate):
    """Read receipts only from this run's protected publisher task and its retries."""
    origin = candidate["producer"]
    build_id = identifier(origin["build"])
    build = ado(f"build/builds/{build_id}")
    if (str(build.get("id")) != build_id or str(build.get("definition", {}).get("id")) != origin["definition"]
            or build.get("project", {}).get("id") != environment("SYSTEM_TEAMPROJECTID")
            or build.get("sourceVersion") != origin["commit"] or build.get("sourceBranch") != "refs/heads/dev"
            or build.get("repository", {}).get("type") != "GitHub"
            or build.get("repository", {}).get("id") != REPOSITORY):
        raise ValueError("Publication ownership must belong to this approved automation run.")
    current = ado(f"build/builds/{build_id}/timeline")
    jobs = [row for row in current["records"] if row["type"] == "Job" and row.get("identifier") == PUBLICATION_JOB]
    if (len(jobs) != 1 or timeline_guid(jobs[0]["id"]) != timeline_guid(environment("SYSTEM_JOBID"))
            or str(jobs[0]["attempt"]) != identifier(environment("SYSTEM_JOBATTEMPT"))):
        raise ValueError("Cannot identify the current protected publication job.")
    if len([row for row in current["records"] if row["type"] == "Task"
            and row.get("parentId") == jobs[0]["id"] and row.get("name") == PUBLICATION_TASK]) != 1:
        raise ValueError("Cannot identify the current protected publisher task.")

    pending = [(current, jobs[0]["id"], "Job")]
    visited, timelines, receipts = set(), {timeline_guid(current["id"]): current}, []
    stages = [row for row in current["records"] if row["type"] == "Stage" and row.get("identifier") == "Publish"]
    if len(stages) != 1:
        raise ValueError("Cannot identify the protected publication stage.")

    pending.extend(previous_publication_records(build_id, stages[0], "Stage", timelines))
    while pending:
        timeline, record_id, kind = pending.pop()
        timeline_id, record_id = timeline_guid(timeline["id"]), timeline_guid(record_id)
        key = (timeline_id, record_id, kind)
        if key in visited:
            continue
        visited.add(key)
        records = {timeline_guid(row["id"]): row for row in timeline["records"]}
        record = records.get(record_id)
        expected = "Publish" if kind == "Stage" else PUBLICATION_JOB
        if record is None or record["type"] != kind or record.get("identifier") != expected:
            raise ValueError("Publication retry history does not identify a protected publisher.")
        pending.extend(previous_publication_records(build_id, record, kind, timelines))
        if kind == "Stage":
            for row in records.values():
                if row["type"] == "Job" and row.get("identifier") == PUBLICATION_JOB:
                    pending.append((timeline, row["id"], "Job"))
            continue
        if record_id != timeline_guid(jobs[0]["id"]) and record.get("state") != "completed":
            raise ValueError("A previous publication job is still active; refusing concurrent recovery.")
        phase = records.get(timeline_guid(record["parentId"]))
        stage = records.get(timeline_guid(phase["parentId"])) if phase and phase["type"] == "Phase" else None
        if stage is None or stage["type"] != "Stage" or stage.get("identifier") != "Publish":
            raise ValueError("Publication job is outside the protected Publish stage.")
        tasks = [row for row in records.values() if row["type"] == "Task"
                 and row.get("parentId") == record["id"] and row.get("name") == PUBLICATION_TASK]
        if len(tasks) > 1:
            raise ValueError("Publication retry has ambiguous publisher task records.")
        for task in tasks:
            task_id = timeline_guid(task["id"])
            receipt = ado(
                f"build/builds/{build_id}/{timeline_id}/{task_id}/attachments/"
                f"{OWNERSHIP_ATTACHMENT}/{OWNERSHIP_FILE}", missing=True,
            )
            if receipt is None:
                continue
            if (not isinstance(receipt, dict) or type(receipt.get("schema")) is not int
                    or receipt != ownership_record(candidate, receipt.get("release"), record_id)):
                raise ValueError("Publication ownership receipt belongs to a different run or candidate.")
            receipts.append(receipt)
    if len({receipt["release"] for receipt in receipts}) > 1:
        raise ValueError("This run has conflicting GitHub publication ownership receipts.")
    return receipts[0] if receipts else None


def attach_publication_receipt(path):
    # The agent retains this on the emitting publisher task, including failed attempts.
    escaped = str(path.resolve()).replace("%", "%AZP25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"##vso[task.addattachment type={OWNERSHIP_ATTACHMENT};name={OWNERSHIP_FILE}]{escaped}", flush=True)


def retain_publication_ownership(candidate, release_id, receipt):
    job_id = timeline_guid(environment("SYSTEM_JOBID"))
    value = ownership_record(candidate, release_id, job_id)
    path = Path(receipt).parent / "ownership" / job_id / OWNERSHIP_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or read(path) != value:
            raise ValueError("Publication ownership file already contains different evidence.")
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
    attach_publication_receipt(path)


def verify_public_assets(release, candidate):
    if release["draft"]:
        raise ValueError("The qualified release is not public.")
    verify_assets(release, candidate)


def verify_assets(release, candidate):
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


def publication_release(candidate, preparation, receipt, draft_only):
    waiver = "Integration tests skipped by release waiver." if candidate.get("skipIntegrationTests") else ""
    version = candidate["wheel"]["version"]
    tag = f"v{version}"
    existing_tag = tag_commit(tag)
    release = find_release(tag)
    if release is not None:
        state = "draft" if release["draft"] else "published release"
        url = release.get("html_url") or f"https://github.com/{REPOSITORY}/releases/tag/{quote(tag, safe='')}"
        if not isinstance(url, str) or not url.startswith(f"https://github.com/{REPOSITORY}/releases/") or any(
                char in url for char in ("\r", "\n")):
            raise ValueError("Existing release has an unexpected GitHub URL.")
        print(f"Existing {state} for {tag}: {url}", flush=True)
        if draft_only and not release["draft"]:
            raise ValueError(f"Draft cannot reuse or modify an already published release: {url}")
    if existing_tag is not None and existing_tag != candidate["sourceCommit"]:
        raise ValueError("Existing release tag points to another commit; it will not be moved.")
    owned = publication_ownership(candidate)
    if release is not None and (not isinstance(owned, dict) or owned.get("release") != int(identifier(release["id"]))):
        raise ValueError(
            f"{tag} already exists as a {state}: {url}. It belongs to another run or ownership is unknown. "
            "A new publication run cannot reuse or promote it. Review the existing release in GitHub; "
            "retry the original Publish job only when its ownership receipt is available."
        )
    if release is None and owned is not None:
        raise ValueError("This run already owns a GitHub release that is no longer present; inspect it manually.")
    if release is None:
        release = github(f"repos/{REPOSITORY}/releases", method="POST", data={
            "tag_name": tag, "target_commitish": candidate["sourceCommit"],
            "name": f"azure-iot-ops {version}", "draft": True,
            "prerelease": preparation["prerelease"], "generate_release_notes": True, "body": waiver,
        })
        retain_publication_ownership(candidate, release["id"], receipt)
    if (release.get("tag_name") != tag
            or release["target_commitish"] != candidate["sourceCommit"] and existing_tag != candidate["sourceCommit"]
            or release["prerelease"] != preparation["prerelease"]):
        raise ValueError("Existing release has different tag, source or prerelease metadata.")
    return release


def publish(directory, receipt, prepared):
    draft_only = release_options()[0] == "Draft"
    publication_allowed(draft=draft_only)
    candidate, preparation = verify_publication_inputs(directory, prepared)
    waiver = "Integration tests skipped by release waiver." if candidate.get("skipIntegrationTests") else ""
    version = candidate["wheel"]["version"]
    tag = f"v{version}"
    release = publication_release(candidate, preparation, receipt, draft_only)
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
    if waiver and waiver not in (release.get("body") or ""):
        if not release["draft"]:
            raise ValueError("Published release does not record the integration waiver; refusing to edit it.")
        github(f"repos/{REPOSITORY}/releases/{release['id']}", method="PATCH",
               data={"body": waiver + "\n\n" + (release.get("body") or "")})
    if draft_only:
        staged = github(f"repos/{REPOSITORY}/releases/{release['id']}")
        if (not staged["draft"] or staged.get("tag_name") != tag
                or staged["target_commitish"] != candidate["sourceCommit"]
                or staged["prerelease"] != preparation["prerelease"]
                or waiver and waiver not in (staged.get("body") or "")
                or tag_commit(tag) not in (None, candidate["sourceCommit"])):
            raise ValueError("Staged release identity or integration waiver changed.")
        verify_assets(staged, candidate)
        result = {"release": release["id"], "tag": tag, "draft": True, "candidate": candidate}
        write(receipt, result)
        print(f"Staged draft {release['id']} for {tag}; no tag creation, publication or index PR.", flush=True)
        return result
    if release["draft"]:
        current_tag = tag_commit(tag)
        if current_tag is None:
            github(f"repos/{REPOSITORY}/git/refs", method="POST",
                   data={"ref": f"refs/tags/{tag}", "sha": candidate["sourceCommit"]})
        elif current_tag != candidate["sourceCommit"]:
            raise ValueError("Tag changed during staging; release remains a draft.")
        github(f"repos/{REPOSITORY}/releases/{release['id']}", method="PATCH", data={"draft": False})
    published = github(f"repos/{REPOSITORY}/releases/{release['id']}")
    if published.get("tag_name") != tag or published.get("prerelease") != preparation["prerelease"]:
        raise ValueError("Published release identity changed.")
    verify_public_assets(published, candidate)
    if waiver and waiver not in (published.get("body") or ""):
        raise ValueError("Published release is missing its integration waiver.")
    if tag_commit(tag) != candidate["sourceCommit"]:
        raise ValueError("Published tag no longer matches the qualified commit.")
    wheel_url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{candidate['wheel']['file']}"
    result = {"release": release["id"], "tag": tag, "wheelUrl": wheel_url, "draft": False, "candidate": candidate}
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
                 + ("Integration tests skipped by release waiver. " if candidate.get("skipIntegrationTests")
                    else "Qualified by the Azure IoT Operations CLI ADO release pipeline. ")
                 + "Index-team review is required; "
                 "this automation does not merge the PR."),
    })
    print(f"Index review required: {result['html_url']}", flush=True)
    return {"status": "review-required", "url": result["html_url"]}


def run_blob_upload(directory, receipt):
    try:
        result = upload_wheel(directory, receipt)
    except BlobUploadError as error:
        report_blob_upload(receipt, error=error)
        raise SystemExit(1) from None
    report_blob_upload(receipt, result=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=[
        "access", "options", "resolve", "checkout", "build", "candidate", "verify", "integrate", "cancel",
        "verify-integration", "feed-environment", "prepare-publication", "publish", "index",
        "unit-constraints", "unit-inventory", "prepare-upload", "upload",
        "verify-runtime",
    ])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    if args.operation == "access":
        check_access()
    elif args.operation == "options":
        mode, create_index_pr = release_options()
        skipped = skip_integration_tests()
        if skipped:
            print("##vso[task.logissue type=warning]Integration tests skipped by release waiver.")
        print(json.dumps({"mode": mode, "createIndexPr": create_index_pr, "skipIntegrationTests": skipped,
                          "uploadWheelToBlob": upload_wheel_to_blob()}))
    elif args.operation in ("resolve", "checkout"):
        checkout(args.source, resolving=args.operation == "resolve")
    elif args.operation == "candidate":
        create_candidate(args.source, args.directory)
    elif args.operation == "build":
        build_candidate(args.source, args.work_dir, args.inventory)
    elif args.operation in ("unit-constraints", "unit-inventory"):
        unit_dependencies(args.source, args.directory, check=args.operation == "unit-inventory")
    elif args.operation == "verify-runtime":
        verify_runtime_inventory(args.source, args.inventory)
    elif args.operation == "feed-environment":
        configure_feed()
    elif args.operation == "prepare-publication":
        prepare_publication(args.directory, args.prepared, args.work_dir)
    elif args.operation == "prepare-upload":
        prepare_upload(args.directory, args.prepared)
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
        run_blob_upload(args.directory, args.record)
    elif args.operation == "index":
        result = index_pull_request(args.directory, args.record, args.work_dir, args.prepared)
        write(args.work_dir / "index-pr.json", result)


if __name__ == "__main__":
    main()
