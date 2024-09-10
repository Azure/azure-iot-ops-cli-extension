# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from rich.padding import Padding
from rich.table import Table
from kubernetes.client.models import V1Pod
from typing import List, Optional, Tuple

from .check_manager import CheckManager
from .display import colorize_string
from ..common import (
    COLOR_STR_FORMAT,
    POD_CONDITION_TEXT_MAP,
    PodStatusConditionResult,
    PodStatusResult,
    ResourceOutputDetailLevel,
)
from ....common import CheckTaskStatus


logger = get_logger(__name__)


def decorate_pod_phase(phase: str) -> Tuple[str, str]:
    from ....common import PodState

    status = PodState.map_to_status(phase)
    return COLOR_STR_FORMAT.format(color=status.color, value=phase), status.value


def evaluate_pod_health(
    check_manager: CheckManager,
    target: str,
    namespace: str,
    padding: int,
    pods: List[V1Pod],
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:

    if not pods:
        return

    # prep table
    table = Table(show_header=True, header_style="bold", show_lines=True, caption_justify="left")

    if detail_level != ResourceOutputDetailLevel.summary.value:
        for column_name, justify in [
            ("Pod Name", "left"),
            ("Phase", "left"),
            ("Conditions", "left"),
        ]:
            table.add_column(column_name, justify=f"{justify}")
    else:
        table = Table.grid(padding=(0, 0, 0, 2))

    add_footer = False
    pod_statuses = []

    for pod in pods:
        pod_status_result: PodStatusResult = _process_pod_status(
            check_manager=check_manager,
            target=target,
            pod=pod,
            namespace=namespace,
            detail_level=detail_level,
        )
        pod_statuses.append(pod_status_result.eval_status)
        table.add_row(*pod_status_result.display_strings)

    add_footer = not all([status == CheckTaskStatus.success.value for status in pod_statuses])

    if pods:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(table, (0, 0, 0, padding)),
        )

    if add_footer:
        footer = ":magnifying_glass_tilted_left:" + colorize_string(
            " See more details by attaching : --detail-level 1 or --detail-level 2"
        )
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(footer, (0, 0, 0, padding)),
        )


def _process_pod_status(
    check_manager: CheckManager,
    target: str,
    pod: V1Pod,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> PodStatusResult:

    target_service_pod = f"pod/{pod.metadata.name}"

    conditions = [
        f"{target_service_pod}.status.phase",
        f"{target_service_pod}.status.conditions",
    ]

    if check_manager.targets.get(target, {}).get(namespace, {}).get("conditions", None):
        check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=conditions)
    else:
        check_manager.set_target_conditions(target_name=target, namespace=namespace, conditions=conditions)

    pod_dict = pod.to_dict()
    pod_name = pod_dict["metadata"]["name"]
    pod_phase = pod_dict.get("status", {}).get("phase")
    pod_conditions: list = pod_dict.get("status", {}).get("conditions", [])
    pod_phase_deco, status = decorate_pod_phase(pod_phase)

    pod_eval_value = {}
    pod_eval_status = status
    pod_eval_value["status.phase"] = pod_phase

    conditions_readiness = True
    conditions_display_list: List[PodStatusConditionResult] = []
    unknown_conditions_display_list: List[PodStatusConditionResult] = []

    # When pod in obnormal state, sometimes the conditions are not available
    if pod_conditions:
        known_condition_values = [value.replace(" ", "").lower() for value in POD_CONDITION_TEXT_MAP.values()]
        for condition in pod_conditions:
            type = condition["type"]
            condition_type = POD_CONDITION_TEXT_MAP.get(type)

            if condition_type:
                condition_status = condition.get("status").lower() == "true"
                conditions_readiness = conditions_readiness and condition_status
                status = CheckTaskStatus.success.value if condition_status else CheckTaskStatus.error.value
                pod_condition_deco = colorize_string(value=condition_status, color=CheckTaskStatus(status).color)
                pod_eval_status = status if status != CheckTaskStatus.success.value else pod_eval_status
            else:
                condition_type = type
                condition_status = condition.get("status")

            formatted_reason = ""
            condition_reason = condition.get("reason", "")

            if condition_reason:
                formatted_reason = f"[red]Reason: {condition_reason}[/red]"

            if condition_type.replace(" ", "").lower() in known_condition_values:
                conditions_display_list.append(
                    PodStatusConditionResult(
                        condition_string=f"{condition_type}: {pod_condition_deco}",
                        failed_reason=formatted_reason,
                        eval_status=status,
                    )
                )
            else:
                unknown_conditions_display_list.append(
                    PodStatusConditionResult(
                        condition_string=f"{condition_type}: {condition_status}",
                        failed_reason=formatted_reason,
                        eval_status=status,
                    )
                )

            pod_eval_value[f"status.conditions.{type.lower()}"] = condition_status

    if not conditions_readiness:
        pod_eval_status = CheckTaskStatus.error.value
    elif unknown_conditions_display_list and pod_eval_status != CheckTaskStatus.error.value:
        pod_eval_status = CheckTaskStatus.warning.value

    check_manager.add_target_eval(
        target_name=target,
        status=pod_eval_status,
        value=pod_eval_value,
        namespace=namespace,
        resource_name=target_service_pod,
    )

    # text to display in the table
    pod_health_text = f"Pod {{[bright_blue]{pod_name}[/bright_blue]}}"

    if detail_level != ResourceOutputDetailLevel.summary.value:
        pod_health_text = f"\n{pod_health_text}"

    if detail_level == ResourceOutputDetailLevel.summary.value:
        status_obj = CheckTaskStatus(pod_eval_status)
        emoji = status_obj.emoji
        color = status_obj.color
        return PodStatusResult(
            display_strings=[colorize_string(value=emoji, color=color), pod_health_text], eval_status=pod_eval_status
        )
    else:
        pod_conditions_text = "N/A"

        if pod_conditions:

            if detail_level == ResourceOutputDetailLevel.detail.value:
                pod_conditions_text = "[green]Ready[/green]" if conditions_readiness else ""
            else:
                pod_conditions_text = ""

            # Only display the condition if it is not ready when detail level is 1, or the detail level is 2
            for condition_result in conditions_display_list:
                condition_not_ready = condition_result.eval_status == CheckTaskStatus.error.value
                if (
                    detail_level == ResourceOutputDetailLevel.detail.value and condition_not_ready
                ) or detail_level == ResourceOutputDetailLevel.verbose.value:
                    pod_conditions_text += f"{condition_result.condition_string}\n"

                    if condition_result.failed_reason:
                        pod_conditions_text += f"{condition_result.failed_reason}\n"

            if conditions_readiness:
                for condition_result in unknown_conditions_display_list:
                    condition_text: str = (
                        f"[yellow]Irregular Condition {condition_result.condition_string} found.[/yellow]"
                    )
                    pod_conditions_text += f"{condition_text}\n"

                    if condition_result.failed_reason and detail_level == ResourceOutputDetailLevel.verbose.value:
                        pod_conditions_text += f"{condition_result.failed_reason}\n"

        return PodStatusResult(
            display_strings=[pod_name, pod_phase_deco, pod_conditions_text], eval_status=pod_eval_status
        )
