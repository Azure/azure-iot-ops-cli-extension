# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Resolve and acquire published CLI releases without Azure credentials or live tests."""

import argparse
import ast
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile

from packaging.version import InvalidVersion, Version


REPOSITORIES = {
    "azure-iot": "Azure/azure-iot-cli-extension",
    "azure-iot-ops": "Azure/azure-iot-ops-cli-extension",
}
CLOUDS = {"public": "AzureCloud", "fairfax": "AzureUSGovernment", "mooncake": "AzureChinaCloud"}
HOSTS = {
    "api.github.com", "raw.githubusercontent.com", "github.com",
    "release-assets.githubusercontent.com", "objects.githubusercontent.com",
}
TEMPLATE = "azext_edge/edge/providers/orchestration/template{}.py"
MAX_BYTES = 64 * 1024 * 1024


class NonStableRuntime(ValueError):
    """A published CLI's bundled runtime is not a stable monitor target."""


def validate_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.port not in (None, 443)
            or parsed.username is not None or parsed.password is not None or parsed.fragment):
        raise ValueError("Release downloads require an approved, credential-free GitHub HTTPS URL.")


class ReleaseRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    validate_url(url)
    request = Request(url, headers={"User-Agent": "azure-iot-release-monitor"})
    with build_opener(ReleaseRedirectHandler()).open(request, timeout=60) as response:
        validate_url(response.url)
        value = response.read(MAX_BYTES + 1)
    if len(value) > MAX_BYTES:
        raise ValueError("Release download exceeds the size limit.")
    return value


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("An immutable 40-character source commit is required.")
    return value


def settings(extension):
    if extension not in REPOSITORIES:
        raise ValueError("Unknown monitored extension.")
    return {
        "extension": extension, "repository": REPOSITORIES[extension],
        "package": "azext_iot" if extension == "azure-iot" else "azext_edge",
    }


def tag_commit(repository, tag):
    ref = f"refs/tags/{tag}"
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", f"https://github.com/{repository}.git", ref, ref + "^{}"],
        check=True, capture_output=True, text=True, timeout=60,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    refs = dict(line.split()[::-1] for line in result.stdout.splitlines())
    return commit(refs.get(ref + "^{}", refs.get(ref)))


def published_releases(repository):
    releases = []
    for page in range(1, 11):
        values = json.loads(download(f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"))
        if not isinstance(values, list):
            raise ValueError("GitHub did not return a release list.")
        releases.extend(values)
        if len(values) < 100:
            return releases
    raise ValueError("Release discovery exceeded its pagination limit.")


def release_version(release):
    tag = release.get("tag_name", "")
    if not isinstance(tag, str) or not re.fullmatch(r"v[0-9][0-9A-Za-z.+-]*", tag):
        raise ValueError("Published release has an invalid version tag.")
    try:
        version = Version(tag[1:])
    except InvalidVersion as error:
        raise ValueError("Published release has an invalid version tag.") from error
    if version.is_devrelease or version.local:
        raise ValueError("Development and local builds are not published monitor targets.")
    return version


def parse_runtime_profile(source, cloud, channel="stable"):
    if channel not in {"stable", "preview"} or cloud != "public" and channel != "stable":
        raise ValueError("The selected cloud has no supported runtime channel.")
    suffix = "_preview" if channel == "preview" else "_fairfax" if cloud == "fairfax" else ""
    profiles = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        values = {key.value: value for key, value in zip(node.keys, node.values)
                  if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        if "VERSIONS" not in values or "TRAINS" not in values:
            continue
        versions, trains = ast.literal_eval(values["VERSIONS"]), ast.literal_eval(values["TRAINS"])
        if "iotOperations" not in versions:
            continue
        version = Version(versions["iotOperations"])
        train = trains.get("iotOperations")
        if not isinstance(train, str) or not train:
            raise ValueError("The bundled runtime is missing its release train.")
        profiles.append({
            "milestone": f"{version.major}.{version.minor}", "version": versions["iotOperations"],
            "train": train, "template": TEMPLATE.format(suffix),
        })
    if len(profiles) != 1:
        raise ValueError("The release does not contain one unambiguous runtime profile.")
    version = Version(profiles[0]["version"])
    if channel == "stable" and (version.is_prerelease or version.is_devrelease or profiles[0]["train"] != "stable"):
        raise NonStableRuntime("A monitored milestone must have a stable bundled runtime.")
    if channel == "preview" and profiles[0]["train"] != "preview":
        raise ValueError("The preview runtime must declare its preview release train.")
    return profiles[0]


def runtime_profile(repository, source_commit, cloud, channel="stable"):
    suffix = "_preview" if channel == "preview" else "_fairfax" if cloud == "fairfax" else ""
    url = f"https://raw.githubusercontent.com/{repository}/{commit(source_commit)}/{TEMPLATE.format(suffix)}"
    try:
        source = download(url).decode("utf-8")
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    return parse_runtime_profile(source, cloud, channel)


def wheel_asset(release, extension, version):
    name = f"{extension.replace('-', '_')}-{version}-py3-none-any.whl"
    assets = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    if len(assets) != 1:
        raise ValueError(f"Published release must contain exactly one {name}.")
    asset = assets[0]
    digest = asset.get("digest", "")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("The published wheel is missing its GitHub SHA256 digest.")
    expected = f"https://github.com/{REPOSITORIES[extension]}/releases/download/{release['tag_name']}/{name}"
    if asset.get("browser_download_url") != expected:
        raise ValueError("Wheel asset URL does not belong to the selected release.")
    return {"name": name, "url": expected, "sha256": digest.removeprefix("sha256:")}


def resolve(extension, cloud, track, automation_commit, releases=None):
    config = settings(extension)
    if cloud not in CLOUDS or extension == "azure-iot-ops" and cloud == "mooncake":
        raise ValueError("This product/cloud combination is not supported.")
    if (extension == "azure-iot" and track not in {"ga", "preview"}
            or extension == "azure-iot-ops" and not re.fullmatch(r"[1-9][0-9]*\.[0-9]+", track)):
        raise ValueError("Select GA/Preview for IoT or an explicit runtime milestone for AIO.")
    automation_commit = commit(automation_commit)
    releases = published_releases(config["repository"]) if releases is None else releases
    candidates = []
    for item in releases:
        if item.get("draft"):
            continue
        version = release_version(item)
        preview = bool(item.get("prerelease")) or version.is_prerelease
        if preview != (extension == "azure-iot" and track == "preview"):
            continue
        candidates.append((version, item))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    selected, runtime = None, None
    for version, release in candidates:
        source_commit = tag_commit(config["repository"], release["tag_name"])
        if extension == "azure-iot":
            selected = (version, release, source_commit)
            break
        try:
            profile = runtime_profile(config["repository"], source_commit, "public")
        except NonStableRuntime:
            print(f"Skipping published CLI {release['tag_name']}: no stable bundled Public runtime.", file=sys.stderr)
            continue
        if profile is None:
            raise ValueError("A published AIO release is missing its Public runtime profile.")
        if profile["milestone"] == track:
            selected = (version, release, source_commit)
            break
    if selected is None:
        raise ValueError("No matching published release was found.")
    if extension == "azure-iot-ops":
        runtime = runtime_profile(config["repository"], selected[2], cloud)
        if runtime is not None and runtime["milestone"] != track:
            raise ValueError("The cloud-specific runtime does not belong to the selected milestone.")
    version, release, source_commit = selected
    blockers = []
    if extension == "azure-iot-ops" and runtime is None:
        blockers.append("This release has no reviewed bundled runtime profile for the selected cloud.")
    manifest = {
        "schema": 1, **config, "cloud": CLOUDS[cloud], "cloudKey": cloud, "track": track,
        "automationCommit": automation_commit,
        "release": {
            "id": release["id"], "tag": release["tag_name"], "version": str(version), "commit": source_commit,
        },
        "wheel": wheel_asset(release, extension, version), "runtime": runtime, "runtimes": {"stable": runtime},
        "testSourceCommit": source_commit, "blockers": blockers,
        "releaseQualified": False,
    }
    if extension == "azure-iot-ops":
        from release_test_compatibility import compatibility
        plan = compatibility(manifest)
        if plan is not None:
            manifest["testCompatibility"] = plan
    return manifest


def validate_manifest(manifest, *, extension=None, cloud=None, track=None, slot=None, automation_commit=None):
    config = settings(manifest["extension"])
    if any(manifest.get(key) != value for key, value in config.items()) or manifest.get("schema") != 1:
        raise ValueError("Invalid release manifest repository or schema.")
    cloud_key = manifest["cloudKey"]
    if (cloud_key not in CLOUDS or manifest["cloud"] != CLOUDS[cloud_key]
            or manifest["extension"] == "azure-iot-ops" and cloud_key == "mooncake"):
        raise ValueError("Invalid release manifest cloud.")
    for key, expected in (
        ("extension", extension), ("cloudKey", cloud), ("track", track), ("slot", slot),
        ("automationCommit", automation_commit),
    ):
        if expected is not None and manifest.get(key) != expected:
            raise ValueError(f"Release manifest differs from the requested {key}.")
    if "slot" in manifest:
        allowed = {"ga", "preview"} if config["extension"] == "azure-iot" else {"v1", "v2", "v3", "preview"}
        if (manifest["slot"] not in allowed
                or config["extension"] == "azure-iot" and manifest["slot"] != manifest["track"]):
            raise ValueError("Invalid release-health support slot.")
    commit(manifest["automationCommit"])
    if commit(manifest["testSourceCommit"]) != commit(manifest["release"]["commit"]):
        raise ValueError("Test source must match the released source commit.")
    if config["extension"] == "azure-iot-ops":
        from release_test_compatibility import compatibility
        if manifest.get("testCompatibility") != compatibility(manifest):
            raise ValueError("Test compatibility differs from the frozen automation manifest.")
    version = release_version({"tag_name": manifest["release"]["tag"]})
    if str(version) != manifest["release"]["version"] or manifest.get("releaseQualified") is not False:
        raise ValueError("Invalid published version or release-qualification boundary.")
    expected_name = f"{config['extension'].replace('-', '_')}-{version}-py3-none-any.whl"
    expected_url = (
        f"https://github.com/{config['repository']}/releases/download/{manifest['release']['tag']}/{expected_name}"
    )
    if (manifest["wheel"].get("name") != expected_name or manifest["wheel"].get("url") != expected_url
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["wheel"].get("sha256", ""))):
        raise ValueError("Invalid published wheel identity.")
    if config["extension"] == "azure-iot":
        if (manifest["track"] not in {"ga", "preview"} or manifest["runtime"] is not None
                or version.is_prerelease != (manifest["track"] == "preview")):
            raise ValueError("Invalid IoT release track.")
    else:
        runtime = manifest["runtime"]
        if (version.is_prerelease or not re.fullmatch(r"[1-9][0-9]*\.[0-9]+", manifest["track"])
                or runtime is not None and (
                    runtime["milestone"] != manifest["track"] or runtime["train"] != "stable"
                    or runtime["template"] != TEMPLATE.format("_fairfax" if cloud_key == "fairfax" else ""))):
            raise ValueError("Invalid AIO milestone profile.")
        runtimes = manifest.get("runtimes")
        if (not isinstance(runtimes, dict) or set(runtimes) - {"stable", "preview"}
                or "stable" not in runtimes or runtimes["stable"] != runtime):
            raise ValueError("Invalid frozen runtime channel profiles.")
        if "preview" in runtimes:
            preview = runtimes["preview"]
            parsed = Version(preview["version"])
            if (cloud_key != "public" or preview["train"] != "preview"
                    or preview["template"] != TEMPLATE.format("_preview")
                    or preview["milestone"] != f"{parsed.major}.{parsed.minor}"):
                raise ValueError("Invalid frozen preview runtime profile.")
    expected_blockers = (
        ["This release has no reviewed bundled runtime profile for the selected cloud."]
        if config["extension"] == "azure-iot-ops" and manifest["runtime"] is None else []
    )
    if manifest["blockers"] != expected_blockers:
        raise ValueError("Release capability blockers do not match its runtime profile.")
    return manifest


def verify_wheel(path, manifest):
    validate_manifest(manifest)
    path = Path(path)
    if (path.name != manifest["wheel"]["name"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["wheel"]["sha256"]):
        raise ValueError("Released wheel filename or SHA256 does not match the frozen manifest.")
    with ZipFile(path) as archive:
        metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1 or f"{manifest['package']}/__init__.py" not in archive.namelist():
            raise ValueError("Released artifact is not the selected CLI extension wheel.")
        headers = Parser().parsestr(archive.read(metadata[0]).decode("utf-8"))
        if (not headers["Name"] or not headers["Version"]
                or headers["Name"].replace("_", "-") != manifest["extension"]
                or Version(headers["Version"]) != Version(manifest["release"]["version"])):
            raise ValueError("Wheel metadata does not match the selected release.")
        for channel, runtime in manifest["runtimes"].items():
            if runtime is None:
                continue
            profile = parse_runtime_profile(
                archive.read(runtime["template"]).decode("utf-8"), manifest["cloudKey"], channel,
            )
            if profile != runtime:
                raise ValueError("Wheel runtime differs from the resolved release source.")


def verify_bundle(directory, **expected):
    directory = Path(directory)
    manifest = validate_manifest(read_json(directory / "manifest.json"), **expected)
    wheel = directory / manifest["wheel"]["name"]
    verify_wheel(wheel, manifest)
    source = directory / "source"
    snapshot = directory / "source.json"
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != manifest.get("sourceSha256"):
        raise ValueError("Released source inventory does not match the acquired bundle.")
    inventory = read_json(snapshot)
    if inventory["commit"] != manifest["testSourceCommit"] or inventory["files"] != source_files(source):
        raise ValueError("Released test source is missing, modified, or belongs to a different commit.")
    if manifest.get("testCompatibility"):
        from release_test_compatibility import verify_source
        verify_source(source, manifest["testCompatibility"])
    with ZipFile(wheel) as archive:
        prefix = manifest["package"] + "/"
        entries = {name for name in archive.namelist() if name.startswith(prefix) and not name.endswith("/")}
        for name in entries:
            path = source / name
            if not path.is_file() or path.is_symlink() or path.read_bytes() != archive.read(name):
                raise ValueError(f"Release source differs from the published wheel: {name}")
        for path in (source / manifest["package"]).rglob("*.py"):
            relative = path.relative_to(source).as_posix()
            if not relative.startswith(prefix + "tests/") and relative not in entries:
                raise ValueError(f"Release source contains product code absent from the wheel: {relative}")
    return manifest


def source_files(source):
    files = {}
    for path in sorted(Path(source).rglob("*")):
        relative = path.relative_to(source)
        if relative.parts[0] == ".git":
            continue
        if path.is_symlink():
            raise ValueError("Released test source must not contain symbolic links.")
        if path.is_file():
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError("Released test source is empty.")
    return files


def acquire(manifest, output):
    validate_manifest(manifest)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    wheel = output / manifest["wheel"]["name"]
    wheel.write_bytes(download(manifest["wheel"]["url"]))
    verify_wheel(wheel, manifest)
    source = output / "source"
    if source.exists():
        raise ValueError("Release-source destination already exists; use a fresh attempt directory.")
    source.mkdir()
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for arguments in (
        ["init", "--quiet"],
        ["fetch", "--quiet", "--depth=1", f"https://github.com/{manifest['repository']}.git",
         commit(manifest["testSourceCommit"])],
        ["checkout", "--quiet", "--detach", "FETCH_HEAD"],
    ):
        subprocess.run(["git", "-C", str(source), *arguments], check=True, env=environment, timeout=180)
    actual = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual != manifest["testSourceCommit"]:
        raise ValueError("Downloaded test source does not match its frozen commit.")
    write_json(output / "source.json", {"commit": actual, "files": source_files(source)})
    source_digest = hashlib.sha256((output / "source.json").read_bytes()).hexdigest()
    if manifest.get("sourceSha256", source_digest) != source_digest:
        raise ValueError("The fixed release commit produced different test-source bytes.")
    manifest = {**manifest, "sourceSha256": source_digest}
    write_json(output / "manifest.json", manifest)
    verify_bundle(output)


def frozen_manifest(history, extension, cloud, track, automation_commit, attempt, *, slot=None):
    paths = sorted(Path(history).glob("release-selection-*/manifest.json")) if history else []
    if not paths:
        if attempt != 1:
            raise ValueError("A retry cannot rediscover releases without its original frozen manifest.")
        value = resolve(extension, cloud, track, automation_commit)
        if slot is not None:
            value["slot"] = slot
        return validate_manifest(value, slot=slot)
    values = [
        validate_manifest(read_json(path), extension=extension, cloud=cloud, track=track, slot=slot,
                          automation_commit=automation_commit)
        for path in paths
    ]
    if any(value != values[0] for value in values):
        raise ValueError("Release identity changed between attempts; start a new run.")
    return values[0]


def configured_tracks(config):
    extension = config["extension"]
    settings(extension)
    tracks = config["tracks"]
    if not isinstance(tracks, dict):
        raise ValueError("Configure an explicit release target for every health track or support slot.")
    if extension == "azure-iot" and tracks != {"ga": "ga", "preview": "preview"}:
        raise ValueError("IoT monitoring requires GA and Preview.")
    if extension == "azure-iot-ops":
        if set(tracks) != {"v1", "v2", "v3"} or any(
                not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*\.[0-9]+", value)
                for value in tracks.values()):
            raise ValueError("AIO health requires v1, v2 and v3 mapped to explicit runtime milestones.")
        versions = [Version(tracks[key]) for key in ("v1", "v2", "v3")]
        if len(set(versions)) != 3 or versions != sorted(versions, reverse=True):
            raise ValueError("AIO support slots must select distinct milestones, newest first.")
        return {**tracks, "preview": tracks["v1"]}
    return tracks


def configurations(config):
    extension = config["extension"]
    tracks = configured_tracks(config)
    expected_clouds = {"public", "fairfax", "mooncake"} if extension == "azure-iot" else {"public", "fairfax"}
    if set(config["clouds"]) != expected_clouds:
        raise ValueError("Monitor clouds do not match the product's supported cloud matrix.")
    result = []
    for cloud, profile in config["clouds"].items():
        supported = profile.get("supportedTracks", list(tracks))
        if not isinstance(supported, list) or not set(supported) <= set(tracks):
            raise ValueError("Cloud support must name configured health slots.")
        for track in tracks:
            label = {"ga": "GA", "preview": "Preview"}.get(track, track)
            result.append({
                "name": f"{config['namePrefix']} ({profile['displayName']} {label})",
                "variables": {
                    "MonitorCloud": cloud, "MonitorTrack": track, "MonitorAzureCloud": CLOUDS[cloud],
                    **{name: value.format(track=track, cloud=cloud) for name, value in profile["variables"].items()},
                },
            })
    return result


def check_definition(config, extension, cloud, track):
    if config["extension"] != extension:
        raise ValueError("Monitor configuration belongs to a different extension.")
    matches = [
        item for item in configurations(config)
        if item["variables"]["MonitorCloud"] == cloud and item["variables"]["MonitorTrack"] == track
    ]
    if len(matches) != 1 or os.environ.get("BUILD_DEFINITIONNAME") != matches[0]["name"]:
        raise ValueError("This pipeline definition is not the selected version/cloud monitor.")
    if track not in config["clouds"][cloud].get("supportedTracks", configured_tracks(config)):
        raise ValueError(f"{cloud} {track} is unsupported; keep this health pipeline disabled.")
    if os.environ.get("BUILD_REPOSITORY_NAME", "").lower() != REPOSITORIES[extension].lower():
        raise ValueError("Monitor automation belongs to a different repository.")
    for name, expected in matches[0]["variables"].items():
        if os.environ.get(name.upper(), "") != expected:
            raise ValueError(f"{name} differs from the reviewed monitor configuration.")


def health_yaml(extension, cloud, track):
    suffix = "" if cloud == "public" else "-" + cloud
    if extension == "azure-iot":
        suffix += "-preview" if track == "preview" else ""
    elif track != "v1":
        suffix += "-" + track
    return f".azure-devops/release-monitor{suffix}.yml"


def bind_profile(manifest, config):
    configured_cloud = os.environ["MONITORCLOUD"]
    configured_track = os.environ["MONITORTRACK"]
    profiles = {
        (item["variables"]["MonitorCloud"], item["variables"]["MonitorTrack"]): item["variables"]
        for item in configurations(config)
    }
    configured = profiles[(configured_cloud, configured_track)]
    cloud, track = manifest["cloudKey"], manifest["slot"]
    selected = profiles[(cloud, track)]
    if track not in config["clouds"][cloud].get("supportedTracks", configured_tracks(config)):
        raise ValueError(f"{cloud} {track} has no supported health profile.")
    for key, expected in selected.items():
        if key in {"MonitorRegion", "MonitorServices"}:
            continue
        name = "TEST" + key.removeprefix("Monitor").upper()
        if os.environ.get(name) != expected:
            raise ValueError(f"{name} differs from the selected reviewed cloud profile.")
    region = os.environ["TESTREGION"]
    services = os.environ["TESTSERVICES"].split(",")
    regions = region.split(",")
    pythons = os.environ["TESTPYTHONS"].split(",")
    mode = os.environ["TESTMODE"]
    if (any(not re.fullmatch(r"[a-z][a-z0-9]+", value) for value in regions)
            or len(regions) != len(set(regions)) or not all(services)
            or len(services) != len(set(services))):
        raise ValueError("Select distinct valid regions and services/scenarios.")
    if (not pythons or set(pythons) - {"3.10", "3.11", "3.12", "3.13"}
            or len(pythons) != len(set(pythons)) or mode not in {"Dry run", "Integration tests"}):
        raise ValueError("Select supported Python versions and a test mode.")
    if config["extension"] == "azure-iot" and not set(services).issubset(selected["MonitorServices"].split(",")):
        raise ValueError("Selected services are unsupported in the selected cloud.")
    expected = {
        "cloud": configured_cloud, "version": configured_track, "region": configured["MonitorRegion"],
        "services": sorted(configured.get("MonitorServices", "Default scenarios").split(",")),
        "python": ["3.13"], "mode": "Integration tests",
    }
    actual = {
        "cloud": cloud, "version": track, "region": region, "services": sorted(services),
        "python": sorted(pythons), "mode": mode,
    }
    channels = os.environ["TESTCHANNELS"].split(",")
    preview_health = config["extension"] == "azure-iot-ops" and "preview" in {configured_track, track}
    if preview_health and channels != ["preview"]:
        raise ValueError("Dedicated Preview health requires only the preview runtime channel.")
    baselines = json.loads(os.environ["TESTBASELINES"])
    timeout = int(os.environ["TESTTIMEOUT"])
    if (len(regions) != 1 or not channels or set(channels) - {"stable", "preview"}
            or len(channels) != len(set(channels)) or not isinstance(baselines, dict)
            or timeout not in {90, 180, 360} or cloud != "public" and channels != ["stable"]):
        raise ValueError("Select supported regions, runtime channels, upgrade baselines and timeout.")
    expected.update(
        channels=["preview" if config["extension"] == "azure-iot-ops" and configured_track == "preview" else "stable"],
        baselines={}, timeout=360,
    )
    actual.update(channels=sorted(channels), baselines=baselines, timeout=timeout)
    if manifest.get("kind") == "source":
        expected["branch"] = "refs/heads/" + (
            "dev" if configured_track == "ga" else "release/1.2.0-preview"
        )
        actual["branch"] = manifest["source"]["branch"]
    profile = {"configured": expected, "selected": actual}
    if "profile" in manifest and manifest["profile"] != profile:
        raise ValueError("Health profile changed between attempts; start a new run.")
    for channel in channels:
        if channel not in manifest["runtimes"]:
            if "profile" in manifest:
                raise ValueError("A retry cannot rediscover a missing runtime profile.")
            runtime = runtime_profile(manifest["repository"], manifest["testSourceCommit"], cloud, channel)
            if runtime is None:
                raise ValueError(f"The published release has no {channel} runtime profile.")
            manifest["runtimes"][channel] = runtime
    manifest["profile"] = profile
    return manifest


def definitions(config, baseline, branch):
    repository = baseline["repository"]
    if (repository["name"].lower() != REPOSITORIES[config["extension"]].lower()
            or repository["type"].lower() != "github"
            or not re.fullmatch(r"refs/heads/[A-Za-z0-9._/-]+", branch) or ".." in branch):
        raise ValueError("Select the product's GitHub definition and an explicit automation branch.")
    source = {
        key: repository[key] for key in ("id", "name", "type", "url")
    }
    source["defaultBranch"] = branch
    source["properties"] = {"connectedServiceId": repository["properties"]["connectedServiceId"]}
    return [{
        "name": item["name"], "path": "\\official\\release-health", "type": "build",
        "queueStatus": "disabled", "triggers": [], "repository": source,
        "queue": {"id": baseline["queue"]["id"]},
        "process": {"type": 2, "yamlFilename": health_yaml(
            config["extension"], item["variables"]["MonitorCloud"], item["variables"]["MonitorTrack"],
        )},
        "variables": {
            name: {"value": value, "isSecret": False, "allowOverride": False}
            for name, value in item["variables"].items()
        },
    } for item in configurations(config)]


def run_title(manifest, build):
    validate_manifest(manifest)
    if not re.fullmatch(r"[1-9][0-9]*", build):
        raise ValueError("A positive ADO build ID is required for the release-health run title.")
    prefix = "iot" if manifest["extension"] == "azure-iot" else "aio"
    preview_health = manifest["extension"] == "azure-iot-ops" and manifest.get("slot") == "preview"
    track = "preview" if preview_health else manifest["track"]
    title = f"{prefix}-health-{manifest['cloudKey']}-{track}-cli{manifest['release']['version']}"
    if manifest["extension"] == "azure-iot-ops":
        selected_runtime = manifest["runtimes"].get("preview") if preview_health else manifest["runtime"]
        if preview_health and selected_runtime is None:
            raise ValueError("Dedicated Preview health has no frozen preview runtime.")
        runtime = selected_runtime["version"] if selected_runtime else "unavailable"
        title += f"-runtime{runtime}"
    title += f"-b{build}"
    if "profile" in manifest and manifest["profile"]["configured"] != manifest["profile"]["selected"]:
        title += "-manual"
    if manifest.get("profile", {}).get("selected", {}).get("mode") == "Dry run":
        title += "-dryrun"
    if len(title) > 255:
        raise ValueError("The resolved release-health run title exceeds the ADO name limit.")
    return title


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("resolve")
    plan.add_argument("--extension", choices=REPOSITORIES, required=True)
    plan.add_argument("--cloud", choices=CLOUDS, required=True)
    plan.add_argument("--track", required=True)
    plan.add_argument("--automation-commit", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--history")
    plan.add_argument("--attempt", type=int, default=1)
    plan.add_argument("--configuration")
    fetch = commands.add_parser("acquire")
    fetch.add_argument("--manifest", required=True)
    fetch.add_argument("--output", required=True)
    setup = commands.add_parser("definitions")
    setup.add_argument("--configuration", required=True)
    setup.add_argument("--baseline", required=True)
    setup.add_argument("--branch", required=True)
    setup.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "resolve":
        target, slot = args.track, None
        if args.configuration:
            config = read_json(args.configuration)
            check_definition(config, args.extension, os.environ["MONITORCLOUD"], os.environ["MONITORTRACK"])
            target, slot = configured_tracks(config)[args.track], args.track
        value = frozen_manifest(
            args.history, args.extension, args.cloud, target, args.automation_commit, args.attempt, slot=slot,
        )
        if args.configuration:
            bind_profile(value, config)
        write_json(args.output, value)
        print(json.dumps(value, indent=2))
        if args.configuration:
            print(f"##vso[build.updatebuildnumber]{run_title(value, os.environ['BUILD_BUILDID'])}")
    elif args.command == "acquire":
        acquire(read_json(args.manifest), args.output)
    else:
        write_json(args.output, definitions(read_json(args.configuration), read_json(args.baseline), args.branch))


if __name__ == "__main__":
    main()
