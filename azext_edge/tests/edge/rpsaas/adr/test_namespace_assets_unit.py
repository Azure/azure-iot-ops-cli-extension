# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
import json
import pytest
import responses

from azext_edge.edge.commands_namespaces import (
    show_namespace_asset,
    delete_namespace_asset,
    update_namespace_asset,
)

from .conftest import get_namespace_mgmt_uri
from ....generators import BASE_URL, generate_random_string


NAMESPACE_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/assets"
RESOURCE_API_VERSION = "2024-03-01"


def get_namespace_asset_mgmt_uri(
    namespace_name: str, resource_group_name: str, asset_name: Optional[str] = None
) -> str:
    """
    Get the management URI for a namespace asset.
    """
    base_uri = get_namespace_mgmt_uri(
        namespace_name=namespace_name, namespace_resource_group=resource_group_name
    )
    base_uri += "/assets" + (f"/{asset_name}" if asset_name else "")
    return f"{base_uri}?api-version={RESOURCE_API_VERSION}"


def get_namespace_asset_record(
    asset_name: str, namespace_name: str, resource_group_name: str
) -> dict:
    """
    Get a mock namespace asset record.
    """
    return {
        "name": asset_name,
        "id": get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ).split("?", maxsplit=1)[0][len(BASE_URL) :],
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
            resource_group_name=resource_group_name
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
        resource_group_name=resource_group_name
    )

    # Add mock response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
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
    )    # Verify result matches mock response
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [200, 404])
@pytest.mark.parametrize("req", [
    # Test with minimal parameters
    {},
    # Test with several properties
    {
        "display_name": "Updated Asset Name",
        "description": "Updated description",
        "documentation_uri": "https://example.com/docs",
        "tags": {"tag1": "value1", "tag2": "value2"},
    },
    # Test with different set of properties
    {
        "disabled": True,
        "hardware_revision": "2.0",
        "manufacturer": "Test Manufacturer",
    },
])
def test_update_namespace_asset(
    mocked_cmd,
    mocked_responses: responses,
    req: dict,
    response_status: int
):
    """
    Test the update_namespace_asset function.
    """
    # Setup variables
    asset_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock original asset record
    mock_original_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Create updated record for successful response
    mock_updated_asset = mock_original_asset.copy()

    # Update properties based on request
    if "display_name" in req:
        mock_updated_asset["properties"]["displayName"] = req["display_name"]

    if "description" in req:
        mock_updated_asset["properties"]["description"] = req["description"]

    if "documentation_uri" in req:
        mock_updated_asset["properties"]["documentationUri"] = req["documentation_uri"]

    if "disabled" in req:
        mock_updated_asset["properties"]["disabled"] = req["disabled"]

    if "hardware_revision" in req:
        mock_updated_asset["properties"]["hardwareRevision"] = req["hardware_revision"]

    if "manufacturer" in req:
        mock_updated_asset["properties"]["manufacturer"] = req["manufacturer"]

    if "tags" in req:
        mock_updated_asset["tags"] = req["tags"]

    # Add mock response
    error_response = {"error": {"code": "NotFound", "message": "Asset not found"}}
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=mock_updated_asset if response_status == 200 else error_response,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            update_namespace_asset(
                cmd=mocked_cmd,
                asset_name=asset_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0,
                **req
            )
        return

    # Test update_namespace_asset for success case
    result = update_namespace_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
        **req
    )

    # Verify result matches mock response
    assert result == mock_updated_asset

    # Verify API call was made correctly
    assert len(mocked_responses.calls) == 1
    assert mocked_responses.calls[0].request.method == "PATCH"

    # Verify request body contains expected values
    if req:
        call_body = json.loads(mocked_responses.calls[0].request.body)

        # Check properties updates
        props_keys = ["display_name", "description", "documentation_uri",
                      "disabled", "hardware_revision", "manufacturer"]
        if any(key in req for key in props_keys):
            assert "properties" in call_body

            if "display_name" in req:
                assert call_body["properties"].get("displayName") == req["display_name"]

            if "description" in req:
                assert call_body["properties"].get("description") == req["description"]

            if "documentation_uri" in req:
                assert call_body["properties"].get("documentationUri") == req["documentation_uri"]

            if "disabled" in req:
                assert call_body["properties"].get("disabled") == req["disabled"]

            if "hardware_revision" in req:
                assert call_body["properties"].get("hardwareRevision") == req["hardware_revision"]

            if "manufacturer" in req:
                assert call_body["properties"].get("manufacturer") == req["manufacturer"]

        # Check tags update
        if "tags" in req:
            assert call_body.get("tags") == req["tags"]
