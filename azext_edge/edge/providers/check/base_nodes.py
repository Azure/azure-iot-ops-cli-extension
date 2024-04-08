# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1Node,
    V1NodeList
)
from rich.console import NewLine
from rich.padding import Padding
from rich.table import Table

from .check_manager import CheckManager
from .common import AIO_SUPPORTED_ARCHITECTURES, DISPLAY_BYTES_PER_GIGABYTE, MIN_NODE_MEMORY, MIN_NODE_STORAGE, MIN_NODE_VCPU
from ...common import CheckTaskStatus

from ..base import (
    client,
)

logger = get_logger(__name__)


def check_nodes(as_list: bool = False) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalClusterNodes", check_desc="Evaluate cluster nodes")
    padding = (0, 0, 0, 8)
    target = "cluster/nodes"
    check_manager.add_target(target_name=target, conditions=["len(cluster/nodes)>=1"])

    try:
        core_client = client.CoreV1Api()
        nodes: V1NodeList = core_client.list_node()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = "Unable to fetch nodes. Is there connectivity to the cluster?"
        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.error.value,
            value=api_error_text,
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(api_error_text, (0, 0, 0, 8)),
        )
    else:
        target_display = "At least 1 node is required. {}"
        if not nodes or not nodes.items:
            target_display = Padding("No nodes detected.", padding)
            check_manager.add_target_eval(
                target_name=target, status=CheckTaskStatus.error.value, value="No nodes detected.")
            check_manager.add_display(target_name=target, display=target_display)
            return check_manager.as_dict()

        if len(nodes.items) > 1:
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    "[yellow]Currently, only single-node clusters are officially supported for AIO deployments", padding
                ),
            )

        target_display = Padding(
            target_display.format(f"[green]Detected {len(nodes.items)}[/green]."),
            (0, 0, 0, 8),
        )
        check_manager.add_display(target_name=target, display=target_display)
        check_manager.add_display(target_name=target, display=NewLine())

        table = generate_node_table(check_manager, nodes)
    check_manager.add_display(target_name=target, display=Padding(table, padding))

    return check_manager.as_dict(as_list)


def generate_node_table(check_manager: CheckManager, nodes: V1NodeList) -> Table:
    from kubernetes.utils import parse_quantity
    # prep table
    table = Table(
        show_header=True, header_style="bold", show_lines=True, caption="Node resources", caption_justify="left"
    )
    for column_name, justify in [
        ("Name", "left"),
        ("Architecture", "right"),
        ("CPU (vCPU)", "right"),
        ("Memory (GB)", "right"),
        ("Storage (GB)", "right"),
    ]:
        table.add_column(column_name, justify=f"{justify}")

    node: V1Node
    for node in nodes.items:
        node_name = node.metadata.name

        # check_manager target for node
        node_target = f"cluster/nodes/{node_name}"
        check_manager.add_target(target_name=node_target)

        # verify architecture
        # build node table row
        row_status = CheckTaskStatus.success
        row_cells = []
        for condition, expected, actual in [
            (
                "info.architecture",
                AIO_SUPPORTED_ARCHITECTURES,
                node.status.node_info.architecture,
            ),
            (
                "condition.cpu",
                MIN_NODE_VCPU,
                parse_quantity(node.status.capacity.get("cpu", 0)),
            ),
            (
                "condition.memory",
                MIN_NODE_MEMORY,
                parse_quantity(node.status.capacity.get("memory", 0)),
            ),
            (
                "condition.ephemeral-storage",
                MIN_NODE_STORAGE,
                parse_quantity(node.status.capacity.get("ephemeral-storage", 0)),
            ),
        ]:
            # determine strings, expected, status
            condition_str = f"{condition}>={expected}"
            displayed = actual
            cell_status = CheckTaskStatus.success
            if isinstance(expected, list):
                condition_str = f"{condition} in ({','.join(expected)})"
                if actual not in expected:
                    row_status = CheckTaskStatus.error
                    cell_status = CheckTaskStatus.error
            else:
                displayed = get_display_number(displayed, expected)
                expected = parse_quantity(expected)
                if actual < expected:
                    row_status = CheckTaskStatus.error
                    cell_status = CheckTaskStatus.error
                actual = int(actual)

            check_manager.add_target_conditions(target_name=node_target, conditions=[condition_str])
            check_manager.add_target_eval(target_name=node_target, status=cell_status.value, value={condition: actual})
            row_cells.append(f"[{cell_status.color}]{displayed}[/{cell_status.color}]")

        # overall node name color
        node_name_display = f"[{row_status.color}]{node_name}[/{row_status.color}]"
        table.add_row(node_name_display, *row_cells)
    return table


def get_display_number(number: int, number_with_unit: str) -> str:
    displayed = f"{number}"
    if number_with_unit.endswith("G"):
        displayed = "%.2f" % (number / DISPLAY_BYTES_PER_GIGABYTE)
    return displayed
