# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from knack.log import get_logger
from rich import print
from rich.console import Console

from ...util.az_client import get_iotops_mgmt_client, parse_resource_id, wait_for_terminal_state
from ...util.queryable import Queryable

logger = get_logger(__name__)


QUERIES = {
    "get_cl_from_instance": """
        resources
        | where type =~ 'microsoft.extendedlocation/customlocations'
        | where id =~ '{resource_id}'
        | project id, name, properties
        """
}

INSTANCES_API_VERSION = "2021-10-01-privatepreview"
# TODO temporary
BASE_URL = "https://eastus2euap.management.azure.com"
QUALIFIED_RESOURCE_TYPE = "Private.IoTOperations/instances"


class Instances(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id, endpoint=BASE_URL, api_version=INSTANCES_API_VERSION
        )
        self.console = Console()

    def show(self, name: str, resource_group_name: str, show_tree: Optional[bool] = None) -> Optional[dict]:
        result = self.iotops_mgmt_client.instance.get(instance_name=name, resource_group_name=resource_group_name)

        if show_tree:
            self._show_tree(result)
            return

        return result

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.iotops_mgmt_client.instance.list_by_resource_group(resource_group_name=resource_group_name)

        return self.iotops_mgmt_client.instance.list_by_subscription()

    def _show_tree(self, instance: dict):
        custom_location = self._get_associated_cl(instance)
        resource_id_container = parse_resource_id(custom_location["properties"]["hostResourceId"])

        # Currently resource map will query cluster state upon init
        # therefore we only use it when necessary to save cycles.
        from .resource_map import IoTOperationsResourceMap

        resource_map = IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=resource_id_container.resource_name,
            resource_group_name=resource_id_container.resource_group_name,
        )
        print(resource_map.build_tree(category_color="cyan"))

    def _get_associated_cl(self, instance: dict) -> dict:
        return self.query(
            QUERIES["get_cl_from_instance"].format(resource_id=instance["extendedLocation"]["name"]), first=True
        )

    def update(
        self, name: str, resource_group_name: str, tags: Optional[dict] = None, description: Optional[str] = None
    ) -> dict:
        instance = self.show(name=name, resource_group_name=resource_group_name)

        if description:
            instance["properties"]["description"] = description

        if tags:
            instance["tags"] = tags

        with self.console.status("Working..."):
            poller = self.iotops_mgmt_client.instance.begin_create_or_update(
                instance_name=name, resource_group_name=resource_group_name, resource=instance
            )
            return wait_for_terminal_state(poller)
