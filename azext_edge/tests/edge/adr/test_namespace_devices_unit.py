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

from azure.cli.core.azclierror import FileOperationError, InvalidArgumentValueError

from azext_edge.edge.commands_namespaces import (
    create_namespace_device,
    delete_namespace_device,
    query_namespace_devices,
    show_namespace_device,
    update_namespace_device,
    list_namespace_device_endpoints,
    remove_inbound_device_endpoints,
    list_inbound_device_endpoints,
    add_inbound_custom_device_endpoint,
    add_inbound_media_device_endpoint,
    add_inbound_onvif_device_endpoint,
    add_inbound_opcua_device_endpoint,
    add_inbound_rest_device_endpoint
)
from azext_edge.edge.providers.adr.common import ADRAuthModes
from azext_edge.edge.providers.adr.namespace_devices import DeviceEndpointType
from azext_edge.edge.providers.adr.specs import SecurityMode, SecurityPolicy
from azext_edge.edge.util.common import parse_kvp_nargs
from azext_edge.edge.util.az_client import DeviceRegistryMgmtApiVersion

# Import necessary modules
from .test_namespaces_unit import get_namespace_mgmt_uri
from ...generators import generate_random_string, BASE_URL, get_zeroed_subscription


def get_namespace_device_mgmt_uri(namespace_name: str, resource_group_name: str, device_name: str = None) -> str:
    base_uri = (
        f"{BASE_URL}/subscriptions/{get_zeroed_subscription()}/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.DeviceRegistry/namespaces/{namespace_name}/devices"
    )
    if device_name:
        base_uri += f"/{device_name}"
    return f"{base_uri}?api-version={DeviceRegistryMgmtApiVersion.V20251001.value}"


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
        "resourceGroup": resource_group_name,
        "extendedLocation": {
            "name": generate_random_string(),
            "type": "CustomLocation"
        },
        "properties": {
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


def generate_device_inbound_endpoint(
    endpoint_name: Optional[str] = None,
    endpoint_type: Optional[str] = None,
):
    """
    Generate a mock inbound device endpoint record.
    """
    if not endpoint_name:
        endpoint_name = f"endpoint-{generate_random_string()}"
    if not endpoint_type:
        endpoint_type = generate_random_string()

    return {
        endpoint_name: {
            "endpointType": endpoint_type,
            "address": f"{endpoint_type.lower()}://example.com",
            "authentication": {
                "type": ADRAuthModes.anonymous.value
            },
            "additionalConfiguration": json.dumps({
                "publishingInterval": 500,
                "samplingInterval": 500,
                "queueSize": 1
            })
        }
    }


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("req", [
    {},
    {
        "custom_attributes": ["key1=value1", "key2=value2"],
        "disabled": True,
        "manufacturer": "Fabrikam",
        "model": "ModelY",
        "operating_system": "Windows",
        "operating_system_version": "2.0",
        "tags": {"env": "test", "purpose": "demo"},
    },
    {
        "disabled": False,
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
    namespace_name = mocked_get_extended_location.return_value["namespace"]["name"]
    resource_group_name = mocked_get_extended_location.return_value["namespace"]["resource_group"]
    instance_name = f"test-inst{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace get response for location
    namespace_location = f"westus{generate_random_string()}"

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json={"location": namespace_location},
        status=200,
        content_type="application/json",
    )

    # Create mock create response
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                wait_sec=0,
                **req
            )
        return

    # Test create_namespace_device for success case
    result = create_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
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
    assert call_body["properties"]["enabled"] == (not req.get("disabled"))

    # Check optional fields if provided
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


@pytest.mark.parametrize("req", [
    {},  # No filters
    {
        "device_name": "test-device",
        "manufacturer": "Contoso",
        "model": "Model X",
        "operating_system": "Linux",
        "operating_system_version": "1.0",
        "disabled": True
    },
    {
        "disabled": False,
        "instance_name": "test-instance",
        "instance_resource_group": "test-rg"
    },
    {
        "custom_query": " | where name contains 'special' | project name, location"
    },
    {
        "device_name": "another-device",
        "manufacturer": "Fabrikam",
        "custom_query": " | where resourceGroup == 'test-rg' | project name, type",
        "instance_name": "test-instance",
        "instance_resource_group": "test-rg"
    }
])
def test_query_namespace_devices(mocked_cmd, mocker, req: Dict):
    return_value = [{"id": "device1"}, {"id": "device2"}]
    # Mock the query method from the Queryable class
    mock_query = mocker.patch(
        "azext_edge.edge.util.queryable.Queryable.query",
        return_value=return_value
    )

    # Test query_namespace_devices for success case
    result = query_namespace_devices(
        cmd=mocked_cmd,
        **req
    )

    # Verify the function returns the mocked query result
    assert result == return_value

    # Assert that the query method was called
    assert mock_query.call_count == 1

    # Check the query string that was passed to the query method
    query = mock_query.call_args[1]["query"]

    device_start = "Resources | where type =~ 'Microsoft.DeviceRegistry/namespaces/devices'"
    # Assert that the query starts with the expected base
    if "instance_name" in req or "instance_resource_group" in req:
        assert query.startswith("Resources | where type =~ 'microsoft.iotoperations/instances'")
        if "instance_name" in req:
            assert f"| where name =~ \"{req['instance_name']}\"" in query
        if "instance_resource_group" in req:
            assert f"| where resourceGroup =~ \"{req['instance_resource_group']}\"" in query
        # there still will be the device query part
        assert device_start in query
        # make sure both locations are projected away
        assert "| project-away customLocation1, customLocation" in query
    else:
        assert query.startswith(query)

    custom = "custom_query" in req
    # Verify specific filters based on request parameters
    if custom:
        # Custom query should be used as-is after the base query
        assert req["custom_query"] in query
    # Verify individual filters are applied
    for param, prop in [
        ("device_name", "name"),
        ("manufacturer", "properties.manufacturer"),
        ("model", "properties.model"),
        ("operating_system", "properties.operatingSystem"),
        ("operating_system_version", "properties.operatingSystemVersion"),
    ]:
        if param in req:
            assert (f'| where {prop} =~ "{req[param]}"' in query) is not custom

    if "disabled" in req:
        assert (f'| where properties.enabled == {not req["disabled"]}' in query) is not custom


@pytest.mark.parametrize("response_status", [202, 443])
def test_delete_namespace_device(
    mocked_cmd, mocked_get_namespace_for_instance, mocked_responses: responses, response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

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
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                wait_sec=0,
                confirm_yes=True
            )
        return

    # Test delete_namespace_device for success case
    delete_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        wait_sec=0,
        confirm_yes=True
    )

    # Verify the delete call was made
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [200, 443])
def test_show_namespace_device(
    mocked_cmd, mocked_get_namespace_for_instance, mocked_responses: responses, response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create mock device record
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
        return

    # Test show_namespace_device for success case
    result = show_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
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
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocked_responses: responses,
    req: dict,
    response_status: int
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create mock device records for PATCH responses
    mock_original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create updated record for successful response
    mock_updated_device = deepcopy(mock_original_device)

    # Update the mock response based on the request params
    if "tags" in req:
        mock_updated_device["tags"] = req["tags"]
    if "custom_attributes" in req:
        mock_updated_device["properties"]["customAttributes"] = parse_kvp_nargs(req["custom_attributes"])
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
        status=response_status,
        content_type="application/json",
    )

    if response_status == 200:
        # Add mock GET response for final response
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                device_name=device_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            ),
            json=mock_updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        # Execute test based on response status
        with pytest.raises(Exception):  # Use more specific exception if available
            update_namespace_device(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                wait_sec=0,
                **req
            )
        return

    # Test update_namespace_device for success case
    result = update_namespace_device(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        wait_sec=0,
        **req
    )

    # Verify result matches the mock updated namespace
    assert result == mock_updated_device

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[0].request.method == "PATCH"
    assert mocked_responses.calls[1].request.method == "GET"

    # Verify request body contains expected values
    call_body = json.loads(mocked_responses.calls[0].request.body)
    call_body_properties = call_body.get("properties", {})

    assert call_body.get("tags") == req.get("tags")
    assert call_body_properties.get("operatingSystemVersion") == req.get("operating_system_version")
    if "custom_attributes" in req:
        assert call_body_properties["attributes"] == parse_kvp_nargs(req["custom_attributes"])
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
@pytest.mark.parametrize("inbound", [True, False])
def test_list_namespace_device_endpoints(
    mocked_cmd,
    mocked_responses: responses,
    endpoints: dict,
    inbound: bool,
    response_status: int,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create mock device record with the specified endpoints
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                inbound=inbound
            )
        return

    # Test list_namespace_device_endpoints for success case
    result = list_namespace_device_endpoints(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        inbound=inbound
    )

    # Verify result matches the endpoints in the mock response
    assert result == (endpoints if inbound else {"inbound": endpoints})

    # Verify the GET call was made
    assert len(mocked_responses.calls) == 1
    assert mocked_responses.calls[0].request.method == "GET"


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("endpoints", [
    {},
    {  # Test with one endpoint
        "endpoint1": {
            "endpointType": "Microsoft.Media",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "Anonymous"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        }
    },
    {  # Test with multiple endpoints
        "endpoint1": {
            "endpointType": "Microsoft.Media",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "Anonymous"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        },
        "endpoint2": {
            "endpointType": "Microsoft.Media",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "Anonymous"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        },
        "endpoint3": {
            "endpointType": "MyCustomType",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "Anonymous"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        },
        "endpoint4": {
            "endpointType": "Microsoft.Onvif",
            "address": "mqtt://example.com:1883",
            "authentication": {"type": "Anonymous"},
            "additionalConfiguration": "{\"publishingInterval\": 500, \"samplingInterval\": 500, \"queueSize\": 1}"
        },
    },
])
@pytest.mark.parametrize("endpoint_type", [
    None,
    "media",
    "Microsoft.Media",
    "mEdia",
    "mycustomtype"
])
def test_list_namespace_device_inbound_endpoints(
    mocked_cmd,
    mocked_responses: responses,
    endpoints: dict,
    endpoint_type: Optional[str],
    response_status: int,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create mock device record with the specified endpoints
    device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
            list_inbound_device_endpoints(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                inbound_endpoint_type=endpoint_type
            )
        return

    # Test list_inbound_device_endpoints for success case
    result = list_inbound_device_endpoints(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        inbound_endpoint_type=endpoint_type
    )

    # Verify result matches the endpoints in the mock response
    if endpoint_type:
        endpoint_type = DeviceEndpointType.get_type_from_keyword(endpoint_type, return_custom_keyword=False)
        endpoints = {
            name: endpoint for name, endpoint in endpoints.items()
            if not endpoint_type or endpoint["endpointType"].lower() == endpoint_type.lower()
        }
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
def test_remove_namespace_device_inbound_endpoints(
    mocked_cmd,
    mocked_responses: responses,
    original_endpoints: dict,
    endpoint_names_to_remove: list,
    response_status: int,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create original device record
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
        status=response_status,
        content_type="application/json",
    )

    if response_status == 200:
        # Mock the GET call to show_namespace_device after removal
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                device_name=device_name
            ),
            json=updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        # Execute test based on status code
        with pytest.raises(Exception):
            remove_inbound_device_endpoints(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_names=endpoint_names_to_remove,
                wait_sec=0,
                confirm_yes=True
            )
        return

    # Test remove_inbound_device_endpoints for success case
    result = remove_inbound_device_endpoints(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_names=endpoint_names_to_remove,
        wait_sec=0,
        confirm_yes=True
    )

    # Verify result matches expected
    assert result == expected_remaining

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"
    assert mocked_responses.calls[2].request.method == "GET"

    # Verify request body contains expected endpoints
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    patch_endpoints = patch_body["properties"]["endpoints"]["inbound"]
    for endpoint in patch_endpoints:
        if endpoint in expected_remaining:
            assert patch_endpoints[endpoint] == expected_remaining[endpoint]
        else:
            assert patch_endpoints[endpoint] is None


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("config_is_file, additional_configuration", [
    (False, '{"customSetting": "value"}'),  # Test with JSON string
    (True, '{"fileContent": "content"}'),   # Test with file content
])
@pytest.mark.parametrize("cert_ref, key_ref, intermediate_cert_ref, username_ref, password_ref", [
    (None, None, None, None, None),              # Anonymous auth
    (None, None, None, "auth-secret/username", "auth-secret/password"),  # Username/Password auth
    ("cert-secret/certificate", None, None, None, None),  # Basic certificate auth
    ("cert-secret/certificate", "cert-secret/privateKey", None, None, None),  # Certificate with key
    ("cert-secret/certificate", None, "cert-secret/intermediateCerts", None, None),  # Certificate with intermediate
    (
        "cert-secret/certificate", "cert-secret/privateKey", "cert-secret/intermediateCerts", None, None
    ),  # Full certificate chain
])
@pytest.mark.parametrize("endpoint_version", [None, "1.0"])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_custom_device_endpoint(
    mocker,
    mocked_cmd,
    mocked_responses: responses,
    config_is_file: bool,
    additional_configuration: str,
    cert_ref: Optional[str],
    key_ref: Optional[str],
    intermediate_cert_ref: Optional[str],
    username_ref: Optional[str],
    password_ref: Optional[str],
    response_status: int,
    endpoint_version: Optional[str],
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"custom-endpoint-{generate_random_string()}"
    endpoint_type = "Custom.Type"
    endpoint_address = "192.168.1.100:8080"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Setup mock for file reading
    mock_read_file_content = mocker.patch("azext_edge.edge.util.read_file_content")
    expected_additional_configuration = additional_configuration
    if config_is_file:
        mock_read_file_content.return_value = expected_additional_configuration
        additional_configuration = f"{generate_random_string()}.json"
    else:
        mock_read_file_content.side_effect = FileOperationError("Not a file")

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    original_device["properties"]["endpoints"] = {
        "inbound": generate_device_inbound_endpoint() if endpoints_present else {}
    }
    if replace:
        original_device["properties"]["endpoints"]["inbound"].update(
            generate_device_inbound_endpoint(endpoint_name=endpoint_name)
        )

    # Create expected endpoint structure based on auth type
    expected_endpoint = {
        "endpointType": endpoint_type,
        "address": endpoint_address,
        "additionalConfiguration": expected_additional_configuration,
        "version": endpoint_version
    }

    # Set up authentication structure based on auth type
    if cert_ref:
        x509_credentials = {"certificateSecretName": cert_ref}
        if key_ref:
            x509_credentials["keySecretName"] = key_ref
        if intermediate_cert_ref:
            x509_credentials["intermediateCertificatesSecretName"] = intermediate_cert_ref

        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.certificate.value,
            "x509Credentials": x509_credentials
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
        status=response_status,
        content_type="application/json",
    )

    if response_status == 200:
        # Mock the GET call to show_namespace_device after adding endpoint
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                device_name=device_name
            ),
            json=updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        # Execute test based on status code
        with pytest.raises(Exception):
            add_inbound_custom_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_name=endpoint_name,
                endpoint_type=endpoint_type,
                endpoint_address=endpoint_address,
                additional_configuration=additional_configuration,
                certificate_reference=cert_ref,
                key_reference=key_ref,
                intermediate_certificate_reference=intermediate_cert_ref,
                username_reference=username_ref,
                password_reference=password_ref,
                endpoint_version=endpoint_version,
                replace=replace,
                wait_sec=0
            )
        return

    # Test add_inbound_custom_device_endpoint for success case
    result = add_inbound_custom_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_type=endpoint_type,
        endpoint_address=endpoint_address,
        additional_configuration=additional_configuration,
        certificate_reference=cert_ref,
        key_reference=key_ref,
        intermediate_certificate_reference=intermediate_cert_ref,
        username_reference=username_ref,
        password_reference=password_ref,
        endpoint_version=endpoint_version,
        replace=replace,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]
    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"
    assert mocked_responses.calls[2].request.method == "GET"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    patch_endpoints = patch_body["properties"]["endpoints"]["inbound"]
    assert endpoint_name in patch_endpoints
    patch_endpoint = patch_endpoints[endpoint_name]
    assert patch_endpoint["endpointType"] == endpoint_type
    assert patch_endpoint["version"] == endpoint_version
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
@pytest.mark.parametrize("endpoint_version", [None, "1.0"])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_media_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    username_ref: Optional[str],
    password_ref: Optional[str],
    response_status: int,
    endpoint_version: Optional[str],
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"media-endpoint-{generate_random_string()}"
    endpoint_address = "rtsp://192.168.1.100:554/stream"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    original_device["properties"]["endpoints"] = {
        "inbound": generate_device_inbound_endpoint() if endpoints_present else {}
    }
    if replace:
        original_device["properties"]["endpoints"]["inbound"].update(
            generate_device_inbound_endpoint(endpoint_name=endpoint_name)
        )

    # Create expected endpoint structure
    expected_endpoint = {
        "endpointType": DeviceEndpointType.MEDIA.value,
        "address": endpoint_address,
        "version": endpoint_version
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

    if response_status == 200:
        # Mock the GET call to show_namespace_device after adding endpoint
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                device_name=device_name
            ),
            json=updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        # Execute test based on status code
        with pytest.raises(Exception):
            add_inbound_media_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                username_reference=username_ref,
                password_reference=password_ref,
                endpoint_version=endpoint_version,
                replace=replace,
                wait_sec=0
            )
        return

    # Test add_inbound_media_device_endpoint for success case
    result = add_inbound_media_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        username_reference=username_ref,
        password_reference=password_ref,
        endpoint_version=endpoint_version,
        replace=replace,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"
    assert mocked_responses.calls[2].request.method == "GET"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.MEDIA.value
    assert endpoint_patch["version"] == endpoint_version
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
@pytest.mark.parametrize("endpoint_version", [None, "1.0"])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_onvif_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    username_ref: Optional[str],
    password_ref: Optional[str],
    accept_invalid_hostnames: bool,
    accept_invalid_certificates: bool,
    response_status: int,
    endpoint_version: Optional[str],
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"onvif-endpoint-{generate_random_string()}"
    endpoint_address = "http://192.168.1.100:80/onvif/device_service"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    original_device["properties"]["endpoints"] = {
        "inbound": generate_device_inbound_endpoint() if endpoints_present else {}
    }
    if replace:
        original_device["properties"]["endpoints"]["inbound"].update(
            generate_device_inbound_endpoint(endpoint_name=endpoint_name)
        )

    # Create expected endpoint structure
    expected_endpoint = {
        "endpointType": DeviceEndpointType.ONVIF.value,
        "address": endpoint_address,
        "acceptInvalidHostnames": accept_invalid_hostnames,
        "acceptInvalidCertificates": accept_invalid_certificates,
        "version": endpoint_version
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

    if response_status == 200:
        # Mock the GET call to show_namespace_device after adding endpoint
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                device_name=device_name
            ),
            json=updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        with pytest.raises(Exception):
            add_inbound_onvif_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                username_reference=username_ref,
                password_reference=password_ref,
                accept_invalid_hostnames=accept_invalid_hostnames,
                accept_invalid_certificates=accept_invalid_certificates,
                endpoint_version=endpoint_version,
                replace=replace,
                wait_sec=0
            )
        return

    # Test add_inbound_onvif_device_endpoint for success case
    result = add_inbound_onvif_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        username_reference=username_ref,
        password_reference=password_ref,
        accept_invalid_hostnames=accept_invalid_hostnames,
        accept_invalid_certificates=accept_invalid_certificates,
        endpoint_version=endpoint_version,
        replace=replace,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"
    assert mocked_responses.calls[2].request.method == "GET"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.ONVIF.value
    assert endpoint_patch["version"] == endpoint_version
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
        "security_policy": SecurityPolicy.aes128.value,
        "security_mode": SecurityMode.signandencrypt.value,
        "run_asset_discovery": True,
        "endpoint_version": "1.0"
    },
    {   # Partial set of parameters
        "application_name": "Simple OPC UA App",
        "session_enable_tracing_headers": True,
        "security_auto_accept_certificates": True,
        "security_policy": SecurityPolicy.basic256sha256.value,
        "security_mode": SecurityMode.sign.value,
    }
])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_opcua_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    username_ref: Optional[str],
    password_ref: Optional[str],
    req: dict,
    response_status: int,
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"opcua-endpoint-{generate_random_string()}"
    endpoint_address = "opc.tcp://192.168.1.100:4840"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    endpoint_version = req.get("endpoint_version")
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
        security_policy = f"http://opcfoundation.org/UA/SecurityPolicy#{security_policy}"
    security_mode = req.get("security_mode", None)
    run_asset_discovery = req.get("run_asset_discovery", False)

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    original_device["properties"]["endpoints"] = {
        "inbound": generate_device_inbound_endpoint() if endpoints_present else {}
    }
    if replace:
        original_device["properties"]["endpoints"]["inbound"].update(
            generate_device_inbound_endpoint(endpoint_name=endpoint_name)
        )

    # Create expected endpoint structure with OPC UA specific properties
    expected_endpoint = {
        "endpointType": DeviceEndpointType.OPCUA.value,
        "address": endpoint_address,
        "version": endpoint_version,
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

    if response_status == 200:
        # Mock the GET call to show_namespace_device after adding endpoint
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                device_name=device_name
            ),
            json=updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        with pytest.raises(Exception):
            add_inbound_opcua_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                username_reference=username_ref,
                password_reference=password_ref,
                replace=replace,
                wait_sec=0,
                **req
            )
        return

    # Test add_inbound_opcua_device_endpoint for success case
    result = add_inbound_opcua_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        username_reference=username_ref,
        password_reference=password_ref,
        replace=replace,
        wait_sec=0,
        **req
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"
    assert mocked_responses.calls[2].request.method == "GET"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.OPCUA.value
    assert endpoint_patch["address"] == endpoint_address
    assert endpoint_patch["version"] == endpoint_version

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


@pytest.mark.parametrize("endpoint_type, command_func", [
    (DeviceEndpointType.ONVIF.value, add_inbound_onvif_device_endpoint),
    (DeviceEndpointType.MEDIA.value, add_inbound_media_device_endpoint),
    (DeviceEndpointType.OPCUA.value, add_inbound_opcua_device_endpoint),
    (DeviceEndpointType.REST.value, add_inbound_rest_device_endpoint),
    ("custom", add_inbound_custom_device_endpoint)
])
def test_add_inbound_device_endpoint_error(
    mocked_cmd,
    mocked_responses: responses,
    endpoint_type: str,
    command_func,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"error-endpoint-{generate_random_string()}"
    endpoint_address = f"http://{generate_random_string()}"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    original_device["properties"]["endpoints"] = {
        "inbound": (
            generate_device_inbound_endpoint(endpoint_name=endpoint_name)
        )
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

    kwargs = {
        "cmd": mocked_cmd,
        "device_name": device_name,
        "instance_name": instance_name,
        "instance_resource_group": instance_resource_group,
        "endpoint_name": endpoint_name,
        "endpoint_address": endpoint_address,
        "wait_sec": 0
    }
    if endpoint_type == "custom":
        kwargs["endpoint_type"] = endpoint_type

    with pytest.raises(InvalidArgumentValueError) as exc_info:
        command_func(**kwargs)

    assert f"Inbound endpoint '{endpoint_name}' already exists. Use --replace to update it." in str(exc_info.value)


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("cert_ref, key_ref, intermediate_cert_ref, username_ref, password_ref", [
    (None, None, None, None, None),              # Anonymous auth
    (None, None, None, "auth-secret/username", "auth-secret/password"),  # Username/Password auth
    ("cert-secret/certificate", None, None, None, None),  # Basic certificate auth
    ("cert-secret/certificate", "cert-secret/privateKey", None, None, None),  # Certificate with key
    ("cert-secret/certificate", None, "cert-secret/intermediateCerts", None, None),  # Certificate with intermediate
    (
        "cert-secret/certificate", "cert-secret/privateKey", "cert-secret/intermediateCerts", None, None
    ),  # Full certificate chain
])
@pytest.mark.parametrize("endpoint_version", [None, "1.0"])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_rest_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    cert_ref: Optional[str],
    key_ref: Optional[str],
    intermediate_cert_ref: Optional[str],
    username_ref: Optional[str],
    password_ref: Optional[str],
    response_status: int,
    endpoint_version: Optional[str],
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"media-endpoint-{generate_random_string()}"
    endpoint_address = "rtsp://192.168.1.100:554/stream"

    # Mock namespace information returned by get_namespace_for_instance
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Create original device record with no endpoints
    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    original_device["properties"]["endpoints"] = {
        "inbound": generate_device_inbound_endpoint() if endpoints_present else {}
    }
    if replace:
        original_device["properties"]["endpoints"]["inbound"].update(
            generate_device_inbound_endpoint(endpoint_name=endpoint_name)
        )

    # Create expected endpoint structure
    expected_endpoint = {
        "endpointType": DeviceEndpointType.MEDIA.value,
        "address": endpoint_address,
        "version": endpoint_version
    }

    # Set up authentication structure based on auth type
    if cert_ref:
        x509_credentials = {"certificateSecretName": cert_ref}
        if key_ref:
            x509_credentials["keySecretName"] = key_ref
        if intermediate_cert_ref:
            x509_credentials["intermediateCertificatesSecretName"] = intermediate_cert_ref

        expected_endpoint["authentication"] = {
            "method": ADRAuthModes.certificate.value,
            "x509Credentials": x509_credentials
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

    if response_status == 200:
        # Mock the GET call to show_namespace_device after adding endpoint
        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_device_mgmt_uri(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                device_name=device_name
            ),
            json=updated_device,
            status=200,
            content_type="application/json",
        )
    else:
        # Execute test based on status code
        with pytest.raises(Exception):
            add_inbound_rest_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                certificate_reference=cert_ref,
                username_reference=username_ref,
                password_reference=password_ref,
                endpoint_version=endpoint_version,
                replace=replace,
                wait_sec=0
            )
        return

    # Test add_inbound_rest_device_endpoint for success case
    result = add_inbound_rest_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        certificate_reference=cert_ref,
        key_reference=key_ref,
        intermediate_certificate_reference=intermediate_cert_ref,
        username_reference=username_ref,
        password_reference=password_ref,
        endpoint_version=endpoint_version,
        replace=replace,
        wait_sec=0
    )
    assert result == updated_device["properties"]["endpoints"]["inbound"]

    # Verify that both GET and PATCH calls were made
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PATCH"
    assert mocked_responses.calls[2].request.method == "GET"

    # Verify request body contains expected endpoint
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == DeviceEndpointType.REST.value
    assert endpoint_patch["version"] == endpoint_version
    assert endpoint_patch["address"] == endpoint_address
    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]
