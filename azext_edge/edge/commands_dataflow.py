# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable

from .providers.orchestration.resources import DataFlowEndpoints, DataFlowProfiles


def show_dataflow_profile(cmd, profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowProfiles(cmd).show(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_profiles(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)


def show_dataflow(cmd, dataflow_name: str, profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowProfiles(cmd).dataflows.show(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflows(cmd, profile_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).dataflows.list(
        dataflow_profile_name=profile_name, instance_name=instance_name, resource_group_name=resource_group_name
    )


def show_dataflow_endpoint(cmd, dataflow_endpoint_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowEndpoints(cmd).show(
        name=dataflow_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_endpoints(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)
