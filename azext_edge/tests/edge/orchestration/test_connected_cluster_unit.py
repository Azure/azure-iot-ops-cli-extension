# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

from ...generators import generate_random_string, get_zeroed_subscription


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
    assert resource_id == (
        f"/subscriptions/{sub}/resourceGroups/{rg_name}"
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
    )

    target_namespace = generate_random_string()
    connected_cluster.get_custom_location_for_namespace(namespace=target_namespace)

    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where properties.hostResourceId =~ '{connected_cluster.resource_id}'
        | where properties.namespace =~ '{target_namespace}'
        | project id, name, location, properties, apiVersion
        """
    )

    connected_cluster.get_aio_extensions()
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        kubernetesconfigurationresources
        | where type =~ 'microsoft.kubernetesconfiguration/extensions'
        | where id startswith '{connected_cluster.resource_id}'
        | where properties.ExtensionType startswith 'microsoft.iotoperations'
            or properties.ExtensionType =~ 'microsoft.deviceregistry.assets'
            or properties.ExtensionType =~ 'microsoft.azurekeyvaultsecretsprovider'
        | project id, name, apiVersion
        """
    )

    connected_cluster.get_aio_custom_locations()
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
    connected_cluster.get_aio_resources(custom_location_id=target_custom_location)
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where extendedLocation.name =~ '{target_custom_location}'
        | where type startswith 'microsoft.iotoperations'
            or type startswith 'microsoft.deviceregistry'
        | project id, name, apiVersion
        """
    )

    connected_cluster.get_resource_sync_rules(custom_location_id=target_custom_location)
    mocked_resource_graph.return_value.query_resources.assert_called_with(
        query=f"""
        resources
        | where type =~ "microsoft.extendedlocation/customlocations/resourcesyncrules"
        | where id startswith '{target_custom_location}'
        | project id, name, apiVersion
        """
    )
