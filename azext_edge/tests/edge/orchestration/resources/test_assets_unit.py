# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from typing import Optional

from .conftest import get_base_endpoint, get_mock_resource

ADR_RP = "Microsoft.DeviceRegistry"
ADR_API_VERSION = "2024-11-01"


def get_asset_endpoint(resource_group_name: str, asset_name: Optional[str] = None) -> str:
    resource_path = "/assets"
    if asset_name:
        resource_path += f"/{asset_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=ADR_RP,
        api_version=ADR_API_VERSION,
    )


def get_mock_asset_record(asset_name: str, resource_group_name: str, properties: Optional[dict] = None) -> dict:
    default_properties = {
        "uuid": "0808929d-0801-4f8f-a4a1-244bdd64c766",
        "enabled": True,
        "externalAssetId": "18b6939b-05ee-4cae-bf85-fceeeb179a55",
        "displayName": "A thermostat generating only events",
        "description": "An aep0asset0n21 sample thermostat",
        "assetEndpointProfileRef": "aep0n69",
        "version": 1,
        "defaultDatasetsConfiguration": '{"publishingInterval": 1000, "samplingInterval": 500, "queueSize": 1}',
        "defaultEventsConfiguration": '{"publishingInterval": 1000, "samplingInterval": 500, "queueSize": 1}',
        "datasets": [
            {
                "name": "default",
                "dataPoints": [
                    {
                        "name": "point0",
                        "dataSource": "source0",
                        "observabilityMode": "Histogram",
                        "dataPointConfiguration": '{"samplingInterval": 40, "queueSize": 10}',
                    },
                    {
                        "name": "point1",
                        "dataSource": "source1",
                        "observabilityMode": "Histogram",
                        "dataPointConfiguration": "{}",
                    },
                ],
            }
        ],
        "events": [
            {
                "name": "event0",
                "eventNotifier": "notifier0",
                "observabilityMode": "None",
                "eventConfiguration": '{"samplingInterval": 40, "queueSize": 10}',
            },
            {
                "name": "event1",
                "eventNotifier": "notifier1",
                "observabilityMode": "Log",
                "eventConfiguration": "{}",
            },
        ],
        "status": {"errors": []},
        "provisioningState": "Succeeded",
    }

    return get_mock_resource(
        name=asset_name,
        resource_path=f"/assets/{asset_name}",
        properties=properties or default_properties,
        resource_group_name=resource_group_name,
        qualified_type="microsoft.deviceregistry/assets",
    )
