# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Own a temporary resource group for one Trust Bundle job, without cross-run locks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import UUID


class AzureCLI:
    def run(self, arguments, *, timeout=900):
        return subprocess.check_output(arguments, text=True, timeout=timeout)

    def az_json(self, *arguments):
        return json.loads(self.run(["az", *arguments, "--output", "json"]))


def group_name(owner):
    if not owner or "\n" in owner or "\r" in owner:
        raise ValueError("An explicit, single-line job owner is required.")
    return "ops-cli-wlif-" + hashlib.sha256(owner.encode()).hexdigest()[:20]


def identity(subscription, owner):
    return {
        "name": group_name(owner),
        "id": f"/subscriptions/{UUID(subscription)}/resourceGroups/{group_name(owner)}",
        "tags": {
            "managedBy": "azure-iot-ops-cli-tests",
            "jobOwner": hashlib.sha256(owner.encode()).hexdigest(),
        },
    }


def check_group(group, expected):
    if (group.get("id", "").lower() != expected["id"].lower()
            or any((group.get("tags") or {}).get(key) != value for key, value in expected["tags"].items())):
        raise ValueError("Refusing a resource group without this job's exact ownership tags and ID.")


def create(commands, receipt, subscription, source_group, owner):
    expected = identity(subscription, owner)
    if expected["name"].lower() == source_group.lower():
        raise ValueError("The temporary group must differ from the configured base resource group.")
    base = commands.az_json("group", "show", "--name", source_group, "--subscription", subscription)
    if commands.az_json("group", "exists", "--name", expected["name"], "--subscription", subscription):
        raise ValueError("Temporary resource group already exists; refusing reuse.")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump({**expected, "sourceGroup": source_group}, stream, indent=2)
    group = commands.az_json(
        "group", "create", "--name", expected["name"], "--location", base["location"],
        "--subscription", subscription, "--tags",
        *(f"{key}={value}" for key, value in expected["tags"].items()),
    )
    check_group(group, expected)
    return expected["name"]


def owned_group(commands, receipt, subscription, owner):
    if not receipt.is_file():
        print("No temporary resource-group creation intent; nothing to delete.", flush=True)
        return None
    expected = identity(subscription, owner)
    recorded = json.loads(receipt.read_text(encoding="utf-8"))
    if (any(recorded.get(key) != expected[key] for key in ("name", "id", "tags"))
            or recorded.get("sourceGroup", "").lower() == expected["name"].lower()):
        raise ValueError("Temporary resource-group receipt belongs to a different job.")
    if not commands.az_json("group", "exists", "--name", expected["name"], "--subscription", subscription):
        print(f"Temporary resource group {expected['name']} is absent.", flush=True)
        return None
    group = commands.az_json("group", "show", "--name", expected["name"], "--subscription", subscription)
    check_group(group, expected)
    return group


def cleanup(commands, receipt, subscription, owner):
    if owned_group(commands, receipt, subscription, owner) is None:
        return
    name = group_name(owner)
    commands.run(["az", "group", "delete", "--name", name, "--subscription", subscription, "--yes"], timeout=900)
    if commands.az_json("group", "exists", "--name", name, "--subscription", subscription):
        raise RuntimeError(f"Temporary resource group {name} remains after cleanup.")
    print(f"Deleted temporary resource group {name}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "cleanup"))
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--source-group")
    args = parser.parse_args()
    commands = AzureCLI()
    if args.operation == "create":
        if not args.source_group:
            parser.error("--source-group is required for creation")
        name = create(commands, args.receipt, args.subscription, args.source_group, args.owner)
        with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
            stream.write(f"RESOURCE_GROUP={name}\n")
    else:
        cleanup(commands, args.receipt, args.subscription, args.owner)


if __name__ == "__main__":
    main()
