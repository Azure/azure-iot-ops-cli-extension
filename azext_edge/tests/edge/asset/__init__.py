# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from ...generators import generate_generic_id


# Paths for mocking
ASSETS_PATH = "azext_edge.edge.commands_assets"

# Main command paths
SHOW_ASSETS_PATH = f"{ASSETS_PATH}.show_asset"

# Helper paths
BUILD_SUB_POINT_ASSETS_PATH = f"{ASSETS_PATH}._build_asset_sub_point"
CHECK_ASSET_PREREQS_PATH = f"{ASSETS_PATH}._check_asset_cluster_and_custom_location"
PROCESS_SUB_POINTS_ASSETS_PATH = f"{ASSETS_PATH}._process_asset_sub_points"
UPDATE_PROPERTIES_ASSETS_PATH = f"{ASSETS_PATH}._update_properties"

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
        "connectivityProfileUri": generate_generic_id(),
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
        "connectivityProfileUri": generate_generic_id(),
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
