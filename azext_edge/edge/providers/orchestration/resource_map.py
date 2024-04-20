# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, NamedTuple, Union

from rich.tree import Tree

from .connected_cluster import ConnectedCluster


class IoTOperationsResource(NamedTuple):
    resource_id: str
    display_id: str


class IoTOperationsResourceMap:
    def __init__(self, cmd, cluster_name: str, resource_group_name: str):
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
        self.base_id_prefix = f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group_name}/providers"
        self._resource_map = self.refresh_related_resource_ids()

    @property
    def extensions(self) -> List[IoTOperationsResource]:
        result = []
        filter_prefix = (
            f"{self.base_id_prefix}/Microsoft.Kubernetes/ConnectedClusters/{self.cluster_name}"
            "/providers/Microsoft.KubernetesConfiguration/Extensions/"
        ).lower()
        if "extensions" in self._resource_map and self._resource_map["extensions"]:
            for ext_id in self._resource_map["extensions"]:
                result.append(
                    IoTOperationsResource(resource_id=ext_id, display_id=ext_id.lower().split(filter_prefix)[-1])
                )
        return result

    @property
    def custom_locations(self) -> List[IoTOperationsResource]:
        result = []
        filter_prefix = f"{self.base_id_prefix}/Microsoft.ExtendedLocation/customLocations/".lower()
        if "customLocations" in self._resource_map and self._resource_map["customLocations"]:
            for cl_id in self._resource_map["customLocations"]:
                result.append(
                    IoTOperationsResource(resource_id=cl_id, display_id=cl_id.lower().split(filter_prefix)[-1])
                )
        return result

    def get_resource_sync_rules(self, custom_location_id: str) -> List[IoTOperationsResource]:
        result = []
        filter_prefix = f"{custom_location_id}/resourceSyncRules/".lower()

        if (
            "customLocations" in self._resource_map
            and self._resource_map["customLocations"]
            and custom_location_id in self._resource_map["customLocations"]
            and self._resource_map["customLocations"][custom_location_id]
            and "resourceSyncRules" in self._resource_map["customLocations"][custom_location_id]
            and self._resource_map["customLocations"][custom_location_id]["resourceSyncRules"]
        ):
            for rsr_id in self._resource_map["customLocations"][custom_location_id]["resourceSyncRules"]:
                result.append(
                    IoTOperationsResource(resource_id=rsr_id, display_id=rsr_id.lower().split(filter_prefix)[-1])
                )
        return result

    def refresh_related_resource_ids(self) -> Dict[str, Union[List[str], Dict[str, List[str]]]]:
        result = {}
        extensions = self.connected_cluster.get_aio_extensions()
        if extensions:
            result["extensions"] = [ext["id"] for ext in extensions]
        custom_locations = self.connected_cluster.get_aio_custom_locations()
        if custom_locations:
            result["customLocations"] = {}
            custom_location_ids = [cl["id"] for cl in custom_locations]
            for cl_id in custom_location_ids:
                result["customLocations"][cl_id] = {}
                cl_sync_rules = self.connected_cluster.get_resource_sync_rules(cl_id)
                if cl_sync_rules:
                    result["customLocations"][cl_id]["resourceSyncRules"] = [
                        cl_sync["id"] for cl_sync in cl_sync_rules
                    ]

                cl_resources = self.connected_cluster.get_aio_resources(cl_id)
                if cl_resources:
                    result["customLocations"][cl_id]["resources"] = [cl_r["id"] for cl_r in cl_resources]

        return result

    def build_tree(self):
        tree = Tree(f"[green]{self.cluster_name}[/green]")
        extensions_node = tree.add(label="[cyan]extensions[/cyan]")
        [extensions_node.add(ext.display_id) for ext in self.extensions]

        custom_locations = self.custom_locations
        if custom_locations:
            root_cl_node = tree.add(label="[cyan]customLocations[/cyan]")
            #import pdb; pdb.set_trace()
            for cl in custom_locations:
                cl_node = root_cl_node.add(cl.display_id)
                resource_sync_rules = self.get_resource_sync_rules(cl.resource_id)
                if resource_sync_rules:
                    rsr_node = cl_node.add("[cyan]resourceSyncRules[/cyan]")
                    [rsr_node.add(rsr.display_id) for rsr in resource_sync_rules]

        return tree
