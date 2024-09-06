# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from rich.padding import Padding
from kubernetes.client.models import V1Pod
from typing import List, Optional, Tuple

from .check_manager import CheckManager
from .display import add_display_and_eval
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
    namespace: str,
    target: str,
    pod: str,
    display_padding: int,
    service_label: Optional[str] = None,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    target_service_pod = f"pod/{pod}"
    pods = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace, label_selector=service_label)

    process_pod_status(
        check_manager=check_manager,
        target=target,
        target_service_pod=target_service_pod,
        pods=pods,
        display_padding=display_padding,
        namespace=namespace,
        detail_level=detail_level,
    )


def process_pod_status(
    check_manager: CheckManager,
    target: str,
    target_service_pod: str,
    pods: List[V1Pod],
    display_padding: int,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:

    def _decorate_pod_condition(condition: bool) -> Tuple[str, str]:
        if condition:
            return f"[green]{condition}[/green]", CheckTaskStatus.success.value
        return f"[red]{condition}[/red]", CheckTaskStatus.error.value

    # TODO: Consolidate more using table view
    if not pods:
        return add_display_and_eval(
            check_manager=check_manager,
            target_name=target,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=CheckTaskStatus.warning.value,
            eval_value=None,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, display_padding),
        )

    for pod in pods:
        target_service_pod = f"pod/{pod.metadata.name}"

        pod_conditions = [
            f"{target_service_pod}.status.phase",
            f"{target_service_pod}.status.conditions",
        ]

        if check_manager.targets.get(target, {}).get(namespace, {}).get("conditions", None):
            check_manager.add_target_conditions(
                target_name=target, namespace=namespace, conditions=pod_conditions
            )
        else:
            check_manager.set_target_conditions(
                target_name=target, namespace=namespace, conditions=pod_conditions
            )

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

                known_condition_values = [
                    value.replace(" ", "").lower() for value in POD_CONDITION_TEXT_MAP.values()
                ]
                if condition_type.replace(" ", "").lower() in known_condition_values:
                    conditions_display_list.append(
                        (f"{condition_type}: {pod_condition_deco}", formatted_reason)
                    )
                else:
                    unknown_conditions_display_list.append(
                        (f"{condition_type}: {condition_status}", formatted_reason)
                    )

                pod_eval_value[f"status.conditions.{type.lower()}"] = condition_status

        if not conditions_readiness:
            pod_eval_status = CheckTaskStatus.error.value
        else:
            # add warning if there are unknown conditions when known conditions are all in good state
            if unknown_conditions_display_list and pod_eval_status != CheckTaskStatus.error.value:
                pod_eval_status = CheckTaskStatus.warning.value

        _add_pod_health_display(
            check_manager=check_manager,
            target=target,
            namespace=namespace,
            pod_name=pod_name,
            pod_phase_deco=pod_phase_deco,
            pod_conditions=pod_conditions,
            pod_eval_status=pod_eval_status,
            conditions_readiness=conditions_readiness,
            conditions_display_list=conditions_display_list,
            unknown_conditions_display_list=unknown_conditions_display_list,
            display_padding=display_padding,
            detail_level=detail_level,
        )

        check_manager.add_target_eval(
            target_name=target,
            status=pod_eval_status,
            value=pod_eval_value,
            namespace=namespace,
            resource_name=target_service_pod,
        )


def _add_pod_health_display(
    check_manager: CheckManager,
    target: str,
    namespace: str,
    pod_name: str,
    pod_phase_deco: str,
    pod_conditions: List,
    pod_eval_status: str,
    conditions_readiness: bool,
    conditions_display_list: List[Tuple[str, str]],
    unknown_conditions_display_list: List[Tuple[str, str]],
    display_padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    pod_health_status = "[green]Healthy[/green]"

    if pod_eval_status == CheckTaskStatus.error.value:
        pod_health_status = "[red]Unhealthy[/red]"
    elif pod_eval_status == CheckTaskStatus.warning.value:
        pod_health_status = "[yellow]Indeterminate[/yellow]"

    pod_health_text = f"Pod {{[bright_blue]{pod_name}[/bright_blue]}} is {pod_health_status}"

    if detail_level != ResourceOutputDetailLevel.summary.value:
        pod_health_text = f"\n{pod_health_text}"

    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding(pod_health_text, (0, 0, 0, display_padding)),
    )

    padding = display_padding + 4

    if detail_level != ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"- Phase: {pod_phase_deco}", (0, 0, 0, padding)),
        )

        if pod_conditions:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    (
                        "- Conditions: [green]Ready[/green]"
                        if conditions_readiness
                        else "- Conditions: [red]Not Ready[/red]"
                    ),
                    (0, 0, 0, padding),
                ),
            )

            # Only display the condition if it is not ready when detail level is 1, or the detail level is 2
            for condition, reason in conditions_display_list:
                condition_not_ready = condition.endswith("[red]False[/red]")
                if (
                    detail_level == ResourceOutputDetailLevel.detail.value and condition_not_ready
                ) or detail_level == ResourceOutputDetailLevel.verbose.value:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(condition, (0, 0, 0, padding + 4)),
                    )

                    if reason:
                        check_manager.add_display(
                            target_name=target,
                            namespace=namespace,
                            display=Padding(reason, (0, 0, 0, padding + 8)),
                        )

            if conditions_readiness:
                for condition, reason in unknown_conditions_display_list:
                    condition_text: str = f"[yellow]Irregular Condition {condition} found.[/yellow]"
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(condition_text, (0, 0, 0, padding + 4)),
                    )

                    if reason and detail_level == ResourceOutputDetailLevel.verbose.value:
                        check_manager.add_display(
                            target_name=target,
                            namespace=namespace,
                            display=Padding(reason, (0, 0, 0, padding + 8)),
                        )
