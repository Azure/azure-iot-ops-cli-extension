# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import responses
from ....generators import generate_random_string, BASE_URL, generate_resource_id


@pytest.fixture()
def mocked_logger(mocker):
    yield mocker.patch("azext_edge.edge.providers.rpsaas.adr2.helpers.logger", autospec=True)


@pytest.mark.parametrize("connected", [True, False])
def test_check_cluster_connectivity(mocked_cmd, mocked_logger, mocked_responses: responses, connected: bool):
    from azext_edge.edge.providers.rpsaas.adr2.helpers import check_cluster_connectivity
    # base resource - should be ok if it is not an instance object
    resource = {
        "extendedLocation": {
            "name": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider=generate_random_string(),
                resource_path=f"/{generate_random_string()}"
            )
        }
    }
    # the custom location
    cl_resource = {
        "properties": {
            "hostResourceId": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider="Microsoft.Kubernetes/connectedClusters",
                resource_path=f"/{generate_random_string()}"
            )
        }
    }
    # get custom location (from base resource)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{resource['extendedLocation']['name']}",
        json=cl_resource,
        status=200,
        content_type="application/json",
    )
    # get cluster (from custom location)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{cl_resource['properties']['hostResourceId']}",
        json={"properties": {"connectivityStatus": "connected" if connected else "offline"}},
        status=200,
        content_type="application/json",
    )
    check_cluster_connectivity(cmd=mocked_cmd, resource=resource)

    assert mocked_logger.warning.called is not connected


@pytest.mark.parametrize("connected", [True, False])
@pytest.mark.parametrize("subscription", [None, generate_random_string()])
def test_get_extended_location(
    mocked_cmd, mocked_logger, mocked_responses: responses, connected: bool, subscription: str
):
    from azext_edge.edge.providers.rpsaas.adr2.helpers import get_extended_location
    name = generate_random_string()
    resource_group = generate_random_string()
    location = generate_random_string()
    # base resource - should be ok if it is not an instance object
    resource = {
        "extendedLocation": {
            "name": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider=generate_random_string(),
                resource_path=f"/{generate_random_string()}"
            )
        },
        "id": generate_resource_id(
            resource_group_name=resource_group,
            resource_provider="Microsoft.IoTOperations/instances",
            resource_path=f"/{name}"
        )
    }
    # the custom location
    cl_resource = {
        "properties": {
            "hostResourceId": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider="Microsoft.Kubernetes/connectedClusters",
                resource_path=f"/{generate_random_string()}"
            )
        }
    }
    # get instance
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{resource['id']}",
        json=resource,
        status=200,
        content_type="application/json",
    )
    # get custom location (from base resource)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{resource['extendedLocation']['name']}",
        json=cl_resource,
        status=200,
        content_type="application/json",
    )
    # get cluster (from custom location)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{cl_resource['properties']['hostResourceId']}",
        json={
            "location": location,
            "properties": {"connectivityStatus": "connected" if connected else "offline"}
        },
        status=200,
        content_type="application/json",
    )
    result = get_extended_location(
        cmd=mocked_cmd,
        instance_name=name,
        instance_resource_group=resource_group,
        instance_subscription=subscription
    )

    assert result["type"] == "CustomLocation"
    assert result["name"] == resource['extendedLocation']['name']
    assert result["cluster_location"] == location
    assert mocked_logger.warning.called is not connected
