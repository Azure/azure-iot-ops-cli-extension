# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Dict, List, Optional
import json
import pytest
import responses

from azext_edge.edge.commands_namespaces import (
    create_namespace,
    delete_namespace,
    list_namespaces,
    show_namespace,
    update_namespace,
)
from ...orchestration.resources.conftest import get_base_endpoint

from ....generators import generate_random_string, get_zeroed_subscription
# TODO: remove ADR_BASE_URL once service is public
ADR_BASE_URL = "https://eastus2euap.management.azure.com"


RESOURCES_API_VERSION = "2024-03-01"
ADR_REFRESH_API_VERSION = "2025-07-01-preview"
EVENTGRIDTOPIC_API_VERSION = "2025-02-15"
EVENTGRIDTOPIC_RESOURCE_TYPE = "Microsoft.EventGrid/topics"


def convert_dict_to_nargs(input_dict: Dict[str, str]) -> List[str]:
    """
    Converts a dictionary to a list of key=value strings.
    """
    return [f"{key}={value}" for key, value in input_dict.items()]


def get_namespace_mgmt_uri(
    namespace_name: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    subscription: Optional[str] = None,
    include_api: bool = True
) -> str:
    resource_group_name = f"/resourceGroups/{resource_group_name}" if resource_group_name else ""
    namespace_name = f"/{namespace_name}" if namespace_name else ""

    namespace_id = (
        f"/subscriptions/{subscription or get_zeroed_subscription()}{resource_group_name}/providers/"
        f"Microsoft.DeviceRegistry/namespaces{namespace_name}"
    )
    if include_api:
        namespace_id += f"?api-version={ADR_REFRESH_API_VERSION}"
    return f"{ADR_BASE_URL}{namespace_id}"


def get_namespace_record(
    namespace_name: str,
    resource_group_name: str,
    subscription: Optional[str] = None,
) -> dict:
    namespace = {
        "id": get_namespace_mgmt_uri(
            namespace_name, resource_group_name, subscription, include_api=False
        )[len(ADR_BASE_URL) :],
        "name": namespace_name,
        "resourceGroup": resource_group_name,
        "type": "Microsoft.DeviceRegistry/namespaces",
        "location": "westus3",
        "identity": {
            "principalId": generate_random_string(),
            "tenantId": generate_random_string(),
            "type": "SystemAssigned"
        },
        "properties": {
            "uuid": generate_random_string(),
            "messaging": {
                "endpoints": {
                    "myPrimaryEventGridEndpoint": {
                        "address": "https://myeventgridtopic1.westeurope-1.eventgrid.azure.net",
                        "endpointType": "Microsoft.EventGrid"
                    },
                    "mySecondaryEventGridEndpoint": {
                        "address": "https://myeventgridtopic2.westeurope-1.eventgrid.azure.net",
                        "endpointType": "Microsoft.EventGrid"
                    }
                }
            },
            "provisioningState": "Succeeded"
        }
    }
    return namespace


@pytest.fixture()
def mocked_logger(mocker):
    return mocker.patch("azext_edge.edge.providers.rpsaas.adr.namespaces.logger", autospec=True)


@pytest.mark.parametrize("response_status", [200, 400])
@pytest.mark.parametrize("req", [
    {},
    {
        "location": "westus",
        "tags": {"tag1": "value1", "tag2": "value2"},
    },
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
    if "location" not in req:
        mocked_responses.add(
            method=responses.GET,
            url=get_base_endpoint(
                resource_group_name=resource_group_name, resource_provider="", api_version=RESOURCES_API_VERSION
            ).replace("resourceGroups", "resourcegroups"),
            json=mock_resource_group,
            status=200,
        )

    # Create mock response
    mock_namespace_record = get_namespace_record(
        namespace_name=namespace_name, resource_group_name=resource_group_name
    )

    # Add mock response
    mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, resource_group_name=resource_group_name),
        json=mock_namespace_record if response_status == 200 else {"error": "BadRequest"},
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

    # Verify result matches mock response and the number of API calls
    assert result == mock_namespace_record
    assert len(mocked_responses.calls) == len(mocked_responses.registered())

    # Verify request body contains expected values
    call_body = json.loads(mocked_responses.calls[-1].request.body)

    # Check location
    expected_location = req.get("location", mock_resource_group["location"])
    assert call_body.get("location") == expected_location

    # Check tags
    assert call_body.get("tags") == req.get("tags")


@pytest.mark.parametrize("response_status", [202, 443])
def test_namespace_delete(mocked_cmd, mocked_responses: responses, response_status: int):
    namespace_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Mock the delete call with the parameterized status code
    mocked_responses.add(
        method=responses.DELETE,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, resource_group_name=resource_group_name),
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
                confirm_yes=True
            )
    else:
        # Test the delete_namespace function for success case
        delete_namespace(
            cmd=mocked_cmd,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            wait_sec=0,
            confirm_yes=True
        )

        # Verify only the DELETE API call was made
        assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("records", [0, 2])
@pytest.mark.parametrize("resource_group_name", [None, generate_random_string()])
@pytest.mark.parametrize("response_status", [200, 443])
def test_namespace_list(
    mocked_cmd, mocked_responses: responses, records: int, resource_group_name: Optional[str], response_status: int
):
    mock_namespace_records = {
        "value": [
            get_namespace_record(
                namespace_name=generate_random_string(),
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(resource_group_name=resource_group_name),
        json=mock_namespace_records,
        status=response_status,
        content_type="application/json",
    )

    if response_status != 200:
        with pytest.raises(Exception):
            list(list_namespaces(
                cmd=mocked_cmd,
                resource_group_name=resource_group_name,
            ))
        return

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
        resource_group_name=resource_group_name
    )

    # Configure mock response for GET request
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, resource_group_name=resource_group_name),
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
        "tags": {"tag1": "value1", "tag2": "value2"},
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

    # Create mock namespace records for PATCH responses
    mock_original_namespace = get_namespace_record(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    # Add identity and tags to original namespace for testing update logic
    mock_original_namespace["tags"] = {"original": "tag"}

    # Create updated record for successful response
    mock_updated_namespace = deepcopy(mock_original_namespace)
    if "tags" in req:
        mock_updated_namespace["tags"] = req["tags"]

    # Add mock PATCH response for update operation
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_mgmt_uri(namespace_name=namespace_name, resource_group_name=resource_group_name),
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
    assert len(mocked_responses.calls) == 1
    assert mocked_responses.calls[0].request.method == "PATCH"

    # Verify request body contains expected values
    call_body = json.loads(mocked_responses.calls[0].request.body)

    # Check tags update
    assert call_body.get("tags") == req.get("tags")
