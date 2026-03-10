# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import (
    AzureResponseError,
)
from knack.log import get_logger
from rich.console import Console

from ....util.az_client import get_extloc_mgmt_client
from ....util.queryable import Queryable
from ..common import KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID
from ..permissions import (
    ROLE_DEF_FORMAT_STR,
    PermissionManager,
    PrincipalType,
    get_ra_user_error_msg,
)
from . import Instances

K8_BRIDGE_APP_ID = "319f651f-7ddb-4fc6-9857-7aef9250bd05"
ADR_PROVIDER = "Microsoft.DeviceRegistry"
OPS_PROVIDER = "Microsoft.IoTOperations"

logger = get_logger(__name__)
console = Console()


class SyncRules(Queryable):
    def __init__(self, cmd, resource_group_name: str, instance_name: str):
        super().__init__(cmd=cmd)
        self.resource_group_name = resource_group_name
        self.instance_name = instance_name
        self.instances = Instances(self.cmd)
        self.custom_location = self.instances.get_associated_cl(
            self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
        )
        self.extloc_mgmt_client = get_extloc_mgmt_client(**self._get_client_kwargs())

    def enable(
        self,
        custom_role_id: Optional[str] = None,
        k8_bridge_sp_oid: Optional[str] = None,
        **kwargs,
    ) -> Optional[dict]:
        with console.status("Working...") as c:
            target_role_def = custom_role_id or ROLE_DEF_FORMAT_STR.format(
                subscription_id=self.default_subscription_id, role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID
            )
            k8_bridge_sp_oid = k8_bridge_sp_oid or self.get_sp_id(K8_BRIDGE_APP_ID)
            if not k8_bridge_sp_oid:
                c.stop()
                logger.warning(
                    "Unable to query K8 Bridge service principal and OID not provided via parameter. "
                    "Role assignment can not be made."
                )
                return

            permission_manager = PermissionManager(self.default_subscription_id)
            try:
                result = permission_manager.apply_role_assignment(
                    scope=self.custom_location["id"],
                    principal_id=k8_bridge_sp_oid,
                    role_def_id=target_role_def,
                    principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
                    **kwargs,
                )

                if result is None:
                    console.print(":exclamation: Role assignment already exists for K8 Bridge service principal.")
                    action_msg = "already exists"
                else:
                    action_msg = "successfully created"

                logger.info(
                    "Role assignment %s for K8 Bridge service principal on custom location '%s'.",
                    action_msg,
                    self.custom_location["name"],
                )
                return result
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
