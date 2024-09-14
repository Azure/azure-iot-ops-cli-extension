# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional, List

from knack.log import get_logger

from .providers.orchestration.resources import Instances

logger = get_logger(__name__)


def secretsync_enable(
    cmd, instance_name: str, resource_group_name: str, mi_user_assigned: str, keyvault_resource_id: str
) -> dict:
    return Instances(cmd).enable_secretsync(
        name=instance_name,
        resource_group_name=resource_group_name,
        mi_user_assigned=mi_user_assigned,
        keyvault_resource_id=keyvault_resource_id,
    )


def secretsync_show(cmd, instance_name: str, resource_group_name: str) -> dict:
    return Instances(cmd).show_secretsync(
        name=instance_name,
        resource_group_name=resource_group_name,
    )


def secretsync_disable(cmd, instance_name: str, resource_group_name: str, mi_user_assigned: str) -> dict:
    return Instances(cmd).disable_secretsync(
        name=instance_name,
        resource_group_name=resource_group_name,
        mi_user_assigned=mi_user_assigned,
    )
