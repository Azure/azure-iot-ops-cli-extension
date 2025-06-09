# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from copy import deepcopy
from typing import Optional
from ....generators import generate_random_string, get_zeroed_subscription
from ....helpers import run


@pytest.fixture()
def require_init(init_setup):
    # get the custom location used for tests.
    if not all([init_setup.get("instanceName"), init_setup.get("resourceGroup")]):
        pytest.skip("Cannot run this test without knowing the instance information.")

    cluster_result = run(
        f"az iot ops show -n {init_setup['instanceName']} -g {init_setup['resourceGroup']} "
    )
    init_setup["customLocationId"] = cluster_result["extendedLocation"]["name"]
    yield init_setup


@pytest.fixture()
def asset_helpers_fixture(mocker, request):
    request_params = getattr(request, "param", {})
    patched_sp = mocker.patch(f"{ASSETS_PATH}._process_asset_sub_points")
    patched_sp.return_value = request_params.get("process_asset_sub_points", [generate_random_string()])
    patched_spfp = mocker.patch(f"{ASSETS_PATH}._process_asset_sub_points_file_path")
    patched_spfp.return_value = request_params.get(
        "process_asset_sub_points_file_path", [generate_random_string()]
    )

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
        "process_asset_sub_points_file_path": patched_spfp,
        "update_properties": patched_up,
        "convert_sub_points_to_csv": patched_to_csv,
        "convert_sub_points_from_csv": patched_from_csv
    }


@pytest.fixture()
def mocked_get_extended_location(mocker):
    result = {
        "type": "CustomLocation",
        "name": generate_random_string(),
        "cluster_location": generate_random_string()
    }
    mock = mocker.patch(
        "azext_edge.edge.providers.rpsaas.adr.helpers.get_extended_location",
        return_value=result,
        autospec=True
    )
    mock.original_return_value = deepcopy(result)
    yield mock


@pytest.fixture()
def mocked_check_cluster_connectivity(mocker):
    yield mocker.patch(
        "azext_edge.edge.providers.rpsaas.adr.helpers.check_cluster_connectivity",
        autospec=True
    )


def get_asset_id(
    asset_name: Optional[str] = None,
    asset_resource_group: Optional[str] = None,
    asset_subscription: Optional[str] = None,
    discovered: bool = False
) -> str:
    asset_subscription = asset_subscription or get_zeroed_subscription()
    asset_type = "discoveredAssets" if discovered else "assets"
    asset_resource_group = f"/resourceGroups/{asset_resource_group}" if asset_resource_group else ""
    asset_name = f"/{asset_name}" if asset_name else ""

    return f"/subscriptions/{asset_subscription}{asset_resource_group}/providers/"\
        f"Microsoft.DeviceRegistry/{asset_type}{asset_name}"


def get_profile_id(
    profile_name: Optional[str] = None,
    profile_resource_group: Optional[str] = None,
    profile_subscription: Optional[str] = None,
    discovered: bool = False
) -> str:
    profile_subscription = profile_subscription or get_zeroed_subscription()
    profile_type = "discoveredAssetEndpointProfiles" if discovered else "assetEndpointProfiles"
    profile_resource_group = f"/resourceGroups/{profile_resource_group}" if profile_resource_group else ""
    profile_name = f"/{profile_name}" if profile_name else ""

    return f"/subscriptions/{profile_subscription}{profile_resource_group}/providers/"\
        f"Microsoft.DeviceRegistry/{profile_type}{profile_name}"


def get_mgmt_uri(resource_id: str):
    return f"https://management.azure.com{resource_id}"


def get_asset_mgmt_uri(
    asset_name: Optional[str] = None,
    asset_resource_group: Optional[str] = None,
    asset_subscription: Optional[str] = None,
    discovered: bool = False
) -> str:
    asset_id = get_asset_id(
        asset_name=asset_name,
        asset_resource_group=asset_resource_group,
        asset_subscription=asset_subscription,
        discovered=discovered
    )
    return f"https://management.azure.com{asset_id}"


def get_asset_record(
    asset_name: str,
    asset_resource_group: str,
    asset_subscription: Optional[str] = None,
    full: bool = True,
    discovered: bool = False
) -> dict:
    asset_id = get_asset_id(asset_name, asset_resource_group, asset_subscription, discovered)
    asset = deepcopy(FULL_ASSET) if full else deepcopy(MINIMUM_ASSET)
    asset["name"] = asset_name
    asset["resourceGroup"] = asset_resource_group
    asset["id"] = asset_id
    if discovered:
        asset["type"] = "microsoft.deviceregistry/discoveredAssets"
    return asset


def get_profile_record(
    profile_name: str,
    profile_resource_group: str,
    profile_subscription: Optional[str] = None,
    full: bool = True,
    discovered: bool = False
) -> dict:
    profile_id = get_profile_id(profile_name, profile_resource_group, profile_subscription, discovered)
    asset = deepcopy(FULL_AEP) if full else deepcopy(MINIMUM_AEP)
    asset["name"] = profile_name
    asset["resourceGroup"] = profile_resource_group
    asset["id"] = profile_id
    if discovered:
        asset["type"] = "microsoft.deviceregistry/discoveredAssetEndpointProfiles"
    return asset


# Paths for mocking
ASSETS_PATH = "azext_edge.edge.providers.rpsaas.adr.assets"

# Generic objects
# Assets
MINIMUM_ASSET = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "location": "westus3",
    "name": "props-test-min",
    "properties": {
        "assetEndpointProfileUri": generate_random_string(),
        "defaultDatasetConfiguration": "{\"publishingInterval\": 1000, \"samplingInterval\": 500, "
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
    "location": "westus3",
    "name": "props-test-max",
    "properties": {
        "assetType": generate_random_string(),
        "assetEndpointProfileUri": generate_random_string(),
        "attributes": {
            generate_random_string(): generate_random_string(),
            generate_random_string(): generate_random_string()
        },
        "datasets": [
            {
                "name": "default",
                "dataPoints": [
                    {
                        "capabilityId": generate_random_string(),
                        "dataPointConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                        "dataSource": generate_random_string(),
                        "name": generate_random_string(),
                        "observabilityMode": generate_random_string()
                    },
                    {
                        "name": generate_random_string(),
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
                ]
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
                "name": generate_random_string(),
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


# Asset Endpoint Profiles
MINIMUM_AEP = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "id": generate_random_string(),
    "location": "westus3",
    "name": "aep-min",
    "properties": {
        "endpointProfileType": generate_random_string(),
        "targetAddress": generate_random_string(),
        "authentication": {
            "method": "Anonymous"
        },
    },
    "resourceGroup": generate_random_string(),
    "type": "microsoft.deviceregistry/assetendpointprofiles"
}
# TODO: add in additional config
FULL_AEP = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "id": generate_random_string(),
    "location": "westus3",
    "name": "aep-full",
    "properties": {
        "additionalConfiguration": {
            "applicationName": generate_random_string(),
            "keepAliveMilliseconds": 10,
            "defaults": {
                "publishingIntervalMilliseconds": 0,
                "samplingIntervalMilliseconds": 0,
                "queueSize": 0
            },
            "session": {
                "timeoutMilliseconds": 0,
                "keepAliveIntervalMilliseconds": 0,
                "reconnectPeriodMilliseconds": 100,
                "reconnectExponentialBackOffMilliseconds": 300
            },
            "subscription": {
                "maxItems": 10,
                "lifeTimeMilliseconds": 5000
            },
            "security": {
                "autoAcceptUntrustedServerCertificates": True,
                "securityPolicy": generate_random_string(),
                "securityMode": "sign"
            },
            "runAssetDiscovery": True
        },
        "endpointProfileType": "Microsoft.OpcUa",
        "targetAddress": generate_random_string(),
        "authentication": {
            "method": "UsernamePassword",
            "usernamePasswordCredentials": {
                "passwordReference": generate_random_string(),
                "usernameReference": generate_random_string()
            }
        },
    },
    "resourceGroup": generate_random_string(),
    "type": "microsoft.deviceregistry/assetendpointprofiles"
}
