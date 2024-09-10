# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional, Union, Dict

from ...util.resource_graph import ResourceGraph


QUERIES = {
    "get_custom_location_for_namespace": """
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where properties.hostResourceId =~ '{resource_id}'
        | where properties.namespace =~ '{namespace}'
        | project id, name, location, properties, apiVersion
        """,
    "get_aio_extensions": """
        kubernetesconfigurationresources
        | where type =~ 'microsoft.kubernetesconfiguration/extensions'
        | where id startswith '{resource_id}'
        | where properties.ExtensionType startswith 'microsoft.iotoperations'
            or properties.ExtensionType =~ 'microsoft.deviceregistry.assets'
            or properties.ExtensionType =~ 'microsoft.azurekeyvaultsecretsprovider'
            or properties.ExtensionType =~ 'microsoft.secretsynccontroller'
            or properties.ExtensionType =~ 'microsoft.openservicemesh'
            or properties.ExtensionType =~ 'microsoft.arc.containerstorage'
        | project id, name, apiVersion
        """,
    "get_aio_custom_locations": """
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where properties.hostResourceId =~ '{resource_id}'
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
        """,
    "get_aio_resources": """
        resources
        | where extendedLocation.name =~ '{custom_location_id}'
        | where type startswith 'microsoft.iotoperations'
            or type startswith 'microsoft.deviceregistry'
        | project id, name, apiVersion
        """,
    "get_resource_sync_rules": """
        resources
        | where type =~ "microsoft.extendedlocation/customlocations/resourcesyncrules"
        | where id startswith '{custom_location_id}'
        | project id, name, apiVersion
        """,
}


class ConnectedCluster:
    def __init__(self, cmd, subscription_id: str, cluster_name: str, resource_group_name: str):
        self.subscription_id = subscription_id
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.resource_graph = ResourceGraph(cmd=cmd, subscriptions=[self.subscription_id])

        # TODO - @digimaun - temp necessary due to circular import
        from ..orchestration.resources import ConnectedClusters

        self.clusters = ConnectedClusters(cmd, subscription_id)

    @property
    def resource_id(self) -> str:
        return self.resource["id"]

    @property
    def resource(self) -> dict:
        # TODO: Cache
        return self.clusters.show(resource_group_name=self.resource_group_name, cluster_name=self.cluster_name)

    @property
    def location(self) -> str:
        return self.resource["location"]

    @property
    def connected(self) -> bool:
        properties = self.resource.get("properties", {})
        return "connectivityStatus" in properties and properties["connectivityStatus"].lower() == "connected"

    @property
    def extensions(self) -> List[dict]:
        return list(
            self.clusters.extensions.list(resource_group_name=self.resource_group_name, cluster_name=self.cluster_name)
        )

    def get_extensions_by_type(self, *type_names: str) -> Optional[Dict[str, dict]]:
        extensions = self.extensions
        desired_extension_map = {name.lower(): None for name in type_names}
        for extension in extensions:
            extension_type = extension["properties"].get("extensionType", "").lower()
            if extension_type in desired_extension_map:
                desired_extension_map[extension_type] = extension

        return desired_extension_map

    def get_custom_location_for_namespace(self, namespace: str) -> Optional[dict]:
        query = QUERIES["get_custom_location_for_namespace"].format(resource_id=self.resource_id, namespace=namespace)

        result = self.resource_graph.query_resources(query=query)
        return self._process_query_result(result, first=True)

    def get_aio_extensions(self) -> Optional[List[dict]]:
        query = QUERIES["get_aio_extensions"].format(resource_id=self.resource_id)
        # TODO - @digimaun microsoft.azurekeyvaultsecretsprovider optionality

        result = self.resource_graph.query_resources(query=query)
        return self._process_query_result(result)

    def get_aio_custom_locations(self) -> Optional[List[dict]]:
        query = QUERIES["get_aio_custom_locations"].format(resource_id=self.resource_id)

        result = self.resource_graph.query_resources(query=query)
        return self._process_query_result(result)

    def get_aio_resources(self, custom_location_id: str) -> Optional[List[dict]]:
        query = QUERIES["get_aio_resources"].format(custom_location_id=custom_location_id)

        result = self.resource_graph.query_resources(query=query)
        return self._process_query_result(result)

    def get_resource_sync_rules(self, custom_location_id: str) -> Optional[List[dict]]:
        query = QUERIES["get_resource_sync_rules"].format(custom_location_id=custom_location_id)

        result = self.resource_graph.query_resources(query=query)
        return self._process_query_result(result)

    def _process_query_result(self, result: dict, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        if "data" in result and result["data"]:
            if first:
                return result["data"][0]
            return result["data"]
