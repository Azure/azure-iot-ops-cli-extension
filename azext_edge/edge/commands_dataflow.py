# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from azext_edge.edge.common import DEFAULT_DATAFLOW_PROFILE

from .providers.orchestration.resources import DataFlowEndpoints, DataFlowProfiles


def show_dataflow_profile(cmd, profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowProfiles(cmd).show(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_profiles(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)


def show_dataflow(
    cmd,
    dataflow_name: str,
    instance_name: str,
    resource_group_name: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
) -> dict:
    return DataFlowProfiles(cmd).dataflows.show(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflows(
    cmd,
    instance_name: str,
    resource_group_name: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
) -> Iterable[dict]:
    return DataFlowProfiles(cmd).dataflows.list(
        dataflow_profile_name=profile_name, instance_name=instance_name, resource_group_name=resource_group_name
    )


def apply_dataflow(
    cmd,
    dataflow_name: str,
    instance_name: str,
    resource_group_name: str,
    config_file: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
    **kwargs: dict,
) -> dict:
    return DataFlowProfiles(cmd).dataflows.apply(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file=config_file,
        **kwargs,
    )


def delete_dataflow(
    cmd,
    dataflow_name: str,
    instance_name: str,
    resource_group_name: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
    confirm_yes: Optional[bool] = None,
    **kwargs: dict,
):
    return DataFlowProfiles(cmd).dataflows.delete(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def apply_dataflow_endpoint(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    config_file: str,
    **kwargs,
) -> dict:
    return DataFlowEndpoints(cmd).apply(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file=config_file,
        **kwargs,
    )


def delete_dataflow_endpoint(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: bool = False,
    **kwargs,
):
    return DataFlowEndpoints(cmd).delete(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def show_dataflow_endpoint(cmd, endpoint_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowEndpoints(cmd).show(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_endpoints(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowEndpoints(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)
