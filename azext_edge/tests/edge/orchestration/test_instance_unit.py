# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
from typing import Optional

import pytest
import responses

from azext_edge.edge.providers.orchestration.instances import Instances

from ...generators import generate_random_string, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
BASE_URL = "https://management.azure.com"
QUALIFIED_RESOURCE_TYPE = "Microsoft.IoTOperations/instances"
INSTANCES_API_VERSION = "2024-07-01-preview"


def get_instance_endpoint(resource_group_name: Optional[str] = None, instance_name: Optional[str] = None):
    expected_endpoint = f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}"
    if resource_group_name:
        expected_endpoint += f"/resourceGroups/{resource_group_name}"
    expected_endpoint += f"/providers/{QUALIFIED_RESOURCE_TYPE}"
    if instance_name:
        expected_endpoint += f"/{instance_name}"
    expected_endpoint += f"?api-version={INSTANCES_API_VERSION}"

    return expected_endpoint


def get_mock_instance_record(
    name: str, resource_group_name: str, subscription_id: str = ZEROED_SUBSCRIPTION, cl_name: str = "test_cl"
):
    return {
        "etag": '"1d0044af-0000-0c00-0000-6675cef80000"',
        "extendedLocation": {
            "name": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.ExtendedLocation/customLocations/{cl_name}",
            "type": "CustomLocation",
        },
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
        f"/providers/{QUALIFIED_RESOURCE_TYPE}/{name}",
        "location": "northeurope",
        "name": name,
        "properties": {"description": "AIO Instance description.", "provisioningState": "Succeeded"},
        "resourceGroup": resource_group_name,
        "systemData": {
            "createdAt": "2024-06-21T19:04:29.2176544Z",
            "createdBy": "",
            "createdByType": "Application",
            "lastModifiedAt": "2024-06-21T19:04:29.2176544Z",
            "lastModifiedBy": "",
            "lastModifiedByType": "Application",
        },
        "type": QUALIFIED_RESOURCE_TYPE,
    }


def test_instance_show(mocked_cmd, mocked_responses: responses):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    instances = Instances(mocked_cmd)
    result = instances.show(name=instance_name, resource_group_name=resource_group_name)
    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "resource_group_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_instance_list(mocked_cmd, mocked_responses: responses, resource_group_name: str, records: int):
    instance_name = generate_random_string()

    # If no resource_group_name, oh well
    mock_instance_records = {
        "value": [
            get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(resource_group_name=resource_group_name),
        json=mock_instance_records,
        status=200,
        content_type="application/json",
    )

    instances = Instances(mocked_cmd)
    result = list(instances.list(resource_group_name=resource_group_name))
    assert result == mock_instance_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "description",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "tags",
    [None, {"a": "b", "c": "d"}],
)
def test_instance_update(mocked_cmd, mocked_responses: responses, description: Optional[str], tags: Optional[dict]):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PUT,
        url=instance_endpoint,
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    instances = Instances(mocked_cmd)
    result = instances.update(
        name=instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        description=description,
        wait_sec=0.5,
    )
    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 2

    update_request = json.loads(mocked_responses.calls[1].request.body)
    if description:
        assert update_request["properties"]["description"] == description

    if tags:
        assert update_request["tags"] == tags

    if not any([description, tags]):
        assert update_request == mock_instance_record
