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

    if not pods:
        return add_display_and_eval(
            check_manager=check_manager,
            target_name=target,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=CheckTaskStatus.warning.value,
            eval_value=None,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, display_padding)
        )

    for pod in pods:
        target_service_pod = f"pod/{pod.metadata.name}"

        pod_conditions = [
            f"{target_service_pod}.status.phase",
            f"{target_service_pod}.status.conditions.ready",
            f"{target_service_pod}.status.conditions.initialized",
            f"{target_service_pod}.status.conditions.containersready",
            f"{target_service_pod}.status.conditions.podscheduled",
            f"{target_service_pod}.status.conditions.podreadytostartcontainers",
        ]

        if check_manager.targets.get(target, {}).get(namespace, {}).get("conditions", None):
            check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)
        else:
            check_manager.set_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)

        pod_dict = pod.to_dict()
        pod_name = pod_dict["metadata"]["name"]
        pod_phase = pod_dict.get("status", {}).get("phase")
        pod_conditions = pod_dict.get("status", {}).get("conditions", [])
        pod_phase_deco, status = decorate_pod_phase(pod_phase)

        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=status,
            resource_name=target_service_pod,
            value={"name": pod_name, "status.phase": pod_phase},
        )

        for text in [
            f"\nPod {{[bright_blue]{pod_name}[/bright_blue]}}",
            f"- Phase: {pod_phase_deco}"
        ]:
            padding = 2 if "\nPod" not in text else 0
            padding += display_padding
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(text, (0, 0, 0, padding)),
            )

        # When pod in obnormal state, sometimes the conditions are not available
        if pod_conditions:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding("- Conditions:", (0, 0, 0, padding)),
            )

            for condition in pod_conditions:
                type = condition["type"]
                condition_type = POD_CONDITION_TEXT_MAP[type]
                condition_status = condition.get("status") == "True"
                pod_condition_deco, status = _decorate_pod_condition(condition=condition_status)

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target,
                    display_text=f"{condition_type}: {pod_condition_deco}",
                    eval_status=status,
                    eval_value={"name": pod_name, f"status.conditions.{type.lower()}": condition_status},
                    resource_name=target_service_pod,
                    namespace=namespace,
                    padding=(0, 0, 0, display_padding + 8)
                )

                if detail_level > ResourceOutputDetailLevel.summary.value:
                    condition_reason = condition.get("message", "")

                    if condition_reason:
                        # remove the [ and ] to prevent console not printing the text
                        formatted_reason = condition_reason.replace("[", "\\[")
                        check_manager.add_display(
                            target_name=target,
                            namespace=namespace,
                            display=Padding(
                                f"[red]Reason: {formatted_reason}[/red]",
                                (0, 0, 0, display_padding + 8),
                            ),
                        )
