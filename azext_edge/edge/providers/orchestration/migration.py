# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Optional

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
        include_assets: Optional[list[str]] = None,  # TODO param plumbing
        confirm_yes: Optional[bool] = False,
        **kwargs,
    ):
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
        if include_assets:
            include_assets = set(include_assets)

        for asset in instance_root_assets:
            if include_assets and asset["name"] not in include_assets:
                continue
            resource_ids.append(asset["id"])

        # The following asset resource Ids will be migrated.
        console.print("The following asset resource Ids will be migrated:")
        console.print_json(data=resource_ids)
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes, context="Migration")
        if should_bail:
            return

        if not resource_ids:
            logger.warning("No migration work to do.")
            return

        import pdb; pdb.set_trace()
        payload = {"resourceIds": resource_ids, "scope": "Resources"}
        with console.status("Working..."):
            poller = self.ops.begin_migrate(
                resource_group_name=parsed_ns_id["resource_group"], namespace_name=parsed_ns_id["name"], body=payload
            )
            return wait_for_terminal_state(poller, **kwargs)

        # delete AEPs afterwards?
