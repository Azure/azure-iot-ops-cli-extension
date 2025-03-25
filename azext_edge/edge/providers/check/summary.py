# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, NamedTuple

from rich.padding import Padding
from rich.table import Table
from rich.console import NewLine

from ...common import OPCUA_SERVICE, CheckTaskStatus, OpsServiceType
from ...providers.edge_api import DATAFLOW_API_V1, DEVICEREGISTRY_API_V1, MQ_ACTIVE_API, OPCUA_API_V1
from .akri import check_akri_deployment
from .base import CheckManager
from .base.display import colorize_string
from .common import ResourceOutputDetailLevel
from .dataflow import PADDING, check_dataflows_deployment
from .deviceregistry import check_deviceregistry_deployment
from .mq import check_mq_deployment
from .opcua import check_opcua_deployment


class ServiceCheck(NamedTuple):
    svc: str
    title: str
    target: str
    check_func: callable


def check_summary(
    resource_name: str,
    resource_kinds: List[str],
    detail_level=ResourceOutputDetailLevel.summary.value,
    as_list: bool = False,
) -> dict:
    # define checks
    service_checks: List[ServiceCheck] = [
        ServiceCheck(
            svc=OpsServiceType.akri.value,
            title="Akri",
            target="Akri",
            check_func=check_akri_deployment,
        ),
        ServiceCheck(
            svc=OpsServiceType.mq.value,
            title="Broker",
            target=MQ_ACTIVE_API.as_str(),
            check_func=check_mq_deployment,
        ),
        ServiceCheck(
            svc=OpsServiceType.deviceregistry.value,
            title="DeviceRegistry",
            target=DEVICEREGISTRY_API_V1.as_str(),
            check_func=check_deviceregistry_deployment,
        ),
        ServiceCheck(
            svc=OPCUA_SERVICE,
            title="OPCUA",
            target="OPCUA",
            check_func=check_opcua_deployment,
        ),
        ServiceCheck(
            svc=OpsServiceType.dataflow.value,
            title="Dataflow",
            target=DATAFLOW_API_V1.as_str(),
            check_func=check_dataflows_deployment,
        ),
    ]

    check_manager = CheckManager(check_name="evalAIOSummary", check_desc="Service summary checks")
    for check in service_checks:

        # run checks for service
        result = check.check_func(
            detail_level=ResourceOutputDetailLevel.summary.value,
            resource_name=resource_name,
            as_list=as_list,
            resource_kinds=resource_kinds,
        )

        # add service check results to check manager
        target = check.target
        check_manager.add_target(target_name=target)
        check_manager.add_display(
            target_name=target,
            display=Padding(
                check.title,
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
                value={obj.get("name", "checkResult"): status},
            )
            # add row to grid
            grid.add_row(colorize_string(value=emoji, color=color), description)

        # display grid
        check_manager.add_display(target_name=target, display=Padding(grid, (0, 0, 0, PADDING)))

        # service check suggestion footer
        if add_footer:
            footer = ":magnifying_glass_tilted_left:" + colorize_string(
                f" See details by running: az iot ops check --svc {check.svc}"
            )
            check_manager.add_display(target_name=target, display=NewLine())
            check_manager.add_display(target_name=target, display=Padding(footer, (0, 0, 0, PADDING)))

    return check_manager.as_dict(as_list=as_list)
