from tabnanny import check
from turtle import color
from typing import Any, Dict, List

from rich.padding import Padding

from azext_edge.edge.common import CheckTaskStatus
from azext_edge.edge.providers.check.base.display import colorize_string

from .common import PADDING_SIZE, ResourceOutputDetailLevel
from .base import CheckManager
from .akri import check_akri_deployment
from .dataflow import PADDING, check_dataflows_deployment
from .deviceregistry import check_deviceregistry_deployment
from .mq import check_mq_deployment
from .opcua import check_opcua_deployment


def check_summary(
    resource_name: str,
    resource_kinds: List[str],
    detail_level = ResourceOutputDetailLevel.summary.value,
    as_list: bool = False,
) -> None:
    service_check_dict = {
        "Akri": check_akri_deployment,
        "Broker": check_mq_deployment,
        "DeviceRegistry": check_deviceregistry_deployment,
        "OPCUA": check_opcua_deployment,
        "Dataflow": check_dataflows_deployment,
    }
    check_manager = CheckManager(check_name="evalAIOSummary", check_desc=f"Evaluate AIO components")
    for service_name, check_func in service_check_dict.items():
        result = check_func(
            detail_level=ResourceOutputDetailLevel.summary.value,
            resource_name=resource_name,
            as_list=as_list,
            resource_kinds=resource_kinds,
        )
        target = f"{service_name}"
        check_manager.add_target(target_name=target)
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"{service_name} checks",
                (0, 0, 0, PADDING),
            )
        )
        for obj in result:
            status = obj["status"]
            status_obj = CheckTaskStatus(status)
            emoji = status_obj.emoji
            color = status_obj.color

            # TODO - if status is not success or skipped, add directions to run --svc check
            description = obj["description"]
            check_manager.add_target_eval(
                target_name=target,
                status=status,
                value=obj,
            )
            # TODO - build a table for each svc
            check_manager.add_display(target_name=target, display=Padding(
                f"- {colorize_string(value=emoji, color=color)} {description}", (0, 0, 0, PADDING)
            ))
    return check_manager.as_dict(as_list=as_list)