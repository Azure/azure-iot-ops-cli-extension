# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Tuple

from knack.log import get_logger
from rich.padding import Padding

from .check_manager import CheckManager
from .display import add_display_and_eval
from ..common import COLOR_STR_FORMAT
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
    service_label: str
) -> None:
    target_service_pod = f"pod/{pod}"
    check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=[f"{target_service_pod}.status.phase"])
    pods = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace, label_selector=service_label)
    process_pods_status(
        check_manager=check_manager,
        namespace=namespace,
        target=target,
        target_service_pod=target_service_pod,
        pods=pods,
        display_padding=display_padding,
    )


def process_pods_status(
    check_manager: CheckManager,
    namespace: str,
    target: str,
    target_service_pod: str,
    pods: List[dict],
    display_padding: int,
) -> None:
    if not pods:
        add_display_and_eval(
            check_manager=check_manager,
            target_name=target,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=CheckTaskStatus.warning.value,
            eval_value=None,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, display_padding)
        )

    else:
        for pod in pods:
            pod_dict = pod.to_dict()
            pod_name = pod_dict["metadata"]["name"]
            pod_phase = pod_dict.get("status", {}).get("phase")
            pod_phase_deco, status = decorate_pod_phase(pod_phase)
            target_service_pod = f"pod/{pod_name}"

            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=status,
                resource_name=target_service_pod,
                value={"name": pod_name, "status.phase": pod_phase},
            )
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"Pod {{[bright_blue]{pod_name}[/bright_blue]}} in phase {{{pod_phase_deco}}}.",
                    (0, 0, 0, display_padding),
                ),
            )
