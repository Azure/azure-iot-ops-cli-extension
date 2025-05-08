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
    create_namespace,
    delete_namespace,
    list_namespaces,
    show_namespace,
    update_namespace,
    add_namespace_endpoint,
    list_namespace_endpoints,
    remove_namespace_endpoint,
)
from ...orchestration.resources.conftest import get_base_endpoint

from .conftest import get_namespace_mgmt_uri, get_namespace_record
from ....generators import generate_random_string, BASE_URL


RESOURCES_API_VERSION = "2024-03-01"
EVENTGRIDTOPIC_API_VERSION = "2025-02-15"
EVENTGRIDTOPIC_RESOURCE_TYPE = "Microsoft.EventGrid/topics"


@pytest.fixture()
def mocked_logger(mocker):
    return mocker.patch("azext_edge.edge.providers.rpsaas.adr.namespaces.logger", autospec=True)


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("req", [
    {},
    {
        "initial_endpoint_ids": ["endpoint-id-1", "endpoint-id-2"],
        "location": "westus",
        "mi_system_identity": True,
        "tags": {"tag1": "value1", "tag2": "value2"},
    },
    {
        "initial_endpoint_ids": ["endpoint-id-1"],
        "mi_system_identity": False,
        "invalid_endpoint_ids": ["invalid-endpoint-id"],
    }
])
def test_namespace_create(
    mocked_logger,
    mocked_cmd,
    mocked_responses: responses,
    req: Dict[str, str],
    response_status: int
):
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Add mock response for resource group location
    mock_resource_group = {"location": generate_random_string()}
    if not req.get("location"):
        mocked_responses.add(
            method=responses.GET,
            url=get_base_endpoint(
                resource_group_name=resource_group_name, resource_provider="", api_version=RESOURCES_API_VERSION
            ).replace("resourceGroups", "resourcegroups"),
            json=mock_resource_group,
            status=200,
        )

    # Setup mock for endpoint processing if endpoints are provided
    expected_endpoints = {}
    if req.get("initial_endpoint_ids"):
        endpoint_ids = []
        for endpoint_name in req["initial_endpoint_ids"]:
            endpoint_rg = generate_random_string()
            endpoint_uri = f"https://{endpoint_name}.eventgrid.azure.net/topics/{generate_random_string()}"
            endpoint_resource_id = get_base_endpoint(
                resource_group_name=endpoint_rg,
                resource_path=EVENTGRIDTOPIC_RESOURCE_TYPE,
            ).split("?")[0][len(BASE_URL) :]
            mocked_responses.add(
                method=responses.GET,
                url=get_base_endpoint(
                    resource_group_name=endpoint_rg,
                    resource_path=EVENTGRIDTOPIC_RESOURCE_TYPE,
                    api_version=EVENTGRIDTOPIC_API_VERSION,
                ),
                json={
                    "properties": {
                        "endpoint": endpoint_uri,
                    },
                    "name": endpoint_name,
                    "resourceGroup": endpoint_rg,
                    "type": EVENTGRIDTOPIC_RESOURCE_TYPE,
                },
                status=200,
            )
            expected_endpoints[f"{endpoint_rg}-{endpoint_name}"] = {
                "address": endpoint_uri,
                "resourceId": endpoint_resource_id,
                "endpointType": EVENTGRIDTOPIC_RESOURCE_TYPE.split("/")[0],
            }
            endpoint_ids.append(endpoint_resource_id)
        req["initial_endpoint_ids"] = endpoint_ids

    # Process invalid endpoint IDs if provided
    if req.get("invalid_endpoint_ids"):
        endpoint_ids = []
        for endpoint_name in req["invalid_endpoint_ids"]:
            endpoint_resource_id = get_base_endpoint(
                resource_group_name=endpoint_rg,
                resource_path=EVENTGRIDTOPIC_RESOURCE_TYPE,
            ).split("?")[0][len(BASE_URL) :]
            mocked_responses.add(
                method=responses.GET,
                url=get_base_endpoint(
                    resource_group_name=endpoint_rg,
                    resource_path=EVENTGRIDTOPIC_RESOURCE_TYPE,
                    api_version=EVENTGRIDTOPIC_API_VERSION,
                ),
                json={},
                status=443,
            )
            endpoint_ids.append(endpoint_resource_id)
        req["initial_endpoint_ids"].extend(endpoint_ids)

    # Create mock response
    mock_namespace_record = get_namespace_record(
        namespace_name=namespace_name, namespace_resource_group=resource_group_name
    )

    # Add error response for failure case
    error_response = {
        "error": {
            "code": "BadRequest",
            "message": "Invalid request parameters"
        }
    }

    # Add mock response
    namespace_put = mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_namespace_record if response_status == 200 else error_response,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):  # Use a more specific exception if available
            create_namespace(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0,
                **req
            )
        return

    # Test create_namespace for success case
    result = create_namespace(
        cmd=mocked_cmd,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
        **req
    )

    # Verify result matches mock response
    assert result == mock_namespace_record

    # Verify API call was made with correct URL and method
    expected_calls = 1 + len(req.get("initial_endpoint_ids", []))
    if not req.get("location"):
        expected_calls += 1
    assert len(mocked_responses.calls) == expected_calls

    # Verify request body contains expected values
    call_body = json.loads(namespace_put.calls[0].request.body)

    # Check identity
    if "mi_system_identity" in req:
        expected_identity_type = "SystemAssigned" if req["mi_system_identity"] else "None"
        assert call_body["identity"]["type"] == expected_identity_type

    # Check location
    expected_location = req.get("location", mock_resource_group["location"])
    assert call_body.get("location") == expected_location

    # Check tags
    assert call_body.get("tags") == req.get("tags")

    # Check messaging.endpoints
    call_endpoints = call_body["properties"]["messaging"]["endpoints"]
    assert len(call_endpoints) == len(expected_endpoints)
    for endpoint_key, endpoint in call_endpoints.items():
        assert endpoint["address"] == expected_endpoints[endpoint_key]["address"]
        assert endpoint["resourceId"] == expected_endpoints[endpoint_key]["resourceId"]
        assert endpoint["endpointType"] == expected_endpoints[endpoint_key]["endpointType"]


@pytest.mark.parametrize("response_status", [202, 443])
def test_namespace_delete(mocked_cmd, mocked_responses: responses, response_status: int):
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Mock the delete call with the parameterized status code
    mocked_responses.add(
        method=responses.DELETE,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        status=response_status,
        content_type="application/json",
    )

    # For error status codes, expect an exception
    if response_status == 443:
        with pytest.raises(Exception):  # Use a more specific exception if known
            delete_namespace(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0,
            )
    else:
        # Test the delete_namespace function for success case
        delete_namespace(
            cmd=mocked_cmd,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            wait_sec=0,
        )

        # Verify only the DELETE API call was made
        assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("records", [0, 2])
@pytest.mark.parametrize("resource_group_name", [None, generate_random_string()])
def test_namespace_list(
    mocked_cmd, mocked_responses: responses, records: int, resource_group_name: Optional[str]
):
    mock_namespace_records = {
        "value": [
            get_namespace_record(
                namespace_name=generate_random_string(),
                namespace_resource_group=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_resource_group=resource_group_name),
        json=mock_namespace_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_namespaces(cmd=mocked_cmd, resource_group_name=resource_group_name))
    assert result == mock_namespace_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [200, 443])
def test_namespace_show(mocked_cmd, mocked_responses: responses, response_status: int):
    # Setup test data
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create a mock namespace record for successful response
    mock_namespace_record = get_namespace_record(
        namespace_name=namespace_name,
        namespace_resource_group=resource_group_name
    )

    # Configure mock response for GET request
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_namespace_record if response_status == 200 else {"error": "Namespace not found"},
        status=response_status,
        content_type="application/json",
    )

    # For 443 response, expect an exception
    if response_status == 443:
        with pytest.raises(Exception):  # Use a more specific exception if known
            show_namespace(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
            )
    else:
        # Test the show_namespace function
        result = show_namespace(
            cmd=mocked_cmd,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
        )

        # Verify the result matches the mock namespace record
        assert result == mock_namespace_record

        # Verify the API call was made with correct parameters
        assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("req", [
    # Test with minimal parameters
    {},
    # Test with all parameters
    {
        "mi_system_identity": True,
        "tags": {"tag1": "value1", "tag2": "value2"},
    },
    # Test with just identity change
    {
        "mi_system_identity": False,
    },
    # Test with just tags change
    {
        "tags": {"environment": "test"},
    }
])
def test_namespace_update(
    mocked_logger,
    mocked_cmd,
    mocked_responses: responses,
    req: dict,
    response_status: int
):
    # Setup test data
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock namespace records for GET and PUT responses
    mock_original_namespace = get_namespace_record(
        namespace_name=namespace_name,
        namespace_resource_group=resource_group_name
    )
    # Add identity and tags to original namespace for testing update logic
    mock_original_namespace["identity"] = {"type": "SystemAssigned"}
    mock_original_namespace["tags"] = {"original": "tag"}

    # Create updated record for successful response
    mock_updated_namespace = mock_original_namespace.copy()
    if "tags" in req:
        mock_updated_namespace["tags"] = req["tags"]
    if "mi_system_identity" in req:
        mock_updated_namespace["identity"]["type"] = "SystemAssigned" if req["mi_system_identity"] else "None"

    # Add mock GET response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_original_namespace,
        status=200,
        content_type="application/json",
    )

    # Add mock PUT response for update operation
    mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_updated_namespace,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on response status
    if response_status != 200:
        with pytest.raises(Exception):  # Use more specific exception if available
            update_namespace(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                wait_sec=0,
                **req
            )
        return

    # Test update_namespace for success case
    result = update_namespace(
        cmd=mocked_cmd,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
        **req
    )

    # Verify result matches the mock updated namespace
    assert result == mock_updated_namespace

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 2  # GET followed by PUT
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "PUT"

    # Verify request body contains expected values
    call_body = json.loads(mocked_responses.calls[1].request.body)

    # Check tags update
    if "tags" in req:
        assert call_body["tags"] == req["tags"]
    else:
        assert call_body["tags"] == mock_original_namespace["tags"]

    # Check identity update
    if "mi_system_identity" in req:
        expected_identity_type = "SystemAssigned" if req["mi_system_identity"] else "None"
        assert call_body["identity"]["type"] == expected_identity_type


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("num_of_new_endpoints", [1, 3])
@pytest.mark.parametrize("num_of_endpoints_to_replace", [0, 1])
def test_add_namespace_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    num_of_new_endpoints: int,
    num_of_endpoints_to_replace: int,
):
    # Setup test data
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Setup endpoint mock and input
    endpoint_ids = []
    expected_endpoints = {}
    for i in range(num_of_new_endpoints):
        endpoint_name = generate_random_string()
        endpoint_rg = generate_random_string()
        endpoint_uri = f"https://{endpoint_name}.eventgrid.azure.net/topics/{generate_random_string()}"
        endpoint_resource_id = get_base_endpoint(
            resource_group_name=endpoint_rg,
            resource_path=endpoint_name,
            resource_provider=EVENTGRIDTOPIC_RESOURCE_TYPE,
        ).split("?")[0][len(BASE_URL) :]
        mocked_responses.add(
            method=responses.GET,
            url=get_base_endpoint(
                resource_group_name=endpoint_rg,
                resource_path=endpoint_name,
                resource_provider=EVENTGRIDTOPIC_RESOURCE_TYPE,
                api_version=EVENTGRIDTOPIC_API_VERSION,
            ),
            json={
                "properties": {
                    "endpoint": endpoint_uri,
                },
                "name": endpoint_name,
                "resourceGroup": endpoint_rg,
                "type": EVENTGRIDTOPIC_RESOURCE_TYPE,
            },
            status=200,
        )
        expected_endpoints[f"{endpoint_rg}-{endpoint_name}"] = {
            "address": endpoint_uri,
            "resourceId": endpoint_resource_id,
            "endpointType": EVENTGRIDTOPIC_RESOURCE_TYPE.split("/", maxsplit=1)[0],
        }
        endpoint_ids.append(endpoint_resource_id)

    # Setup mock for original namespace
    mock_original_namespace = get_namespace_record(
        namespace_name=namespace_name,
        namespace_resource_group=resource_group_name
    )

    # Add endpoints to replace
    for i in range(num_of_endpoints_to_replace):
        endpoint_id = endpoint_ids[i]
        endpoint_id_parts = endpoint_id.split('/')
        endpoint_resource_group = endpoint_id_parts[4]
        endpoint_name = endpoint_id_parts[-1]
        endpoint_key = f"{endpoint_resource_group}-{endpoint_name}"

        mock_original_namespace["properties"]["messaging"]["endpoints"][endpoint_key] = {
            "endpointType": "Microsoft.EventGrid",
            "address": f"https://example{i}.eventgrid.azure.net",
            "resourceId": endpoint_id
        }

    # Setup mock for updated namespace (after adding endpoints)
    mock_updated_namespace = mock_original_namespace.copy()
    mock_updated_namespace["properties"]["messaging"]["endpoints"].update(expected_endpoints)

    # Mock the GET response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_original_namespace,
        status=200,
        content_type="application/json",
    )

    namespace_put = mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_updated_namespace,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on response status
    if response_status != 200:
        with pytest.raises(Exception):
            add_namespace_endpoint(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_ids=endpoint_ids,
                wait_sec=0,
            )
        return

    # Test add_namespace_endpoint for success case
    result = add_namespace_endpoint(
        cmd=mocked_cmd,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_ids=endpoint_ids,
        wait_sec=0,
    )

    # Verify result matches mock response
    assert result == mock_updated_namespace

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (2 + num_of_new_endpoints)

    # Verify the PUT request body contains all the expected endpoints
    call_body = json.loads(namespace_put.calls[0].request.body)

    # Check that all endpoints were added
    endpoints_in_body = call_body["properties"]["messaging"]["endpoints"]
    assert len(endpoints_in_body) == len(mock_updated_namespace["properties"]["messaging"]["endpoints"])

    for endpoint_key, endpoint_data in expected_endpoints.items():
        assert endpoint_key in endpoints_in_body
        assert endpoints_in_body[endpoint_key]["resourceId"] == endpoint_data["resourceId"]
        assert endpoints_in_body[endpoint_key]["address"] == endpoint_data["address"]
        assert endpoints_in_body[endpoint_key]["endpointType"] == endpoint_data["endpointType"]


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("endpoints_exist", [True, False])
def test_list_namespace_endpoints(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    endpoints_exist: bool
):
    # Setup test data
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create mock namespace with or without endpoints
    mock_namespace = get_namespace_record(
        namespace_name=namespace_name,
        namespace_resource_group=resource_group_name,
        full=endpoints_exist
    )

    # Mock the GET response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_namespace if response_status == 200 else {"error": "Namespace not found"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on response status
    if response_status != 200:
        with pytest.raises(Exception):
            list_namespace_endpoints(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            )
        return

    # Test list_namespace_endpoints for success case
    result = list_namespace_endpoints(
        cmd=mocked_cmd,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )

    # Verify the result matches expected endpoints
    assert result == mock_namespace["properties"]["messaging"]["endpoints"]

    # Verify only one API call was made (GET)
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("response_status", [200, 443])
@pytest.mark.parametrize("num_endpoints_to_remove", [1, 3])
@pytest.mark.parametrize("num_endpoints_to_keep", [0, 1])
def test_remove_namespace_endpoint(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    num_endpoints_to_remove: int,
    num_endpoints_to_keep: int
):
    # Setup test data
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Create endpoints to remove
    endpoint_ids_to_remove = []
    mock_endpoints = {}
    for i in range(num_endpoints_to_remove):
        endpoint_name = f"topic-remove-{i}"
        endpoint_rg = generate_random_string()
        endpoint_id = get_base_endpoint(
            resource_group_name=endpoint_rg,
            resource_path=endpoint_name,
            resource_provider=EVENTGRIDTOPIC_RESOURCE_TYPE,
        ).split("?")[0][len(BASE_URL) :]
        endpoint_ids_to_remove.append(endpoint_id)
        mock_endpoints[f"{endpoint_rg}-{endpoint_name}"] = {
            "endpointType": "Microsoft.EventGrid/topics",
            "address": f"https://{endpoint_name}.eventgrid.azure.net",
            "resourceId": endpoint_id
        }

    # Create endpoints to keep + expected result
    expected_endpoints = {}
    for i in range(num_endpoints_to_keep):
        endpoint_name = f"topic-keep-{i}"
        endpoint_rg = generate_random_string()
        endpoint_id = get_base_endpoint(
            resource_group_name=endpoint_rg,
            resource_path=endpoint_name,
            resource_provider=EVENTGRIDTOPIC_RESOURCE_TYPE,
        ).split("?")[0][len(BASE_URL) :]
        endpoint = {
            "endpointType": "Microsoft.EventGrid/topics",
            "address": f"https://{endpoint_name}.eventgrid.azure.net",
            "resourceId": endpoint_id
        }
        mock_endpoints[f"{endpoint_rg}-{endpoint_name}"] = endpoint
        expected_endpoints[f"{endpoint_rg}-{endpoint_name}"] = endpoint

    # Create original namespace with endpoints
    mock_original_namespace = get_namespace_record(
        namespace_name=namespace_name,
        namespace_resource_group=resource_group_name
    )
    mock_original_namespace["properties"]["messaging"]["endpoints"] = mock_endpoints
    mock_updated_namespace = mock_original_namespace.copy()
    mock_updated_namespace["properties"]["messaging"]["endpoints"] = expected_endpoints

    # Mock the GET response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_original_namespace,
        status=200,
        content_type="application/json",
    )

    # Mock the PUT response for update
    mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, namespace_resource_group=resource_group_name),
        json=mock_updated_namespace,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on response status
    if response_status != 200:
        with pytest.raises(Exception):
            remove_namespace_endpoint(
                cmd=mocked_cmd,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
                endpoint_ids=endpoint_ids_to_remove,
                wait_sec=0,
            )
        return

    # Test remove_namespace_endpoint for success case
    result = remove_namespace_endpoint(
        cmd=mocked_cmd,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_ids=endpoint_ids_to_remove,
        wait_sec=0,
    )

    # Verify result matches mock response
    assert result == mock_updated_namespace

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 2  # GET followed by PUT

    # Verify the PUT request body has all endpoints removed
    call_body = json.loads(mocked_responses.calls[1].request.body)

    endpoints_in_body = call_body["properties"]["messaging"]["endpoints"]
    endpoint_ids_in_body = [endpoint_data["resourceId"] for endpoint_data in endpoints_in_body.values()]

    # Verify all endpoints to remove are gone
    for endpoint_id in endpoint_ids_to_remove:
        assert endpoint_id not in endpoint_ids_in_body

    # Verify endpoints to keep is still there
    for endpoint_key in expected_endpoints:
        assert endpoint_key in endpoints_in_body
