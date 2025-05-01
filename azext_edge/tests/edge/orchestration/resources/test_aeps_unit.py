# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from typing import Optional

from .conftest import get_base_endpoint, get_mock_resource

ADR_RP = "Microsoft.DeviceRegistry"
ADR_API_VERSION = "2024-11-01"


def get_aep_endpoint(resource_group_name: str, asset_name: Optional[str] = None) -> str:
    resource_path = "/assetEndpointProfiles"
    if asset_name:
        resource_path += f"/{asset_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=ADR_RP,
        api_version=ADR_API_VERSION,
    )


def get_mock_aep_record(aep_name: str, resource_group_name: str, properties: Optional[dict] = None) -> dict:
    default_properties = {
        "uuid": "54bde3af-30a7-4c4c-b517-4197b9d76475",
        "targetAddress": "opc.tcp://opcplc-000000.azure-iot-operations:50000",
        "endpointProfileType": "Microsoft.OpcUa",
        "authentication": {"method": "Anonymous"},
        "additionalConfiguration": "{}",
        "provisioningState": "Succeeded",
    }

    return get_mock_resource(
        name=aep_name,
        resource_path=f"/assetEndpointProfiles/{aep_name}",
        properties=properties or default_properties,
        resource_group_name=resource_group_name,
        qualified_type="microsoft.deviceregistry/assetendpointprofiles",
    )
