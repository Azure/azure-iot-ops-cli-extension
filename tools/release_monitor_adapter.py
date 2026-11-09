# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bind the native AIO runner to a published wheel and its released test sources."""

import argparse
import os
from pathlib import Path
import re

import ado_integration as native
from release_monitor import CLOUDS, configured_tracks, validate_manifest, verify_bundle


def target_track():
    tracks = configured_tracks(native.read(native.ROOT / ".azure-devops/release-monitors.json"))
    slot = native.required("MONITOR_TRACK")
    if slot not in tracks:
        raise ValueError("Select a configured AIO support slot.")
    return tracks[slot]


def bundle_manifest(bundle):
    return verify_bundle(
        bundle, extension="azure-iot-ops", cloud=os.environ["MONITOR_CLOUD"],
        slot=os.environ["MONITOR_TRACK"], track=target_track(), automation_commit=native.producer()["commit"],
    )


def plan(bundle):
    bundle = Path(bundle).resolve()
    manifest = bundle_manifest(bundle)
    if manifest["blockers"]:
        raise ValueError("; ".join(manifest["blockers"]))
    native.plan(bundle, scenario_source=bundle / "source")
    native.candidate(bundle)
    for filename in ("plan.json", "candidate.json"):
        value = native.read(bundle / filename)
        value["monitor"] = manifest
        native.write(bundle / filename, value)


def prepare(output):
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    manifest = bundle_manifest(bundle)
    if manifest["blockers"] or native.release_build_id() != "0":
        raise ValueError("A blocked monitor or release candidate cannot enter released-version execution.")
    if (native.read(bundle / "candidate.json").get("monitor") != manifest
            or native.read(native.required("OPS_PLAN")).get("monitor") != manifest):
        raise ValueError("Monitor plan and acquired wheel do not share the frozen release identity.")
    native.prepare(output)
    state = native.read(output / "state.json")
    state["monitor"] = manifest
    state["baseResourceGroup"] = state["resourceGroup"]
    state["resourceGroup"] = resource_group(state["baseResourceGroup"], state["suffix"])
    old_scope = f"/resourceGroups/{state['baseResourceGroup']}/"
    new_scope = f"/resourceGroups/{state['resourceGroup']}/"
    state["resources"] = {key: value.replace(old_scope, new_scope) for key, value in state["resources"].items()}
    validate_state(state)
    native.write(output / "state.json", state)


def validate_state(state):
    if not isinstance(state.get("monitor"), dict):
        raise ValueError("Monitor execution state is missing the frozen release identity.")
    manifest = validate_manifest(
        state["monitor"], extension="azure-iot-ops", automation_commit=native.producer()["commit"],
        cloud=os.environ["MONITOR_CLOUD"], slot=os.environ["MONITOR_TRACK"], track=target_track(),
    )
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    if (manifest["blockers"] or manifest["cloud"] != state["cloud"]
            or state["sha256"] != manifest["wheel"]["sha256"]
            or Path(state["wheel"]).resolve() != bundle / manifest["wheel"]["name"]
            or state["row"]["scenario"]["channel"] != "stable"
            or state.get("baseResourceGroup") != native.required("OPS_RESOURCE_GROUP")
            or state["resourceGroup"] != resource_group(state["baseResourceGroup"], state["suffix"])):
        raise ValueError("Monitor execution state differs from its released artifact or cloud.")


def resource_group(base, suffix):
    if not re.fullmatch(r"[0-9a-f]{11}", suffix):
        raise ValueError("A released scenario needs its own valid resource suffix.")
    group = f"{base}-{native.producer()['build']}-{suffix}"
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", group):
        raise ValueError("The isolated monitor resource group exceeds Azure naming limits.")
    return group


def group_tags(state):
    return {
        "cliHealthBuild": state["producer"]["build"],
        "cliHealthDefinition": state["producer"]["pipeline"],
        "cliHealthAttempt": state["suffix"],
    }


def prepare_group(commands, state, output):
    if commands.az_json("group", "exists", "--name", state["resourceGroup"]):
        raise ValueError("The isolated monitor resource group already exists; refusing reuse.")
    state["groupCreationAttempted"] = True
    native.write(output / "state.json", state)
    group = commands.az_json(
        "group", "create", "--name", state["resourceGroup"], "--location", state["locations"]["clusterRegion"],
        "--tags", *(f"{key}={value}" for key, value in group_tags(state).items()),
    )
    if any(group.get("tags", {}).get(key) != value for key, value in group_tags(state).items()):
        raise ValueError("The created monitor group does not have this attempt's ownership tags.")


def cleanup_group(commands, state):
    if not state.get("groupCreationAttempted"):
        return
    if not commands.az_json("group", "exists", "--name", state["resourceGroup"]):
        return
    group = commands.az_json("group", "show", "--name", state["resourceGroup"])
    if any(group.get("tags", {}).get(key) != value for key, value in group_tags(state).items()):
        raise ValueError("Refusing to delete a monitor group without matching attempt ownership tags.")
    commands.run(["az", "group", "delete", "--name", state["resourceGroup"], "--yes"], timeout=900)
    if commands.az_json("group", "exists", "--name", state["resourceGroup"]):
        raise ValueError("The owned monitor resource group remains after cleanup.")


def test_source(state):
    validate_state(state)
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    if bundle_manifest(bundle) != state["monitor"]:
        raise ValueError("Released source changed after scenario preparation.")
    return bundle / "source"


def verify_runtime(commands, state, output):
    expected = state["monitor"]["runtime"]
    cloud = commands.az_json("cloud", "show")
    if cloud["name"] != CLOUDS[state["monitor"]["cloudKey"]]:
        raise ValueError("Runtime verification is using a different Azure cloud.")
    endpoint = cloud["endpoints"]["resourceManager"].rstrip("/")
    resources = commands.az_json(
        "rest", "--method", "GET", "--url",
        endpoint + state["resources"]["cluster"]
        + "/providers/Microsoft.KubernetesConfiguration/extensions?api-version=2023-05-01",
    )["value"]
    matches = [
        resource["properties"] for resource in resources
        if resource.get("properties", {}).get("extensionType", "").lower() == "microsoft.iotoperations"
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one deployed AIO runtime.")
    observed = {"version": matches[0]["version"], "train": matches[0]["releaseTrain"].lower()}
    if observed != {key: expected[key] for key in ("version", "train")}:
        raise ValueError("Deployed AIO runtime does not match the monitored release.")
    state["observedRuntime"] = observed
    native.write(output / "state.json", state)


def gate(output):
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    manifest = bundle_manifest(bundle)
    value = native.read(bundle / "plan.json")
    if (value.get("monitor") != manifest or manifest["blockers"]
            or value["producer"] != native.producer() or value["cloud"] != manifest["cloud"]
            or native.release_build_id() != "0" or value.get("releaseBuildId", "0") != "0"
            or native.required("OPS_CANDIDATE_DIGEST") != manifest["wheel"]["sha256"]):
        raise ValueError("Monitor results do not belong to this standalone released-version plan.")
    verified = [
        receipt for _, _, receipt in native.scenario_evidence(value, Path(native.required("OPS_HISTORY")))
    ]
    native.write(output / "monitor-results.json", {
        "schema": 1, "producer": native.producer(), "monitor": manifest,
        "scenarios": verified, "releaseQualified": False,
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "prepare", "gate"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan(args.output)
    elif args.command == "prepare":
        prepare(args.output.resolve())
    else:
        gate(args.output.resolve())


if __name__ == "__main__":
    main()
