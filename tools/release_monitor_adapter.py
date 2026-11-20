# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bind the native AIO runner to a published wheel and its released test sources."""

import argparse
import os
from pathlib import Path

import ado_integration as native
from release_monitor import CLOUDS, configured_tracks, validate_manifest, verify_bundle


def target_track():
    if os.environ.get("MONITOR_KIND") == "branch":
        from branch_health import TRACKS
        slot = native.required("MONITOR_TRACK")
        if (native.required("MONITOR_CLOUD"), slot) not in TRACKS:
            raise ValueError("Unsupported fixed Branch Health track.")
        return slot
    tracks = configured_tracks(native.read(native.ROOT / ".azure-devops/release-monitors.json"))
    slot = native.required("MONITOR_TRACK")
    if slot not in tracks:
        raise ValueError("Select a configured AIO support slot.")
    return tracks[slot]


def bundle_manifest(bundle, require_wheel=True):
    manifest = verify_bundle(
        bundle, require_wheel=require_wheel, extension="azure-iot-ops", cloud=os.environ["MONITOR_CLOUD"],
        slot=os.environ["MONITOR_TRACK"], track=target_track(), automation_commit=native.producer()["commit"],
    )
    if (manifest.get("kind") == "branch") != (os.environ.get("MONITOR_KIND") == "branch"):
        raise ValueError("Published and source-built health identities cannot be interchanged.")
    return manifest


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
    announce(
        native.read(bundle / "plan.json"), manifest, bundle,
        native.release.wheel_metadata(bundle / manifest["wheel"]["name"]),
    )


def title(bundle):
    """Title a Branch Health run from its acquired source before the wheel exists."""
    bundle = Path(bundle).resolve()
    manifest = bundle_manifest(bundle, require_wheel=False)
    value = {
        "producer": native.producer(), "cloud": native.cloud_name(),
        "rows": [{"scenario": scenario} for scenario in native.select_scenarios(bundle / "source")],
        "locations": {"clusterRegion": native.required("OPS_CLUSTER_REGION")},
    }
    announce(value, manifest, bundle, manifest["source"]["version"])


def announce(value, manifest, bundle, version):
    channels = {row["scenario"]["channel"] for row in value["rows"]}
    runtimes = [manifest["runtimes"][channel]["version"] for channel in ("stable", "preview") if channel in channels]
    name = native.run_title(value, native.required("OPS_MODE"), version, runtimes, scenario_source=bundle / "source")
    print(f"##vso[build.updatebuildnumber]{name}", flush=True)


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
    validate_state(state)
    native.write(output / "state.json", state)


def validate_state(state):
    if not isinstance(state.get("monitor"), dict):
        raise ValueError("Monitor execution state is missing the frozen release identity.")
    manifest = validate_manifest(
        state["monitor"], extension="azure-iot-ops", automation_commit=native.producer()["commit"],
        cloud=os.environ["MONITOR_CLOUD"], slot=os.environ["MONITOR_TRACK"], track=target_track(),
    )
    if (manifest.get("kind") == "branch") != (os.environ.get("MONITOR_KIND") == "branch"):
        raise ValueError("Execution kind differs from the selected health pipeline.")
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    if (manifest["blockers"] or manifest["cloud"] != state["cloud"]
            or state["sha256"] != manifest["wheel"]["sha256"]
            or Path(state["wheel"]).resolve() != bundle / manifest["wheel"]["name"]
            or state["row"]["scenario"]["channel"] not in manifest["runtimes"]
            or manifest.get("slot") == "preview" and state["row"]["scenario"]["channel"] != "preview"
            or state["resourceGroup"] != native.required("OPS_RESOURCE_GROUP")):
        raise ValueError("Monitor execution state differs from its released artifact or cloud.")


def test_source(state):
    validate_state(state)
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    if bundle_manifest(bundle) != state["monitor"]:
        raise ValueError("Released source changed after scenario preparation.")
    return bundle / "source"


def verify_runtime(commands, state, output):
    expected = state["monitor"]["runtimes"][state["row"]["scenario"]["channel"]]
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
    result = {
        "schema": 1, "status": "incomplete", "phase": "release-identity", "releaseQualified": False,
    }
    # Publish failure-shaped evidence before validation can reject the run.
    native.write(output / "monitor-results.json", result)
    bundle = Path(native.required("OPS_MONITOR_BUNDLE")).resolve()
    manifest = bundle_manifest(bundle)
    value = native.read(bundle / "plan.json")
    if (value.get("monitor") != manifest or manifest["blockers"]
            or value["producer"] != native.producer() or value["cloud"] != manifest["cloud"]
            or native.release_build_id() != "0" or value.get("releaseBuildId", "0") != "0"
            or native.required("OPS_CANDIDATE_DIGEST") != manifest["wheel"]["sha256"]):
        raise ValueError("Monitor results do not belong to this standalone released-version plan.")
    result.update(
        producer=native.producer(), monitor=manifest, phase="scenario-evidence",
        expectedScenarios=[row["key"] for row in value["rows"]],
    )
    native.write(output / "monitor-results.json", result)
    verified = [
        receipt for _, _, receipt in native.scenario_evidence(value, Path(native.required("OPS_HISTORY")))
    ]
    result.update(status="passed", phase="complete", scenarios=verified)
    native.write(output / "monitor-results.json", result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "title", "prepare", "gate"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan(args.output)
    elif args.command == "title":
        title(args.output)
    elif args.command == "prepare":
        prepare(args.output.resolve())
    else:
        gate(args.output.resolve())


if __name__ == "__main__":
    main()
