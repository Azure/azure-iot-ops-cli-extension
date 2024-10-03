# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.console import Console

from ....util.az_client import get_registry_mgmt_client
from ....util.common import should_continue_prompt
from ....util.queryable import Queryable
from ..common import SchemaFormat

logger = get_logger(__name__)

console = Console()


if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt.operations import (
        SchemasOperations,
    )


class Schemas(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.registry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "SchemasOperations" = self.registry_mgmt_client.schemas

    def create(
        self,
        name: str,
        schema_registry_name: str,
        resource_group_name: str,
        schema_type: str,
        schema_format: str,
        description: Optional[str] = None,
        display_name: Optional[str] = None,
        tags: Optional[str] = None,
        **kwargs,
    ) -> dict:
        with console.status("Working..."):
            schema_format = SchemaFormat[schema_format].full_value
            resource = {
                "properties": {
                    "format": schema_format,
                    "schemaType": schema_type,
                    "description": description,
                    "displayName": display_name,
                },
            }
            # should this need system identity assigned identiyt?
            # schema type - messageschema . is there planned support for more?
            # format = there are two - is there planned support for more?
            # how can I check things are working correctly?
            if tags:
                resource["tags"] = tags

            return self.ops.create_or_replace(
                resource_group_name=resource_group_name,
                schema_registry_name=schema_registry_name,
                schema_name=name,
                resource=resource
            )

    def show(self, name: str, schema_registry_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            schema_registry_name=schema_registry_name,
            schema_name=name
        )

    def list(self, schema_registry_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_schema_registry(
            resource_group_name=resource_group_name, schema_registry_name=schema_registry_name
        )

    def delete(
        self,
        name: str,
        schema_registry_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            return self.ops.delete(
                resource_group_name=resource_group_name,
                schema_registry_name=schema_registry_name,
                schema_name=name
            )
