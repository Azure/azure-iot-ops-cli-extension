# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional

from azure.cli.core.azclierror import ArgumentUsageError
from azext_edge.edge.providers.edge_api.dataflow import DataflowResourceKinds
from rich.console import Console

from ..common import ListableEnum, OpsServiceType
from .check.base import check_pre_deployment, display_as_list
from .check.common import COLOR_STR_FORMAT, ResourceOutputDetailLevel
from .check.deviceregistry import check_deviceregistry_deployment
from .check.mq import check_mq_deployment
from .check.opcua import check_opcua_deployment
from .edge_api.deviceregistry import DeviceRegistryResourceKinds
from .edge_api.mq import MqResourceKinds
from .check.akri import check_akri_deployment
from .check.dataflow import check_dataflows_deployment
from .check.summary import check_summary
from .edge_api.akri import AkriResourceKinds
from .edge_api.opcua import OpcuaResourceKinds

console = Console(width=100, highlight=False)


def run_checks(
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    ops_service: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> Dict[str, Any]:
    result = {}

    # check if the resource_kinds are valid for the requested service
    if resource_kinds:
        _validate_resource_kinds_under_service(ops_service, resource_kinds)

    with console.status(status="Analyzing cluster...", refresh_per_second=12.5):
        from time import sleep

        sleep(0.5)

        color = COLOR_STR_FORMAT.format(color="bright_blue", value="{text}") if as_list else "{text}"
        title_subject = (
            f"{{{color.format(text=ops_service)}}} service deployment"
            if post_deployment
            else color.format(text="IoT Operations readiness")
        )
        result["title"] = f"Evaluation for {title_subject}"

        if pre_deployment:
            check_pre_deployment(result, as_list)
        if post_deployment:
            result["postDeployment"] = []
            service_check_dict = {
                OpsServiceType.akri.value: check_akri_deployment,
                OpsServiceType.mq.value: check_mq_deployment,
                OpsServiceType.deviceregistry.value: check_deviceregistry_deployment,
                OpsServiceType.opcua.value: check_opcua_deployment,
                OpsServiceType.dataflow.value: check_dataflows_deployment,
                None: check_summary
            }
            service_result = service_check_dict[ops_service](
                detail_level=detail_level,
                resource_name=resource_name,
                as_list=as_list,
                resource_kinds=resource_kinds
            )
            if isinstance(service_result, list):
                for obj in service_result:
                    result["postDeployment"].append(obj)
            else:
                result["postDeployment"].append(service_result)

        if as_list:
            return display_as_list(console=console, result=result)
        return result


def _validate_resource_kinds_under_service(ops_service: str, resource_kinds: List[str]) -> None:
    service_kinds_dict: Dict[str, ListableEnum] = {
        OpsServiceType.akri.value: AkriResourceKinds,
        OpsServiceType.deviceregistry.value: DeviceRegistryResourceKinds,
        OpsServiceType.mq.value: MqResourceKinds,
        OpsServiceType.opcua.value: OpcuaResourceKinds,
        OpsServiceType.dataflow.value: DataflowResourceKinds,
    }

    valid_resource_kinds = service_kinds_dict[ops_service].list() if ops_service in service_kinds_dict else []

    for resource_kind in resource_kinds:
        if resource_kind not in valid_resource_kinds:
            raise ArgumentUsageError(
                f"Resource kind {resource_kind} is not supported for service {ops_service}. "
                f"Allowed resource kinds for this service are {valid_resource_kinds}"
            )
