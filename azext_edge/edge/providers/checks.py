# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from azure.cli.core.azclierror import ArgumentUsageError
from rich.console import Console

from ..common import ListableEnum, OpsServiceType
from .check.base import check_pre_deployment, process_as_list
from .check.common import ResourceOutputDetailLevel
from .check.dataprocessor import check_dataprocessor_deployment
from .check.lnm import check_lnm_deployment
from .check.mq import check_mq_deployment
from .check.opcua import check_opcua_deployment
from .edge_api.dataprocessor import DataProcessorResourceKinds
from .edge_api.lnm import LnmResourceKinds
from .edge_api.mq import MqResourceKinds
from .edge_api.opcua import OpcuaResourceKinds

console = Console(width=100, highlight=False)


def run_checks(
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    ops_service: str = OpsServiceType.mq.value,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
) -> Dict[str, Any]:
    result = {}

    # check if the resource_kinds are valid for the requested service
    if resource_kinds:
        _validate_resource_kinds_under_service(ops_service, resource_kinds)

    with console.status(status="Analyzing cluster...", refresh_per_second=12.5):
        from time import sleep

        sleep(0.5)

        result["title"] = f"Evaluation for {{[bright_blue]{ops_service}[/bright_blue]}} service deployment"

        if pre_deployment:
            check_pre_deployment(result, as_list)
        if post_deployment:
            result["postDeployment"] = []
            service_check_dict = {
                OpsServiceType.mq.value: check_mq_deployment,
                OpsServiceType.dataprocessor.value: check_dataprocessor_deployment,
                OpsServiceType.lnm.value: check_lnm_deployment,
                OpsServiceType.opcua.value: check_opcua_deployment,
            }
            service_check_dict[ops_service](
                detail_level=detail_level,
                result=result,
                as_list=as_list,
                resource_kinds=resource_kinds
            )

        if as_list:
            return process_as_list(console=console, result=result) if as_list else result
        return result


def _validate_resource_kinds_under_service(ops_service: str, resource_kinds: List[str]) -> None:
    service_kinds_dict: Dict[str, ListableEnum] = {
        OpsServiceType.dataprocessor.value: DataProcessorResourceKinds,
        OpsServiceType.mq.value: MqResourceKinds,
        OpsServiceType.lnm.value: LnmResourceKinds,
        OpsServiceType.opcua.value: OpcuaResourceKinds
    }

    valid_resource_kinds = service_kinds_dict[ops_service].list() if ops_service in service_kinds_dict else []

    for resource_kind in resource_kinds:
        if resource_kind not in valid_resource_kinds:
            raise ArgumentUsageError(
                f"Resource kind {resource_kind} is not supported for service {ops_service}. "
                f"Allowed resource kinds for this service are {valid_resource_kinds}"
            )
