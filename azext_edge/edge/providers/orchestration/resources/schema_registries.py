# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from azure.cli.core.azclierror import ValidationError, FileOperationError, ForbiddenError, InvalidArgumentValueError
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
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
from ..common import SchemaFormat, SchemaType
from ..permissions import PermissionManager, ROLE_DEF_FORMAT_STR

logger = get_logger(__name__)
console = Console()
if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt.operations import (
        SchemaRegistriesOperations,
        SchemasOperations,
        SchemaVersionsOperations,
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
        from ..rp_namespace import register_providers, ADR_PROVIDER
        with console.status("Working...") as c:
            # Register the schema (ADR) provider
            register_providers(self.default_subscription_id, ADR_PROVIDER)

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
                    scope=blob_container["id"],
                    principal_id=result["identity"]["principalId"],
                    role_def_id=target_role_def,
                )
            except Exception as e:
                c.stop()
                logger.warning(
                    get_user_msg_warn_ra(
                        prefix=f"Role assignment failed with:\n{str(e)}.",
                        principal_id=result["identity"]["principalId"],
                        scope=blob_container["id"],
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
            try:
                poller = self.ops.begin_delete(resource_group_name=resource_group_name, schema_registry_name=name)
                wait_for_terminal_state(poller, **kwargs)
            except HttpResponseError as e:
                if e.status_code != 200:
                    raise e


class Schemas(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.registry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "SchemasOperations" = self.registry_mgmt_client.schemas
        self.version_ops: "SchemaVersionsOperations" = self.registry_mgmt_client.schema_versions

    def create(
        self,
        name: str,
        schema_registry_name: str,
        resource_group_name: str,
        schema_type: str,
        schema_format: str,
        schema_version_content: str,
        schema_version: int = 1,
        description: Optional[str] = None,
        display_name: Optional[str] = None,
        schema_version_description: Optional[str] = None
    ) -> dict:
        with console.status("Working...") as c:
            schema_type = SchemaType[schema_type].full_value
            schema_format = SchemaFormat[schema_format].full_value
            resource = {
                "properties": {
                    "format": schema_format,
                    "schemaType": schema_type,
                    "description": description,
                    "displayName": display_name,
                },
            }
            schema = self.ops.create_or_replace(
                resource_group_name=resource_group_name,
                schema_registry_name=schema_registry_name,
                schema_name=name,
                resource=resource
            )
            logger.info(f"Created schema {name}.")
            # TODO: maybe add in an exception catch for auth errors
            self.add_version(
                name=schema_version,
                schema_version_content=schema_version_content,
                schema_name=name,
                schema_registry_name=schema_registry_name,
                resource_group_name=resource_group_name,
                description=schema_version_description,
                current_console=c
            )
            logger.info(f"Added version {schema_version} to schema {name}.")
            return schema

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
    ):
        if not should_continue_prompt(confirm_yes=confirm_yes):
            return

        with console.status("Working..."):
            return self.ops.delete(
                resource_group_name=resource_group_name,
                schema_registry_name=schema_registry_name,
                schema_name=name
            )

    def add_version(
        self,
        name: int,
        schema_name: str,
        schema_registry_name: str,
        resource_group_name: str,
        schema_version_content: str,
        description: Optional[str] = None,
        current_console: Optional[Console] = None,
    ) -> dict:
        from ....util import read_file_content

        if name < 0:
            raise InvalidArgumentValueError("Version must be a positive number")

        try:
            logger.debug("Processing schema content.")
            schema_version_content = read_file_content(schema_version_content)
        except FileOperationError:
            logger.debug("Given schema content is not a file.")
            pass

        resource = {
            "properties": {
                "schemaContent": schema_version_content,
                "description": description,
            },
        }
        try:
            with current_console or console.status("Working..."):
                return self.version_ops.create_or_replace(
                    resource_group_name=resource_group_name,
                    schema_registry_name=schema_registry_name,
                    schema_name=schema_name,
                    schema_version_name=name,
                    resource=resource
                )
        except HttpResponseError as e:
            if e.status_code == 412:
                raise ForbiddenError(
                    "Schema versions require public network access to be enabled in the associated storage account."
                )
            raise e

    def show_version(
        self,
        name: int,
        schema_name: str,
        schema_registry_name: str,
        resource_group_name: str,
    ) -> dict:
        # service verifies hash during create already
        return self.version_ops.get(
            resource_group_name=resource_group_name,
            schema_registry_name=schema_registry_name,
            schema_name=schema_name,
            schema_version_name=name,
        )

    def list_versions(
        self, schema_name: str, schema_registry_name: str, resource_group_name: str
    ) -> Iterable[dict]:
        return self.version_ops.list_by_schema(
            resource_group_name=resource_group_name,
            schema_registry_name=schema_registry_name,
            schema_name=schema_name
        )

    def remove_version(
        self,
        name: int,
        schema_name: str,
        schema_registry_name: str,
        resource_group_name: str,
    ):
        with console.status("Working..."):
            return self.version_ops.delete(
                resource_group_name=resource_group_name,
                schema_registry_name=schema_registry_name,
                schema_name=schema_name,
                schema_version_name=name,
            )

    def list_dataflow_friendly_versions(
        self,
        schema_registry_name: str,
        resource_group_name: str,
        schema_name: Optional[str] = None,
        schema_version: Optional[int] = None,
        latest: bool = False
    ) -> dict:
        from collections import OrderedDict
        # note temporary until dataflow create is added.
        versions_map = {}
        with console.status("Fetching version info..."):
            # get all the versions first
            if schema_name and schema_version:
                versions_map[schema_name] = [int(schema_version)]
            elif schema_name:
                versions_map.update(
                    self._get_schema_version_dict(
                        schema_name=schema_name,
                        schema_registry_name=schema_registry_name,
                        resource_group_name=resource_group_name,
                        latest=latest
                    )
                )
            elif schema_version:
                # TODO: maybe do the weird
                raise InvalidArgumentValueError(
                    "Please provide the schema name if schema versions is used."
                )
            else:
                schema_list = self.list(
                    schema_registry_name=schema_registry_name, resource_group_name=resource_group_name
                )
                for schema in schema_list:
                    versions_map.update(
                        self._get_schema_version_dict(
                            schema_name=schema["name"],
                            schema_registry_name=schema_registry_name,
                            resource_group_name=resource_group_name,
                            latest=latest
                        )
                    )

            ref_format = "aio-sr://{schema}:{version}"
            # change to ordered dict for order, azure cli does not like the int keys at that level
            for schema_name, versions_list in versions_map.items():
                ordered = OrderedDict(
                    (str(ver), ref_format.format(schema=schema_name, version=ver)) for ver in versions_list
                )
                versions_map[schema_name] = ordered

            return versions_map

    def _get_schema_version_dict(
        self, schema_name: str, schema_registry_name: str, resource_group_name: str, latest: bool = False
    ) -> dict:
        version_list = self.list_versions(
            schema_name=schema_name,
            schema_registry_name=schema_registry_name,
            resource_group_name=resource_group_name
        )
        version_list = [int(ver["name"]) for ver in version_list]
        if latest:
            version_list = [max(version_list)]
        return {schema_name: sorted(version_list)}
