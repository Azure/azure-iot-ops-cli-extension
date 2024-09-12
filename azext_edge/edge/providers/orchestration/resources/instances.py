# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional, List

from knack.log import get_logger
from rich import print
from rich.console import Console

from ....util.az_client import (
    get_iotops_mgmt_client,
    parse_resource_id,
    wait_for_terminal_state,
)
from ....util.queryable import Queryable
from ..common import CUSTOM_LOCATIONS_API_VERSION
from ..resource_map import IoTOperationsResourceMap

logger = get_logger(__name__)

console = Console()


class Instances(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )

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
        resource_map = self.get_resource_map(instance)
        with console.status("Working..."):
            resource_map.refresh_resource_state()
        print(resource_map.build_tree(category_color="cyan"))

    def _get_associated_cl(self, instance: dict) -> dict:
        return self.resource_client.resources.get_by_id(
            resource_id=instance["extendedLocation"]["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )

    def get_resource_map(self, instance: dict) -> IoTOperationsResourceMap:
        custom_location = self._get_associated_cl(instance)
        resource_id_container = parse_resource_id(custom_location["properties"]["hostResourceId"])

        return IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=resource_id_container.resource_name,
            resource_group_name=resource_id_container.resource_group_name,
            defer_refresh=True,
        )

    def update(
        self,
        name: str,
        resource_group_name: str,
        tags: Optional[dict] = None,
        description: Optional[str] = None,
        mi_user_assigned_identities: Optional[List[str]] = None,
        **kwargs: dict,
    ) -> dict:
        instance = self.show(name=name, resource_group_name=resource_group_name)

        if description:
            instance["properties"]["description"] = description

        if tags or tags == {}:
            instance["tags"] = tags

        if mi_user_assigned_identities:
            self._handle_mi_user_assigned(instance, mi_user_assigned_identities)

        with console.status("Working..."):
            poller = self.iotops_mgmt_client.instance.begin_create_or_update(
                instance_name=name,
                resource_group_name=resource_group_name,
                resource=instance,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def _handle_mi_user_assigned(self, instance: dict, mi_user_assigned: List[str]):
        """
        Responsible for federating and building the instance identity object.
        """
        resource_map = self.get_resource_map(instance)
        import pdb; pdb.set_trace()
