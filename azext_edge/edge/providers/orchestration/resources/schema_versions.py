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
        SchemaVersionsOperations,
    )


class SchemaVersions(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.registry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "SchemaVersionsOperations" = self.registry_mgmt_client.schema_versions

    def create(
        self,
        name: str,
        schema_name: str,
        schema_registry_name: str,
        resource_group_name: str,
        schema_content: str,
        description: Optional[str] = None,
        **kwargs,
    ) -> dict:
        with console.status("Working..."):
            # TODO: have the schema_content support files too

            resource = {
                "properties": {
                    "schemaContent": schema_content,
                    "description": description,
                },
            }

            return self.ops.create_or_replace(
                resource_group_name=resource_group_name,
                schema_registry_name=schema_registry_name,
                schema_name=schema_name,
                schema_version_name=name,
                resource=resource
            )

    def show(
        self,
        name: str,
        schema_name: str,
        schema_registry_name: str,
        resource_group_name: str,
    ) -> dict:
        version = self.ops.get(
            resource_group_name=resource_group_name,
            schema_registry_name=schema_registry_name,
            schema_name=schema_name,
            schema_version_name=name,
        )
        # verify version via hash - not sure if necessary
        return version

    def list(self, schema_name: str, schema_registry_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_schema(
            resource_group_name=resource_group_name,
            schema_registry_name=schema_registry_name,
            schema_name=schema_name
        )

    def delete(
        self,
        name: str,
        schema_name: str,
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
                schema_name=schema_name,
                schema_version_name=name,
            )
