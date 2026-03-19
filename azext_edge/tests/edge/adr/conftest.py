# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from copy import deepcopy
from typing import Optional

from azext_edge.edge.util.id_tools import parse_resource_id
from ...generators import generate_random_string, get_zeroed_subscription
from ...helpers import run


@pytest.fixture()
def require_namespace_init(require_init):
    """Extends require_init to ensure the instance has an ADR namespace reference.

    If the instance does not have one, the test is skipped. Set up a namespace
    manually before running these tests — see README or conftest docstring.
    """
    if not require_init.get("adrNamespaceRef"):
        pytest.skip(
            "Instance does not have an ADR namespace reference (adrNamespaceRef). "
            "Create one and link it to the instance before running namespace tests. "
            "See: az iot ops ns create / az iot ops update"
        )
    yield require_init


@pytest.fixture(scope="module")
def require_namespace_init_module(require_init_module):
    """Module-scoped version of require_namespace_init for shared fixtures."""
    if not require_init_module.get("adrNamespaceRef"):
        pytest.skip(
            "Instance does not have an ADR namespace reference (adrNamespaceRef). "
            "Create one and link it to the instance before running namespace tests. "
            "See: az iot ops ns create / az iot ops update"
        )
    yield require_init_module


@pytest.fixture(scope="module")
def shared_device(require_namespace_init_module, tracked_resources):
    """Single shared device for all tests in this module."""
    instance_name = require_namespace_init_module["instanceName"]
    resource_group = require_namespace_init_module["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    result = run(
        f"az iot ops ns device create --name {device_name} "
        f"--instance {instance_name} -g {resource_group}"
    )
    if isinstance(result, dict) and "id" in result:
        tracked_resources.append(result["id"])
    yield device_name


@pytest.fixture(scope="module")
def endpoint_cache():
    """Module-scoped cache for endpoint names keyed by (type, address)."""
    yield {}


@pytest.fixture(scope="module")
def format_test_asset_cache():
    """Module-scoped cache for assets shared across format variants."""
    yield {}


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
        "cluster_location": generate_random_string(),
        "namespace": parse_resource_id(
            rid=f"/subscriptions/{get_zeroed_subscription()}/resourceGroups/{generate_random_string()}"
            f"/providers/Microsoft.DeviceRegistry/namespaces/{generate_random_string()}"
        )
    }
    mock = mocker.patch(
        "azext_edge.edge.providers.adr.helpers.get_extended_location",
        return_value=result,
        autospec=True
    )
    mock.original_return_value = deepcopy(result)
    yield mock


@pytest.fixture()
def mocked_check_cluster_connectivity(mocker):
    # Patch where the function is used (namespace_assets), not where it's defined (helpers)
    mock = mocker.Mock()
    for target in [
        "azext_edge.edge.providers.adr.namespace_assets.check_cluster_connectivity",
        "azext_edge.edge.providers.adr.helpers.check_cluster_connectivity",
    ]:
        mocker.patch(target, mock)
    yield mock


@pytest.fixture()
def mocked_get_namespace_for_instance(mocker):
    # Patch where the function is used (namespace_assets), not where it's defined (helpers)
    return_value = parse_resource_id(
        rid=f"/subscriptions/{get_zeroed_subscription()}/resourceGroups/rg{generate_random_string(size=5)}"
        f"/providers/Microsoft.DeviceRegistry/namespaces/ns{generate_random_string(size=5)}"
    )

    # Use a shared mock so assertions capture calls from any module under test.
    mock = mocker.Mock(return_value=return_value)

    for target in [
        "azext_edge.edge.providers.adr.namespace_assets.get_namespace_for_instance",
        "azext_edge.edge.providers.adr.helpers.get_namespace_for_instance",
    ]:
        mocker.patch(target, mock)

    yield mock


@pytest.fixture()
def mocked_connector_metadata_validator(mocker):
    """Mock the ConnectorMetadataValidator to avoid actual validation during tests."""
    mock_validator_instance = mocker.Mock()
    mock_validator_instance.validate_dataset = mocker.Mock(return_value=None)
    mock_validator_instance.validate_datapoint = mocker.Mock(return_value=None)
    mock_validator_instance.validate_event = mocker.Mock(return_value=None)
    mock_validator_instance.validate_event_group = mocker.Mock(return_value=None)

    mock_validator_class = mocker.Mock(return_value=mock_validator_instance)
    mock_validator_class.from_asset = mocker.Mock(return_value=mock_validator_instance)

    mocker.patch(
        "azext_edge.edge.providers.adr.namespace_assets.ConnectorMetadataValidator",
        mock_validator_class
    )

    yield mock_validator_instance


@pytest.fixture()
def mocked_get_endpoint_version_from_template(mocker):
    """
    Mock ConnectorTemplates to return None from get_endpoint_version_for_type by default.
    This prevents the class from making API calls during unit tests.
    """
    mock = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    # Configure the mock instance's get_endpoint_version_for_type method
    mock.return_value.get_endpoint_version_for_type.return_value = None
    # Yield the method mock so tests can configure return values
    yield mock.return_value.get_endpoint_version_for_type


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
ASSETS_PATH = "azext_edge.edge.providers.adr.assets"

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
