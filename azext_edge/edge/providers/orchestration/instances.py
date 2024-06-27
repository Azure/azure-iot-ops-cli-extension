# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional

from knack.log import get_logger
from rich import print

from ...util.az_client import AzMicroMgmtClient
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
        self.micro_client = AzMicroMgmtClient(subscription_id=self.default_subscription_id, base_url=BASE_URL)

    def show(self, name: str, resource_group_name: str, show_tree: Optional[bool] = None) -> Optional[dict]:
        result = self.micro_client.get_resource_by_id(
            resource_id=f"/subscriptions/{self.default_subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/{QUALIFIED_RESOURCE_TYPE}/{name}",
            api_version=INSTANCES_API_VERSION,
        )

        if show_tree:
            self._show_tree(result)
            return

        return result

    def list(self, resource_group_name: Optional[str] = None) -> List[dict]:
        return self.micro_client.list_resources(
            qualified_resource_type=QUALIFIED_RESOURCE_TYPE,
            api_version=INSTANCES_API_VERSION,
            resource_group_name=resource_group_name,
        )

    def _show_tree(self, instance: dict):
        custom_location = self._get_associated_cl(instance)
        resource_id_container = self.micro_client.parse_resource_id(custom_location["properties"]["hostResourceId"])

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
