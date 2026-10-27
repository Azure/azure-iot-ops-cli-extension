# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Shared runtime behavior and channel-boundary tests, run unchanged on GA and preview."""

import json
import os
import shlex
import subprocess

import pytest

from ...helpers import run
from ...runtime_checks import assert_runtime, read_runtime


pytestmark = pytest.mark.runtime_channel


@pytest.fixture
def channel_target():
    channel = os.environ.get("azext_edge_runtime_channel")
    if not channel:
        pytest.skip("Set azext_edge_runtime_channel for dual-channel qualification.")
    return os.environ["azext_edge_instance"], os.environ["azext_edge_rg"], channel


@pytest.mark.parametrize("operation", ["list", "show"])
def test_connector_commands_require_preview_runtime(channel_target, operation):
    name, group, channel = channel_target
    assert_runtime(name, group, channel)
    reference = "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6"
    arguments = [
        "az", "iot", "ops", "connector", operation, "--instance", name, "--resource-group", group,
        "--output", "json", "--only-show-errors",
    ]
    if operation == "show":
        arguments.extend(["--ref", reference])
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False,
    )
    if channel == "stable":
        assert result.returncode != 0, f"Connector {operation} unexpectedly succeeded on a stable runtime."
        assert "requires a preview runtime; the target uses stable" in result.stderr.lower(), result.stderr
        assert not result.stdout.strip(), f"Rejected connector {operation} returned results."
        return

    assert result.returncode == 0, result.stderr
    if operation == "show":
        metadata = json.loads(result.stdout)
        assert metadata["metadataRef"] == reference
        assert isinstance(metadata["metadata"], dict) and metadata["metadata"]
        return
    connectors = json.loads(result.stdout)
    assert isinstance(connectors, list)
    for connector in connectors:
        assert connector["name"]
        assert connector["source"] in {"FirstParty", "Marketplace"}
        assert connector["metadataRef"]
        if connector["source"] == "FirstParty":
            metadata = run(shlex.join([
                "az", "iot", "ops", "connector", "show", "--ref", connector["metadataRef"],
                "--instance", name, "--resource-group", group,
                "--output", "json", "--only-show-errors",
            ]))
            assert metadata["metadataRef"] == connector["metadataRef"]
            assert isinstance(metadata["metadata"], dict) and metadata["metadata"]


def test_shared_instance_update_preserves_runtime_channel(channel_target):
    name, group, channel = channel_target
    before, instance, _ = read_runtime(name, group)
    description = instance["properties"].get("description") or ""
    try:
        run(f"az iot ops update -n {name} -g {group} --description channel-integration-check")
        after = assert_runtime(name, group, channel)
        assert after.identity == before.identity
    finally:
        # Use argv rather than shell quoting for arbitrary existing descriptions.
        subprocess.run(
            ["az", "iot", "ops", "update", "-n", name, "-g", group, "--description", description], check=True,
        )


@pytest.mark.serial
def test_preview_mcp_feature_toggle(channel_target):
    name, group, channel = channel_target
    if channel != "preview":
        pytest.skip("MCP is only supported on the preview runtime.")
    instance = run(f"az iot ops show -n {name} -g {group}")
    original_mode = instance.get("properties", {}).get("features", {}).get("mcp", {}).get("mode") or "Preview"
    try:
        disabled = run(f"az iot ops update -n {name} -g {group} --feature mcp.mode=Disabled")
        assert disabled["properties"]["features"]["mcp"]["mode"] == "Disabled"
        enabled = run(f"az iot ops update -n {name} -g {group} --feature mcp.mode=Preview")
        assert enabled["properties"]["features"]["mcp"]["mode"] == "Preview"
    finally:
        subprocess.run(
            ["az", "iot", "ops", "update", "-n", name, "-g", group, "--feature", f"mcp.mode={original_mode}"],
            check=True,
        )


@pytest.mark.serial
def test_cross_channel_upgrade_rejected_without_mutation(channel_target):
    name, group, channel = channel_target
    assert_runtime(name, group, channel)
    _, instance_before, extensions_before = read_runtime(name, group)
    opposite = "preview" if channel == "stable" else "stable"
    result = subprocess.run(
        ["az", "iot", "ops", "upgrade", "-n", name, "-g", group, "--ops-train", opposite,
         "--force", "--yes", "--no-progress"], capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0, "Cross-channel upgrade unexpectedly succeeded."
    assert any(message in result.stderr.lower() for message in (
        "cross-train", "ga clusters must remain ga", "train overrides cannot change",
    )), result.stderr
    _, instance_after, extensions_after = read_runtime(name, group)
    assert instance_after["properties"] == instance_before["properties"]
    # Controller status timestamps can advance independently of this rejected command.
    configuration = ("version", "releaseTrain", "configurationSettings", "autoUpgradeMinorVersion")
    before = {ext["id"]: {key: ext["properties"].get(key) for key in configuration} for ext in extensions_before}
    after = {ext["id"]: {key: ext["properties"].get(key) for key in configuration} for ext in extensions_after}
    assert after == before, "Rejected upgrade changed extension state."
