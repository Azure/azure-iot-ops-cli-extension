# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger

from ....util.az_client import get_registry_mgmt_client
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
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

    def show(self, name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, schema_registry_name=name)

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()
