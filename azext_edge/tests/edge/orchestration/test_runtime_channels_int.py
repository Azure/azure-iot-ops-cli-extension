# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Shared runtime behavior and channel-boundary tests, run unchanged on GA and preview."""

import os
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
