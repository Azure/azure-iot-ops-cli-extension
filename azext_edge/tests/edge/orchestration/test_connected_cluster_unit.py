# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional, Type, Union
from unittest.mock import Mock

import pytest

from ...generators import generate_random_string, get_zeroed_subscription


@pytest.fixture
def mocked_connected_clusters(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.resources.ConnectedClusters", autospec=True)
    yield patched


@pytest.mark.parametrize(
    "expected_query_result",
    [
        {"data": []},
        {
            "data": [
                {
                    "id": generate_random_string(),
                    "name": generate_random_string(),
                }
            ]
        },
    ],
)
def test_connected_cluster_queries(
    mocker,
    mocked_cmd: Mock,
    mocked_resource_graph: Mock,
    mocked_connected_clusters: Mock,
    expected_query_result: dict,
):
    def _assert_query_result(
        result: Optional[Union[dict, List[dict]]], expected_type: Union[Type[dict], Type[list]] = list
    ):
        if expected_query_result["data"]:
            assert result
            assert isinstance(result, expected_type)
        else:
            assert result is None

    from azext_edge.edge.providers.orchestration.connected_cluster import (
        ConnectedCluster,
    )

    sub = get_zeroed_subscription()
    cluster_name = generate_random_string()
    rg_name = generate_random_string()

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd, subscription_id=sub, cluster_name=cluster_name, resource_group_name=rg_name
    )
    mocked_resource_graph.return_value.query_resources.return_value = expected_query_result

    target_namespace = generate_random_string()
    _assert_query_result(
        connected_cluster.get_custom_location_for_namespace(namespace=target_namespace), expected_type=dict
    )
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where properties.hostResourceId =~ '{connected_cluster.resource_id}'
        | where properties.namespace =~ '{target_namespace}'
        | project id, name, location, properties, apiVersion
        """
    )

    _assert_query_result(connected_cluster.get_aio_extensions())
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        kubernetesconfigurationresources
        | where type =~ 'microsoft.kubernetesconfiguration/extensions'
        | where id startswith '{connected_cluster.resource_id}'
        | where properties.ExtensionType startswith 'microsoft.iotoperations'
            or properties.ExtensionType =~ 'microsoft.deviceregistry.assets'
            or properties.ExtensionType =~ 'microsoft.azurekeyvaultsecretsprovider'
            or properties.ExtensionType =~ 'microsoft.azure.secretstore'
            or properties.ExtensionType =~ 'microsoft.openservicemesh'
            or properties.ExtensionType =~ 'microsoft.arc.containerstorage'
        | project id, name, apiVersion
        """
    )

    _assert_query_result(connected_cluster.get_aio_custom_locations())
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where properties.hostResourceId =~ '{connected_cluster.resource_id}'
        | extend clusterExtensionIds=properties.clusterExtensionIds
        | mv-expand clusterExtensionIds
        | extend clusterExtensionId = tolower(clusterExtensionIds)
        | join kind=inner(
            extendedlocationresources
            | where type =~ 'microsoft.extendedlocation/customLocations/enabledResourcetypes'
            | project clusterExtensionId = tolower(properties.clusterExtensionId),
                extensionType = tolower(properties.extensionType)
            | where extensionType startswith 'microsoft.iotoperations'
                or extensionType startswith 'microsoft.deviceregistry'
        ) on clusterExtensionId
        | distinct id, name, apiVersion
        """
    )

    target_custom_location = generate_random_string()
    _assert_query_result(connected_cluster.get_aio_resources(custom_location_id=target_custom_location))
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where extendedLocation.name =~ '{target_custom_location}'
        | where type startswith 'microsoft.iotoperations'
            or type startswith 'microsoft.deviceregistry'
        | project id, name, apiVersion
        """
    )

    _assert_query_result(connected_cluster.get_resource_sync_rules(custom_location_id=target_custom_location))
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where type =~ "microsoft.extendedlocation/customlocations/resourcesyncrules"
        | where id startswith '{target_custom_location}'
        | project id, name, apiVersion
        """
    )


def get_connected_cluster_payload(connectivityStatus: str = "Connected") -> dict:
    return {
        "location": generate_random_string(),
        "id": "/resource/id",
        "properties": {"connectivityStatus": connectivityStatus},
    }


@pytest.mark.parametrize(
    "expected_resource_state",
    [get_connected_cluster_payload(), get_connected_cluster_payload("Disconnected")],
)
def test_connected_cluster_attr(
    mocker,
    mocked_cmd: Mock,
    mocked_resource_graph: Mock,
    mocked_connected_clusters: Mock,
    expected_resource_state: dict,
):
    from azext_edge.edge.providers.orchestration.connected_cluster import (
        ConnectedCluster,
    )

    sub = get_zeroed_subscription()
    cluster_name = generate_random_string()
    rg_name = generate_random_string()

    mocked_connected_clusters(mocked_cmd).show.return_value = expected_resource_state
    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd, subscription_id=sub, cluster_name=cluster_name, resource_group_name=rg_name
    )

    assert connected_cluster.subscription_id == sub
    assert connected_cluster.cluster_name == cluster_name
    assert connected_cluster.resource_group_name == rg_name

    assert connected_cluster.resource == expected_resource_state
    assert connected_cluster.resource_id == expected_resource_state["id"]
    assert connected_cluster.location == expected_resource_state["location"]

    assert connected_cluster.connected is (
        "properties" in expected_resource_state
        and "connectivityStatus" in expected_resource_state["properties"]
        and expected_resource_state["properties"]["connectivityStatus"].lower() == "connected"
    )
