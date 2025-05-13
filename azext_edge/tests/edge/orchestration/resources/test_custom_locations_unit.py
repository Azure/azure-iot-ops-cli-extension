# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional, List

import pytest
import responses

from azext_edge.edge.providers.orchestration.resources.custom_locations import CustomLocations

from ....generators import generate_random_string
from .conftest import (
    ZEROED_SUBSCRIPTION,
    get_base_endpoint,
    get_mock_resource,
)

CUSTOM_LOCATION_RP = "Microsoft.ExtendedLocation"
CUSTOM_LOCATION_RP_API_VERSION = "2021-08-31-preview"


def get_custom_location_endpoint(
    resource_group_name: Optional[str] = None, custom_location_name: Optional[str] = None
) -> str:
    resource_path = "/customLocations"
    if custom_location_name:
        resource_path += f"/{custom_location_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=CUSTOM_LOCATION_RP,
        api_version=CUSTOM_LOCATION_RP_API_VERSION,
    )


def get_mock_custom_location_record(
    name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    cluster_name: Optional[str] = None,
    namespace: Optional[str] = None,
    ops_extension_name: str = "azure-iot-operations",
) -> dict:
    record = get_mock_resource(
        name=name,
        resource_provider=CUSTOM_LOCATION_RP,
        resource_path=f"/customLocations/{name}",
        location=location,
        properties={
            "hostResourceId": (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name or 'mycluster'}"
            ),
            "namespace": namespace or "azure-iot-operations",
            "displayName": "location-cbe85",
            "provisioningState": "Succeeded",
            "clusterExtensionIds": [
                (
                    f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
                    "/providers/Microsoft.Kubernetes/connectedClusters/mycluster/providers"
                    "/Microsoft.KubernetesConfiguration/extensions/azure-iot-operations-platform"
                ),
                (
                    f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
                    "/providers/Microsoft.Kubernetes/connectedClusters/mycluster/providers"
                    "/Microsoft.KubernetesConfiguration/extensions/azure-secret-store"
                ),
                (
                    f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
                    "/providers/Microsoft.Kubernetes/connectedClusters/mycluster/providers"
                    f"/Microsoft.KubernetesConfiguration/extensions/{ops_extension_name}"
                ),
            ],
            "authentication": {},
        },
        resource_group_name=resource_group_name,
        qualified_type=f"{CUSTOM_LOCATION_RP}/customLocations",
    )
    record.pop("extendedLocation")
    return record


def test_custom_locations_show(mocked_cmd, mocked_responses: responses):
    cl_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_cl_record = get_mock_custom_location_record(resource_group_name=resource_group_name, name=cl_name)
    mocked_responses.add(
        method=responses.GET,
        url=get_custom_location_endpoint(resource_group_name=resource_group_name, custom_location_name=cl_name),
        json=mock_cl_record,
        status=200,
        content_type="application/json",
    )

    custom_locations = CustomLocations(mocked_cmd)
    result = custom_locations.show(name=cl_name, resource_group_name=resource_group_name)

    assert result == mock_cl_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "tags",
    [None, {"a": "b", "c": "d"}],
)
@pytest.mark.parametrize(
    "display_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "cluster_extension_ids",
    [[generate_random_string()], [generate_random_string(), generate_random_string()]],
)
def test_custom_locations_create(
    mocked_cmd,
    mocked_responses: responses,
    cluster_extension_ids: List[str],
    display_name: Optional[str],
    tags: Optional[dict],
):
    cl_name = generate_random_string()
    resource_group_name = generate_random_string()
    host_resource_id = generate_random_string()
    namespace = generate_random_string()
    location = generate_random_string()

    create_cl_kwargs = {
        "name": cl_name,
        "resource_group_name": resource_group_name,
        "host_resource_id": host_resource_id,
        "namespace": namespace,
        "cluster_extension_ids": cluster_extension_ids,
        "location": location,
        "display_name": display_name,
        "tags": tags,
        "wait_sec": 0,
    }

    cl_create_endpoint = get_custom_location_endpoint(
        resource_group_name=resource_group_name, custom_location_name=cl_name
    )
    mock_cl_record = get_mock_custom_location_record(resource_group_name=resource_group_name, name=cl_name)
    create_response = mocked_responses.add(
        method=responses.PUT,
        url=cl_create_endpoint,
        json=mock_cl_record,
        status=200,
    )

    custom_locations = CustomLocations(mocked_cmd)
    result = custom_locations.create(**create_cl_kwargs)
    assert result == mock_cl_record

    request_body = json.loads(create_response.calls[0].request.body)

    assert request_body["location"] == location
    assert request_body["properties"]["hostResourceId"] == host_resource_id
    assert request_body["properties"]["clusterExtensionIds"] == cluster_extension_ids
    assert request_body["properties"]["namespace"] == namespace

    if display_name:
        assert request_body["properties"]["displayName"] == display_name

    if tags:
        assert request_body["tags"] == tags
