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
    display_name: str
    api_version: str


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
        if "extensions" in self._resource_map and self._resource_map["extensions"]:
            for ext in self._resource_map["extensions"]:
                result.append(
                    IoTOperationsResource(
                        resource_id=ext["id"], display_name=ext["name"], api_version=ext["apiVersion"]
                    )
                )
        return result

    @property
    def custom_locations(self) -> List[IoTOperationsResource]:
        result = []
        if "customLocations" in self._resource_map and self._resource_map["customLocations"]:
            for cl_id in self._resource_map["customLocations"]:
                result.append(
                    IoTOperationsResource(
                        resource_id=cl_id,
                        display_name=self._resource_map["customLocations"][cl_id]["name"],
                        api_version=self._resource_map["customLocations"][cl_id]["apiVersion"],
                    )
                )
        return result

    def get_resource_sync_rules(self, custom_location_id: str) -> List[IoTOperationsResource]:
        result = []
        if (
            "customLocations" in self._resource_map
            and self._resource_map["customLocations"]
            and custom_location_id in self._resource_map["customLocations"]
            and self._resource_map["customLocations"][custom_location_id]
            and "resourceSyncRules" in self._resource_map["customLocations"][custom_location_id]
            and self._resource_map["customLocations"][custom_location_id]["resourceSyncRules"]
        ):
            for rsr in self._resource_map["customLocations"][custom_location_id]["resourceSyncRules"]:
                result.append(
                    IoTOperationsResource(
                        resource_id=rsr["id"], display_name=rsr["name"], api_version=rsr["apiVersion"]
                    )
                )
        return result

    def get_resources(self, custom_location_id: str) -> List[IoTOperationsResource]:
        result = []
        if (
            "customLocations" in self._resource_map
            and self._resource_map["customLocations"]
            and custom_location_id in self._resource_map["customLocations"]
            and self._resource_map["customLocations"][custom_location_id]
            and "resources" in self._resource_map["customLocations"][custom_location_id]
            and self._resource_map["customLocations"][custom_location_id]["resources"]
        ):
            sorted_resources = sorted(
                self._resource_map["customLocations"][custom_location_id]["resources"],
                key=lambda r: (len(r["id"].split("/")), r["name"].lower()),
                reverse=True,
            )
            for resource in sorted_resources:
                result.append(
                    IoTOperationsResource(
                        resource_id=resource["id"], display_name=resource["name"], api_version=resource["apiVersion"]
                    )
                )

        return result

    def refresh_related_resource_ids(
        self,
    ) -> Dict[str, Union[List[Dict[str, str]], Dict[str, Dict[str, Union[List[Dict[str, str]], str]]]]]:
        result = {}
        extensions = self.connected_cluster.get_aio_extensions()

        if extensions:
            result["extensions"] = []
            for ext in extensions:
                ext_map = {"id": ext["id"], "name": ext["name"], "apiVersion": ext["apiVersion"]}
                result["extensions"].append(ext_map)

        custom_locations = self.connected_cluster.get_aio_custom_locations()
        if custom_locations:
            result["customLocations"] = {}
            for cl in custom_locations:
                result["customLocations"][cl["id"]] = {"name": cl["name"], "apiVersion": cl["apiVersion"]}

                cl_sync_rules = self.connected_cluster.get_resource_sync_rules(cl["id"])
                if cl_sync_rules:
                    result["customLocations"][cl["id"]]["resourceSyncRules"] = []
                    for sync_rule in cl_sync_rules:
                        sync_rule_map = {
                            "id": sync_rule["id"],
                            "name": sync_rule["name"],
                            "apiVersion": sync_rule["apiVersion"],
                        }
                        result["customLocations"][cl["id"]]["resourceSyncRules"].append(sync_rule_map)

                cl_resources = self.connected_cluster.get_aio_resources(cl["id"])
                if cl_resources:
                    result["customLocations"][cl["id"]]["resources"] = []
                    for resource in cl_resources:
                        res_map = {
                            "id": resource["id"],
                            "name": resource["name"],
                            "apiVersion": resource["apiVersion"],
                        }
                        result["customLocations"][cl["id"]]["resources"].append(res_map)

        return result

    def build_tree(self):
        tree = Tree(f"[green]{self.cluster_name}[/green]")
        extensions_node = tree.add(label="[cyan]extensions[/cyan]")
        [extensions_node.add(ext.display_name) for ext in self.extensions]

        custom_locations = self.custom_locations
        if custom_locations:
            root_cl_node = tree.add(label="[cyan]customLocations[/cyan]")
            for cl in custom_locations:
                cl_node = root_cl_node.add(cl.display_name)
                resource_sync_rules = self.get_resource_sync_rules(cl.resource_id)
                if resource_sync_rules:
                    rsr_node = cl_node.add("[cyan]resourceSyncRules[/cyan]")
                    [rsr_node.add(rsr.display_name) for rsr in resource_sync_rules]

                cl_resources = self.get_resources(cl.resource_id)
                if cl_resources:
                    resource_node = cl_node.add("[cyan]resources[/cyan]")
                    [resource_node.add(resource.display_name) for resource in cl_resources]

        return tree
