# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from fnmatch import fnmatch
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from azure.cli.core.azclierror import (
    AzureResponseError,
    ValidationError,
)
from knack.log import get_logger
from rich.console import Console
from rich.status import Status

from ...util.az_client import (
    get_registry_mgmt_client,
    wait_for_terminal_state,
    DeviceRegistryMgmtApiVersion
)
from ...util.common import should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.queryable import Queryable
from ..adr.assets import ASSET_RESOURCE_TYPE
from .common import (
    ADR_RP_APP_ID,
    KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID,
    MIN_INSTANCE_VERSION_FOR_MIGRATE,
)
from .permissions import (
    ROLE_DEF_FORMAT_STR,
    PermissionManager,
    PrincipalType,
    get_ra_user_error_msg,
)
from .resources import Instances

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt.operations import NamespacesOperations


console = Console()
logger = get_logger(__name__)


class AssetMigrationManager(Queryable):
    def __init__(self, cmd, instance_name: str, resource_group_name: str):
        super().__init__(cmd=cmd)
        from ...util.machinery import scoped_semver_import

        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
            api_version=DeviceRegistryMgmtApiVersion.V20250701_preview.value
        )
        self.ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces
        self.instances = Instances(self.cmd)
        self.permission_manager = PermissionManager(self.default_subscription_id)
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.instance_record = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
        self.semver = scoped_semver_import()

    def _handle_adr_permission(self, status: Status, adr_sp_oid: Optional[str] = None):
        status.update("Checking Device Registry permission...")
        skip_ra_txt = "--skip-ra to skip the role assignment step of this operation."
        adr_sp_oid = adr_sp_oid or self.get_sp_id(ADR_RP_APP_ID)
        if not adr_sp_oid:
            raise ValidationError(
                "Unable to look up Device Registry service principal Id. Please provide with --adr-sp-oid "
                f"or append {skip_ra_txt}"
            )
        target_role_def = ROLE_DEF_FORMAT_STR.format(
            subscription_id=self.default_subscription_id, role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID
        )
        target_scope = self.instance_record["extendedLocation"]["name"]
        try:
            self.permission_manager.apply_role_assignment(
                scope=target_scope,
                principal_id=adr_sp_oid,
                role_def_id=target_role_def,
                principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
            )
        except Exception as e:
            status.stop()
            raise AzureResponseError(
                get_ra_user_error_msg(
                    error_str=str(e),
                    sp_name="Device Registry",
                    sp_id=adr_sp_oid,
                    expected_role="Azure Kubernetes Service Arc Contributor Role",
                    scope=target_scope,
                    supplemental_info=f"Append {skip_ra_txt}",
                )
            )

    def migrate_to_namespace(
        self,
        name_patterns: Optional[list[str]] = None,  # Accept exact names or glob patterns (e.g. 'pump*')
        confirm_yes: Optional[bool] = None,
        skip_adr_ra: Optional[bool] = None,
        adr_sp_oid: Optional[str] = None,
        **kwargs,
    ):
        with console.status("Querying resources...") as status:
            instance_version = self.instance_record["properties"].get("version", "0.0.0")
            if self.semver.parse(instance_version) < self.semver.parse(MIN_INSTANCE_VERSION_FOR_MIGRATE):
                raise ValidationError(
                    f"The instance must be at least version {MIN_INSTANCE_VERSION_FOR_MIGRATE} to migrate assets."
                )

            instance_ns_id = self.instance_record["properties"].get("adrNamespaceRef", {}).get("resourceId")
            if not instance_ns_id:
                raise ValidationError("The instance does not have an associated ADR namespace.")
            parsed_ns_id = parse_resource_id(rid=instance_ns_id)

            connected_cluster = self.instances.get_resource_map(self.instance_record).connected_cluster
            if not connected_cluster.connected:
                raise ValidationError(f"Cluster {connected_cluster.cluster_name} is not connected.")

            resource_query = connected_cluster.get_cl_resources_by_type(
                custom_location_id=self.instance_record["extendedLocation"]["name"],
                resource_types={ASSET_RESOURCE_TYPE},
            )
            instance_root_assets = resource_query.get(ASSET_RESOURCE_TYPE.lower(), [])
            if not instance_root_assets:
                status.stop()
                logger.warning("No root assets are associated with the instance.")
                return

            if not skip_adr_ra:
                self._handle_adr_permission(status=status, adr_sp_oid=adr_sp_oid)

            resource_ids = []
            if name_patterns:
                # Single pass to separate exact names from patterns
                exact_names = set()
                patterns = []
                for item in name_patterns:
                    # Check if item contains glob special characters
                    if "*" in item or "?" in item or "[" in item:
                        patterns.append(item)
                    else:
                        exact_names.add(item)

                for asset in instance_root_assets:
                    asset_name = asset["name"]
                    # Check exact match first (O(1)), then patterns
                    if asset_name in exact_names or any(fnmatch(asset_name, p) for p in patterns):
                        resource_ids.append(asset["id"])
            else:
                # No filter, include all
                resource_ids = [asset["id"] for asset in instance_root_assets]

        if not resource_ids:
            logger.warning("No root assets to migrate found.")
            return

        correlation_id = str(uuid4())
        correlation_id_text = f"Migration correlation Id: {correlation_id}"
        if not confirm_yes:
            console.print(f"The following {len(resource_ids)} asset resource Id(s) will be migrated:")
            console.print_json(data=resource_ids)
            console.print("Post migration - unreferenced endpoint profiles can be deleted.")
            console.print(correlation_id_text)
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes, context="Migration")
        if should_bail:
            return

        headers = {"x-ms-correlation-request-id": correlation_id, "CommandName": "iot ops migrate-assets"}
        payload = {"resourceIds": resource_ids, "scope": "Resources"}
        with console.status("Working..."):
            logger.debug(correlation_id_text)
            poller = self.ops.begin_migrate(
                resource_group_name=parsed_ns_id["resource_group"],
                namespace_name=parsed_ns_id["name"],
                body=payload,
                headers=headers,
            )
            return wait_for_terminal_state(poller, **kwargs)
