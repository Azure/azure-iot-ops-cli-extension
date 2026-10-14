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

from azure.cli.core.azclierror import (
    FileOperationError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)

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
    add_inbound_rest_device_endpoint,
    add_inbound_sse_device_endpoint,
    add_inbound_mqtt_device_endpoint,
    apply_inbound_device_endpoint,
)
from azext_edge.edge.providers.adr.common import ADRAuthModes
from azext_edge.edge.providers.adr.helpers import _slim_schema, strip_nulls as _strip_nulls
from azext_edge.edge.providers.adr.namespace_devices import DeviceEndpointType
from azext_edge.edge.providers.adr.specs import SecurityMode, SecurityPolicy
from azext_edge.edge.util.common import parse_kvp_nargs
from azext_edge.edge.util.az_client import DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION

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
    return f"{base_uri}?api-version={DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION.value}"


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
    },
    {
        "manufacturer": None,
        "model": None,
        "operating_system": None,
        "operating_system_version": None,
    },
    {
        "manufacturer": "",
        "model": "",
        "operating_system": "",
        "operating_system_version": "",
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
    for argument, property_name in (
        ("manufacturer", "manufacturer"),
        ("model", "model"),
        ("operating_system", "operatingSystem"),
        ("operating_system_version", "operatingSystemVersion"),
    ):
        if req.get(argument) is None:
            assert property_name not in call_body["properties"]
        else:
            assert call_body["properties"][property_name] == req[argument]
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
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
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
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
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
@pytest.mark.parametrize("fallback_to_username_token_auth", [True, False])
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
    fallback_to_username_token_auth: bool,
    response_status: int,
    endpoint_version: Optional[str],
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
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
                fallback_to_username_token_auth=fallback_to_username_token_auth,
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
        fallback_to_username_token_auth=fallback_to_username_token_auth,
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
    assert additional_config["fallbackToUsernameTokenAuth"] == fallback_to_username_token_auth

    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("cert_ref, key_ref, intermediate_cert_ref, username_ref, password_ref", [
    (None, None, None, None, None),              # Anonymous auth
    (None, None, None, "secretRef:username", "secretRef:password"),  # Username/Password auth
    ("cert-secret/certificate", None, None, None, None),  # Basic certificate auth
    ("cert-secret/certificate", "cert-secret/privateKey", None, None, None),  # Certificate with key
    ("cert-secret/certificate", None, "cert-secret/intermediateCerts", None, None),  # Certificate with intermediate
    (
        "cert-secret/certificate", "cert-secret/privateKey", "cert-secret/intermediateCerts", None, None
    ),  # Full certificate chain
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
        "sync_properties_into_state_store": True,
        "shared": True,
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
    cert_ref: Optional[str],
    key_ref: Optional[str],
    intermediate_cert_ref: Optional[str],
    username_ref: Optional[str],
    password_ref: Optional[str],
    req: dict,
    response_status: int,
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
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
    sync_properties_into_state_store = req.get("sync_properties_into_state_store", False)
    shared = req.get("shared", False)

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
            "runAssetDiscovery": run_asset_discovery,
            "syncPropertiesIntoStateStore": sync_properties_into_state_store,
            "shared": shared
        })
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
        with pytest.raises(Exception):
            add_inbound_opcua_device_endpoint(
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
        certificate_reference=cert_ref,
        key_reference=key_ref,
        intermediate_certificate_reference=intermediate_cert_ref,
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
    assert additional_config["syncPropertiesIntoStateStore"] == sync_properties_into_state_store
    assert additional_config["shared"] == shared

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
    (DeviceEndpointType.SSE.value, add_inbound_sse_device_endpoint),
    (DeviceEndpointType.MQTT.value, add_inbound_mqtt_device_endpoint),
    ("custom", add_inbound_custom_device_endpoint)
])
def test_apply_inbound_device_endpoint_error(
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
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
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
    # Simulate connector template returning version when user doesn't provide one
    template_version = "1.0"  # REST connector template default
    if endpoint_version is None:
        mocked_get_endpoint_version_from_template.return_value = template_version
        expected_version = template_version
    else:
        expected_version = endpoint_version
    expected_endpoint = {
        "endpointType": DeviceEndpointType.REST.value,
        "address": endpoint_address,
        "version": expected_version
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
    assert endpoint_patch["version"] == expected_version
    assert endpoint_patch["address"] == endpoint_address
    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("cert_ref, key_ref, intermediate_cert_ref, username_ref, password_ref", [
    (None, None, None, None, None),  # Anonymous auth
    ("cert-ref", None, None, None, None),  # X509 auth with cert only
    ("cert-ref", "key-ref", None, None, None),  # X509 auth with cert and key
    ("cert-ref", "key-ref", "intermediate-cert-ref", None, None),  # X509 auth with cert, key and intermediate cert
    (None, None, None, "user-ref", "pass-ref"),  # Username/password auth
])
@pytest.mark.parametrize("endpoint_version", [None, "1.1"])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_sse_device_endpoint(
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
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"sse-endpoint-{generate_random_string()}"
    endpoint_address = "https://192.168.1.100:8080/events"

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
    # Simulate connector template returning version when user doesn't provide one
    template_version = "1.1"  # SSE connector template default
    if endpoint_version is None:
        mocked_get_endpoint_version_from_template.return_value = template_version
        expected_version = template_version
    else:
        expected_version = endpoint_version
    expected_endpoint = {
        "endpointType": DeviceEndpointType.SSE.value,
        "address": endpoint_address,
        "version": expected_version
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
            add_inbound_sse_device_endpoint(
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

    # Test add_inbound_sse_device_endpoint for success case
    result = add_inbound_sse_device_endpoint(
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
    assert endpoint_patch["endpointType"] == DeviceEndpointType.SSE.value
    assert endpoint_patch["version"] == expected_version
    assert endpoint_patch["address"] == endpoint_address
    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("endpoint_version", [None, "0.3.4"])
@pytest.mark.parametrize("asset_level, topic_filter, topic_mapping_prefix", [
    (1, None, None),  # Default values
    (2, "factory/device/+/telemetry", "assets/"),  # All MQTT params specified
])
@pytest.mark.parametrize("endpoints_present, replace", [
    (False, False),  # Endpoint does not exist, do not replace
    (True, False),   # Endpoint exists, do not replace
    (True, True)     # Endpoint exists, replace it
])
def test_add_inbound_mqtt_device_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    endpoint_version: Optional[str],
    asset_level: int,
    topic_filter: Optional[str],
    topic_mapping_prefix: Optional[str],
    endpoints_present: bool,
    replace: bool,
    mocked_get_namespace_for_instance,
    mocked_get_endpoint_version_from_template
):
    # Setup test data
    device_name = generate_random_string()
    instance_name = f"test-inst-{generate_random_string()}"
    instance_resource_group = f"inst-rg-{generate_random_string()}"
    endpoint_name = f"mqtt-endpoint-{generate_random_string()}"
    endpoint_address = "aio-broker:18883"

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

    # Create expected endpoint structure (MQTT has no authentication)
    # Simulate connector template returning version when user doesn't provide one
    template_version = "5"  # MQTT connector template default
    if endpoint_version is None:
        mocked_get_endpoint_version_from_template.return_value = template_version
        expected_version = template_version
    else:
        expected_version = endpoint_version
    expected_mqtt_config = {
        "assetLevel": asset_level,
    }
    if topic_filter is not None:
        expected_mqtt_config["topicFilter"] = topic_filter
    if topic_mapping_prefix is not None:
        expected_mqtt_config["topicMappingPrefix"] = topic_mapping_prefix

    expected_endpoint = {
        "endpointType": DeviceEndpointType.MQTT.value,
        "address": endpoint_address,
        "version": expected_version,
        "authentication": {
            "method": ADRAuthModes.anonymous.value
        }
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
            add_inbound_mqtt_device_endpoint(
                cmd=mocked_cmd,
                device_name=device_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_name=endpoint_name,
                endpoint_address=endpoint_address,
                endpoint_version=endpoint_version,
                asset_level=asset_level,
                topic_filter=topic_filter,
                topic_mapping_prefix=topic_mapping_prefix,
                replace=replace,
                wait_sec=0
            )
        return

    # Test add_inbound_mqtt_device_endpoint for success case
    result = add_inbound_mqtt_device_endpoint(
        cmd=mocked_cmd,
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        endpoint_version=endpoint_version,
        asset_level=asset_level,
        topic_filter=topic_filter,
        topic_mapping_prefix=topic_mapping_prefix,
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
    assert endpoint_patch["endpointType"] == DeviceEndpointType.MQTT.value
    assert endpoint_patch["version"] == expected_version
    assert endpoint_patch["address"] == endpoint_address
    assert endpoint_patch["authentication"]["method"] == expected_endpoint["authentication"]["method"]
    assert endpoint_patch["authentication"] == expected_endpoint["authentication"]

    assert endpoint_patch["additionalConfiguration"]
    additional_config = json.loads(endpoint_patch["additionalConfiguration"])
    assert additional_config == expected_mqtt_config


# ---------------------------------------------------------------------------
# Tests for the generalized apply_inbound_device_endpoint command
# ---------------------------------------------------------------------------


def _make_connector_template(connector_type: str, version: str = "1.0.0", schema_refs=None):
    """Build a minimal mock connector template resource.

    configurationSchemaRefs uses the dict shape matching real connector templates
    (e.g. keys like additionalConfigSchemaRef), not a plain list.
    """
    if schema_refs is None:
        config_schema_refs = {}
    elif isinstance(schema_refs, list):
        # Wrap list into dict shape: first entry becomes additionalConfigSchemaRef
        config_schema_refs = {"additionalConfigSchemaRef": schema_refs[0]} if schema_refs else {}
    else:
        config_schema_refs = schema_refs
    return {
        "name": f"template-{connector_type.lower()}",
        "properties": {
            "connectorMetadataRef": f"mcr.microsoft.com/azureiotoperations/{connector_type.lower()}-metadata:1.0",
            "deviceInboundEndpointTypes": [
                {
                    "endpointType": connector_type,
                    "version": version,
                    "configurationSchemaRefs": config_schema_refs,
                }
            ],
            "runtimeConfiguration": {
                "managedConfigurationSettings": {
                    "imageConfigurationSettings": {
                        "tagDigestSettings": {"tag": version}
                    }
                }
            },
        },
    }


@pytest.mark.parametrize("connector_type,template_mode", [
    ("Microsoft.OpcUa", "config"),
    ("Microsoft.OpcUa", "schema"),
    ("Microsoft.Onvif", "config"),
    ("Microsoft.Onvif", "schema"),
])
def test_apply_inbound_device_endpoint_show_template(
    mocked_cmd,
    mocker,
    connector_type: str,
    template_mode: str,
    mocked_get_namespace_for_instance,
):
    """--show-template returns config template without hitting device APIs.

    OPC UA: schema comes from bundled metadata via _get_opcua_info.
    Other types: schema comes from ConnectorTemplates.get_endpoint_schema.

    config mode: fields shown as default value (null if no default).
    schema mode: fields shown with type, default, and constraints.
    """
    raw_schema = {"type": "object", "properties": {"foo": {"type": "string"}}}

    is_opcua = connector_type.lower() == "microsoft.opcua"

    if template_mode == "config":
        # foo has no default -> null in config mode
        expected_endpoint_config = {"foo": None}
    else:
        # schema mode: foo has no default -> full metadata
        expected_endpoint_config = {"foo": {"type": "string", "default": None}}

    if is_opcua:
        mocker.patch(
            "azext_edge.edge.providers.adr.helpers.get_opcua_info",
            return_value={
                "version": "1.2.82",
                "inboundEndpoints": [
                    {"endpointType": "Microsoft.OpcUa", "additionalConfigurationSchema": raw_schema}
                ],
            },
        )
        mock_ct = mocker.patch(
            "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
        )
        mock_ct.return_value.get_endpoint_schema.side_effect = AssertionError(
            "ConnectorTemplates.get_endpoint_schema must not be called for OPC UA"
        )
    else:
        mock_ct = mocker.patch(
            "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
        )
        mock_ct.return_value.get_endpoint_schema.return_value = {
            "connectorType": connector_type,
            "endpointConfig": raw_schema,
        }

    instance_name = f"inst-{generate_random_string()}"
    instance_resource_group = f"rg-{generate_random_string()}"

    result = apply_inbound_device_endpoint(
        cmd=mocked_cmd,
        connector_type=connector_type,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        show_template=template_mode,
    )

    expected = {"connectorType": connector_type, "endpointConfig": expected_endpoint_config}
    assert result == expected
    if not is_opcua:
        mock_ct.return_value.get_endpoint_schema.assert_called_once_with(
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            connector_type=connector_type,
        )


def test_apply_inbound_device_endpoint_skip_connector_check_with_config_file_errors(mocked_cmd):
    """--skip-connector-check and --endpoint-config together must raise InvalidArgumentValueError."""
    with pytest.raises(InvalidArgumentValueError, match="--skip-connector-check cannot be used when --endpoint-config"):
        apply_inbound_device_endpoint(
            cmd=mocked_cmd,
            connector_type="Microsoft.OpcUa",
            instance_name="my-instance",
            instance_resource_group="my-rg",
            device_name="my-device",
            endpoint_name="ep1",
            endpoint_address="opc.tcp://1.2.3.4:4840",
            endpoint_config="./config.json",
            skip_connector_check=True,
        )


@pytest.mark.parametrize("missing_arg, kwargs_override", [
    ("device_name", {"device_name": None}),
    ("endpoint_name", {"endpoint_name": None}),
    ("endpoint_address", {"endpoint_address": None}),
])
def test_apply_inbound_device_endpoint_missing_required_args(
    mocked_cmd,
    mocker,
    missing_arg: str,
    kwargs_override: dict,
):
    """When not in show_schema mode, --device / --name / --endpoint-address are required."""
    # Patch connector template so we never hit the network
    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.return_value = _make_connector_template("Microsoft.OpcUa")

    base_kwargs = {
        "connector_type": "Microsoft.OpcUa",
        "instance_name": "my-instance",
        "instance_resource_group": "my-rg",
        "device_name": "my-device",
        "endpoint_name": "ep1",
        "endpoint_address": "opc.tcp://1.2.3.4:4840",
        "skip_connector_check": True,  # skip template lookup so we hit arg validation
    }
    base_kwargs.update(kwargs_override)

    with pytest.raises(RequiredArgumentMissingError):
        apply_inbound_device_endpoint(cmd=mocked_cmd, **base_kwargs)


def test_apply_inbound_device_endpoint_no_template_errors(
    mocked_cmd,
    mocker,
):
    """When connector template is not found for a non-OPC UA type and --skip-connector-check
    is not set, raise ResourceNotFoundError.
    OPC UA is excluded here because it never uses connector templates.
    """
    connector_type = "Microsoft.Onvif"  # non-OPC UA type that requires a connector template
    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.return_value = None

    with pytest.raises(ResourceNotFoundError, match="No connector template found for connector type"):
        apply_inbound_device_endpoint(
            cmd=mocked_cmd,
            connector_type=connector_type,
            instance_name="my-instance",
            instance_resource_group="my-rg",
            device_name="my-device",
            endpoint_name="ep1",
            endpoint_address="http://1.2.3.4:80/onvif",
            skip_connector_check=False,
        )


@pytest.mark.parametrize("with_config_file, skip_connector_check, endpoints_present, replace", [
    # (with_config_file, skip_connector_check, endpoints_present, replace)
    # with_config_file=True + skip_connector_check=True is mutually exclusive and is covered by
    # test_apply_inbound_device_endpoint_skip_connector_check_with_config_file_errors
    (False, False, False, False),
    (False, False, True, True),
    (False, True, False, False),
    (False, True, True, True),
    (True, False, False, False),
    (True, False, True, True),
])
def test_apply_inbound_device_endpoint_success(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    mocked_get_namespace_for_instance,
    with_config_file: bool,
    skip_connector_check: bool,
    endpoints_present: bool,
    replace: bool,
):
    """
    Happy-path tests for apply_inbound_device_endpoint.
    Covers: with/without config file, skip/no-skip connector check, replace semantics.
    """

    connector_type = "Microsoft.OpcUa"
    version_from_template = "1.3.0"

    # OPC UA does not use Akri connector templates — mock _get_opcua_info instead.
    # For skip_connector_check=True neither path is taken, so the mock is a no-op there.
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.get_opcua_info",
        return_value={"version": version_from_template, "inboundEndpoints": []},
    )
    # ConnectorTemplates should NOT be called for OPC UA; patch it to catch any accidental call.
    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.side_effect = AssertionError(
        "ConnectorTemplates should not be called for OPC UA"
    )

    # Setup identifiers
    device_name = generate_random_string()
    instance_name = f"inst-{generate_random_string()}"
    instance_resource_group = f"rg-{generate_random_string()}"
    endpoint_name = f"ep-{generate_random_string()}"
    endpoint_address = "opc.tcp://10.0.0.1:4840"

    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Build endpoint config file content (inline JSON, not an actual file path)
    endpoint_config_content = '{"keepAlive": 5000}'
    config_file_path = None
    if with_config_file:
        config_file_path = endpoint_config_content
        # patch process_additional_configuration so it just returns the JSON string
        mocker.patch(
            "azext_edge.edge.providers.adr.helpers.process_additional_configuration",
            return_value=endpoint_config_content,
        )

    # Build original device
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

    # Determine expected endpoint body
    # OPC UA version is always None — ADR manages it (consistent with DOE behavior).
    expected_version = None
    expected_inbound = {
        endpoint_name: {
            "endpointType": connector_type,
            "address": endpoint_address,
            "version": expected_version,
            "authentication": {"method": ADRAuthModes.anonymous.value},
        }
    }
    if with_config_file:
        expected_inbound[endpoint_name]["additionalConfiguration"] = endpoint_config_content

    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {"inbound": expected_inbound}

    # Mock GET (original device)
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name,
        ),
        json=original_device,
        status=200,
        content_type="application/json",
    )
    # Mock PATCH
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name,
        ),
        json=updated_device,
        status=200,
        content_type="application/json",
    )
    # Mock GET (final read-back)
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name,
        ),
        json=updated_device,
        status=200,
        content_type="application/json",
    )

    result = apply_inbound_device_endpoint(
        cmd=mocked_cmd,
        connector_type=connector_type,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        device_name=device_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        endpoint_config=config_file_path,
        skip_connector_check=skip_connector_check,
        wait_sec=0,
        replace=replace,
    )

    assert result == expected_inbound

    # OPC UA never uses ConnectorTemplates — template lookup must not be called in any case.
    mock_ct.return_value.get_connector_template_for_type.assert_not_called()

    # Verify HTTP calls
    assert len(mocked_responses.calls) == 3
    patch_body = json.loads(mocked_responses.calls[1].request.body)
    endpoint_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert endpoint_patch["endpointType"] == connector_type
    assert endpoint_patch["version"] == expected_version
    assert endpoint_patch["address"] == endpoint_address

    if with_config_file:
        assert endpoint_patch.get("additionalConfiguration") == endpoint_config_content
    else:
        assert "additionalConfiguration" not in endpoint_patch


def test_apply_inbound_device_endpoint_duplicate_no_replace_errors(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    mocked_get_namespace_for_instance,
):
    """Duplicate endpoint name without --replace must raise InvalidArgumentValueError."""
    connector_type = "Microsoft.OpcUa"
    # OPC UA uses bundled metadata, not connector templates.
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.get_opcua_info",
        return_value={"version": "1.2.82", "inboundEndpoints": []},
    )
    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.side_effect = AssertionError(
        "ConnectorTemplates should not be called for OPC UA"
    )

    device_name = generate_random_string()
    endpoint_name = f"ep-{generate_random_string()}"
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    # Pre-populate the endpoint so it already exists
    original_device["properties"]["endpoints"]["inbound"] = {
        endpoint_name: {"endpointType": connector_type, "address": "opc.tcp://old:4840", "authentication": {}}
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            device_name=device_name,
        ),
        json=original_device,
        status=200,
        content_type="application/json",
    )

    with pytest.raises(InvalidArgumentValueError, match="already exists"):
        apply_inbound_device_endpoint(
            cmd=mocked_cmd,
            connector_type=connector_type,
            instance_name="my-instance",
            instance_resource_group="my-rg",
            device_name=device_name,
            endpoint_name=endpoint_name,
            endpoint_address="opc.tcp://new:4840",
            no_replace=True,
            wait_sec=0,
        )


# ---------------------------------------------------------------------------
# _slim_schema unit tests
# ---------------------------------------------------------------------------


def test_slim_schema_config_mode_flat():
    """config mode: fields with defaults use the default; fields without default → None."""
    schema = {
        "type": "object",
        "properties": {
            "withDefault": {"type": "integer", "default": 42},
            "noDefault": {"type": "string"},
        },
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"withDefault": 42, "noDefault": None}


def test_slim_schema_schema_mode_flat():
    """schema mode: every field is a metadata dict with type and default."""
    schema = {
        "type": "object",
        "properties": {
            "withDefault": {"type": "integer", "default": 42},
            "noDefault": {"type": "string"},
        },
    }
    result = _slim_schema(schema, mode="schema")
    assert result == {
        "withDefault": {"type": "integer", "default": 42},
        "noDefault": {"type": "string", "default": None},
    }


def test_slim_schema_schema_mode_required_visible():
    """schema mode: 'required' list is included in the output so users know which fields are mandatory.
    config mode: 'required' is NOT included (it only affects the null-field warning)."""
    schema = {
        "type": "object",
        "required": ["name", "enabled"],
        "properties": {
            "name": {"type": "string"},
            "enabled": {"type": "boolean", "default": True},
            "optional": {"type": "integer", "default": 0},
        },
    }
    schema_result = _slim_schema(schema, mode="schema")
    assert schema_result["required"] == ["name", "enabled"]
    assert schema_result["name"] == {"type": "string", "default": None}
    assert schema_result["enabled"] == {"type": "boolean", "default": True}
    assert schema_result["optional"] == {"type": "integer", "default": 0}

    config_result = _slim_schema(schema, mode="config")
    assert "required" not in config_result
    assert config_result == {"name": None, "enabled": True, "optional": 0}


def test_slim_schema_schema_mode_no_required_no_key():
    """schema mode: when there is no 'required' in the schema, the key is omitted from output."""
    schema = {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
        },
    }
    result = _slim_schema(schema, mode="schema")
    assert "required" not in result


def test_slim_schema_nested_objects():
    """Both modes recurse into nested objects (sub-properties)."""
    schema = {
        "type": "object",
        "properties": {
            "security": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "default": "Sign"},
                    "policy": {"type": "string"},
                },
            }
        },
    }
    config = _slim_schema(schema, mode="config")
    assert config == {"security": {"mode": "Sign", "policy": None}}

    schema_result = _slim_schema(schema, mode="schema")
    assert schema_result == {
        "security": {
            "mode": {"type": "string", "default": "Sign"},
            "policy": {"type": "string", "default": None},
        }
    }


@pytest.mark.parametrize("constraint_key,constraint_value", [
    ("minimum", 0),
    ("maximum", 100),
    ("exclusiveMinimum", 1),
    ("exclusiveMaximum", 99),
    ("enum", ["a", "b", "c"]),
    ("pattern", "^[a-z]+$"),
])
def test_slim_schema_schema_mode_constraints(constraint_key, constraint_value):
    """schema mode: constraint keys are preserved in the metadata dict."""
    schema = {
        "type": "object",
        "properties": {
            "field": {"type": "string", **{constraint_key: constraint_value}},
        },
    }
    result = _slim_schema(schema, mode="schema")
    assert result["field"][constraint_key] == constraint_value


def test_slim_schema_config_mode_ignores_constraints():
    """config mode: constraint keys are NOT included — only the default value is returned."""
    schema = {
        "type": "object",
        "properties": {
            "field": {"type": "integer", "default": 5, "minimum": 0, "maximum": 100},
        },
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"field": 5}


def test_slim_schema_type_array_drops_null():
    """When type is an array like ['string', 'null'], null is stripped in both modes."""
    schema = {
        "type": "object",
        "properties": {
            "field": {"type": ["string", "null"]},
        },
    }
    config = _slim_schema(schema, mode="config")
    assert config == {"field": None}

    schema_result = _slim_schema(schema, mode="schema")
    assert schema_result["field"]["type"] == "string"


def test_slim_schema_items_array_config_mode():
    """config mode: array field with items sub-schema renders as a list with one slimmed item."""
    schema = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string", "default": "tag"},
            },
        },
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"tags": ["tag"]}


def test_slim_schema_items_array_schema_mode():
    """schema mode: array field exposes type, default, and items metadata."""
    schema = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }
    result = _slim_schema(schema, mode="schema")
    assert result == {
        "tags": {
            "type": "array",
            "default": None,
            "items": {"type": "string", "default": None},
        }
    }


def test_slim_schema_oneof_picks_first_non_null_variant():
    """oneOf: the first non-null variant is selected and its properties are used."""
    schema = {
        "oneOf": [
            {"type": "null"},
            {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "default": 8080},
                },
            },
        ]
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"port": 8080}


def test_slim_schema_anyof_ignored():
    """anyOf is unsupported and silently ignored; result is the scalar/null fallback."""
    schema = {
        "anyOf": [
            {"type": "null"},
            {"type": "string", "default": "hello"},
        ]
    }
    # anyOf key is ignored; schema has no properties/items/type → scalar leaf with default=None
    result = _slim_schema(schema, mode="config")
    assert result is None


def test_slim_schema_oneof_multi_variant_config_mode_picks_first():
    """config mode with multiple real oneOf variants: first non-null is used (must be concrete)."""
    schema = {
        "oneOf": [
            {"type": "null"},
            {"type": "string", "default": "basic"},
            {"type": "string", "default": "advanced"},
        ]
    }
    result = _slim_schema(schema, mode="config")
    assert result == "basic"


def test_slim_schema_oneof_multi_variant_schema_mode_preserves_all():
    """schema mode with multiple oneOf variants: all variants including null are preserved."""
    schema = {
        "oneOf": [
            {"type": "null"},
            {"type": "string", "default": "basic"},
            {"type": "string", "default": "advanced"},
        ]
    }
    result = _slim_schema(schema, mode="schema")
    assert "oneOf" in result
    assert result["oneOf"] == [
        {"type": "null", "default": None},
        {"type": "string", "default": "basic"},
        {"type": "string", "default": "advanced"},
    ]


def test_slim_schema_anyof_ignored_schema_mode():
    """anyOf is unsupported; in schema mode it is silently ignored and the schema falls through."""
    schema = {
        "anyOf": [
            {"type": "null"},
            {"type": "object", "properties": {"host": {"type": "string", "default": "localhost"}}},
            {"type": "object", "properties": {"url": {"type": "string", "default": "http://"}}},
        ]
    }
    result = _slim_schema(schema, mode="schema")
    # anyOf key is ignored; schema has no properties/items/type → scalar metadata dict
    assert "anyOf" not in result
    assert result == {"type": "string", "default": None}


def test_slim_schema_allof_merges_properties():
    """allOf config mode: properties from all sub-schemas are merged into one flat object."""
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": "localhost"},
                },
            },
            {
                "properties": {
                    "port": {"type": "integer", "default": 443},
                },
            },
        ]
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"host": "localhost", "port": 443}


def test_slim_schema_allof_schema_mode_preserves_structure():
    """allOf schema mode: each sub-schema is slimmed separately and allOf key is preserved."""
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": "127.0.0.1"},
                },
            },
            {
                "properties": {
                    "port": {"type": "integer", "default": 8080},
                    "timeout": {"type": "integer", "default": 30},
                },
            },
        ]
    }
    result = _slim_schema(schema, mode="schema")
    assert "allOf" in result
    assert len(result["allOf"]) == 2
    assert result["allOf"][0] == {"host": {"type": "string", "default": "127.0.0.1"}}
    assert result["allOf"][1] == {
        "port": {"type": "integer", "default": 8080},
        "timeout": {"type": "integer", "default": 30},
    }


def test_slim_schema_ref_definitions_path():
    """$ref with #/definitions/... (Draft-07 style) is resolved against the root schema."""
    schema = {
        "definitions": {
            "AuthConfig": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "default": "admin"},
                    "password": {"type": "string"},
                },
            }
        },
        "type": "object",
        "properties": {
            "host": {"type": "string", "default": "localhost"},
            "auth": {"$ref": "#/definitions/AuthConfig"},
        },
    }
    result_config = _slim_schema(schema, mode="config")
    assert result_config["host"] == "localhost"
    assert result_config["auth"] == {"username": "admin", "password": None}

    result_schema = _slim_schema(schema, mode="schema")
    assert result_schema["host"] == {"type": "string", "default": "localhost"}
    assert result_schema["auth"] == {
        "username": {"type": "string", "default": "admin"},
        "password": {"type": "string", "default": None},
    }


def test_slim_schema_ref_named_anchor_ignored():
    """$ref with a named anchor (#Name) is unsupported and silently ignored.
    Only #/definitions/... paths are resolved; bare-fragment anchors return None."""
    schema = {
        "type": "object",
        "properties": {
            "conn": {"$ref": "#ConnDef"},
            "ConnDef": {
                "$anchor": "ConnDef",
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": "127.0.0.1"},
                    "port": {"type": "integer", "default": 8080},
                },
            },
        },
    }
    result = _slim_schema(schema, mode="config")
    # Named anchor ref is not a #/definitions/... path → silently ignored → None
    assert result["conn"] is None


def test_slim_schema_ref_unresolvable_skipped():
    """Unsupported $ref formats are silently dropped; remaining sibling keys are processed."""
    schema = {
        "type": "object",
        "properties": {
            "field": {
                "$ref": "#/definitions/DoesNotExist",
                "default": "fallback",
            },
        },
    }
    result = _slim_schema(schema, mode="config")
    # $ref path not found in definitions; sibling 'default' key remains → scalar fallback
    assert result["field"] == "fallback"


def test_slim_schema_additional_properties_ignored():
    """additionalProperties is unsupported and must NOT appear in the output in any form."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "myDevice"},
        },
        "additionalProperties": {"type": "string"},
    }
    result_config = _slim_schema(schema, mode="config")
    assert result_config == {"name": "myDevice"}
    assert "<additionalKey>" not in result_config

    result_schema = _slim_schema(schema, mode="schema")
    assert result_schema == {"name": {"type": "string", "default": "myDevice"}}
    assert "<additionalKey>" not in result_schema


def test_slim_schema_additional_properties_false_ignored():
    """additionalProperties: false is not a schema — it must NOT appear in the output."""
    schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "default": "localhost"},
        },
        "additionalProperties": False,
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"host": "localhost"}
    assert "<additionalKey>" not in result


def test_slim_schema_const_config_mode():
    """const in config mode returns the fixed value directly."""
    schema = {
        "type": "object",
        "properties": {
            "version": {"const": "1.0.0"},
            "name": {"type": "string", "default": "test"},
        },
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"version": "1.0.0", "name": "test"}


def test_slim_schema_const_schema_mode():
    """const in schema mode returns a metadata dict with type 'const'."""
    schema = {
        "type": "object",
        "properties": {
            "version": {"const": "1.0.0"},
        },
    }
    result = _slim_schema(schema, mode="schema")
    assert result["version"] == {"type": "const", "const": "1.0.0"}


def test_slim_schema_ref_with_sibling_overrides():
    """$ref properties are overridden by sibling keys per JSON Schema spec."""
    schema = {
        "definitions": {
            "interval": {
                "type": "integer",
                "minimum": 1,
                "maximum": 86400000,
            }
        },
        "type": "object",
        "properties": {
            "publishingInterval": {
                "title": "Publishing interval (ms)",
                "default": 100,
                "$ref": "#/definitions/interval",
            },
            "samplingInterval": {
                "title": "Sampling interval (ms)",
                "default": 500,
                "$ref": "#/definitions/interval",
            },
        },
    }
    result = _slim_schema(schema, mode="config")
    assert result == {"publishingInterval": 100, "samplingInterval": 500}

    result_schema = _slim_schema(schema, mode="schema")
    assert result_schema["publishingInterval"]["type"] == "integer"
    assert result_schema["publishingInterval"]["default"] == 100
    assert result_schema["publishingInterval"]["minimum"] == 1
    assert result_schema["samplingInterval"]["default"] == 500


# ---------------------------------------------------------------------------
# _strip_nulls unit tests
# ---------------------------------------------------------------------------


def test_strip_nulls_removes_null_values_from_dict():
    """Null values in a dict are removed."""
    assert _strip_nulls({"a": 1, "b": None, "c": "x"}) == {"a": 1, "c": "x"}


def test_strip_nulls_removes_null_items_from_list():
    """Null items in a list are removed."""
    assert _strip_nulls([1, None, "x", None]) == [1, "x"]


def test_strip_nulls_filters_empty_dicts_from_list():
    """Array items that become empty dicts after stripping are dropped.

    This covers the --show-template round-trip case: an all-null placeholder
    like {"browsePath": null, "fieldId": null} should produce an empty array
    rather than [{}], which would fail 'required' schema validation.
    """
    assert _strip_nulls([{"browsePath": None, "fieldId": None}]) == []


def test_strip_nulls_keeps_partially_filled_array_items():
    """Array items with at least one non-null field are kept."""
    result = _strip_nulls([{"browsePath": "ns=1;i=42", "fieldId": None}])
    assert result == [{"browsePath": "ns=1;i=42"}]


def test_strip_nulls_mixed_list_drops_all_null_items():
    """Mixed list: fully-null items dropped, partially-filled items kept."""
    result = _strip_nulls([
        {"browsePath": None, "fieldId": None},
        {"browsePath": "ns=1;i=1"},
        {"browsePath": None, "fieldId": None},
    ])
    assert result == [{"browsePath": "ns=1;i=1"}]


def test_strip_nulls_nested_recursion():
    """Null removal recurses into nested dicts and lists."""
    obj = {
        "eventFilter": {
            "selectClauses": [
                {"browsePath": None, "fieldId": None, "typeDefinitionId": None}
            ]
        },
        "publishingInterval": 1000,
    }
    result = _strip_nulls(obj)
    assert result == {
        "eventFilter": {"selectClauses": []},
        "publishingInterval": 1000,
    }


def test_strip_nulls_scalars_pass_through():
    """Non-container values pass through unchanged."""
    assert _strip_nulls(42) == 42
    assert _strip_nulls("hello") == "hello"
    assert _strip_nulls(True) is True


# ---------------------------------------------------------------------------
# check_json_schema dialect guard (used by mgmt actions and namespace_devices)
# ---------------------------------------------------------------------------

def test_check_json_schema_accepts_json_schema_org_dialects():
    """check_json_schema accepts any json-schema.org dialect (Draft-04 through 2020-12).

    mgmt actions may use any standard JSON Schema draft, so the shared utility
    accepts all json-schema.org URIs.  The stricter Draft-07-only gate lives
    inline in namespace_devices.py apply flow only.
    """
    from azext_edge.edge.util.schema_validation import check_json_schema

    for dialect in [
        "http://json-schema.org/draft-07/schema#",
        "https://json-schema.org/draft/2020-12/schema",
        "http://json-schema.org/draft-04/schema#",
        "http://json-schema.org/draft-06/schema#",
    ]:
        reason = check_json_schema({"$schema": dialect, "type": "object"})
        assert reason is None, f"check_json_schema should accept json-schema.org dialect '{dialect}'"


def test_check_json_schema_rejects_non_json_schema_org_dialects():
    """check_json_schema rejects completely unknown/custom $schema URIs."""
    from azext_edge.edge.util.schema_validation import check_json_schema

    for bad_dialect in [
        "custom://my-schema",
        "https://example.com/my-schema",
        "urn:my-org:schema:v1",
    ]:
        reason = check_json_schema({"$schema": bad_dialect, "type": "object"})
        assert reason is not None, f"Expected rejection for dialect '{bad_dialect}'"
        assert "not a recognized JSON Schema format" in reason


def test_check_json_schema_allows_missing_schema_key():
    """check_json_schema is lenient when $schema is absent."""
    from azext_edge.edge.util.schema_validation import check_json_schema

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    assert check_json_schema(schema) is None


def test_apply_inbound_endpoint_skips_validation_for_non_draft07_schema(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    mocked_get_namespace_for_instance,
):
    """When the connector schema declares a non-Draft-07 dialect, validation is
    skipped with a warning and the endpoint is applied without error."""
    endpoint_config = json.dumps({"someKey": "someValue"})
    non_draft07_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"someKey": {"type": "string"}},
    }

    device_name = generate_random_string()
    endpoint_name = generate_random_string()
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    original_device["properties"]["endpoints"] = {"inbound": {}}

    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"]["inbound"][endpoint_name] = {
        "endpointType": "Custom.MyConnector",
        "address": "tcp://host:1234",
        "version": "1.0",
        "authentication": {"method": ADRAuthModes.anonymous.value},
        "additionalConfiguration": endpoint_config,
    }

    mock_ct = mocker.patch("azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates")
    mock_ct.return_value.get_connector_template_for_type.return_value = {"id": "fake"}
    mock_ct.return_value.get_endpoint_version_for_type.return_value = "1.0"
    mock_ct.return_value.get_endpoint_schema.return_value = {"endpointConfig": non_draft07_schema}

    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.process_additional_configuration",
        return_value=endpoint_config,
    )

    device_uri = get_namespace_device_mgmt_uri(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        device_name=device_name,
    )
    mocked_responses.add(responses.GET, device_uri, json=original_device, status=200)
    mocked_responses.add(responses.PATCH, device_uri, json=updated_device, status=200)
    mocked_responses.add(responses.GET, device_uri, json=updated_device, status=200)

    # Should not raise even though schema dialect is not Draft-07
    apply_inbound_device_endpoint(
        cmd=mocked_cmd,
        connector_type="Custom.MyConnector",
        instance_name="my-instance",
        instance_resource_group="my-rg",
        device_name=device_name,
        endpoint_name=endpoint_name,
        endpoint_address="tcp://host:1234",
        endpoint_config=endpoint_config,
        wait_sec=0,
    )


# ---------------------------------------------------------------------------
# --show-template + --endpoint-config mutual exclusion (unit)
# ---------------------------------------------------------------------------

def test_apply_inbound_device_endpoint_show_template_with_config_errors(
    mocked_cmd,
    mocked_get_namespace_for_instance,
):
    """--show-template and --endpoint-config together must raise InvalidArgumentValueError."""
    from azure.cli.core.azclierror import InvalidArgumentValueError as _IAE
    with pytest.raises(_IAE, match="--show-template and --endpoint-config cannot be used together"):
        apply_inbound_device_endpoint(
            cmd=mocked_cmd,
            connector_type="Microsoft.OpcUa",
            instance_name="my-instance",
            instance_resource_group="my-rg",
            show_template="config",
            endpoint_config='{"applicationName": "test"}',
        )


# ---------------------------------------------------------------------------
# Non-OpcUa happy path (ConnectorTemplates IS called)
# ---------------------------------------------------------------------------

def test_apply_inbound_device_endpoint_success_non_opcua(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    mocked_get_namespace_for_instance,
):
    """
    Happy-path for a non-OPC UA connector type (Microsoft.Onvif).
    ConnectorTemplates.get_connector_template_for_type must be called to resolve version.
    """
    connector_type = "Microsoft.Onvif"
    version_from_template = "2.1.0"

    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.return_value = _make_connector_template(
        connector_type, version=version_from_template
    )
    mock_ct.return_value.get_endpoint_version_for_type.return_value = version_from_template

    device_name = generate_random_string()
    endpoint_name = f"ep-{generate_random_string()}"
    endpoint_address = "http://192.168.1.10:80/onvif/device_service"

    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    expected_inbound = {
        endpoint_name: {
            "endpointType": connector_type,
            "address": endpoint_address,
            "version": version_from_template,
            "authentication": {"method": ADRAuthModes.anonymous.value},
        }
    }
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {"inbound": expected_inbound}

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=original_device,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=updated_device,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=updated_device,
        status=200,
        content_type="application/json",
    )

    result = apply_inbound_device_endpoint(
        cmd=mocked_cmd,
        connector_type=connector_type,
        instance_name="my-instance",
        instance_resource_group="my-rg",
        device_name=device_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        wait_sec=0,
    )

    assert result == expected_inbound
    mock_ct.return_value.get_connector_template_for_type.assert_called_once()

    patch_body = json.loads(mocked_responses.calls[1].request.body)
    ep_patch = patch_body["properties"]["endpoints"]["inbound"][endpoint_name]
    assert ep_patch["endpointType"] == connector_type
    assert ep_patch["version"] == version_from_template


# ---------------------------------------------------------------------------
# Schema validation tests for --endpoint-config
# ---------------------------------------------------------------------------


def test_apply_inbound_device_endpoint_opcua_config_fails_schema_validation(
    mocked_cmd,
    mocker,
    mocked_get_namespace_for_instance,
):
    """Invalid OPC UA endpoint config raises InvalidArgumentValueError via bundled schema."""
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.get_opcua_info",
        return_value={"version": "1.2.82", "inboundEndpoints": []},
    )
    # keepAliveMilliseconds must be an integer — passing a string violates the schema.
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.process_additional_configuration",
        return_value='{"keepAliveMilliseconds": "not-an-integer"}',
    )

    with pytest.raises(InvalidArgumentValueError, match="endpoint"):
        apply_inbound_device_endpoint(
            cmd=mocked_cmd,
            connector_type="Microsoft.OpcUa",
            instance_name="my-instance",
            instance_resource_group="my-rg",
            device_name="my-device",
            endpoint_name="ep1",
            endpoint_address="opc.tcp://1.2.3.4:4840",
            endpoint_config='{"keepAliveMilliseconds": "not-an-integer"}',
        )


def test_apply_inbound_device_endpoint_non_opcua_config_fails_schema_validation(
    mocked_cmd,
    mocker,
    mocked_get_namespace_for_instance,
):
    """Invalid non-OPC UA endpoint config raises InvalidArgumentValueError via schema from get_endpoint_schema."""
    strict_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "port": {"type": "integer"},
        },
        "additionalProperties": False,
    }
    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.return_value = _make_connector_template(
        "Microsoft.Onvif", version="2.0.0"
    )
    mock_ct.return_value.get_endpoint_version_for_type.return_value = "2.0.0"
    mock_ct.return_value.get_endpoint_schema.return_value = {
        "connectorType": "Microsoft.Onvif",
        "endpointConfig": strict_schema,
    }
    # unknownField is rejected by additionalProperties: false
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.process_additional_configuration",
        return_value='{"unknownField": "bad"}',
    )

    with pytest.raises(InvalidArgumentValueError):
        apply_inbound_device_endpoint(
            cmd=mocked_cmd,
            connector_type="Microsoft.Onvif",
            instance_name="my-instance",
            instance_resource_group="my-rg",
            device_name="my-device",
            endpoint_name="ep1",
            endpoint_address="http://1.2.3.4:80/onvif",
            endpoint_config='{"unknownField": "bad"}',
        )

    mock_ct.return_value.get_endpoint_schema.assert_called_once_with(
        instance_name="my-instance",
        instance_resource_group="my-rg",
        connector_type="Microsoft.Onvif",
    )


def test_apply_inbound_device_endpoint_non_opcua_non_standard_dialect_skips_validation(
    mocked_cmd,
    mocker,
    mocked_get_namespace_for_instance,
    mocked_responses: responses,
):
    """Non-standard schema dialect causes validation to be skipped (warning logged, no error)."""
    non_standard_schema = {
        "$schema": "https://custom.ops.io/schemas/v1/endpoint",  # not json-schema.org
        "type": "object",
        "properties": {"port": {"type": "integer"}},
        "additionalProperties": False,
    }
    connector_type = "Microsoft.Onvif"
    version_from_template = "2.0.0"

    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.return_value = _make_connector_template(
        connector_type, version=version_from_template
    )
    mock_ct.return_value.get_endpoint_version_for_type.return_value = version_from_template
    mock_ct.return_value.get_endpoint_schema.return_value = {
        "connectorType": connector_type,
        "endpointConfig": non_standard_schema,
    }

    endpoint_config_str = '{"unknownField": "would-fail-if-validated"}'
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.process_additional_configuration",
        return_value=endpoint_config_str,
    )
    # validate_data_against_schema must NOT be called since dialect is non-standard
    mock_validate = mocker.patch(
        "azext_edge.edge.util.schema_validation.validate_data_against_schema"
    )

    device_name = generate_random_string()
    endpoint_name = f"ep-{generate_random_string()}"
    endpoint_address = "http://192.168.1.10:80/onvif/device_service"
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    expected_inbound = {
        endpoint_name: {
            "endpointType": connector_type,
            "address": endpoint_address,
            "version": version_from_template,
            "authentication": {"method": ADRAuthModes.anonymous.value},
            "additionalConfiguration": endpoint_config_str,
        }
    }
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {"inbound": expected_inbound}

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=original_device,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=updated_device,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=updated_device,
        status=200,
        content_type="application/json",
    )

    apply_inbound_device_endpoint(
        cmd=mocked_cmd,
        connector_type=connector_type,
        instance_name="my-instance",
        instance_resource_group="my-rg",
        device_name=device_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        endpoint_config=endpoint_config_str,
        wait_sec=0,
    )

    mock_validate.assert_not_called()


def test_apply_inbound_device_endpoint_non_opcua_get_endpoint_schema_called_with_config(
    mocked_cmd,
    mocker,
    mocked_get_namespace_for_instance,
    mocked_responses: responses,
):
    """Happy path: get_endpoint_schema is called for non-OPC UA when --endpoint-config is provided."""
    connector_type = "Microsoft.Onvif"
    version_from_template = "2.0.0"
    valid_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"port": {"type": "integer"}},
    }

    mock_ct = mocker.patch(
        "azext_edge.edge.providers.adr.namespace_devices.ConnectorTemplates"
    )
    mock_ct.return_value.get_connector_template_for_type.return_value = _make_connector_template(
        connector_type, version=version_from_template
    )
    mock_ct.return_value.get_endpoint_version_for_type.return_value = version_from_template
    mock_ct.return_value.get_endpoint_schema.return_value = {
        "connectorType": connector_type,
        "endpointConfig": valid_schema,
    }

    endpoint_config_str = '{"port": 8080}'
    mocker.patch(
        "azext_edge.edge.providers.adr.helpers.process_additional_configuration",
        return_value=endpoint_config_str,
    )

    device_name = generate_random_string()
    endpoint_name = f"ep-{generate_random_string()}"
    endpoint_address = "http://192.168.1.10:80/onvif/device_service"
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    resource_group_name = mocked_get_namespace_for_instance.return_value["resource_group"]

    original_device = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    expected_inbound = {
        endpoint_name: {
            "endpointType": connector_type,
            "address": endpoint_address,
            "version": version_from_template,
            "authentication": {"method": ADRAuthModes.anonymous.value},
            "additionalConfiguration": endpoint_config_str,
        }
    }
    updated_device = deepcopy(original_device)
    updated_device["properties"]["endpoints"] = {"inbound": expected_inbound}

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=original_device,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=updated_device,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(namespace_name, resource_group_name, device_name),
        json=updated_device,
        status=200,
        content_type="application/json",
    )

    result = apply_inbound_device_endpoint(
        cmd=mocked_cmd,
        connector_type=connector_type,
        instance_name="my-instance",
        instance_resource_group="my-rg",
        device_name=device_name,
        endpoint_name=endpoint_name,
        endpoint_address=endpoint_address,
        endpoint_config=endpoint_config_str,
        wait_sec=0,
    )

    assert result == expected_inbound
    mock_ct.return_value.get_endpoint_schema.assert_called_once_with(
        instance_name="my-instance",
        instance_resource_group="my-rg",
        connector_type=connector_type,
    )
