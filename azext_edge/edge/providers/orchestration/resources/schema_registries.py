# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional
from azure.cli.core.azclierror import ValidationError
from uuid import uuid4

from knack.log import get_logger
from rich.prompt import Confirm

from ....util.az_client import (
    get_registry_mgmt_client,
    get_storage_mgmt_client,
    get_authz_client,
    wait_for_terminal_state,
    parse_resource_id,
)
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt.operations import (
        SchemaRegistriesOperations,
    )

STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_ID = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_DEF = (
    f"/providers/Microsoft.Authorization/roleDefinitions/{STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_ID}"
)


class SchemaRegistries(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.registry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.authz_client = get_authz_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "SchemaRegistriesOperations" = self.registry_mgmt_client.schema_registries

    def create(
        self,
        name: str,
        resource_group_name: str,
        namespace: str,
        storage_account_resource_id: str,
        storage_container_name: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        display_name: Optional[str] = None,
        tags: Optional[str] = None,
        **kwargs,
    ) -> dict:
        if not location:
            location = self.get_resource_group(name=resource_group_name)["location"]

        storage_id_container = parse_resource_id(storage_account_resource_id)

        self.storage_mgmt_client = get_storage_mgmt_client(
            subscription_id=storage_id_container.subscription_id,
        )
        storage_properties: dict = self.storage_mgmt_client.storage_accounts.get_properties(
            resource_group_name=storage_id_container.resource_group_name,
            account_name=storage_id_container.resource_name,
        ).as_dict()
        is_hns_enabled = storage_properties.get("is_hns_enabled", False)
        if not is_hns_enabled:
            raise ValidationError(
                "Schema registry requires the storage account to have hierarchical namespace enabled."
            )

        blob_container = self.storage_mgmt_client.blob_containers.get(
            resource_group_name=storage_id_container.resource_group_name,
            account_name=storage_id_container.resource_name,
            container_name=storage_container_name,
        ).as_dict()
        blob_container_url = f"{storage_properties['primary_endpoints']['blob']}{blob_container['name']}"

        resource = {
            "location": location,
            "identity": {
                "type": "SystemAssigned",
            },
            "properties": {
                "namespace": namespace,
                "storageAccountContainerUrl": blob_container_url,
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
            result = wait_for_terminal_state(poller, **kwargs)

            role_assignments_iter = self.authz_client.role_assignments.list_for_scope(
                scope=storage_properties["id"], filter=f"principalId eq '{result['identity']['principalId']}'"
            )
            for role_assignment in role_assignments_iter:
                role_assignment_dict = role_assignment.as_dict()
                if (
                    role_assignment_dict["role_definition_id"]
                    == f"/subscriptions/{storage_id_container.subscription_id}{STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_DEF}"
                ):
                    return result

            self.authz_client.role_assignments.create(
                scope=storage_properties["id"],
                role_assignment_name=str(uuid4()),
                parameters={
                    "role_definition_id": STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_DEF,
                    "principal_id": result["identity"]["principalId"],
                },
            )

            return result

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
