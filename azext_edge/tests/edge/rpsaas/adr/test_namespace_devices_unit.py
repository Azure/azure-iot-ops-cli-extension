# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, Optional
import json
import pytest
import responses

from azext_edge.edge.commands_namespaces import (
    create_namespace_device,
    list_namespace_devices,
    delete_namespace_device,
    show_namespace_device,
)
from azext_edge.edge.util.common import parse_kvp_nargs

# Import necessary modules
from .conftest import get_namespace_mgmt_uri
from ....generators import generate_random_string, BASE_URL, get_zeroed_subscription

ADR_REFRESH_API_VERSION = "2025-07-01-preview"


def get_namespace_device_mgmt_uri(namespace_name: str, resource_group_name: str, device_name: str = None) -> str:
    base_uri = (
        f"{BASE_URL}/subscriptions/{get_zeroed_subscription()}/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.DeviceRegistry/namespaces/{namespace_name}/devices"
    )

    if device_name:
        return f"{base_uri}/{device_name}?api-version={ADR_REFRESH_API_VERSION}"
    else:
        return f"{base_uri}?api-version={ADR_REFRESH_API_VERSION}"


def get_namespace_device_record(device_name: str, namespace_name: str, resource_group_name: str) -> Dict:
    """
    Get a mock namespace device record.
    """
    # Extract device ID from the full URI path without the api-version parameter
    device_id = get_namespace_device_mgmt_uri(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        device_name=device_name
    ).split("?", maxsplit=1)[0][len(BASE_URL) :]
    return {
        "name": device_name,
        "id": device_id,
        "type": "Microsoft.DeviceRegistry/namespaces/devices",
        "location": "westus",
        "extendedLocation": {
            "name": generate_random_string(),
            "type": "CustomLocation"
        },
        "properties": {
            "deviceGroupId": f"device-group-{generate_random_string()}",
            "deviceTemplateId": f"template-{generate_random_string()}",
            "customAttributes": {},
            "enabled": True,
            "manufacturer": "Contoso",
            "model": "Model X",
            "operatingSystem": "Linux",
            "operatingSystemVersion": "1.0",
            "provisioningState": "Succeeded",
            "endpoints": {
                "inbound": {}
            }
        },
        "systemData": {
            "createdAt": "2023-01-01T00:00:00.000Z",
            "createdBy": "user@example.com",
            "createdByType": "User",
            "lastModifiedAt": "2023-01-01T00:00:00.000Z",
            "lastModifiedBy": "user@example.com",
            "lastModifiedByType": "User"
        }
    }


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("req", [
    {},
    {
        "device_group_id": "test-group",
        "custom_attributes": ["key1=value1", "key2=value2"],
        "disabled": True,
        "instance_resource_group": "instance-rg",
        "instance_subscription": get_zeroed_subscription(),
        "manufacturer": "Fabrikam",
        "model": "ModelY",
        "operating_system": "Windows",
        "operating_system_version": "2.0",
        "tags": {"env": "test", "purpose": "demo"},
    },
    {
        "disabled": False,
        "instance_resource_group": "instance-rg",
        "operating_system": "Windows",
    }
])
def test_create_namespace_device(
    mocked_cmd,
    mocked_get_extended_location,
    mocked_responses: responses,
    req: Dict,
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()
    instance_name = f"test-inst{generate_random_string()}"
    device_template_id = f"template-{generate_random_string()}"

    # Mock namespace get response for location
    namespace_location = f"westus{generate_random_string()}"

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(
            namespace_name=namespace_name,
            namespace_resource_group=resource_group_name
        ),
        json={"location": namespace_location},
        status=200,
        content_type="application/json",
    )

    # Create mock create response
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name
        ),
        json=device_record if response_status == 200 else {"error": "BadRequest"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            create_namespace_device(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                instance_name=instance_name,
                device_template_id=device_template_id,
                resource_group_name=resource_group_name,
                wait_sec=0,
                **req
            )
        return

    # Test create_namespace_device for success case
    result = create_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        instance_name=instance_name,
        device_template_id=device_template_id,
        resource_group_name=resource_group_name,
        wait_sec=0,
        **req
    )

    # Verify result matches mock response
    assert result == device_record

    # Verify request body contains expected values
    assert len(mocked_responses.calls) == 2  # GET namespace, PUT device

    # Verify create request body
    call_body = json.loads(mocked_responses.calls[-1].request.body)

    # Check extended location
    extended_location = mocked_get_extended_location.original_return_value
    assert call_body["extendedLocation"]["name"] == extended_location["name"]

    # Check required fields
    assert call_body["location"] == namespace_location
    assert call_body["properties"]["deviceTemplateId"] == device_template_id
    assert call_body["properties"]["enabled"] == (not req.get("disabled"))

    # Check optional fields if provided
    if "device_group_id" in req:
        assert call_body["properties"]["deviceGroupId"] == req["device_group_id"]
    if "manufacturer" in req:
        assert call_body["properties"]["manufacturer"] == req["manufacturer"]
    if "model" in req:
        assert call_body["properties"]["model"] == req["model"]
    if "operating_system" in req:
        assert call_body["properties"]["operatingSystem"] == req["operating_system"]
    if "operating_system_version" in req:
        assert call_body["properties"]["operatingSystemVersion"] == req["operating_system_version"]
    if "tags" in req:
        assert call_body["tags"] == req["tags"]
    if "custom_attributes" in req:
        assert call_body["properties"]["customAttributes"] == parse_kvp_nargs(req["custom_attributes"])


@pytest.mark.parametrize("records", [0, 2])
@pytest.mark.parametrize("response_status", [200, 443])
def test_list_namespace_devices(
    mocked_cmd, mocked_responses: responses, records: int, response_status: int
):
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_namespace_records = {
        "value": [
            get_namespace_device_record(
                device_name=generate_random_string(),
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name, resource_group_name=resource_group_name
        ),
        json=mock_namespace_records,
        status=response_status,
        content_type="application/json",
    )

    if response_status != 200:
        with pytest.raises(Exception):
            list(list_namespace_devices(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
            ))
        return

    result = list(
        list_namespace_devices(
            cmd=mocked_cmd, namespace_name=namespace_name, resource_group_name=resource_group_name
        )
    )
    assert result == mock_namespace_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [202, 443])
def test_delete_namespace_device(mocked_cmd, mocked_responses: responses, response_status: int):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Mock the delete call
    mocked_responses.add(
        method=responses.DELETE,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name
        ),
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 202:
        with pytest.raises(Exception):
            delete_namespace_device(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0
            )
        return

    # Test delete_namespace_device for success case
    delete_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0
    )

    # Verify the delete call was made
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [200, 443])
def test_show_namespace_device(mocked_cmd, mocked_responses: responses, response_status: int):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock device record
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Mock the get call
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name
        ),
        json=device_record if response_status == 200 else {"error": "Unauthorized"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            show_namespace_device(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            )
        return

    # Test show_namespace_device for success case
    result = show_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Verify result
    assert result == device_record

    # Verify the get call was made
    assert len(mocked_responses.calls) == 1
