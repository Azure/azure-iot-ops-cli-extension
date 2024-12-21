# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_edge import list_instances, show_instance, update_instance
from azext_edge.edge.providers.orchestration.resources import Instances

from ....generators import generate_random_string
from .conftest import (
    BASE_URL,
    CUSTOM_LOCATIONS_API_VERSION,
    get_base_endpoint,
    get_mock_resource,
    get_resource_id,
)

CUSTOM_LOCATION_RP = "Microsoft.ExtendedLocation"
CONNECTED_CLUSTER_RP = "Microsoft.Kubernetes"


def get_instance_endpoint(resource_group_name: Optional[str] = None, instance_name: Optional[str] = None) -> str:
    resource_path = "/instances"
    if instance_name:
        resource_path += f"/{instance_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_cl_endpoint(resource_group_name: Optional[str] = None, cl_name: Optional[str] = None) -> str:
    resource_path = "/customLocations"
    if cl_name:
        resource_path += f"/{cl_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=CUSTOM_LOCATION_RP,
        api_version=CUSTOM_LOCATIONS_API_VERSION,
    )


def get_mock_instance_record(name: str, resource_group_name: str) -> dict:
    return get_mock_resource(
        name=name,
        properties={"description": "AIO Instance description.", "provisioningState": "Succeeded"},
        resource_group_name=resource_group_name,
    )


def get_mock_cl_record(name: str, resource_group_name: str) -> dict:
    resource = get_mock_resource(
        name=name,
        properties={
            "hostResourceId": get_resource_id(
                resource_path="/connectedClusters/mycluster",
                resource_group_name=resource_group_name,
                resource_provider=CONNECTED_CLUSTER_RP,
            ),
            "namespace": "azure-iot-operations",
            "displayName": generate_random_string(),
            "provisioningState": "Succeeded",
            "clusterExtensionIds": [
                generate_random_string(),
                generate_random_string(),
            ],
            "authentication": {},
        },
        resource_group_name=resource_group_name,
    )
    resource.pop("extendedLocation")
    resource.pop("systemData")
    resource.pop("resourceGroup")
    return resource


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

    result = show_instance(cmd=mocked_cmd, instance_name=instance_name, resource_group_name=resource_group_name)

    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 1


def test_instance_get_resource_map(mocker, mocked_cmd, mocked_responses: responses):
    cl_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mock_cl_record = get_mock_cl_record(name=cl_name, resource_group_name=resource_group_name)

    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{mock_instance_record['extendedLocation']['name']}",
        json=mock_cl_record,
        status=200,
        content_type="application/json",
    )

    host_resource_id: str = mock_cl_record["properties"]["hostResourceId"]
    host_resource_parts = host_resource_id.split("/")

    instances = Instances(mocked_cmd)
    resource_map = instances.get_resource_map(mock_instance_record)
    assert resource_map.subscription_id == host_resource_parts[2]

    assert resource_map.connected_cluster.subscription_id == host_resource_parts[2]
    assert resource_map.connected_cluster.resource_group_name == host_resource_parts[4]
    assert resource_map.connected_cluster.cluster_name == host_resource_parts[-1]
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
    # If no resource_group_name, oh well
    mock_instance_records = {
        "value": [
            get_mock_instance_record(name=generate_random_string(), resource_group_name=resource_group_name)
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

    result = list(list_instances(cmd=mocked_cmd, resource_group_name=resource_group_name))

    assert result == mock_instance_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "description",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "tags",
    [None, {"a": "b", "c": "d"}, {}],
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

    result = update_instance(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        instance_description=description,
        wait_sec=0,
    )
    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 2

    update_request = json.loads(mocked_responses.calls[1].request.body)
    if description:
        assert update_request["properties"]["description"] == description

    if tags or tags == {}:
        assert update_request["tags"] == tags

    if not any([description, tags or tags == {}]):
        assert update_request == mock_instance_record
