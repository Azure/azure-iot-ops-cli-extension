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
    check_manager.add_target(
        target_name=target,
        conditions=[
            "len(cluster/nodes)>=1",
            "(cluster/nodes).each(node.status.allocatable[memory]>=140MiB)",
        ],
    )

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

        check_individual_nodes(nodes, check_manager)

    return check_manager.as_dict(as_list)


def check_individual_nodes(nodes: V1NodeList, check_manager: CheckManager):
    from kubernetes.utils import parse_quantity
    from rich.table import Table
    target = "cluster/nodes"
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
        # get node properties
        # metadata: V1ObjectMeta = node.metadata
        node_name = node.metadata.name
        # status: V1NodeStatus = node.status
        # info: V1NodeSystemInfo = status.node_info
        # capacity: dict = status.capacity

        # check_manager target for node
        node_target = f"cluster/nodes/{node_name}"
        check_manager.add_target(target_name=node_target)

        # parse decimal values
        memory_capacity = parse_quantity(node.status.capacity.get("memory"))
        cpu_capacity = parse_quantity(node.status.capacity.get("cpu"))
        storage_capacity = parse_quantity(node.status.capacity.get("ephemeral-storage"))

        # verify architecture
        # TODO - verify / constant
        arch_condition = "info.architecture"
        check_manager.add_target_conditions(
            target_name=node_target, conditions=[f"{arch_condition} in ({','.join(AIO_SUPPORTED_ARCHITECTURES)})"]
        )
        arch = node.status.node_info.architecture

        # arch eval
        arch_status = (
            CheckTaskStatus.success.value if arch in AIO_SUPPORTED_ARCHITECTURES else CheckTaskStatus.error.value
        )
        check_manager.add_target_eval(target_name=node_target, status=arch_status, value={arch_condition: arch})

        # arch display
        arch_status_color = "green" if arch_status == CheckTaskStatus.success.value else "red"
        arch_display = f"[{arch_status_color}]{arch}[/{arch_status_color}]"

        # TODO - constants for expected values
        # build node table row
        row_status = CheckTaskStatus.success.value
        row_cells = []
        for condition, expected, actual, actual_display in [
            (
                "condition.cpu",
                MIN_NODE_VCPU,
                cpu_capacity,
                f"{cpu_capacity}"
            ),
            (
                "condition.memory",
                MIN_NODE_MEMORY,
                memory_capacity,
                "%.2f" % (memory_capacity / DISPLAY_BYTES_PER_GIGABYTE),
            ),
            (
                "condition.ephemeral-storage",
                MIN_NODE_STORAGE,
                storage_capacity,
                "%.2f" % (storage_capacity / DISPLAY_BYTES_PER_GIGABYTE),
            ),
        ]:
            # add expected target (str)
            check_manager.add_target_conditions(target_name=node_target, conditions=[f"{condition}>={expected}"])

            # convert expected to decimal and check
            expected = parse_quantity(expected)
            cell_status = CheckTaskStatus.success.value
            if actual < expected:
                row_status = CheckTaskStatus.error.value
                cell_status = CheckTaskStatus.error.value

            cell_status_color = "green" if cell_status == CheckTaskStatus.success.value else "red"
            check_manager.add_target_eval(target_name=node_target, status=row_status, value={condition: int(actual)})

            row_cells.append(f"[{cell_status_color}]{actual_display}[/{cell_status_color}]")
        import pdb; pdb.set_trace()

        # overall node name color
        node_status_color = "green" if row_status == CheckTaskStatus.success.value else "red"
        node_name_display = f"[{node_status_color}]{node_name}[/{node_status_color}]"
        table.add_row(node_name_display, arch_display, *row_cells)
        node_memory_value = {}
        memory_status = CheckTaskStatus.success.value
        memory: str = node.status.allocatable["memory"]
        memory = memory.replace("Ki", "")
        memory: int = int(int(memory) / 1024)
        mem_colored = f"[green]{memory}[/green]"
        node_name = node.metadata.name
        node_memory_value[node_name] = f"{memory}MiB"

        if memory < 140:
            memory_status = CheckTaskStatus.warning.value
            mem_colored = f"[yellow]{memory}[/yellow]"

        node_memory_display = Padding(
            f"[bright_blue]{node_name}[/bright_blue] {mem_colored} MiB",
            (0, 0, 0, 8),
        )
        check_manager.add_target_eval(
            target_name=target,
            status=memory_status,
            value=node_memory_value,
        )
        check_manager.add_display(target_name=target, display=node_memory_display)
