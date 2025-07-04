# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, List, NamedTuple, Optional

from azure.cli.core.azclierror import (
    AzureResponseError,
)
from knack.log import get_logger
from rich.console import Console

from ....util.az_client import get_extloc_mgmt_client, wait_for_terminal_states
from ....util.common import should_continue_prompt
from ....util.id_tools import parse_resource_id
from ....util.queryable import Queryable
from ..permissions import (
    ROLE_DEF_FORMAT_STR,
    PermissionManager,
    PrincipalType,
    get_ra_user_error_msg,
)
from . import Instances

if TYPE_CHECKING:
    from ....vendor.clients.extendedlocmgmt.operations import (
        ResourceSyncRulesOperations,
    )

KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID = "5d3f1697-4507-4d08-bb4a-477695db5f82"
K8_BRIDGE_APP_ID = "319f651f-7ddb-4fc6-9857-7aef9250bd05"
ADR_PROVIDER = "Microsoft.DeviceRegistry"
OPS_PROVIDER = "Microsoft.IoTOperations"

logger = get_logger(__name__)
console = Console()


class SyncRuleAttr(NamedTuple):
    provider: str
    priority: int
    name: str


def get_sync_rule_attrs(
    custom_location_name: str,
    rule_ops_name: Optional[str] = None,
    rule_adr_name: Optional[str] = None,
    rule_ops_pri: Optional[int] = None,
    rule_adr_pri: Optional[int] = None,
) -> List[SyncRuleAttr]:
    return [
        SyncRuleAttr(
            provider=OPS_PROVIDER,
            priority=rule_ops_pri or 400,
            name=rule_ops_name or f"{custom_location_name}-aio-sync",
        ),
        SyncRuleAttr(
            provider=ADR_PROVIDER,
            priority=rule_adr_pri or 200,
            name=rule_adr_name or f"{custom_location_name}-adr-sync",
        ),
    ]


class SyncRules(Queryable):
    def __init__(self, cmd, resource_group_name: str, instance_name: str):
        super().__init__(cmd=cmd)
        self.resource_group_name = resource_group_name
        self.instance_name = instance_name
        self.instances = Instances(self.cmd)
        self.custom_location = self.instances.get_associated_cl(
            self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
        )
        self.extloc_mgmt_client = get_extloc_mgmt_client(self.default_subscription_id)
        self.ops: "ResourceSyncRulesOperations" = self.extloc_mgmt_client.resource_sync_rules

    def _get_enable_params(
        self, provider_name: str, priority: Optional[int] = None, tags: Optional[dict] = None
    ) -> dict:
        parsed_cl_id = parse_resource_id(self.custom_location["id"])
        rg_id = "/subscriptions/{}/resourceGroups/{}".format(
            parsed_cl_id["subscription"], parsed_cl_id["resource_group"]
        )
        properties = {
            "targetResourceGroup": rg_id,
        }
        parameters = {
            "location": self.custom_location["location"],
        }
        if priority:
            properties["priority"] = priority
        if tags:
            parameters["tags"] = tags

        properties["selector"] = {
            "matchExpressions": [
                {
                    "key": "management.azure.com/provider-name",
                    "operator": "In",
                    "values": [provider_name, provider_name.lower()],
                }
            ]
        }
        parameters["properties"] = properties
        return parameters

    def enable(
        self,
        skip_role_assignments: Optional[bool] = None,
        custom_role_id: Optional[str] = None,
        k8_bridge_sp_oid: Optional[str] = None,
        rule_ops_name: Optional[str] = None,
        rule_adr_name: Optional[str] = None,
        rule_ops_pri: Optional[int] = None,
        rule_adr_pri: Optional[int] = None,
        tags: Optional[dict] = None,
        **kwargs,
    ) -> List[dict]:
        with console.status("Working...") as c:
            pollers = []
            sync_rule_attrs = get_sync_rule_attrs(
                custom_location_name=self.custom_location["name"],
                rule_ops_name=rule_ops_name,
                rule_adr_name=rule_adr_name,
                rule_ops_pri=rule_ops_pri,
                rule_adr_pri=rule_adr_pri,
            )
            for rule_attrs in sync_rule_attrs:
                poller = self.ops.begin_create_or_update(
                    resource_group_name=self.resource_group_name,
                    resource_name=self.custom_location["name"],
                    child_resource_name=rule_attrs.name,
                    parameters=self._get_enable_params(
                        provider_name=rule_attrs.provider,
                        priority=rule_attrs.priority,
                        tags=tags,
                    ),
                )
                pollers.append(poller)
            wait_for_terminal_states(*pollers, **kwargs)
            result = [p.result() for p in pollers]

            if not skip_role_assignments:
                target_role_def = custom_role_id or ROLE_DEF_FORMAT_STR.format(
                    subscription_id=self.default_subscription_id, role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID
                )
                k8_bridge_sp_oid = k8_bridge_sp_oid or self.get_sp_id(K8_BRIDGE_APP_ID)
                if not k8_bridge_sp_oid:
                    c.stop()
                    logger.warning(
                        "Unable to query K8 Bridge service principal and OID not provided via parameter. "
                        "Skipping role assignment."
                    )
                    return result

                permission_manager = PermissionManager(self.default_subscription_id)
                try:
                    permission_manager.apply_role_assignment(
                        scope=self.custom_location["id"],
                        principal_id=k8_bridge_sp_oid,
                        role_def_id=target_role_def,
                        principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
                    )
                except Exception as e:
                    c.stop()
                    raise AzureResponseError(
                        get_ra_user_error_msg(
                            error_str=str(e),
                            sp_name="K8 Bridge",
                            sp_id=K8_BRIDGE_APP_ID,
                            expected_role="Azure Kubernetes Service Arc Contributor Role",
                            scope=self.custom_location["id"],
                        )
                    )

            return result

    def disable(self, confirm_yes: Optional[bool] = None) -> None:
        if not should_continue_prompt(confirm_yes=confirm_yes):
            return

        sync_rules = list(self.list())
        if not sync_rules:
            logger.warning(f"No resource sync rules found for instance '{self.instance_name}'.")
            return

        with console.status("Working..."):
            for rule in sync_rules:
                self.ops.delete(
                    resource_group_name=self.resource_group_name,
                    resource_name=self.custom_location["name"],
                    child_resource_name=rule["name"],
                )

    def list(self) -> List[dict]:
        return self.ops.list_by_custom_location_id(
            resource_group_name=self.resource_group_name,
            resource_name=self.custom_location["name"],
        )
