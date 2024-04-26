# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from ...generators import generate_random_string, get_zeroed_subscription


@pytest.fixture
def mocked_resource_graph(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.connected_cluster.ResourceGraph", autospec=True)
    yield patched


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.connected_cluster.get_resource_client", autospec=True
    )
    yield patched


def test_connected_cluster_operations(
    mocker, mocked_cmd: Mock, mocked_resource_graph: Mock, mocked_get_resource_client: Mock
):
    from azext_edge.edge.providers.orchestration.connected_cluster import (
        ConnectedCluster,
    )

    sub = get_zeroed_subscription()
    cluster_name = generate_random_string()
    rg_name = generate_random_string()

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd, subscription_id=sub, cluster_name=cluster_name, resource_group_name=rg_name
    )

    resource_id = connected_cluster.resource_id
    assert (
        resource_id
        == f"/subscriptions/{sub}/resourceGroups/{rg_name}/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
    )

    target_namespace = generate_random_string()
    connected_cluster.get_custom_location_for_namespace(namespace=target_namespace)

    mocked_resource_graph.return_value.query_resources.assert_called_once_with(
        query=f"""
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where properties.hostResourceId =~ '{connected_cluster.resource_id}'
        | where properties.namespace =~ '{target_namespace}'
        | project id, name, location, properties, apiVersion
        """
    )
