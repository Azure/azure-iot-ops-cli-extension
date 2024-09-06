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
from .display import add_display_and_eval, colorize_string
from ..common import COLOR_STR_FORMAT, POD_CONDITION_TEXT_MAP, ResourceOutputDetailLevel
from ...base import get_namespaced_pods_by_prefix
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
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    pods: Optional[List[V1Pod]] = None,
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

    # If pods are not provided, get them
    # if pods is None:
    #     pods = []
    #     pods_captured = False

    # for pod, label in pod_with_labels:
    #     target_service_pod = f"pod/{pod}"
    #     if not pods_captured:
    #         pods = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace, label_selector=label)
    pod_displays = []

    for pod in pods:
        all_healthy = process_pod_status2(
            check_manager=check_manager,
            target=target,
            pod=pod,
            display_padding=padding,
            namespace=namespace,
            detail_level=detail_level,
        )

        add_footer = add_footer or not all_healthy

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


def process_pod_status(
    check_manager: CheckManager,
    target: str,
    target_service_pod: str,
    pods: List[V1Pod],
    display_padding: int,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    table: Optional[Table] = None,
) -> bool:

    def _decorate_pod_condition(condition: bool) -> Tuple[str, str]:
        if condition:
            return f"[green]{condition}[/green]", CheckTaskStatus.success.value
        return f"[red]{condition}[/red]", CheckTaskStatus.error.value

    pod_eval_statuses = []

    if not pods:
        add_display_and_eval(
            check_manager=check_manager,
            target_name=target,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=CheckTaskStatus.warning.value,
            eval_value=None,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, display_padding),
        )
        return False

    for pod in pods:
        target_service_pod = f"pod/{pod.metadata.name}"

        pod_conditions = [
            f"{target_service_pod}.status.phase",
            f"{target_service_pod}.status.conditions",
        ]

        if check_manager.targets.get(target, {}).get(namespace, {}).get("conditions", None):
            check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)
        else:
            check_manager.set_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)

        pod_dict = pod.to_dict()
        pod_name = pod_dict["metadata"]["name"]
        pod_phase = pod_dict.get("status", {}).get("phase")
        pod_conditions: list = pod_dict.get("status", {}).get("conditions", [])
        pod_phase_deco, status = decorate_pod_phase(pod_phase)

        pod_eval_value = {}
        pod_eval_status = status
        pod_eval_value["status.phase"] = pod_phase

        conditions_readiness = True
        conditions_display_list: List[Tuple[str, str]] = []
        unknown_conditions_display_list: List[Tuple[str, str]] = []

        # When pod in obnormal state, sometimes the conditions are not available
        if pod_conditions:
            for condition in pod_conditions:
                type = condition["type"]
                condition_type = POD_CONDITION_TEXT_MAP.get(type)

                if condition_type:
                    condition_status = condition.get("status") == "True"
                    conditions_readiness = conditions_readiness and condition_status
                    pod_condition_deco, status = _decorate_pod_condition(condition=condition_status)
                    pod_eval_status = status if status != CheckTaskStatus.success.value else pod_eval_status
                else:
                    condition_type = type
                    condition_status = condition.get("status")

                formatted_reason = ""
                condition_reason = condition.get("reason", "")

                if condition_reason:
                    formatted_reason = f"[red]Reason: {condition_reason}[/red]"

                known_condition_values = [value.replace(" ", "").lower() for value in POD_CONDITION_TEXT_MAP.values()]
                if condition_type.replace(" ", "").lower() in known_condition_values:
                    conditions_display_list.append((f"{condition_type}: {pod_condition_deco}", formatted_reason))
                else:
                    unknown_conditions_display_list.append((f"{condition_type}: {condition_status}", formatted_reason))

                pod_eval_value[f"status.conditions.{type.lower()}"] = condition_status

        if not conditions_readiness:
            pod_eval_status = CheckTaskStatus.error.value
        elif unknown_conditions_display_list and pod_eval_status != CheckTaskStatus.error.value:
            pod_eval_status = CheckTaskStatus.warning.value

        pod_eval_statuses.append(pod_eval_status)

        _add_pod_health_display(
            table=table,
            pod_name=pod_name,
            pod_phase_deco=pod_phase_deco,
            pod_conditions=pod_conditions,
            pod_eval_status=pod_eval_status,
            conditions_readiness=conditions_readiness,
            conditions_display_list=conditions_display_list,
            unknown_conditions_display_list=unknown_conditions_display_list,
            detail_level=detail_level,
        )

        check_manager.add_target_eval(
            target_name=target,
            status=pod_eval_status,
            value=pod_eval_value,
            namespace=namespace,
            resource_name=target_service_pod,
        )

    # Return True if all pods are healthy
    return all([status == CheckTaskStatus.success.value for status in pod_eval_statuses])


def process_pod_status2(
    check_manager: CheckManager,
    target: str,
    pod: V1Pod,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> bool:

    def _decorate_pod_condition(condition: bool) -> Tuple[str, str]:
        if condition:
            return f"[green]{condition}[/green]", CheckTaskStatus.success.value
        return f"[red]{condition}[/red]", CheckTaskStatus.error.value

    target_service_pod = f"pod/{pod.metadata.name}"

    pod_conditions = [
        f"{target_service_pod}.status.phase",
        f"{target_service_pod}.status.conditions",
    ]

    if check_manager.targets.get(target, {}).get(namespace, {}).get("conditions", None):
        check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)
    else:
        check_manager.set_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)

    pod_dict = pod.to_dict()
    pod_name = pod_dict["metadata"]["name"]
    pod_phase = pod_dict.get("status", {}).get("phase")
    pod_conditions: list = pod_dict.get("status", {}).get("conditions", [])
    pod_phase_deco, status = decorate_pod_phase(pod_phase)

    pod_eval_value = {}
    pod_eval_status = status
    pod_eval_value["status.phase"] = pod_phase

    conditions_readiness = True
    conditions_display_list: List[Tuple[str, str]] = []
    unknown_conditions_display_list: List[Tuple[str, str]] = []

    # When pod in obnormal state, sometimes the conditions are not available
    if pod_conditions:
        for condition in pod_conditions:
            type = condition["type"]
            condition_type = POD_CONDITION_TEXT_MAP.get(type)

            if condition_type:
                condition_status = condition.get("status") == "True"
                conditions_readiness = conditions_readiness and condition_status
                pod_condition_deco, status = _decorate_pod_condition(condition=condition_status)
                pod_eval_status = status if status != CheckTaskStatus.success.value else pod_eval_status
            else:
                condition_type = type
                condition_status = condition.get("status")

            formatted_reason = ""
            condition_reason = condition.get("reason", "")

            if condition_reason:
                formatted_reason = f"[red]Reason: {condition_reason}[/red]"

            known_condition_values = [value.replace(" ", "").lower() for value in POD_CONDITION_TEXT_MAP.values()]
            if condition_type.replace(" ", "").lower() in known_condition_values:
                conditions_display_list.append((f"{condition_type}: {pod_condition_deco}", formatted_reason))
            else:
                unknown_conditions_display_list.append((f"{condition_type}: {condition_status}", formatted_reason))

            pod_eval_value[f"status.conditions.{type.lower()}"] = condition_status

    if not conditions_readiness:
        pod_eval_status = CheckTaskStatus.error.value
    elif unknown_conditions_display_list and pod_eval_status != CheckTaskStatus.error.value:
        pod_eval_status = CheckTaskStatus.warning.value

    # _add_pod_health_display(
    #     table=table,
    #     pod_name=pod_name,
    #     pod_phase_deco=pod_phase_deco,
    #     pod_conditions=pod_conditions,
    #     pod_eval_status=pod_eval_status,
    #     conditions_readiness=conditions_readiness,
    #     conditions_display_list=conditions_display_list,
    #     unknown_conditions_display_list=unknown_conditions_display_list,
    #     detail_level=detail_level,
    # )

    check_manager.add_target_eval(
        target_name=target,
        status=pod_eval_status,
        value=pod_eval_value,
        namespace=namespace,
        resource_name=target_service_pod,
    )

    # Return True if all pods are healthy
    return all([status == CheckTaskStatus.success.value for status in pod_eval_statuses])


def _add_pod_health_display(
    pod_name: str,
    pod_phase_deco: str,
    pod_conditions: List,
    pod_eval_status: str,
    conditions_readiness: bool,
    conditions_display_list: List[Tuple[str, str]],
    unknown_conditions_display_list: List[Tuple[str, str]],
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    table: Optional[Table] = None,
) -> None:
    pod_health_text = f"Pod {{[bright_blue]{pod_name}[/bright_blue]}}"

    if detail_level != ResourceOutputDetailLevel.summary.value:
        pod_health_text = f"\n{pod_health_text}"

    if detail_level == ResourceOutputDetailLevel.summary.value:
        status_obj = CheckTaskStatus(pod_eval_status)
        emoji = status_obj.emoji
        color = status_obj.color
        table.add_row(colorize_string(value=emoji, color=color), pod_health_text)
    else:
        pod_conditions_text = "N/A"

        if pod_conditions:

            if detail_level == ResourceOutputDetailLevel.detail.value:
                pod_conditions_text = "[green]Ready[/green]" if conditions_readiness else ""
            else:
                pod_conditions_text = ""

            # Only display the condition if it is not ready when detail level is 1, or the detail level is 2
            for condition, reason in conditions_display_list:
                condition_not_ready = condition.endswith("[red]False[/red]")
                if (
                    detail_level == ResourceOutputDetailLevel.detail.value and condition_not_ready
                ) or detail_level == ResourceOutputDetailLevel.verbose.value:
                    pod_conditions_text += f"{condition}\n"

                    if reason:
                        pod_conditions_text += f"{reason}\n"

            if conditions_readiness:
                for condition, reason in unknown_conditions_display_list:
                    condition_text: str = f"[yellow]Irregular Condition {condition} found.[/yellow]"
                    pod_conditions_text += f"{condition_text}\n"

                    if reason and detail_level == ResourceOutputDetailLevel.verbose.value:
                        pod_conditions_text += f"{reason}\n"

        if table:
            table.add_row(pod_name, pod_phase_deco, pod_conditions_text)
