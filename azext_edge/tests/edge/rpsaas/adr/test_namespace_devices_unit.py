# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Dict
import json
import pytest
import responses

from azext_edge.edge.commands_namespaces import (
    create_namespace_device,
    list_namespace_devices,
    delete_namespace_device,
    show_namespace_device,
    update_namespace_device,
    list_namespace_device_endpoints,
    remove_namespace_device_endpoints,
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


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("req", [
    {},
    {
        "custom_attributes": ["key1=value1", "key2=value2"],
        "device_group_id": "test-group",
        "disabled": True,
        "operating_system_version": "2.0",
        "tags": {"env": "test", "purpose": "demo"},
    },
    {
        "disabled": False,
    }
])
def test_namespace_device_update(
    mocked_cmd,
    mocked_responses: responses,
    req: dict,
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock device records for PATCH responses
    mock_original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Create updated record for successful response
    mock_updated_device = deepcopy(mock_original_device)

    # Update the mock response based on the request params
    if "tags" in req:
        mock_updated_device["tags"] = req["tags"]
    if "custom_attributes" in req:
        mock_updated_device["properties"]["customAttributes"] = parse_kvp_nargs(req["custom_attributes"])
    if "device_group_id" in req:
        mock_updated_device["properties"]["deviceGroupId"] = req["device_group_id"]
    if "disabled" in req:
        mock_updated_device["properties"]["enabled"] = not req["disabled"]
    if "operating_system_version" in req:
        mock_updated_device["properties"]["operatingSystemVersion"] = req["operating_system_version"]

    # Add mock PATCH response for update operation
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_device_mgmt_uri(
            device_name=device_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=mock_updated_device,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on response status
    if response_status != 200:
        with pytest.raises(Exception):  # Use more specific exception if available
            update_namespace_device(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0,
                **req
            )
        return

    # Test update_namespace_device for success case
    result = update_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
        **req
    )

    # Verify result matches the mock updated namespace
    assert result == mock_updated_device

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 1
    assert mocked_responses.calls[0].request.method == "PATCH"

    # Verify request body contains expected values
    call_body = json.loads(mocked_responses.calls[0].request.body)
    call_body_properties = call_body.get("properties", {})

    assert call_body.get("tags") == req.get("tags")
    assert call_body_properties.get("deviceGroupId") == req.get("device_group_id")
    assert call_body_properties.get("operatingSystemVersion") == req.get("operating_system_version")
    if "custom_attributes" in req:
        assert call_body_properties["customAttributes"] == parse_kvp_nargs(req["custom_attributes"])
    if "disabled" in req:
        assert call_body_properties.get("enabled") == (not req["disabled"])


# TODO: Implement the test for adding namespace device endpoints
def test_add_namespace_device_endpoints(
    mocked_cmd,
    mocked_responses: responses
):
    pass


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("endpoints", [
    {},  # Test with no endpoints
    {  # Test with one endpoint
        "endpoint1": {
            "endpointType": "MQTT",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "Anonymous"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        }
    },
    {  # Test with multiple endpoints
        "endpoint1": {
            "endpointType": "MQTT",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "UsernamePassword"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        },
        "endpoint2": {
            "endpointType": "AMQP",
            "address": "amqp://example.com:5672",
            "authentication": {"type": "UsernamePassword"},
            "additionalConfiguration": "{\"publishingInterval\": 1000, \"samplingInterval\": 1000, \"queueSize\": 5}"
        }
    }
])
def test_list_namespace_device_endpoints(
    mocked_cmd,
    mocked_responses: responses,
    endpoints: dict,
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock device record with the specified endpoints
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    device_record["properties"]["endpoints"] = {"inbound": endpoints}

    # Mock the GET call to show_namespace_device
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
            list_namespace_device_endpoints(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            )
        return

    # Test list_namespace_device_endpoints for success case
    result = list_namespace_device_endpoints(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Verify result matches the endpoints in the mock response
    assert result == endpoints

    # Verify the GET call was made
    assert len(mocked_responses.calls) == 1
    assert mocked_responses.calls[0].request.method == "GET"


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("original_endpoints, endpoint_names_to_remove", [
    (  # Test removing a single endpoint
        {
            "endpoint1": {
                "endpointType": "MQTT",
                "address": "mqtt://example.com:1883",
                "authentication": {},
                "additionalConfiguration": "{\"publishingInterval\": 500}"
            },
            "endpoint2": {
                "endpointType": "AMQP",
                "address": "amqp://example.com:5672",
                "authentication": {},
                "additionalConfiguration": "{\"publishingInterval\": 1000}"
            }
        },
        ["endpoint1"]
    ),
    (  # Test removing multiple endpoints
        {
            "endpoint1": {"endpointType": "MQTT", "address": "mqtt://example1.com", "authentication": {}},
            "endpoint2": {"endpointType": "AMQP", "address": "amqp://example2.com", "authentication": {}},
            "endpoint3": {"endpointType": "MQTT", "address": "mqtt://example3.com", "authentication": {}}
        },
        ["endpoint1", "endpoint3"]
    ),
    (  # Test removing all endpoints
        {
            "endpoint1": {"endpointType": "MQTT", "address": "mqtt://example.com", "authentication": {}}
        },
        ["endpoint1"]
    ),
    (  # Test removing non-existent endpoints (should not fail)
        {
            "endpoint1": {"endpointType": "MQTT", "address": "mqtt://example.com", "authentication": {}}
        },
        ["endpoint2"]
    )
])
def test_remove_namespace_device_endpoints(
    mocked_cmd,
    mocked_responses: responses,
    original_endpoints: dict,
    endpoint_names_to_remove: list,
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create original device record
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    original_device["properties"]["endpoints"] = {"inbound": original_endpoints}

    # Create updated device record for PATCH response
    updated_device = deepcopy(original_device)
    expected_remaining = {
        endpoint: endpoint_body
        for endpoint, endpoint_body in original_endpoints.items()
        if endpoint not in endpoint_names_to_remove
    }
    updated_device["properties"]["endpoints"] = {"inbound": expected_remaining}

    # Mock the GET call to get the original device with endpoints
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name
        ),
        json=original_device,
        status=200,
        content_type="application/json",
    )

    # Mock the PATCH call to update the endpoints
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name
        ),
        json=updated_device if response_status == 200 else {"error": "Unauthorized"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            remove_namespace_device_endpoints(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_names=endpoint_names_to_remove,
                wait_sec=0
            )
        return

    # Test remove_namespace_device_endpoints for success case
    result = remove_namespace_device_endpoints(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_names=endpoint_names_to_remove,
        wait_sec=0
    )

    # Verify result matches expected
    assert result == expected_remaining

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"

    # Verify request body contains expected endpoints
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    assert patch_body["properties"]["endpoints"]["inbound"] == expected_remaining
