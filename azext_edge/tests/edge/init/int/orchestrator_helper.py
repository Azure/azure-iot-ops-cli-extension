# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
from .helper import get_resource_from_partial_id, ResourceKeys


def assert_orchestrator_args(
    resource_group: str,
    cluster_name: str,
    namespace: str,
    init_resources: List[str],
    target: Optional[str] = None,
    # opcua_discovery_url: Optional[str] = None,
    simulate_plc: Optional[bool] = None,
    **_
):
    resources = [res for res in init_resources if res.startswith(ResourceKeys.orchestrator.value)]
    assert len(resources) == 1

    expected_name = target or (f"{cluster_name}-ops-init-target")
    assert resources[0].endswith(expected_name)

    # orch_obj = get_resource_from_partial_id(resources[0], resource_group)
    # if simulate_plc:
    #     from yaml import safe_load
    #     components = orch_obj["properties"]["components"]
    #     akri_component = None
    #     for comp in components:
    #         if comp["name"] == "akri-opcua-asset":
    #             akri_component = comp
    #             break
    #     discovery_yaml = akri_component["properties"]["resource"]["spec"]["discoveryHandler"]["discoveryDetails"]
    #     discovery_yaml = safe_load(discovery_yaml)
    #     expected_url = opcua_discovery_url or f"opc.tcp://opcplc-000000.{namespace}:50000"
    #     assert discovery_yaml["opcuaDiscoveryMethod"][0]["asset"]["endpointUrl"] == expected_url
