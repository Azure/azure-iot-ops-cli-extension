# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List

from rich.padding import Padding
from rich.table import Table

from ...common import CheckTaskStatus, OpsServiceType
from .akri import check_akri_deployment
from .base import CheckManager
from .base.display import colorize_string
from .common import ResourceOutputDetailLevel
from .dataflow import PADDING, check_dataflows_deployment
from .deviceregistry import check_deviceregistry_deployment
from .mq import check_mq_deployment
from .opcua import check_opcua_deployment


def check_summary(
    resource_name: str,
    resource_kinds: List[str],
    detail_level=ResourceOutputDetailLevel.summary.value,
    as_list: bool = False,
) -> None:
    # define checks
    service_checks = [
        {
            "svc": OpsServiceType.akri.value,
            "title": "Akri",
            "check": check_akri_deployment,
        },
        {
            "svc": OpsServiceType.mq.value,
            "title": "Broker",
            "check": check_mq_deployment,
        },
        {
            "svc": OpsServiceType.deviceregistry.value,
            "title": "DeviceRegistry",
            "check": check_deviceregistry_deployment,
        },
        {
            "svc": OpsServiceType.opcua.value,
            "title": "OPCUA",
            "check": check_opcua_deployment,
        },
        {
            "svc": OpsServiceType.dataflow.value,
            "title": "Dataflow",
            "check": check_dataflows_deployment,
        },
    ]

    check_manager = CheckManager(check_name="evalAIOSummary", check_desc="AIO components")
    for check in service_checks:
        service_name = check.get("title")
        check_func = check.get("check")
        svc = check.get("svc")

        # run checks for service
        result = check_func(
            detail_level=ResourceOutputDetailLevel.summary.value,
            resource_name=resource_name,
            as_list=as_list,
            resource_kinds=resource_kinds,
        )

        # add service check results to check manager
        target = f"{service_name}"
        check_manager.add_target(target_name=target)
        check_manager.add_display(
            target_name=target,
            display=Padding(
                service_name,
                (0, 0, 0, PADDING),
            ),
        )

        # create grid for service check results
        grid = Table.grid(padding=(0, 0, 0, 2))
        add_footer = False

        # parse check results
        for obj in result:
            status = obj.get("status")
            status_obj = CheckTaskStatus(status)
            if status_obj == CheckTaskStatus.error or status_obj == CheckTaskStatus.warning:
                add_footer = True
            emoji = status_obj.emoji
            color = status_obj.color
            description = obj.get("description")
            check_manager.add_target_eval(
                target_name=target,
                status=status,
                value={
                    obj.get("name", "checkResult"): status
                },
            )
            # add row to grid
            grid.add_row(colorize_string(value=emoji, color=color), description)

        # display grid
        check_manager.add_display(target_name=target, display=Padding(grid, (0, 0, 0, PADDING)))

        # service check suggestion footer
        if add_footer:
            footer = f"See details by running: az iot ops check --svc {svc}"
            check_manager.add_display(target_name=target, display=Padding(footer, (0, 0, 0, PADDING)))

    return check_manager.as_dict(as_list=as_list)
