# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.prompt import Confirm

from ....util.az_client import get_registry_mgmt_client, wait_for_terminal_state
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from azure.core.polling import LROPoller

    from ....vendor.clients.deviceregistrymgmt.operations import (
        SchemaRegistriesOperations,
    )


class SchemaRegistries(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.registry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "SchemaRegistriesOperations" = self.registry_mgmt_client.schema_registries

    def create(
        self,
        name: str,
        resource_group_name: str,
        namespace: str,
        storage_container_url: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        display_name: Optional[str] = None,
        tags: Optional[str] = None,
        **kwargs,
    ) -> dict:
        # TODO: @digimaun hierarchy blob

        if not location:
            location = self.get_resource_group(name=resource_group_name)["location"]

        resource = {
            "location": location,
            "identity": {
                "type": "SystemAssigned",
            },
            "properties": {
                "namespace": namespace,
                "storageAccountContainerUrl": storage_container_url,
                "description": description,
                "displayName": display_name,
            },
        }
        if tags:
            resource["tags"] = tags

        with self.console.status("Working..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name=resource_group_name, schema_registry_name=name, resource=resource
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, schema_registry_name=name)

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()

    def delete(self, name: str, resource_group_name: str, confirm_yes: Optional[bool] = None, **kwargs):
        # TODO @digimaun - reuse
        should_delete = True
        if not confirm_yes:
            should_delete = Confirm.ask("Continue?")

        if not should_delete:
            logger.warning("Deletion cancelled.")
            return

        with self.console.status("Working..."):
            poller = self.ops.begin_delete(resource_group_name=resource_group_name, schema_registry_name=name)
            return wait_for_terminal_state(poller, **kwargs)
