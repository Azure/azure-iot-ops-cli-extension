# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Dict, Optional
import json
import pytest
import responses

from azure.cli.core.azclierror import FileOperationError

from azext_edge.edge.commands_namespaces import (
    create_namespace_device,
    list_namespace_devices,
    delete_namespace_device,
    show_namespace_device,
    update_namespace_device,
    list_namespace_device_endpoints,
    remove_inbound_device_endpoints,
    add_inbound_custom_device_endpoint,
    add_inbound_media_device_endpoint,
    add_inbound_onvif_device_endpoint,
    add_inbound_opcua_device_endpoint,
)
from azext_edge.edge.common import ADRAuthModes
from azext_edge.edge.providers.rpsaas.adr.namespace_devices import DeviceEndpointType
from azext_edge.edge.providers.rpsaas.adr.specs import SecurityMode, SecurityPolicy
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
        assert call_body["properties"]["attributes"] == parse_kvp_nargs(req["custom_attributes"])


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
                wait_sec=0,
                confirm_yes=True
            )
        return

    # Test delete_namespace_device for success case
    delete_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
        confirm_yes=True
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
    assert result == {"inbound": endpoints}

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
def test_remove_namespace_device_inbound_endpoints(
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
            remove_inbound_device_endpoints(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_names=endpoint_names_to_remove,
                wait_sec=0,
                confirm_yes=True
            )
        return

    # Test remove_inbound_device_endpoints for success case
    result = remove_inbound_device_endpoints(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_names=endpoint_names_to_remove,
        wait_sec=0,
        confirm_yes=True
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


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("config_is_file, additional_configuration", [
    (False, '{"customSetting": "value"}'),  # Test with JSON string
    (True, '{"fileContent": "content"}'),   # Test with file content
])
@pytest.mark.parametrize("cert_ref, username_ref, password_ref", [
    (None, None, None),              # Anonymous auth
    (None, "secretRef:username", "secretRef:password"),  # Username/Password auth
    ("secretRef:certificate", None, None),  # Certificate auth
])
def test_add_inbound_custom_device_endpoint(
    mocker,
    mocked_cmd,
    mocked_responses: responses,
    config_is_file: bool,
    additional_configuration: str,
    cert_ref: Optional[str],
    username_ref: Optional[str],
    password_ref: Optional[str],
    response_status: int
):
    # Setup mock for file reading
    mock_read_file_content = mocker.patch("azext_edge.edge.util.read_file_content")
    expected_additional_configuration = additional_configuration
    if config_is_file:
        mock_read_file_content.return_value = expected_additional_configuration
        additional_configuration = f"{generate_random_string()}.json"
    else:
        mock_read_file_content.side_effect = FileOperationError("Not a file")

    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()
    endpoint_name = f"custom-endpoint-{generate_random_string()}"
    endpoint_type = "Custom.Type"
    endpoint_address = "192.168.1.100:8080"

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    original_device["properties"]["endpoints"] = {"inbound": {}}

    # Create expected endpoint structure based on auth type
    expected_endpoint = {
        "endpointType": endpoint_type,
        "address": endpoint_address,
        "additionalConfiguration": expected_additional_configuration
    }

    # Set up authentication structure based on auth type
    if cert_ref:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.certificate.value,
            "x509Credentials": {
                "certificateSecretName": cert_ref
            }
        }
    elif username_ref and password_ref:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.userpass.value,
            "usernamePasswordCredentials": {
                "usernameSecretName": username_ref,
                "passwordSecretName": password_ref
            }
        }
    else:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.anonymous.value
        }

    # Create updated device record for PATCH response
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {
        "inbound": {endpoint_name: expected_endpoint}
    }

    # Mock the GET call to get the original device
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
        json=updated_device if response_status == 200 else {"error": "Bad Request"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            add_inbound_custom_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_name=endpoint_name,
                endpoint_type=endpoint_type,
                endpoint_address=endpoint_address,
                additional_configuration=additional_configuration,
                certificate_reference=cert_ref,
                username_reference=username_ref,
                password_reference=password_ref,
                wait_sec=0
            )
        return

    # Test add_inbound_custom_device_endpoint for success case
    result = add_inbound_custom_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_type=endpoint_type,
        endpoint_address=endpoint_address,
        additional_configuration=additional_configuration,
        certificate_reference=cert_ref,
        username_reference=username_ref,
        password_reference=password_ref,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]
    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    patch_endpoints = patch_body["properties"]["endpoints"]["inbound"]
    assert endpoint_name in patch_endpoints
    patch_endpoint = patch_endpoints[endpoint_name]
    assert patch_endpoint["endpointType"] == endpoint_type
    assert patch_endpoint["address"] == endpoint_address
    assert patch_endpoint["additionalConfiguration"] == expected_additional_configuration
    assert patch_endpoint["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert patch_endpoint["authentication"] == expected_endpoint["authentication"]

    # Verify file reading mock was called correctly
    if config_is_file:
        mock_read_file_content.assert_called_once_with(additional_configuration)


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("username_ref, password_ref", [
    (None, None),              # Anonymous auth
    ("secretRef:username", "secretRef:password"),  # Username/Password auth
])
def test_add_inbound_media_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    username_ref: Optional[str],
    password_ref: Optional[str],
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()
    endpoint_name = f"media-endpoint-{generate_random_string()}"
    endpoint_address = "rtsp://192.168.1.100:554/stream"

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    original_device["properties"]["endpoints"] = {"inbound": {}}

    # Create expected endpoint structure
    expected_endpoint = {
        "endpointType": DeviceEndpointType.MEDIA.value,
        "address": endpoint_address,
    }

    # Set up authentication structure based on auth type
    if username_ref and password_ref:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.userpass.value,
            "usernamePasswordCredentials": {
                "usernameSecretName": username_ref,
                "passwordSecretName": password_ref
            }
        }
    else:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.anonymous.value
        }

    # Create updated device record for PATCH response
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {
        "inbound": {endpoint_name: expected_endpoint}
    }

    # Mock the GET call to get the original device
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
        json=updated_device if response_status == 200 else {"error": "Bad Request"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            add_inbound_media_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                username_reference=username_ref,
                password_reference=password_ref,
                wait_sec=0
            )
        return

    # Test add_inbound_media_device_endpoint for success case
    result = add_inbound_media_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        username_reference=username_ref,
        password_reference=password_ref,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.MEDIA.value
    assert endpoint_patch["address"] == endpoint_address
    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("username_ref, password_ref", [
    (None, None),              # Anonymous auth
    ("secretRef:username", "secretRef:password"),  # Username/Password auth
])
@pytest.mark.parametrize("accept_invalid_hostnames", [True, False])
@pytest.mark.parametrize("accept_invalid_certificates", [True, False])
def test_add_inbound_onvif_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    username_ref: Optional[str],
    password_ref: Optional[str],
    accept_invalid_hostnames: bool,
    accept_invalid_certificates: bool,
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()
    endpoint_name = f"onvif-endpoint-{generate_random_string()}"
    endpoint_address = "http://192.168.1.100:80/onvif/device_service"

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    original_device["properties"]["endpoints"] = {"inbound": {}}

    # Create expected endpoint structure
    expected_endpoint = {
        "endpointType": DeviceEndpointType.ONVIF.value,
        "address": endpoint_address,
        "acceptInvalidHostnames": accept_invalid_hostnames,
        "acceptInvalidCertificates": accept_invalid_certificates
    }

    # Set up authentication structure based on auth type
    if username_ref and password_ref:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.userpass.value,
            "usernamePasswordCredentials": {
                "usernameSecretName": username_ref,
                "passwordSecretName": password_ref
            }
        }
    else:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.anonymous.value
        }

    # Create updated device record for PATCH response
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {
        "inbound": {endpoint_name: expected_endpoint}
    }

    # Mock the GET call to get the original device
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
        json=updated_device if response_status == 200 else {"error": "Bad Request"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            add_inbound_onvif_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                username_reference=username_ref,
                password_reference=password_ref,
                accept_invalid_hostnames=accept_invalid_hostnames,
                accept_invalid_certificates=accept_invalid_certificates,
                wait_sec=0
            )
        return

    # Test add_inbound_onvif_device_endpoint for success case
    result = add_inbound_onvif_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        username_reference=username_ref,
        password_reference=password_ref,
        accept_invalid_hostnames=accept_invalid_hostnames,
        accept_invalid_certificates=accept_invalid_certificates,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.ONVIF.value
    assert endpoint_patch["address"] == endpoint_address

    assert endpoint_patch["additionalConfiguration"]
    additional_config = json.loads(endpoint_patch["additionalConfiguration"])
    assert additional_config["acceptInvalidHostnames"] == accept_invalid_hostnames
    assert additional_config["acceptInvalidCertificates"] == accept_invalid_certificates

    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("username_ref, password_ref", [
    (None, None),              # Anonymous auth
    ("secretRef:username", "secretRef:password"),  # Username/Password auth
])
@pytest.mark.parametrize("req", [
    {},  # Default values, no options specified
    {   # All optional parameters specified
        "application_name": "Test OPC UA Application",
        "keep_alive": 15000,
        "publishing_interval": 2000,
        "sampling_interval": 2000,
        "queue_size": 2,
        "key_frame_count": 5,
        "session_timeout": 55000,
        "session_keep_alive_interval": 12000,
        "session_reconnect_period": 3000,
        "session_reconnect_exponential_backoff": 12000,
        "session_enable_tracing_headers": True,
        "subscription_max_items": 1500,
        "subscription_life_time": 65000,
        "security_auto_accept_certificates": True,
        "security_policy": "basic256sha256",
        "security_mode": "signandencrypt",
        "run_asset_discovery": True,
    },
    {   # Partial set of parameters
        "application_name": "Simple OPC UA App",
        "session_enable_tracing_headers": True,
        "security_auto_accept_certificates": True,
        "security_policy": "aes256",
        "security_mode": "sign",
    }
])
def test_add_inbound_opcua_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    username_ref: Optional[str],
    password_ref: Optional[str],
    req: dict,
    response_status: int
):
    """Tests that add_inbound_opcua_device_endpoint calls the expected APIs with the correct parameters."""
    # Setup test data
    device_name = generate_random_string()
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()
    endpoint_name = f"opcua-endpoint-{generate_random_string()}"
    endpoint_address = "opc.tcp://192.168.1.100:4840"

    # Apply default values if not in req
    application_name = req.get("application_name", "OPC UA Broker")
    keep_alive = req.get("keep_alive", 10000)
    publishing_interval = req.get("publishing_interval", 1000)
    sampling_interval = req.get("sampling_interval", 1000)
    queue_size = req.get("queue_size", 1)
    key_frame_count = req.get("key_frame_count", 0)
    session_timeout = req.get("session_timeout", 60000)
    session_keep_alive_interval = req.get("session_keep_alive_interval", 10000)
    session_reconnect_period = req.get("session_reconnect_period", 2000)
    session_reconnect_exponential_backoff = req.get("session_reconnect_exponential_backoff", 10000)
    session_enable_tracing_headers = req.get("session_enable_tracing_headers", False)
    subscription_max_items = req.get("subscription_max_items", 1000)
    subscription_life_time = req.get("subscription_life_time", 60000)
    security_auto_accept_certificates = req.get("security_auto_accept_certificates", False)
    security_policy = req.get("security_policy", None)
    if security_policy:
        security_policy = f"http://opcfoundation.org/UA/SecurityPolicy#{SecurityPolicy[security_policy].value}"
    security_mode = req.get("security_mode", None)
    if security_mode:
        security_mode = SecurityMode[security_mode].value
    run_asset_discovery = req.get("run_asset_discovery", False)

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    original_device["properties"]["endpoints"] = {"inbound": {}}

    # Create expected endpoint structure with OPC UA specific properties
    expected_endpoint = {
        "endpointType": DeviceEndpointType.OPCUA.value,
        "address": endpoint_address,
        "additionalConfiguration": json.dumps({
            "applicationName": application_name,
            "keepAliveMilliseconds": keep_alive,
            "defaults": {
                "publishingIntervalMilliseconds": publishing_interval,
                "samplingIntervalMilliseconds": sampling_interval,
                "queueSize": queue_size,
                "keyFrameCount": key_frame_count
            },
            "session": {
                "timeoutMilliseconds": session_timeout,
                "keepAliveIntervalMilliseconds": session_keep_alive_interval,
                "reconnectPeriodMilliseconds": session_reconnect_period,
                "reconnectExponentialBackOffMilliseconds": session_reconnect_exponential_backoff,
                "enableTracingHeaders": session_enable_tracing_headers
            },
            "subscription": {
                "maxItems": subscription_max_items,
                "lifeTimeMilliseconds": subscription_life_time
            },
            "security": {
                "autoAcceptUntrustedServerCertificates": security_auto_accept_certificates,
                "securityPolicy": security_policy,
                "securityMode": security_mode
            },
            "runAssetDiscovery": run_asset_discovery
        })
    }

    # Set up authentication structure based on auth type
    if username_ref and password_ref:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.userpass.value,
            "usernamePasswordCredentials": {
                "usernameSecretName": username_ref,
                "passwordSecretName": password_ref
            }
        }
    else:
        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.anonymous.value
        }

    # Create updated device record for PATCH response
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {
        "inbound": {endpoint_name: expected_endpoint}
    }

    # Mock the GET call to get the original device
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
        json=updated_device if response_status == 200 else {"error": "Bad Request"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            add_inbound_opcua_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                username_reference=username_ref,
                password_reference=password_ref,
                wait_sec=0,
                **req
            )
        return

    # Test add_inbound_opcua_device_endpoint for success case
    result = add_inbound_opcua_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        username_reference=username_ref,
        password_reference=password_ref,
        wait_sec=0,
        **req
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.OPCUA.value
    assert endpoint_patch["address"] == endpoint_address

    # Parse additionalConfiguration for validation
    assert endpoint_patch["additionalConfiguration"]
    additional_config = json.loads(endpoint_patch["additionalConfiguration"])
    assert additional_config["applicationName"] == application_name
    assert additional_config["keepAliveMilliseconds"] == keep_alive
    assert additional_config["runAssetDiscovery"] == run_asset_discovery

    # Validate defaults settings
    assert additional_config["defaults"]["publishingIntervalMilliseconds"] == publishing_interval
    assert additional_config["defaults"]["samplingIntervalMilliseconds"] == sampling_interval
    assert additional_config["defaults"]["queueSize"] == queue_size
    assert additional_config["defaults"]["keyFrameCount"] == key_frame_count

    # Validate session settings
    config_session = additional_config["session"]
    assert config_session["timeoutMilliseconds"] == session_timeout
    assert config_session["keepAliveIntervalMilliseconds"] == session_keep_alive_interval
    assert config_session["reconnectPeriodMilliseconds"] == session_reconnect_period
    assert config_session["reconnectExponentialBackOffMilliseconds"] == session_reconnect_exponential_backoff
    assert config_session["enableTracingHeaders"] == session_enable_tracing_headers

    # Validate subscription settings
    assert additional_config["subscription"]["maxItems"] == subscription_max_items
    assert additional_config["subscription"]["lifeTimeMilliseconds"] == subscription_life_time

    # Validate security settings
    config_security = additional_config["security"]
    assert config_security["autoAcceptUntrustedServerCertificates"] == security_auto_accept_certificates
    assert config_security["securityPolicy"] == security_policy
    assert config_security["securityMode"] == security_mode

    # Verify authentication structure
    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]
