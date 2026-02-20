# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from .providers.orchestration.mgmt_actions import MgmtActions


def mgmt_actions_enable(
    cmd,
    instance_name: str,
    resource_group_name: str,
    eg_resource_id: str,
    mi_user_assigned: Optional[str] = None,
    eg_client_group: Optional[str] = None,
    adr_role_ids: Optional[List[str]] = None,
    ops_role_ids: Optional[List[str]] = None,
    skip_role_assignments: Optional[bool] = None,
    dataflow_profile: Optional[str] = None,
    **kwargs,
) -> Dict:
    return MgmtActions(cmd).enable(
        name=instance_name,
        resource_group_name=resource_group_name,
        eg_resource_id=eg_resource_id,
        mi_user_assigned=mi_user_assigned,
        eg_client_group=eg_client_group,
        adr_role_ids=adr_role_ids,
        ops_role_ids=ops_role_ids,
        skip_role_assignments=skip_role_assignments,
        dataflow_profile=dataflow_profile,
        **kwargs,
    )


def mgmt_actions_disable(
    cmd,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    **kwargs,
) -> None:
    return MgmtActions(cmd).disable(
        name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )
