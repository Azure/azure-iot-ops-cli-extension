# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from .....generators import generate_random_string


@pytest.fixture()
def asset_helpers_fixture(mocker, request):
    request_params = getattr(request, "param", {})
    patched_sp = mocker.patch(f"{ASSETS_PATH}._process_asset_sub_points")
    patched_sp.return_value = request_params.get("process_asset_sub_points", generate_random_string())

    def mock_update_properties(properties, **kwargs):
        """Minimize how much to check by setting everything update properties should touch to None."""
        for k in kwargs:
            properties.pop(k, None)
        properties.pop("defaultDataPointsConfiguration", None)
        properties.pop("defaultEventsConfiguration", None)
        properties["result"] = request_params.get("update_properties", generate_random_string())

    patched_up = mocker.patch(f"{ASSETS_PATH}._update_properties")
    patched_up.side_effect = mock_update_properties

    patched_to_csv = mocker.patch(f"{ASSETS_PATH}._convert_sub_points_to_csv")
    patched_to_csv.return_value = request_params.get("convert_sub_points_to_csv", generate_random_string())

    patched_from_csv = mocker.patch(f"{ASSETS_PATH}._convert_sub_points_from_csv")
    yield {
        "process_asset_sub_points": patched_sp,
        "update_properties": patched_up,
        "convert_sub_points_to_csv": patched_to_csv,
        "convert_sub_points_from_csv": patched_from_csv
    }


# Paths for mocking
ASSETS_PATH = "azext_edge.edge.providers.rpsaas.adr.assets"

# Generic objects
MINIMUM_ASSET = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "id": generate_random_string(),
    "location": "westus3",
    "name": "props-test-min",
    "properties": {
        "assetEndpointProfileUri": generate_random_string(),
        "defaultDataPointsConfiguration": "{\"publishingInterval\": 1000, \"samplingInterval\": 500, "
        "\"queueSize\": 1}",
        "defaultEventsConfiguration": "{\"publishingInterval\": 1000, \"samplingInterval\": 500, \"queueSize\": 1}",
        "displayName": "props-test-min",
        "enabled": True,
        "externalAssetId": generate_random_string(),
        "provisioningState": "Accepted",
        "uuid": generate_random_string(),
        "version": 1
    },
    "resourceGroup": generate_random_string(),
    "type": "microsoft.deviceregistry/assets"
}
FULL_ASSET = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "id": generate_random_string(),
    "location": "westus3",
    "name": "props-test-max",
    "properties": {
        "assetType": generate_random_string(),
        "assetEndpointProfileUri": generate_random_string(),
        "dataPoints": [
            {
                "capabilityId": generate_random_string(),
                "dataPointConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "dataSource": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            },
            {
                "dataPointConfiguration": "{}",
                "dataSource": generate_random_string(),
            },
            {
                "capabilityId": generate_random_string(),
                "dataPointConfiguration": "{\"samplingInterval\": 100}",
                "dataSource": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            }
        ],
        "defaultDataPointsConfiguration": "{\"publishingInterval\": \"100\", \"samplingInterval\": \"10\","
        " \"queueSize\": \"2\"}",
        "defaultEventsConfiguration": "{\"publishingInterval\": \"200\", \"samplingInterval\": \"20\", "
        "\"queueSize\": \"3\"}",
        "description": generate_random_string(),
        "displayName": "props-test-max",
        "documentationUri": generate_random_string(),
        "enabled": False,
        "events": [
            {
                "capabilityId": generate_random_string(),
                "eventConfiguration": "{\"samplingInterval\": 100}",
                "eventNotifier": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            },
            {
                "eventConfiguration": "{}",
                "eventNotifier": generate_random_string(),
            },
            {
                "capabilityId": generate_random_string(),
                "eventConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "eventNotifier": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            },
        ],
        "externalAssetId": generate_random_string(),
        "hardwareRevision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturerUri": generate_random_string(),
        "model": generate_random_string(),
        "productCode": generate_random_string(),
        "provisioningState": "Failed",
        "serialNumber": generate_random_string(),
        "softwareRevision": generate_random_string(),
        "uuid": generate_random_string(),
        "version": 1
    },
    "resourceGroup": generate_random_string(),
    "tags": {
        generate_random_string(): generate_random_string(),
        generate_random_string(): generate_random_string()
    },
    "type": "microsoft.deviceregistry/assets"
}
