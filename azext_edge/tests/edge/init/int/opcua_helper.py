# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from azext_edge.edge.providers.edge_api import (
    OPCUA_API_V1, OpcuaResourceKinds, DEVICEREGISTRY_API_V1, DeviceRegistryResourceKinds
)
from ....helpers import get_kubectl_custom_items, get_kubectl_workload_items


def assert_simulate_plc_args(
    namespace: str,
    simulate_plc: Optional[bool] = None,
    **_
):
    if not simulate_plc:
        simulate_plc = False

    simulator_pod = get_kubectl_workload_items(
        prefixes="opcplc-00000", service_type="pod", namespace=namespace
    )
    assert bool(simulator_pod) is simulate_plc

    resource_map = get_kubectl_custom_items(resource_api=OPCUA_API_V1, namespace=namespace)
    resource_map.update(get_kubectl_custom_items(resource_api=DEVICEREGISTRY_API_V1, namespace=namespace))
    assert bool(resource_map[OpcuaResourceKinds.ASSET_TYPE.value]) is simulate_plc
    assert bool(resource_map[DeviceRegistryResourceKinds.ASSET.value]) is simulate_plc
    assert bool(resource_map[DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value]) is simulate_plc
