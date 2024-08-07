# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from rich.tree import Tree

from .connected_cluster import ConnectedCluster
from knack.log import get_logger

logger = get_logger(__name__)


class IoTOperationsResource:
    def __init__(self, resource_id: str, display_name: str, api_version: str):
        self.resource_id = resource_id
        self.display_name = display_name
        self.api_version = api_version
        self._segments: Optional[int] = None

    @property
    def segments(self) -> int:
        if not self._segments:
            self._segments = len(self.resource_id.split("/"))
        return self._segments


class CustomLocationsContainer:
    def __init__(self, resource: IoTOperationsResource):
        self.resource: IoTOperationsResource = resource
        self.resource_sync_rules: List[IoTOperationsResource] = []
        self.related_resources: List[IoTOperationsResource] = []


class ClusterContainer:
    def __init__(self):
        self.extensions: List[IoTOperationsResource] = []
        self.custom_locations: Dict[str, CustomLocationsContainer] = {}


class IoTOperationsResourceMap:
    def __init__(self, cmd, cluster_name: str, resource_group_name: str, defer_refresh: bool = False):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.subscription_id = get_subscription_id(cli_ctx=cmd.cli_ctx)
        self.connected_cluster = ConnectedCluster(
            cmd=cmd,
            subscription_id=self.subscription_id,
            cluster_name=self.cluster_name,
            resource_group_name=self.resource_group_name,
        )
        self._cluster_container = ClusterContainer()
        if not defer_refresh:
            self.refresh_resource_state()

    @property
    def extensions(self) -> List[IoTOperationsResource]:
        return self._cluster_container.extensions

    @property
    def custom_locations(self) -> List[IoTOperationsResource]:
        if self._cluster_container.custom_locations:
            cl_records = list(self._cluster_container.custom_locations.values())
            return [record.resource for record in cl_records]
        return []

    def get_resource_sync_rules(self, custom_location_id: str) -> List[IoTOperationsResource]:
        if custom_location_id in self._cluster_container.custom_locations:
            return self._cluster_container.custom_locations[custom_location_id].resource_sync_rules
        return []

    def get_resources(self, custom_location_id: str) -> List[IoTOperationsResource]:
        if custom_location_id in self._cluster_container.custom_locations:
            related_resources = self._cluster_container.custom_locations[custom_location_id].related_resources
            return sorted(related_resources, key=lambda r: (r.segments, r.display_name.lower()), reverse=True)
        return []

    def refresh_resource_state(self):
        refreshed_cluster_container = ClusterContainer()

        custom_locations = self.connected_cluster.get_aio_custom_locations()
        if custom_locations:
            for cl in custom_locations:
                cl_container = CustomLocationsContainer(
                    resource=IoTOperationsResource(
                        resource_id=cl["id"], display_name=cl["name"], api_version=cl["apiVersion"]
                    )
                )

                cl_sync_rules = self.connected_cluster.get_resource_sync_rules(cl["id"])
                if cl_sync_rules:
                    for sync_rule in cl_sync_rules:
                        cl_container.resource_sync_rules.append(
                            IoTOperationsResource(
                                resource_id=sync_rule["id"],
                                display_name=sync_rule["name"],
                                api_version=sync_rule["apiVersion"],
                            )
                        )

                cl_resources = self.connected_cluster.get_aio_resources(cl["id"])
                if cl_resources:
                    for resource in cl_resources:
                        cl_container.related_resources.append(
                            IoTOperationsResource(
                                resource_id=resource["id"],
                                display_name=resource["name"],
                                api_version=resource["apiVersion"],
                            )
                        )

                refreshed_cluster_container.custom_locations[cl["id"]] = cl_container

        extensions = self.connected_cluster.get_aio_extensions()
        if extensions:
            for ext in extensions:
                refreshed_cluster_container.extensions.append(
                    IoTOperationsResource(
                        resource_id=ext["id"],
                        display_name=ext["name"],
                        api_version=ext["apiVersion"],
                    )
                )

        self._cluster_container = refreshed_cluster_container

    def build_tree(self, category_color: str = "red") -> Tree:
        tree = Tree(f"[green]{self.cluster_name}")
        extensions_node = tree.add(label=f"[{category_color}]extensions")
        [extensions_node.add(ext.display_name) for ext in self.extensions]

        root_cl_node = tree.add(label=f"[{category_color}]customLocations")
        custom_locations = self.custom_locations
        if custom_locations:
            for cl in custom_locations:
                cl_node = root_cl_node.add(cl.display_name)
                resource_sync_rules = self.get_resource_sync_rules(cl.resource_id)
                rsr_node = cl_node.add(f"[{category_color}]resourceSyncRules")
                if resource_sync_rules:
                    [rsr_node.add(rsr.display_name) for rsr in resource_sync_rules]

                resource_node = cl_node.add(f"[{category_color}]resources")
                cl_resources = self.get_resources(cl.resource_id)
                if cl_resources:
                    [resource_node.add(resource.display_name) for resource in cl_resources]

        return tree
