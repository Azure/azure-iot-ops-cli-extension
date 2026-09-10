# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from .providers.orchestration.live_data import LiveData


def live_data_enable(
    cmd,
    instance_name: str,
    resource_group_name: str,
    eg_resource_id: str,
    mi_user_assigned: Optional[str] = None,
    ra_scope: Optional[str] = None,
    adr_role_ids: Optional[List[str]] = None,
    ops_role_ids: Optional[List[str]] = None,
    skip_role_assignments: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    **kwargs,
) -> Dict:
    return LiveData(cmd).enable(
        name=instance_name,
        resource_group_name=resource_group_name,
        eg_resource_id=eg_resource_id,
        mi_user_assigned=mi_user_assigned,
        ra_scope=ra_scope,
        adr_role_ids=adr_role_ids,
        ops_role_ids=ops_role_ids,
        skip_role_assignments=skip_role_assignments,
        no_progress=no_progress,
        **kwargs,
    )


def live_data_show(
    cmd,
    instance_name: str,
    resource_group_name: str,
    no_progress: Optional[bool] = None,
    **kwargs,
) -> Dict:
    return LiveData(cmd).show(
        name=instance_name,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
        **kwargs,
    )


def live_data_disable(
    cmd,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    **kwargs,
) -> None:
    return LiveData(cmd).disable(
        name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        no_progress=no_progress,
        **kwargs,
    )
