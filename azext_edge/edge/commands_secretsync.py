# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

from knack.log import get_logger

from .providers.orchestration.resources import Instances

logger = get_logger(__name__)


def secretsync_enable(
    cmd,
    instance_name: str,
    resource_group_name: str,
    mi_user_assigned: str,
    keyvault_resource_id: str,
    spc_name: Optional[str] = None,
    skip_role_assignments: Optional[bool] = None,
    use_self_hosted_issuer: Optional[bool] = None,
    **kwargs,
) -> dict:
    return Instances(cmd).enable_secretsync(
        name=instance_name,
        resource_group_name=resource_group_name,
        mi_user_assigned=mi_user_assigned,
        keyvault_resource_id=keyvault_resource_id,
        spc_name=spc_name,
        skip_role_assignments=skip_role_assignments,
        use_self_hosted_issuer=use_self_hosted_issuer,
        **kwargs,
    )


def secretsync_list(cmd, instance_name: str, resource_group_name: str) -> dict:
    return Instances(cmd).list_secretsync(
        name=instance_name,
        resource_group_name=resource_group_name,
    )


def secretsync_disable(cmd, instance_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None):
    return Instances(cmd).disable_secretsync(
        name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
    )
