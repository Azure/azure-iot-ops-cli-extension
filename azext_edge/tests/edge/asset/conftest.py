# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from ...generators import generate_generic_id


@pytest.fixture()
def asset_helpers_fixture(mocker, request):
    # TODO: see if there is a nicer way to mass mock helper funcs
    helper_fixtures = []
    patched_sp = mocker.patch(f"{ASSETS_PATH}._process_asset_sub_points")
    patched_sp.return_value = request.param["process_asset_sub_points"]
    helper_fixtures.append(patched_sp)

    def mock_update_properties(properties, **kwargs):
        """Minimize how much to check by setting everything update properties should touch to None."""
        for k in kwargs:
            properties.pop(k, None)
        properties.pop("defaultDataPointsConfiguration", None)
        properties.pop("defaultEventsConfiguration", None)
        properties["result"] = request.param["update_properties"]

    patched_up = mocker.patch(f"{ASSETS_PATH}._update_properties")
    patched_up.side_effect = mock_update_properties
    helper_fixtures.append(patched_up)
    yield helper_fixtures


# Paths for mocking
ASSETS_PATH = "azext_edge.edge.providers.assets"

# Generic objects
MINIMUM_ASSET = {
    "extendedLocation": {
        "name": generate_generic_id(),
        "type": generate_generic_id(),
    },
    "id": generate_generic_id(),
    "location": "westus3",
    "name": "props-test-min",
    "properties": {
        "assetEndpointProfileUri": generate_generic_id(),
        "dataPoints": [],
        "defaultDataPointsConfiguration": "{\"publishingInterval\": 1000, \"samplingInterval\": 500, "
        "\"queueSize\": 1}",
        "defaultEventsConfiguration": "{\"publishingInterval\": 1000, \"samplingInterval\": 500, \"queueSize\": 1}",
        "displayName": "props-test-min",
        "enabled": True,
        "events": [],
        "externalAssetId": generate_generic_id(),
        "provisioningState": "Accepted",
        "uuid": generate_generic_id(),
        "version": 1
    },
    "resourceGroup": generate_generic_id(),
    "type": "microsoft.deviceregistry/assets"
}
FULL_ASSET = {
    "extendedLocation": {
        "name": generate_generic_id(),
        "type": generate_generic_id(),
    },
    "id": generate_generic_id(),
    "location": "westus3",
    "name": "props-test-max",
    "properties": {
        "assetType": generate_generic_id(),
        "assetEndpointProfileUri": generate_generic_id(),
        "dataPoints": [
            {
                "capabilityId": generate_generic_id(),
                "dataPointConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "dataSource": generate_generic_id(),
                "name": generate_generic_id(),
                "observabilityMode": generate_generic_id()
            },
            {
                "dataPointConfiguration": "{}",
                "dataSource": generate_generic_id(),
            },
            {
                "capabilityId": generate_generic_id(),
                "dataPointConfiguration": "{\"samplingInterval\": 100}",
                "dataSource": generate_generic_id(),
                "name": generate_generic_id(),
                "observabilityMode": generate_generic_id()
            }
        ],
        "defaultDataPointsConfiguration": "{\"publishingInterval\": \"100\", \"samplingInterval\": \"10\","
        " \"queueSize\": \"2\"}",
        "defaultEventsConfiguration": "{\"publishingInterval\": \"200\", \"samplingInterval\": \"20\", "
        "\"queueSize\": \"3\"}",
        "description": generate_generic_id(),
        "displayName": "props-test-max",
        "documentationUri": generate_generic_id(),
        "enabled": False,
        "events": [
            {
                "capabilityId": generate_generic_id(),
                "eventConfiguration": "{\"samplingInterval\": 100}",
                "eventNotifier": generate_generic_id(),
                "name": generate_generic_id(),
                "observabilityMode": generate_generic_id()
            },
            {
                "eventConfiguration": "{}",
                "eventNotifier": generate_generic_id(),
            },
            {
                "capabilityId": generate_generic_id(),
                "eventConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "eventNotifier": generate_generic_id(),
                "name": generate_generic_id(),
                "observabilityMode": generate_generic_id()
            },
        ],
        "externalAssetId": generate_generic_id(),
        "hardwareRevision": generate_generic_id(),
        "manufacturer": generate_generic_id(),
        "manufacturerUri": generate_generic_id(),
        "model": generate_generic_id(),
        "productCode": generate_generic_id(),
        "provisioningState": "Failed",
        "serialNumber": generate_generic_id(),
        "softwareRevision": generate_generic_id(),
        "uuid": generate_generic_id(),
        "version": 1
    },
    "resourceGroup": generate_generic_id(),
    "tags": {
        generate_generic_id(): generate_generic_id(),
        generate_generic_id(): generate_generic_id()
    },
    "type": "microsoft.deviceregistry/assets"
}
