# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
import responses

from azext_edge.edge.providers.orchestration.instances import BASE_URL, INSTANCES_API_VERSION, QUALIFIED_RESOURCE_TYPE

from ...generators import generate_random_string, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()


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
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/{QUALIFIED_RESOURCE_TYPE}/{name}",
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


@responses.activate
def test_instance_show(mocked_cmd):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    responses.add(
        method=responses.GET,
        url=f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}/"
        f"providers/{QUALIFIED_RESOURCE_TYPE}/{instance_name}?api-version={INSTANCES_API_VERSION}",
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.providers.orchestration.instances import Instances

    instances = Instances(mocked_cmd)
    result = instances.show(name=instance_name, resource_group_name=resource_group_name)
    assert result == mock_instance_record


@pytest.mark.parametrize(
    "resource_group_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "records",
    [0, 2],
)
@responses.activate
def test_instance_list(mocked_cmd, resource_group_name: str, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    # If no resource_group_name, oh well
    mock_instance_records = {
        "value": [
            get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
            for _ in range(records)
        ]
    }

    expected_list_url = f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}"
    if resource_group_name:
        expected_list_url += f"/resourceGroups/{resource_group_name}"
    expected_list_url += f"/providers/{QUALIFIED_RESOURCE_TYPE}?api-version={INSTANCES_API_VERSION}"

    responses.add(
        method=responses.GET,
        url=expected_list_url,
        json=mock_instance_records,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.providers.orchestration.instances import Instances

    instances = Instances(mocked_cmd)
    result = instances.list(resource_group_name=resource_group_name)
    assert result == mock_instance_records["value"]
