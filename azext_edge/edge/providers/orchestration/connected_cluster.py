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
            or properties.ExtensionType =~ 'microsoft.azure.secretstore'
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
            or type startswith 'microsoft.secretsync'
        | project id, name, apiVersion, type
        """,
    "get_cl_resources_by_type": """
        resources
        | where extendedLocation.name =~ '{custom_location_id}'
        {where_clauses}
        | project id, name, apiVersion, location, type, resourceGroup{projections}
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
        self._resource_state = None

        # TODO - @digimaun - temp necessary due to circular import
        from ..orchestration.resources import ConnectedClusters

        self.clusters = ConnectedClusters(cmd, subscription_id)

    @property
    def resource_id(self) -> str:
        return self.resource["id"]

    @property
    def resource(self) -> dict:
        if not self._resource_state:
            self._resource_state = self.clusters.show(
                resource_group_name=self.resource_group_name, cluster_name=self.cluster_name
            )
        return self._resource_state

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

    def get_cl_resources_by_type(
        self, custom_location_id: str, resource_types: Optional[set[str]] = None, show_properties: bool = False
    ) -> dict[str, list[dict]]:
        where_clauses = ""
        projections = ""
        if resource_types:
            where_clauses = "| where type in ({})".format(", ".join(f"'{rt}'" for rt in resource_types))
        if show_properties:
            projections = ", properties, systemData, tags"
        query = QUERIES["get_cl_resources_by_type"].format(
            custom_location_id=custom_location_id, where_clauses=where_clauses, projections=projections
        )

        result_by_type: dict[str, list[dict]] = {}
        result = self.resource_graph.query_resources(query=query)
        processed = self._process_query_result(result)
        if processed:
            for p in processed:
                resource_type = p.get("type", "").lower()
                if resource_type and resource_type not in result_by_type:
                    result_by_type[resource_type] = []
                result_by_type[resource_type].append(p)
        return result_by_type

    def get_resource_sync_rules(self, custom_location_id: str) -> Optional[List[dict]]:
        query = QUERIES["get_resource_sync_rules"].format(custom_location_id=custom_location_id)

        result = self.resource_graph.query_resources(query=query)
        return self._process_query_result(result)

    def update_aio_extension(self, extension_name: str, properties: dict) -> dict:
        update_payload = {"properties": properties}
        return self.clusters.extensions.update_cluster_extension(
            resource_group_name=self.resource_group_name,
            cluster_name=self.cluster_name,
            extension_name=extension_name,
            update_payload=update_payload,
        )

    def _process_query_result(self, result: dict, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        if "data" in result and result["data"]:
            if first:
                return result["data"][0]
            return result["data"]
