# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import responses

from azext_edge.edge.commands_namespaces import (
    show_namespace_asset,
    delete_namespace_asset,
)

from .conftest import get_namespace_mgmt_uri
from ....generators import generate_random_string


NAMESPACE_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/assets"
RESOURCE_API_VERSION = "2024-03-01"


def get_namespace_asset_mgmt_uri(asset_name: str, namespace_name: str, namespace_resource_group: str) -> str:
    """
    Get the management URI for a namespace asset.
    """
    base_uri = get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=namespace_resource_group)
    base_uri += f"/assets" + (f"/{asset_name}" if asset_name else "")
    return f"{base_uri}?api-version={RESOURCE_API_VERSION}"


def get_namespace_asset_record(
    asset_name: str, namespace_name: str, namespace_resource_group: str
) -> dict:
    """
    Get a mock namespace asset record.
    """
    return {
        "name": asset_name,
        "id": f"/subscriptions/sub1/resourceGroups/{namespace_resource_group}/providers/{NAMESPACE_ASSET_RESOURCE_TYPE}/{namespace_name}/{asset_name}",
        "type": NAMESPACE_ASSET_RESOURCE_TYPE,
        "properties": {
            "deviceRef": {
                "deviceName": "testDevice",
                "endpointName": "testEndpoint"
            },
            "description": "Test asset description",
            "displayName": "Test Asset",
            "provisioningState": "Succeeded"
        }
    }


@pytest.mark.parametrize("response_status", [200, 404])
def test_show_namespace_asset(mocked_cmd, mocked_responses: responses, response_status: int):
    """
    Test the show_namespace_asset function.
    """
    # Setup variables
    asset_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock response
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        namespace_resource_group=resource_group_name
    )

    # Add mock response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            namespace_resource_group=resource_group_name
        ),
        json=mock_asset_record if response_status == 200 else {"error": {"code": "NotFound", "message": "Asset not found"}},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            show_namespace_asset(
                cmd=mocked_cmd,
                asset_name=asset_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            )
        return

    # Test show_namespace_asset for success case
    result = show_namespace_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Verify result matches mock response
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [202, 404])
def test_delete_namespace_asset(mocked_cmd, mocked_responses: responses, response_status: int):
    """
    Test the delete_namespace_asset function.
    """
    # Setup variables
    asset_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock response
    mock_response = {} if response_status == 202 else {"error": {"code": "NotFound", "message": "Asset not found"}}

    # Add mock response
    mocked_responses.add(
        method=responses.DELETE,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            namespace_resource_group=resource_group_name
        ),
        json=mock_response,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 202:
        with pytest.raises(Exception):
            delete_namespace_asset(
                cmd=mocked_cmd,
                asset_name=asset_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0
            )
        return

    # Test delete_namespace_asset for success case
    result = delete_namespace_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0
    )

    # Verify result matches mock response
    assert result == mock_response
    assert len(mocked_responses.calls) == 1
