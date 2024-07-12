# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Union
from enum import Enum

from azext_edge.edge.providers.check.cloud_connectors import process_cloud_connector
from azext_edge.edge.providers.edge_api.dataflow import DATAFLOW_API_V1B1, DataflowResourceKinds
from .base import (
    CheckManager,
    decorate_resource_status,
    check_post_deployment,
    evaluate_pod_health,
    get_resource_metadata_property,
    get_resources_by_name,
    get_resources_grouped_by_namespace
)

from rich.console import NewLine
from rich.padding import Padding

from ...common import (
    AIO_MQ_DIAGNOSTICS_SERVICE,
    CheckTaskStatus,
    ResourceState,
)

from .common import (
    AIO_MQ_DIAGNOSTICS_PROBE_PREFIX,
    AIO_MQ_FRONTEND_PREFIX,
    AIO_MQ_BACKEND_PREFIX,
    AIO_MQ_AUTH_PREFIX,
    AIO_MQ_HEALTH_MANAGER,
    PADDING_SIZE,
    DataLakeConnectorTargetType,
    KafkaTopicMapRouteType,
    ResourceOutputDetailLevel,
)

from ...providers.edge_api import (
    MQ_ACTIVE_API,
    MqResourceKinds
)
from ..support.mq import MQ_NAME_LABEL

from ..base import get_namespaced_service


def check_dataflows_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> None:
    evaluate_funcs = {
        DataflowResourceKinds.DATAFLOW: evaluate_dataflows,
        DataflowResourceKinds.DATAFLOWENDPOINT: evaluate_dataflow_endpoints,
        DataflowResourceKinds.DATAFLOWPROFILE: evaluate_dataflow_profiles,
    }

    check_post_deployment(
        api_info=DATAFLOW_API_V1B1,
        check_name="enumerateDataflowApi",
        check_desc="Enumerate Dataflow API resources",
        result=result,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
        resource_name=resource_name,
    )


def evaluate_dataflows(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflows",
        check_desc="Evaluate Dataflows",
    )
    all_dataflows = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOW,
        resource_name=resource_name,
    )
    target = 'dataflows.iotoperations.azure.com'
    check_manager.add_target(target_name=target, namespace='azure-iot-operations')
    check_manager.add_display(target_name=target, namespace='azure-iot-operations', display=Padding(all_dataflows, (0,0,0,0)))
    # check_manager.set_target_status(target_name=target, namespace='azure-iot-operations')
    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_endpoints(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowEndpoints",
        check_desc="Evaluate Dataflow Endpoints",
    )
    all_endpoints = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWENDPOINT,
        resource_name=resource_name,
    )
    target = 'endpoints.dataflows.iotoperations.azure.com'
    check_manager.add_target(target_name=target, namespace='azure-iot-operations')
    check_manager.add_display(target_name=target, namespace='azure-iot-operations', display=Padding(all_endpoints, (0,0,0,0)))
    # check_manager.set_target_status(target_name=target, namespace='azure-iot-operations')
    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_profiles(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowProfiles",
        check_desc="Evaluate Dataflow Profiles",
    )
    all_profiles = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWPROFILE,
        resource_name=resource_name,
    )
    target = 'profiles.dataflows.iotoperations.azure.com'
    check_manager.add_target(target_name=target, namespace='azure-iot-operations')
    check_manager.add_display(target_name=target, namespace='azure-iot-operations', display=Padding(all_profiles, (0,0,0,0)))
    # check_manager.set_target_status(target_name=target, namespace='azure-iot-operations')
    return check_manager.as_dict(as_list=as_list)