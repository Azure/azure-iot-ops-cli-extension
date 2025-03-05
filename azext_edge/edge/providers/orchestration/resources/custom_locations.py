# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Optional, Iterable

from knack.log import get_logger

from ....util.az_client import get_extloc_mgmt_client, wait_for_terminal_state
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.extendedlocmgmt.operations import CustomLocationsOperations


class CustomLocations(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.extloc_mgmt_client = get_extloc_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "CustomLocationsOperations" = self.extloc_mgmt_client.custom_locations

    def show(self, name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, resource_name=name)

    def create(
        self,
        name: str,
        resource_group_name: str,
        host_resource_id: str,
        namespace: str,
        cluster_extension_ids: Iterable[str],
        location: str,
        display_name: Optional[str] = None,
        tags: Optional[dict] = None,
        **kwargs
    ) -> dict:
        properties = {
            "hostResourceId": host_resource_id,
            "namespace": namespace,
            "clusterExtensionIds": list(
                cluster_extension_ids,
            ),
        }

        parameters = {"properties": properties, "location": location}

        if tags:
            parameters["tags"] = tags

        if display_name:
            properties["displayName"] = display_name

        poller = self.ops.begin_create_or_update(
            resource_group_name=resource_group_name,
            resource_name=name,
            parameters=parameters,
        )

        return wait_for_terminal_state(poller, **kwargs)
