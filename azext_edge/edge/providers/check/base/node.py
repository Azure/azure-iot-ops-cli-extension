# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Node, V1NodeList, V1StorageClassList
from rich.padding import Padding
from rich.table import Table

from azext_edge.edge.providers.check.base.display import colorize_string

from ....common import CheckTaskStatus
from ..common import (
    AIO_SUPPORTED_ARCHITECTURES,
    COLOR_STR_FORMAT,
    DISPLAY_BYTES_PER_GIGABYTE,
    MIN_NODE_MEMORY,
    MIN_NODE_VCPU,
)
from .check_manager import CheckManager
from .user_strings import NO_NODES_MSG, UNABLE_TO_FETCH_NODES_MSG

logger = get_logger(__name__)


def check_storage_classes(acs_config: dict, as_list: bool = False) -> Dict[str, Any]:
    from ...base import client

    expected_classes = acs_config.get("feature.diskStorageClass", [])
    check_manager = CheckManager(check_name="evalStorageClasses", check_desc="Evaluate storage classes")
    # padding = (0, 0, 0, 8)
    target = "cluster/storage-classes"
    check_manager.add_target(
        target_name=target,
        conditions=["len(cluster/storage-classes)>=1", f"contains(cluster/storage-classes, any({expected_classes}))"],
    )

    try:
        storage_client = client.StorageV1Api()
        storage_classes: V1StorageClassList = storage_client.list_storage_class()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = "Unable to fetch storage classes"
        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.error.value,
            value=api_error_text,
        )
        # check_manager.add_display(
        #     target_name=target,
        #     display=Padding(api_error_text, (0, 0, 0, 8)),
        # )
    else:
        if not storage_classes or not storage_classes.items:
            # target_display = Padding("No storage classes available", padding)
            check_manager.add_target_eval(
                target_name=target, status=CheckTaskStatus.error.value, value="No storage classes available"
            )
            # check_manager.add_display(target_name=target, display=target_display)
            return check_manager.as_dict()

        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.success.value,
            value={"len(cluster/storage-classes)": len(storage_classes.items)},
        )

        expected_class_names = expected_classes.split(",")
        storage_class_names = [sc.metadata.name for sc in storage_classes.items]
        matches = [sc for sc in storage_class_names if sc in expected_class_names]
        storage_status = CheckTaskStatus.success if len(matches) else CheckTaskStatus.error

        # check_manager.add_display(
        #     target_name=target,
        #     display=Padding(
        #         f"Expected classes: {colorize_string(expected_class_names)}, configured: {colorize_string(storage_class_names, storage_status.color)}",
        #         padding,
        #     ),
        # )

        check_manager.add_target_eval(
            target_name=target,
            status=storage_status.value,
            value=",".join(storage_class_names),
        )

    return check_manager.as_dict(as_list)


def check_nodes(as_list: bool = False) -> Dict[str, Any]:
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
        table = _generate_node_table(check_manager, nodes)

        check_manager.add_display(target_name=target, display=Padding("Node Resources", padding))
        check_manager.add_display(target_name=target, display=Padding(table, padding))

    return check_manager.as_dict(as_list)


def _generate_node_table(check_manager: CheckManager, nodes: V1NodeList) -> Table:
    from kubernetes.utils import parse_quantity

    # prep table
    table = Table(show_header=True, header_style="bold", show_lines=True, caption_justify="left")
    for column_name, justify in [
        ("Name", "left"),
        ("Architecture", "right"),
        ("CPU (vCPU)", "right"),
        ("Memory (GB)", "right"),
        # ("Storage (GB)", "right"),
    ]:
        table.add_column(column_name, justify=f"{justify}")
    table.add_row(
        *[
            COLOR_STR_FORMAT.format(color="cyan", value=value)
            for value in [
                "Minimum requirements",
                ", ".join(AIO_SUPPORTED_ARCHITECTURES),
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
                displayed = _get_display_number(displayed, expected)
                expected = parse_quantity(expected)
                if actual < expected:
                    row_status = CheckTaskStatus.error
                    cell_status = CheckTaskStatus.error
                actual = int(actual)

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
