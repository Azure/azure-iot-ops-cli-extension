# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, List
from azure.cli.core.azclierror import ArgumentUsageError

from rich.console import Console

from ..common import SupportForEdgeServiceType
from .check.bluefin import check_bluefin_deployment
from .check.mq import check_mq_deployment
from .check.common import ResourceOutputDetailLevel
from .edge_api.mq import MqResourceKinds
from .edge_api.bluefin import BluefinResourceKinds

console = Console(width=100, highlight=False)


def run_checks(
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    edge_service: str = SupportForEdgeServiceType.mq.value,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
) -> Dict[str, Any]:
    result = {}

    # check if the resource_kinds is under edge_service
    if resource_kinds:
        _check_resource_kinds_under_edge_service(edge_service, resource_kinds)

    with console.status(status="Analyzing cluster...", refresh_per_second=12.5):
        from time import sleep

        sleep(0.5)

        result["title"] = f"Evaluation for {{[bright_blue]{edge_service}[/bright_blue]}} edge service deployment"

        if edge_service == SupportForEdgeServiceType.mq.value:
            result = check_mq_deployment(
                console=console,
                detail_level=detail_level,
                pre_deployment=pre_deployment,
                post_deployment=post_deployment,
                result=result,
                as_list=as_list,
                resource_kinds=resource_kinds
            )
        elif edge_service == SupportForEdgeServiceType.bluefin.value:
            result = check_bluefin_deployment(
                console=console,
                detail_level=detail_level,
                pre_deployment=pre_deployment,
                post_deployment=post_deployment,
                result=result,
                as_list=as_list,
                resource_kinds=resource_kinds
            )

        return result


def _check_resource_kinds_under_edge_service(edge_service: str, resource_kinds: List[str]) -> None:
    valid_resource_values = []

    if edge_service == SupportForEdgeServiceType.bluefin.value:
        valid_resource_values = BluefinResourceKinds.list()
    elif edge_service == SupportForEdgeServiceType.mq.value:
        valid_resource_values = MqResourceKinds.list()

    for resource_kind in resource_kinds:
        if resource_kind not in valid_resource_values:
            raise ArgumentUsageError(
                f"Resource kind {resource_kind} is not supported for edge service {edge_service}. "
                f"Allowed values for this service are {valid_resource_values}"
            )
