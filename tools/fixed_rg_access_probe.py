# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Read-only, nonqualifying discovery of existing fixed groups and scoped permissions."""

import fnmatch
import json
import os
from pathlib import Path
import subprocess


def main():
    output = Path(os.environ["SMOKE_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"mode": "fixed-rg-access-probe", "qualifiesFullSuite": False, "checks": []}

    def command(name, *args):
        result = subprocess.run(
            ["az", *args, "-o", "json", "--only-show-errors"], capture_output=True,
            text=True, timeout=90, check=False,
        )
        item = {"name": name, "status": "passed" if result.returncode == 0 else "failed"}
        evidence["checks"].append(item)
        if result.returncode:
            item["error"] = result.stderr
            return None
        value = json.loads(result.stdout)
        item["value"] = value
        return value

    try:
        cloud = command("cloud", "cloud", "show", "--query", "{name:name,endpoint:endpoints.resourceManager}")
        account = command("account", "account", "show", "--query", "{id:id,cloud:environmentName}")
        if not cloud or not account or account["id"] != os.environ["MONITOR_SUBSCRIPTION"]:
            raise ValueError("The service connection did not select the expected subscription.")
        if cloud["name"] != os.environ["MONITOR_AZURE_CLOUD"]:
            raise ValueError("The service connection did not select the expected cloud.")
        groups = command("existing_groups", "group", "list", "--query", "[].{name:name,location:location}")
        candidates = {"ops-cli-int-test-rg", "ops-cli-monitor-fairfax-v1", os.environ["MONITOR_RESOURCE_GROUP"]}
        candidates.update(item["name"] for item in groups or [] if "ops" in item["name"].lower())
        requirements = (
            "Microsoft.Resources/deployments/write",
            "Microsoft.ManagedIdentity/userAssignedIdentities/write",
            "Microsoft.ManagedIdentity/userAssignedIdentities/delete",
            "Microsoft.Authorization/roleAssignments/write",
            "Microsoft.Authorization/roleAssignments/delete",
            "Microsoft.Kubernetes/connectedClusters/write",
            "Microsoft.IoTOperations/instances/write",
            "Microsoft.DeviceRegistry/namespaces/write",
        )
        for group in sorted(candidates):
            exists = command(f"group:{group}", "group", "show", "--name", group, "--query", "{id:id,location:location}")
            if not exists:
                continue
            url = (
                cloud["endpoint"].rstrip("/") + exists["id"]
                + "/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
            )
            permissions = command(f"permissions:{group}", "rest", "--method", "get", "--url", url)
            if permissions is not None:
                evidence.setdefault("permissions", {})[group] = {
                    required: any(
                        any(
                            fnmatch.fnmatchcase(required.lower(), action.lower())
                            for action in entry.get("actions", [])
                        )
                        and not any(
                            fnmatch.fnmatchcase(required.lower(), action.lower())
                            for action in entry.get("notActions", [])
                        )
                        for entry in permissions.get("value", [])
                    )
                    for required in requirements
                }
    except (subprocess.SubprocessError, ValueError, KeyError) as error:
        evidence["checks"].append({"name": "probe", "status": "failed", "error": str(error)})
    finally:
        text = json.dumps(evidence, indent=2)
        (output / "fixed-rg-access.json").write_text(text, encoding="utf-8")
        print(text)
    return int(any(item["status"] == "failed" for item in evidence["checks"]))


if __name__ == "__main__":
    raise SystemExit(main())
