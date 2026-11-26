# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.

"""Build fixed dev Branch Health independently from the automation checkout."""

import argparse
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from packaging.version import Version

import release_monitor as monitor
from ado_schedule import check_scheduled_overlap


TRACKS = {("public", "ga"): "stable", ("fairfax", "ga"): "stable", ("public", "preview"): "preview"}
BRANCH = "refs/heads/dev"


def run_identity():
    result = {key: os.environ[key] for key in ("BUILD_BUILDID", "SYSTEM_DEFINITIONID")}
    if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in result.values()):
        raise ValueError("Branch Health requires this pipeline run's identity.")
    return result


def validate_manifest(manifest, **expected):
    config = monitor.settings("azure-iot-ops")
    channel = TRACKS.get((manifest.get("cloudKey"), manifest.get("track")))
    if (manifest.get("kind") != "branch" or manifest.get("schema") != 2 or channel is None
            or any(manifest.get(key) != value for key, value in config.items())
            or manifest["cloud"] != monitor.CLOUDS[manifest["cloudKey"]]
            or manifest.get("slot") != manifest["track"] or manifest.get("producer") != run_identity()
            or manifest.get("automationCommit") != os.environ["BUILD_SOURCEVERSION"]
            or manifest.get("releaseQualified") is not False or manifest.get("blockers") != []
            or "release" in manifest):
        raise ValueError("Invalid fixed-track Branch Health identity.")
    for key, field in (
        ("extension", "extension"), ("cloud", "cloudKey"), ("track", "track"),
        ("slot", "slot"), ("automation_commit", "automationCommit"),
    ):
        if expected.get(key) is not None and manifest.get(field) != expected[key]:
            raise ValueError(f"Branch Health differs from the requested {field}.")
    monitor.commit(manifest["automationCommit"])
    from release_test_compatibility import validate_source_compatibility
    validate_source_compatibility(manifest)
    source = manifest["source"]
    if (source["branch"] != BRANCH or monitor.commit(source["commit"]) != monitor.commit(manifest["testSourceCommit"])
            or source["version"] != str(Version(source["version"]))):
        raise ValueError("Branch Health must use the selected dev product and test commit.")
    runtime = manifest["runtime"]
    parsed = Version(runtime["version"])
    templates = {
        monitor.TEMPLATE.format(option[0])
        for option in monitor.runtime_template_options(channel, manifest["cloudKey"] == "fairfax")
    }
    if (manifest.get("runtimes") != {channel: runtime} or runtime["train"] != channel
            or runtime["template"] not in templates
            or runtime["milestone"] != f"{parsed.major}.{parsed.minor}"
            or channel == "stable" and (parsed.is_prerelease or parsed.is_devrelease)):
        raise ValueError("Branch Health runtime does not match its fixed logical track.")
    wheel = manifest.get("wheel")
    if wheel is not None and (
        set(wheel) != {"name", "sha256"}
        or wheel["name"] != f"azure_iot_ops-{source['version']}-py3-none-any.whl"
        or not re.fullmatch(r"[0-9a-f]{64}", wheel["sha256"])
    ):
        raise ValueError("Invalid source-built candidate wheel.")
    return manifest


def resolve(history, cloud, track, automation, attempt):
    if (cloud, track) not in TRACKS:
        raise ValueError("Unsupported Branch Health cloud/track; Fairfax Preview has no runtime.")
    previous = sorted(Path(history).glob("branch-selection-*/manifest.json"))
    if previous:
        values = [validate_manifest(monitor.read_json(path), cloud=cloud, track=track,
                                    automation_commit=automation) for path in previous]
        if any(value != values[0] for value in values):
            raise ValueError("Branch selection changed between attempts.")
        return values[0]
    if attempt != 1:
        raise ValueError("A retry cannot resolve dev without its original frozen selection.")
    config = monitor.settings("azure-iot-ops")
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", f"https://github.com/{config['repository']}.git", BRANCH],
        capture_output=True, text=True, check=True, timeout=60, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    refs = dict(line.split()[::-1] for line in result.stdout.splitlines())
    source_commit = monitor.commit(refs.get(BRANCH))
    tree = ast.parse(monitor.download(
        f"https://raw.githubusercontent.com/{config['repository']}/{source_commit}/azext_edge/constants.py",
    ).decode("utf-8"))
    version, = [
        ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    ]
    runtime = monitor.runtime_profile(config["repository"], source_commit, cloud, TRACKS[(cloud, track)])
    if runtime is None:
        raise ValueError("Selected dev source has no runtime for this fixed track.")
    manifest = {
        **config, "schema": 2, "kind": "branch", "producer": run_identity(),
        "cloudKey": cloud, "cloud": monitor.CLOUDS[cloud], "track": track, "slot": track,
        "automationCommit": monitor.commit(automation), "testSourceCommit": source_commit,
        "source": {"branch": BRANCH, "commit": source_commit, "version": str(Version(version))},
        "runtime": runtime, "runtimes": {TRACKS[(cloud, track)]: runtime},
        "wheel": None, "blockers": [], "releaseQualified": False,
    }
    return validate_manifest(manifest)


def acquire(manifest, output):
    validate_manifest(manifest)
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    source.mkdir()
    for arguments in (
        ["init", "--quiet"],
        ["fetch", "--quiet", "--depth=1", f"https://github.com/{manifest['repository']}.git",
         manifest["testSourceCommit"]],
        ["checkout", "--quiet", "--detach", "FETCH_HEAD"],
    ):
        subprocess.run(["git", "-C", str(source), *arguments], check=True, timeout=180,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != manifest["testSourceCommit"]:
        raise ValueError("Downloaded source is not the selected dev commit.")
    # Keep only selected repository bytes in the bundle; no agent-local Git metadata.
    shutil.rmtree(source / ".git")
    files = monitor.source_files(source)
    monitor.write_json(output / "source.json", {"commit": actual, "files": files})
    from ado_integration import digest
    from release_test_compatibility import source_compatibility
    manifest = {**manifest, "sourceSha256": digest(output / "source.json")}
    plan = source_compatibility(manifest, source, files)
    if plan is not None:
        manifest["testCompatibility"] = plan
    monitor.write_json(output / "manifest.json", manifest)
    monitor.verify_bundle(output, require_wheel=False)


def build(source, history, output, attempt):
    selected = monitor.verify_bundle(source, require_wheel=False)
    previous = sorted(history.glob("branch-wheel-*"))
    if previous:
        values = [monitor.verify_bundle(path) for path in previous]
        if any(value != values[0] for value in values):
            raise ValueError("Built candidate changed between attempts.")
        if {**values[0], "wheel": None} != selected:
            raise ValueError("Built candidate does not match this run's frozen selection.")
        shutil.copytree(previous[0], output)
    else:
        if attempt != 1:
            raise ValueError("A retry cannot rebuild the candidate without its original wheel artifact.")
        shutil.copytree(source, output)
        work = output.parent / "branch-build-source"
        shutil.copytree(output / "source", work)
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(output.resolve())], cwd=work, check=True,
        )
        wheel, = output.glob("*.whl")
        from ado_integration import digest
        monitor.write_json(output / "manifest.json", {
            **selected, "wheel": {"name": wheel.name, "sha256": digest(wheel)},
        })
    return monitor.verify_bundle(output)


def stage(bundle, output):
    monitor.verify_bundle(bundle)
    shutil.copytree(bundle / "source", output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["resolve", "acquire", "build", "stage"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    attempt = max(int(os.environ["SYSTEM_JOBATTEMPT"]), int(os.environ.get("SYSTEM_STAGEATTEMPT", "1")))
    if args.command == "resolve":
        check_scheduled_overlap()
        monitor.write_json(args.output, resolve(
            args.history, os.environ["MONITOR_CLOUD"], os.environ["MONITOR_TRACK"],
            os.environ["BUILD_SOURCEVERSION"], attempt,
        ))
    elif args.command == "acquire":
        acquire(monitor.read_json(args.source), args.output)
    elif args.command == "build":
        build(args.source, args.history, args.output, attempt)
    else:
        stage(args.source, args.output)


if __name__ == "__main__":
    main()
