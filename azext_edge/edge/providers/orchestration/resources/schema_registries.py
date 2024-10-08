# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console


from ....util.az_client import (
    get_registry_mgmt_client,
    get_storage_mgmt_client,
    parse_resource_id,
    wait_for_terminal_state,
)
from ....util.common import should_continue_prompt
from ....util.queryable import Queryable
from ..permissions import PermissionManager, ROLE_DEF_FORMAT_STR

logger = get_logger(__name__)

console = Console()


if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt.operations import (
        SchemaRegistriesOperations,
    )

STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_ID = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"


def get_user_msg_warn_ra(prefix: str, principal_id: str, scope: str):
    return (
        f"{prefix}\n\n"
        f"The schema registry MSI principal '{principal_id}' needs\n"
        "'Storage Blob Data Contributor' or equivalent role against scope:\n"
        f"'{scope}'\n\n"
        "Please handle this step before continuing."
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
        registry_namespace: str,
        storage_account_resource_id: str,
        storage_container_name: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        display_name: Optional[str] = None,
        tags: Optional[str] = None,
        custom_role_id: Optional[str] = None,
        **kwargs,
    ) -> dict:
        from ..rp_namespace import register_providers
        with console.status("Working...") as c:
            # Register providers - may as well do all for AIO
            register_providers(self.default_subscription_id)

            if not location:
                location = self.get_resource_group(name=resource_group_name)["location"]

            storage_id_container = parse_resource_id(storage_account_resource_id)

            self.storage_mgmt_client = get_storage_mgmt_client(
                subscription_id=storage_id_container.subscription_id,
            )
            storage_account: dict = self.storage_mgmt_client.storage_accounts.get_properties(
                resource_group_name=storage_id_container.resource_group_name,
                account_name=storage_id_container.resource_name,
            )
            storage_properties: dict = storage_account["properties"]
            is_hns_enabled = storage_properties.get("isHnsEnabled", False)
            if not is_hns_enabled:
                raise ValidationError(
                    "Schema registry requires the storage account to have hierarchical namespace enabled."
                )

            try:
                blob_container = self.storage_mgmt_client.blob_containers.get(
                    resource_group_name=storage_id_container.resource_group_name,
                    account_name=storage_id_container.resource_name,
                    container_name=storage_container_name,
                )
            except ResourceNotFoundError:
                blob_container = self.storage_mgmt_client.blob_containers.create(
                    resource_group_name=storage_id_container.resource_group_name,
                    account_name=storage_id_container.resource_name,
                    container_name=storage_container_name,
                    blob_container={},
                )

            blob_container_url = f"{storage_properties['primaryEndpoints']['blob']}{blob_container['name']}"
            resource = {
                "location": location,
                "identity": {
                    "type": "SystemAssigned",
                },
                "properties": {
                    "namespace": registry_namespace,
                    "storageAccountContainerUrl": blob_container_url,
                    "description": description,
                    "displayName": display_name,
                },
            }
            if tags:
                resource["tags"] = tags

            poller = self.ops.begin_create_or_replace(
                resource_group_name=resource_group_name, schema_registry_name=name, resource=resource
            )
            result = wait_for_terminal_state(poller, **kwargs)

            target_role_def = custom_role_id or ROLE_DEF_FORMAT_STR.format(
                subscription_id=storage_id_container.subscription_id, role_id=STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_ID
            )
            permission_manager = PermissionManager(storage_id_container.subscription_id)
            try:
                permission_manager.apply_role_assignment(
                    scope=storage_account["id"],
                    principal_id=result["identity"]["principalId"],
                    role_def_id=target_role_def,
                )
            except Exception as e:
                c.stop()
                logger.warning(
                    get_user_msg_warn_ra(
                        prefix=f"Role assignment failed with:\n{str(e)}.",
                        principal_id=result["identity"]["principalId"],
                        scope=storage_account["id"],
                    )
                )

            return result

    def show(self, name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, schema_registry_name=name)

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()

    def delete(self, name: str, resource_group_name: str, confirm_yes: Optional[bool] = None, **kwargs):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(resource_group_name=resource_group_name, schema_registry_name=name)
            return wait_for_terminal_state(poller, **kwargs)
