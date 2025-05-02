# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, Optional

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Node, V1NodeList
from rich.padding import Padding
from rich.table import Table

from ....common import CheckTaskStatus
from ..common import (
    ACSA_MIN_NODE_KERNEL_VERSION,
    AIO_SUPPORTED_ARCHITECTURES,
    COLOR_STR_FORMAT,
    DISPLAY_BYTES_PER_GIGABYTE,
    MIN_NODE_MEMORY,
    MIN_NODE_STORAGE,
    MIN_NODE_VCPU,
)
from .check_manager import CheckManager
from .user_strings import NO_NODES_MSG, UNABLE_TO_FETCH_NODES_MSG

logger = get_logger(__name__)


def check_nodes(
    as_list: bool = False, kernel_version_check: Optional[bool] = False, storage_space_check: Optional[bool] = True
) -> Dict[str, Any]:
    from ...base import client

    check_manager = CheckManager(check_name="evalClusterNodes", check_desc="Evaluate cluster nodes")
    padding = (0, 0, 0, 8)
    target = "cluster/nodes"
    check_manager.add_target(target_name=target, conditions=["len(cluster/nodes)>=1"])

    try:
        core_client = client.CoreV1Api()
        nodes: V1NodeList = core_client.list_node()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = UNABLE_TO_FETCH_NODES_MSG
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
        if not nodes or not nodes.items:
            target_display = Padding(NO_NODES_MSG, padding)
            check_manager.add_target_eval(target_name=target, status=CheckTaskStatus.error.value, value=NO_NODES_MSG)
            check_manager.add_display(target_name=target, display=target_display)
            return check_manager.as_dict()

        check_manager.add_target_eval(
            target_name=target, status=CheckTaskStatus.success.value, value={"len(cluster/nodes)": len(nodes.items)}
        )
        table = _generate_node_table(
            check_manager=check_manager,
            nodes=nodes,
            acs_kernel_check=kernel_version_check,
            storage_space_check=storage_space_check,
        )

        check_manager.add_display(target_name=target, display=Padding("Node Resources", padding))
        check_manager.add_display(target_name=target, display=Padding(table, padding))

    return check_manager.as_dict(as_list)


def _generate_node_table(
    check_manager: CheckManager,
    nodes: V1NodeList,
    acs_kernel_check: Optional[bool] = False,
    storage_space_check: Optional[bool] = False,
) -> Table:
    from kubernetes.utils import parse_quantity

    from ....util.machinery import scoped_semver_import

    semver = scoped_semver_import()

    # prep table
    table = Table(show_header=True, header_style="bold", show_lines=True, caption_justify="left")
    for column_name, justify in [
        ("Name", "left"),
        ("Architecture", "left"),
        *([("Kernel version", "left")] if acs_kernel_check else []),
        *([("Ephemeral\nStorage (GB)", "left")] if storage_space_check else []),
        ("CPU (vCPU)", "left"),
        ("Memory (GB)", "left"),
    ]:
        table.add_column(column_name, justify=f"{justify}")
    table.add_row(
        *[
            COLOR_STR_FORMAT.format(color="cyan", value=value)
            for value in [
                "Minimum requirements",
                ", ".join(AIO_SUPPORTED_ARCHITECTURES),
                *([ACSA_MIN_NODE_KERNEL_VERSION] if acs_kernel_check else []),
                *([MIN_NODE_STORAGE[:-1]] if storage_space_check else []),
                MIN_NODE_VCPU,
                MIN_NODE_MEMORY[:-1],
            ]
        ]
    )
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
        table_tuples = [
            (
                "info.architecture",
                AIO_SUPPORTED_ARCHITECTURES,
                node.status.node_info.architecture,
            ),
            # Optional kernel version check
            *(
                [
                    (
                        "info.kernel_version",
                        ACSA_MIN_NODE_KERNEL_VERSION,
                        node.status.node_info.kernel_version,
                    )
                ]
                if acs_kernel_check
                else []
            ),
            # Optional storage space check
            *(
                [
                    (
                        "allocatable.ephemeral-storage",
                        MIN_NODE_STORAGE,
                        parse_quantity(node.status.allocatable.get("ephemeral-storage", 0)),
                    )
                ]
                if storage_space_check
                else []
            ),
            (
                "allocatable.cpu",
                MIN_NODE_VCPU,
                parse_quantity(node.status.allocatable.get("cpu", 0)),
            ),
            (
                "allocatable.memory",
                MIN_NODE_MEMORY,
                parse_quantity(node.status.allocatable.get("memory", 0)),
            ),
        ]
        for condition, expected, actual in table_tuples:
            # determine strings, expected, status
            condition_str = f"{condition}>={expected}"
            displayed = actual
            cell_status = CheckTaskStatus.success
            if condition == "info.architecture":
                condition_str = f"{condition} in ({','.join(expected)})"
                if actual not in expected:
                    row_status = cell_status = CheckTaskStatus.error
            elif condition == "info.kernel_version":
                if semver.parse(actual, optional_minor_and_patch=True) < semver.parse(
                    expected, optional_minor_and_patch=True
                ):
                    row_status = cell_status = CheckTaskStatus.error

            else:
                displayed = _get_display_number(displayed, expected)
                expected = parse_quantity(expected)
                if actual < expected:
                    row_status = cell_status = CheckTaskStatus.error
                actual = int(actual)
                # display as "xxG"
                if condition in ["allocatable.memory", "allocatable.ephemeral-storage"]:
                    actual = f"{int(actual / DISPLAY_BYTES_PER_GIGABYTE)}G"

            check_manager.add_target_conditions(target_name=node_target, conditions=[condition_str])
            check_manager.add_target_eval(target_name=node_target, status=cell_status.value, value={condition: actual})
            row_cells.append(COLOR_STR_FORMAT.format(color=cell_status.color, value=displayed))

        # overall node name color
        table.add_row(COLOR_STR_FORMAT.format(color=row_status.color, value=node_name), *row_cells)
    return table


def _get_display_number(number: int, number_with_unit: str) -> str:
    displayed = f"{number}"
    if number_with_unit.endswith("G"):
        displayed = "%.2f" % (number / DISPLAY_BYTES_PER_GIGABYTE)
    return displayed
