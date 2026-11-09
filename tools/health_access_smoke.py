# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Nonqualifying AIO access checks; only an empty owned group may be created."""

import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from packaging.version import Version

from ado_cluster import Commands
from ado_integration import producer
from release_monitor import verify_bundle
from release_monitor_adapter import cleanup_group, prepare_group, resource_group


def main():
    output = Path(os.environ["SMOKE_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    commands = Commands(budget=600)
    evidence = {"mode": "access-smoke", "qualifiesFullSuite": False, "checks": []}
    state = None

    def check(name, operation):
        try:
            value = operation()
            evidence["checks"].append({"name": name, "status": "passed"})
            return value
        except (subprocess.SubprocessError, TimeoutError, ValueError) as error:
            evidence["checks"].append({"name": name, "status": "failed", "error": str(error)})
            return None

    try:
        bundle = Path(os.environ["SMOKE_BUNDLE"])
        manifest = verify_bundle(
            bundle, extension="azure-iot-ops", cloud=os.environ["MONITOR_CLOUD"],
            slot=os.environ["MONITOR_TRACK"], automation_commit=os.environ["BUILD_SOURCEVERSION"],
        )
        if manifest["blockers"]:
            raise ValueError("; ".join(manifest["blockers"]))
        evidence.update(producer=producer(), manifest=manifest)
        commands.run(
            ["az", "extension", "add", "--source", str(bundle / manifest["wheel"]["name"]), "--yes"],
            capture=True, timeout=180,
        )
        installed = commands.az_json("extension", "show", "--name", "azure-iot-ops", "--query", "version")
        if Version(installed) != Version(manifest["release"]["version"]):
            raise ValueError("Installed CLI differs from the frozen published wheel.")
        cloud = commands.az_json("cloud", "show")
        subscription = commands.az_json("account", "show", "--query", "id")
        if cloud["name"] != manifest["cloud"] or subscription != os.environ["MONITOR_SUBSCRIPTION"]:
            raise ValueError("The service connection selected an unexpected cloud or subscription.")
        evidence["checks"].append({"name": "connection_and_frozen_cli", "status": "passed"})
        check("ops_arm_list", lambda: commands.az_json("iot", "ops", "list", "--query", "length(@)"))
        check("provider_access", lambda: commands.az_json(
            "provider", "show", "--namespace", "Microsoft.IoTOperations", "--query", "registrationState",
        ))
        suffix = uuid4().hex[:11]
        state = {
            "producer": producer(), "suffix": suffix,
            "resourceGroup": resource_group(os.environ["MONITOR_RESOURCE_GROUP"], suffix),
            "locations": {"clusterRegion": os.environ["MONITOR_REGION"]},
        }
        evidence["resourceGroup"] = state["resourceGroup"]
        check("isolated_group_create", lambda: prepare_group(commands, state, output))
    except (subprocess.SubprocessError, TimeoutError, ValueError) as error:
        evidence["checks"].append({"name": "setup", "status": "failed", "error": str(error)})
    finally:
        if state is not None:
            cleanup = Commands(budget=300)

            def cleanup_empty():
                if state.get("groupCreationAttempted") and cleanup.az_json(
                        "group", "exists", "--name", state["resourceGroup"]):
                    if cleanup.az_json("resource", "list", "--resource-group", state["resourceGroup"]):
                        raise ValueError("The smoke group is unexpectedly nonempty; refusing group deletion.")
                cleanup_group(cleanup, state)

            check("owned_group_cleanup", cleanup_empty)
        text = json.dumps(evidence, indent=2)
        (output / "access-smoke.json").write_text(text, encoding="utf-8")
        print(text)
    return int(any(item["status"] == "failed" for item in evidence["checks"]))


if __name__ == "__main__":
    raise SystemExit(main())
