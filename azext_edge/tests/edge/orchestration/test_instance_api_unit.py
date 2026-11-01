# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.instance_api import (
    INSTANCE_API_VERSIONS,
    OLDEST_INSTANCE_API_VERSION,
    get_enabled_iotops_api_versions,
    get_instance_iotops_api_version,
)
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.util.az_client import DEFAULT_IOTOPS_MGMT_API_VERSION
from azext_edge.edge.util.cloud_config import CLOUD_AZURE_PUBLIC, CLOUD_AZURE_US_GOVERNMENT

from ...generators import get_zeroed_subscription

INSTANCE_API_PATH = "azext_edge.edge.providers.orchestration.instance_api"
SUBSCRIPTION = get_zeroed_subscription()
CUSTOM_LOCATION_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/cl-rg/providers/Microsoft.ExtendedLocation/customLocations/my-cl"
)


@pytest.mark.parametrize(
    "version,expected",
    [
        ("1.0.34", "2024-11-01"),
        ("1.1.59", "2025-04-01"),
        ("1.2.36", "2025-10-01"),
        ("1.3.14", "2026-03-01"),
        ("1.3.99", "2026-03-01"),
        ("1.4.0", "2026-07-01"),
        ("1.4.112", "2026-07-01"),
        ("1.5.0", "2026-10-01"),
        ("1.5.42", "2026-10-01"),
        ("1.6.0-preview.40", "2026-10-01"),
        ("2.0.0", "2026-10-01"),
        # Prerelease builds map with their release line.
        ("1.5.0-preview.3", "2026-10-01"),
        ("1.4.0-main.20260301.1", "2026-07-01"),
        ("1.3.14-rc.1", "2026-03-01"),
    ],
)
def test_get_instance_iotops_api_version(version: str, expected: str):
    assert get_instance_iotops_api_version(version) == expected


@pytest.mark.parametrize("version", [None, "", "not-a-version", "1.4"])
def test_get_instance_iotops_api_version_unknown_keeps_default(version):
    assert get_instance_iotops_api_version(version) == DEFAULT_IOTOPS_MGMT_API_VERSION.value


def test_instance_api_versions_table_is_ordered():
    """Rows are newest first, and a newer AIO line never maps to an older API version."""
    minimums = [minimum for minimum, _ in INSTANCE_API_VERSIONS]
    api_versions = [api_version.value for _, api_version in INSTANCE_API_VERSIONS]

    assert minimums == sorted(minimums, reverse=True)
    assert api_versions == sorted(api_versions, reverse=True)
    assert OLDEST_INSTANCE_API_VERSION.value < api_versions[-1]


@pytest.mark.parametrize("cloud_name", [CLOUD_AZURE_PUBLIC, CLOUD_AZURE_US_GOVERNMENT])
def test_current_ga_runtime_maps_to_its_profile_api_version(cloud_name: str):
    """Refreshing the GA runtime to a newer API version must also extend the instance API table."""
    profile = get_runtime_catalog(cloud_name).for_create()

    assert get_instance_iotops_api_version(profile.identity.version) == profile.iotops_api_version
    assert profile.iotops_api_version == DEFAULT_IOTOPS_MGMT_API_VERSION.value


def _enabled_type(api_version: str, namespace: str = "Microsoft.IoTOperations", resource_type: str = "instances/x"):
    return {"apiVersion": api_version, "resourceProviderNamespace": namespace, "resourceType": resource_type}


def test_get_enabled_iotops_api_versions(mocker):
    client_factory = mocker.patch(f"{INSTANCE_API_PATH}.get_extloc_mgmt_client")
    list_enabled = client_factory.return_value.custom_locations.list_enabled_resource_types
    list_enabled.return_value = iter(
        [
            {"properties": {"typesMetadata": [_enabled_type("2026-03-01"), _enabled_type("2026-07-01")]}},
            # The resource provider namespace is compared case-insensitively.
            {"properties": {"typesMetadata": [_enabled_type("2025-10-01", namespace="microsoft.iotoperations")]}},
            # Other resource providers and incomplete entries are ignored.
            {"properties": {"typesMetadata": [_enabled_type("2030-01-01", namespace="Microsoft.Other")]}},
            {"properties": {"typesMetadata": [{"resourceProviderNamespace": "Microsoft.IoTOperations"}]}},
            {"properties": {"typesMetadata": None}},
            {"properties": None},
            {},
        ]
    )

    gov_endpoint = "https://management.usgovcloudapi.net/"

    result = get_enabled_iotops_api_versions(CUSTOM_LOCATION_ID, endpoint=gov_endpoint)

    assert result == {"2025-10-01", "2026-03-01", "2026-07-01"}
    client_factory.assert_called_once_with(subscription_id=SUBSCRIPTION, endpoint=gov_endpoint)
    list_enabled.assert_called_once_with(resource_group_name="cl-rg", resource_name="my-cl")


@pytest.mark.parametrize("custom_location_id", [None, "", "not-a-resource-id"])
def test_get_enabled_iotops_api_versions_invalid_custom_location(mocker, custom_location_id):
    client_factory = mocker.patch(f"{INSTANCE_API_PATH}.get_extloc_mgmt_client")

    assert get_enabled_iotops_api_versions(custom_location_id) == set()
    client_factory.assert_not_called()


def _fail_after_first_page():
    yield {"properties": {"typesMetadata": [_enabled_type("2026-07-01")]}}
    raise HttpResponseError("forbidden")


@pytest.mark.parametrize("failure", ["on-request", "while-paging"])
def test_get_enabled_iotops_api_versions_unreadable_returns_empty(mocker, failure: str):
    """An unreadable custom location is unknown, never a partial answer."""
    list_enabled = mocker.patch(
        f"{INSTANCE_API_PATH}.get_extloc_mgmt_client"
    ).return_value.custom_locations.list_enabled_resource_types
    if failure == "on-request":
        list_enabled.side_effect = HttpResponseError("forbidden")
    else:
        list_enabled.return_value = _fail_after_first_page()

    assert get_enabled_iotops_api_versions(CUSTOM_LOCATION_ID) == set()
