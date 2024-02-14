# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from ...generators import generate_generic_id
# from ...helpers import run


@pytest.fixture
def skip_if_no_init(settings):
    if getattr(settings.env, "azext_edge_skip_init"):
        pytest.skip("Test skipped because `az iot ops init` skipped.")


def idfn(val):
    if not val:
        return "min"
    name = []
    if "--cluster-namespace" in val:
        name.append("Custom namespace")
    if "--opcua-discovery-url" in val:
        name.append("Akri")
    if "--dp-instance" in val:
        name.append("Data Processor")
    if "--simulate-plc" in val:
        name.append("OPC-UA Broker")

    return ", ".join(name)


@pytest.mark.parametrize("init_setup", [
    {},
    {
        "--cluster-namespace": generate_generic_id(),
        "--opcua-discovery-url": f"opc.tcp://opcplc-000000.{generate_generic_id()[:5]}:50000"
    },
    {
        "--dp-instance": f"{generate_generic_id()[:5]}-processor",
        "--dp-message-stores": 2,
        "--dp-reader-workers": 3,
        "--dp-runner-workers": 4
    },
    {"--simulate-plc": True},

], ids=idfn, indirect=True)
def test_init(init_setup, skip_if_no_init):
    # TODO: some commands to make sure stuff got generated correctly
    pass
