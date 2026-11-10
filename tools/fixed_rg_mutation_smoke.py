# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bounded ownership smoke: two identities, one template identity and one self-scoped Reader grant."""

import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import owned_resources as owned


def main():
    output = Path(os.environ["SMOKE_OUTPUT"])
    cloud = os.environ["MONITOR_AZURE_CLOUD"]
    group = {"AzureCloud": "ops-cli-int-test-rg", "AzureUSGovernment": "ops-cli-monitor-fairfax-v1"}[cloud]
    paths = [output / attempt / "ownership.json" for attempt in ("a", "b")]
    if sys.argv[1] == "prepare":
        for path in paths:
            owned.create_context(
                path, cloud=cloud, subscription=os.environ["MONITOR_SUBSCRIPTION"], resourceGroup=group,
                producer={"build": os.environ["BUILD_BUILDID"]}, product="fixed-rg-smoke",
            )
        return 0
    if sys.argv[1] != "run":
        raise ValueError("Expected prepare or run.")
    journals = [owned.Journal(path) for path in paths]
    evidence = {"qualifiesFullSuite": False, "checks": [], "group": group}
    suffix = journals[0].context["nonce"][:15]

    def command(path, *args):
        owned.activate(path)
        result = subprocess.run(
            ["az", *args, "-o", "json", "--only-show-errors"], capture_output=True,
            text=True, timeout=240, check=True,
        )
        return json.loads(result.stdout) if result.stdout.strip() else None

    def check(name, operation):
        try:
            result = operation()
            evidence["checks"].append({"name": name, "status": "passed"})
            return result
        except (ImportError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            evidence["checks"].append({"name": name, "status": "failed", "errorType": type(error).__name__})
            print(getattr(error, "stderr", None) or f"{name}: {error}", file=sys.stderr)
            return None

    def create(path, name):
        return command(
            path, "identity", "create", "-g", group, "-n", name, "-l", os.environ["MONITOR_REGION"],
            "--tags", "smoke=fixed-rg",
        )

    try:
        first = check("direct_identity", lambda: create(paths[0], "owna" + suffix))
        other = check("independent_identity", lambda: create(paths[1], "ownb" + suffix))
        if first:
            check("tag_update", lambda: command(
                paths[0], "tag", "update", "--resource-id", first["id"], "--operation", "Merge",
                "--tags", "smoke=changed",
            ))
            check("self_scoped_reader", lambda: command(
                paths[0], "role", "assignment", "create", "--assignee-object-id", first["principalId"],
                "--assignee-principal-type", "ServicePrincipal", "--scope", first["id"],
                "--role", "acdd72a7-3385-48ef-bd42-f606fba81ae7", "--name", str(uuid4()),
            ))
        template = output / "template.json"
        template.write_text(json.dumps({
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "resources": [{
                "type": "Microsoft.ManagedIdentity/userAssignedIdentities", "apiVersion": "2023-01-31",
                "name": "ownt" + suffix, "location": os.environ["MONITOR_REGION"],
            }],
        }), encoding="utf-8")
        check("inline_deployment", lambda: command(
            paths[0], "deployment", "group", "create", "-g", group, "-n", "ownd" + suffix,
            "--template-file", str(template),
        ))
        check("first_owner_cleanup", lambda: owned.cleanup(paths[0], timeout=240))
        if other:
            def verify_other():
                arm = owned.Arm(journals[1])
                resource = other["id"].lower()
                if arm.verify(resource, arm.api_for(resource)) is None:
                    raise ValueError("Cleanup removed the independent attempt's identity.")
            check("independent_owner_preserved", verify_other)
    finally:
        for number, path in enumerate(paths):
            check(f"final_cleanup_{number}", lambda path=path: owned.cleanup(path, timeout=240))
        text = json.dumps(evidence, indent=2)
        (output / "fixed-rg-mutation.json").write_text(text, encoding="utf-8")
        print(text)
    return int(any(item["status"] == "failed" for item in evidence["checks"]))


if __name__ == "__main__":
    raise SystemExit(main())
