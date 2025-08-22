# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from fnmatch import fnmatch
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from azure.cli.core.azclierror import (
    ValidationError,
)
from knack.log import get_logger
from rich.console import Console

from ...util.az_client import (
    get_registry_mgmt_client,
    wait_for_terminal_state,
)
from ...util.common import should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.queryable import Queryable
from ..adr.assets import ASSET_RESOURCE_TYPE
from .resources import Instances

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt.operations import NamespacesOperations


console = Console()
logger = get_logger(__name__)


class AssetMigrationManager(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(subscription_id=self.default_subscription_id)
        self.ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces
        self.instances = Instances(self.cmd)

    def migrate_to_namespace(
        self,
        instance_name: str,
        resource_group_name: str,
        name_patterns: Optional[list[str]] = None,  # Accept exact names or glob patterns (e.g. 'pump*')
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        with console.status("Querying resources..."):
            instance_record = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
            instance_ns_id = instance_record["properties"].get("adrNamespaceRef", {}).get("resourceId")
            if not instance_ns_id:
                raise ValidationError("The instance does not have an associated ADR namespace.")
            parsed_ns_id = parse_resource_id(rid=instance_ns_id)

            connected_cluster = self.instances.get_resource_map(instance_record).connected_cluster
            if not connected_cluster.connected:
                raise ValidationError(f"Cluster {connected_cluster.cluster_name} is not connected.")

            resource_query = connected_cluster.get_cl_resources_by_type(
                custom_location_id=instance_record["extendedLocation"]["name"], resource_types={ASSET_RESOURCE_TYPE}
            )
            instance_root_assets = resource_query.get(ASSET_RESOURCE_TYPE.lower(), [])
            if not instance_root_assets:
                logger.warning("No root assets are associated with the instance.")
                return

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
