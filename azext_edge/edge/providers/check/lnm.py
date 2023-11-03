# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Tuple, Union

from azext_edge.edge.providers.base import get_namespaced_pods_by_prefix

from .base import (
    CheckManager,
    add_display_and_eval,
    check_post_deployment,
    check_pre_deployment,
    decorate_pod_phase,
    process_as_list,
    process_properties,
    resources_grouped_by_namespace,
)

from rich.console import Console
from rich.padding import Padding
from kubernetes.client.models import V1Pod

from ...common import CheckTaskStatus

from .common import (
    AIO_LNM_PREFIX,
    LNM_ALLOWLIST_PROPERTIES,
    LNM_IMAGE_PROPERTIES,
    LNM_POD_CONDITION_TEXT_MAP,
    LNM_REST_PROPERTIES,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    LNM_API_V1B1,
    LnmResourceKinds,
)

from ..support.lnm import LNM_APP_LABELS, LNM_LABEL_PREFIX


def check_lnm_deployment(
    console: Console,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
    result: Dict[str, Any] = None,
) -> Union[Dict[str, Any], None]:
    if pre_deployment:
        check_pre_deployment(result, as_list)

    if post_deployment:
        result["postDeployment"] = []
        # check post deployment according to edge_service type
        check_lnm_post_deployment(detail_level=detail_level, result=result, as_list=as_list, resource_kinds=resource_kinds)

    if not as_list:
        return result

    return process_as_list(console=console, result=result)


def check_lnm_post_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
        LnmResourceKinds.LNM: evaluate_lnms,
    }

    return check_post_deployment(
        api_info=LNM_API_V1B1,
        check_name="enumerateLnmApi",
        check_desc="Enumerate LNM API resources",
        result=result,
        resource_kinds_enum=LnmResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds
    )


def evaluate_lnms(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalLnms", check_desc="Evaluate LNM instances")

    target_lnms = "lnmz.aio.com"
    lnm_namespace_conditions = ["len(lnms)>=1", "status.configStatusLevel", "spec.allowList", "spec.image"]

    all_lnms: dict = LNM_API_V1B1.get_resources(LnmResourceKinds.LNM).get("items", [])

    if not all_lnms:
        fetch_lnms_error_text = "Unable to fetch LNM instances in any namespaces."
        check_manager.add_target(target_name=target_lnms)
        check_manager.add_display(target_name=target_lnms, display=Padding(fetch_lnms_error_text, (0, 0, 0, 8)))

    for (namespace, lnms) in resources_grouped_by_namespace(all_lnms):
        lnm_names = []
        check_manager.add_target(target_name=target_lnms, namespace=namespace, conditions=lnm_namespace_conditions)
        check_manager.add_display(
            target_name=target_lnms,
            namespace=namespace,
            display=Padding(
                f"LNM instance in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        lnms: List[dict] = list(lnms)
        lnms_count = len(lnms)
        lnms_count_text = "- Expecting [bright_blue]>=1[/bright_blue] instance resource per namespace. {}."

        if lnms_count >= 1:
            lnms_count_text = lnms_count_text.format(f"[green]Detected {lnms_count}[/green]")
        else:
            lnms_count_text = lnms_count_text.format(f"[red]Detected {lnms_count}[/red]")
            check_manager.set_target_status(target_name=target_lnms, status=CheckTaskStatus.error.value)
        check_manager.add_display(
            target_name=target_lnms,
            namespace=namespace,
            display=Padding(lnms_count_text, (0, 0, 0, 10))
        )

        for lnm in lnms:
            lnm_name = lnm["metadata"]["name"]
            lnm_names.append(lnm_name)
            status = lnm.get("status", {}).get("configStatusLevel", "undefined")

            lnm_status_eval_value = {"status.configStatusLevel": status}
            lnm_status_eval_status = CheckTaskStatus.success.value

            lnm_status_text = (
                f"- Lnm instance {{[bright_blue]{lnm_name}[/bright_blue]}} detected. Configuration status "
            )

            if status == "ok":
                lnm_status_text = lnm_status_text + f"{{[green]{status}[/green]}}."
            else:
                lnm_status_eval_status = CheckTaskStatus.warning.value
                status_description = lnm.get("status", {}).get("configStatusDescription", "")
                lnm_status_text = lnm_status_text + f"{{[yellow]{status}[/yellow]}}. [yellow]{status_description}[/yellow]"

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_lnms,
                display_text=lnm_status_text,
                eval_status=lnm_status_eval_status,
                eval_value=lnm_status_eval_value,
                resource_name=lnm_name,
                namespace=namespace,
                padding=(0, 0, 0, 12)
            )

            lnm_allowlist = lnm["spec"].get("allowList", None)

            if detail_level > ResourceOutputDetailLevel.summary.value:

                lnm_allowlist_text = (
                    "- Allow List property [green]detected[/green]."
                )

                lnm_allowlist_eval_value = {"spec.allowlist": lnm_allowlist}
                lnm_allowlist_eval_status = CheckTaskStatus.success.value

                if lnm_allowlist is None:
                    lnm_allowlist_text = (
                        "- Allow List property [red]not detected[/red]."
                    )

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_lnms,
                    display_text=lnm_allowlist_text,
                    eval_status=lnm_allowlist_eval_status,
                    eval_value=lnm_allowlist_eval_value,
                    resource_name=lnm_name,
                    namespace=namespace,
                    padding=(0, 0, 0, 16)
                )

                process_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_lnms,
                    prop_value=lnm_allowlist,
                    properties=LNM_ALLOWLIST_PROPERTIES,
                    namespace=namespace,
                    padding=(0, 0, 0, 18)
                )

                process_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_lnms,
                    prop_value=lnm["spec"],
                    properties=LNM_REST_PROPERTIES,
                    namespace=namespace,
                    padding=(0, 0, 0, 16)
                )

            if detail_level == ResourceOutputDetailLevel.verbose.value:
                # image
                lnm_image = lnm["spec"].get("image", None)
                lnm_image_text = (
                    "- Image property [green]detected[/green]."
                )

                lnm_image_eval_value = {"spec.image": lnm_image}
                lnm_image_eval_status = CheckTaskStatus.success.value

                if lnm_image is None:
                    lnm_image_text = (
                        "- Image property [red]not detected[/red]."
                    )

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_lnms,
                    display_text=lnm_image_text,
                    eval_status=lnm_image_eval_status,
                    eval_value=lnm_image_eval_value,
                    resource_name=lnm_name,
                    namespace=namespace,
                    padding=(0, 0, 0, 16)
                )

                process_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_lnms,
                    prop_value=lnm_image,
                    properties=LNM_IMAGE_PROPERTIES,
                    namespace=namespace,
                    padding=(0, 0, 0, 18)
                )

        if lnms_count > 0:
            check_manager.add_display(
                target_name=target_lnms,
                namespace=namespace,
                display=Padding(
                    "\nRuntime Health",
                    (0, 0, 0, 10),
                ),
            )

            # append all lnm_names in lnm_app_labels
            lnm_app_labels = []
            for lnm_name in lnm_names:
                lnm_app_labels.append(f"{LNM_LABEL_PREFIX}-{lnm_name}")

            lnm_label = f"app in ({','.join(lnm_app_labels + LNM_APP_LABELS)})"
            _evaluate_lnm_pod_health(
                check_manager=check_manager,
                target=target_lnms,
                pod=AIO_LNM_PREFIX,
                display_padding=12,
                service_label=lnm_label,
                namespace=namespace,
                detail_level=detail_level,
            )

    # evaluate lnm operator pod no matter if there is lnm instance
    pods = _evaluate_pod_for_other_namespace(
        check_manager=check_manager,
        conditions=lnm_namespace_conditions,
        target=target_lnms,
        detail_level=detail_level,
    )

    if not all_lnms and not pods:
        check_manager.set_target_status(target_name=target_lnms, status=CheckTaskStatus.skipped.value)

    return check_manager.as_dict(as_list)


def _evaluate_pod_for_other_namespace(
    check_manager: CheckManager,
    conditions: List[str],
    target: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> List[dict]:
    from itertools import groupby

    lnm_operator_label = f"app in ({','.join(LNM_APP_LABELS)})"
    pods = get_namespaced_pods_by_prefix(prefix=AIO_LNM_PREFIX, namespace="", label_selector=lnm_operator_label)
    pods.extend(
        get_namespaced_pods_by_prefix(prefix=f"svclb-{AIO_LNM_PREFIX}", namespace="", label_selector=None)
    )

    def get_namespace(pod: V1Pod) -> str:
        return pod.metadata.namespace

    pods.sort(key=get_namespace)

    for (namespace, pods) in groupby(pods, get_namespace):
        # only evaluate operator pod if there is no target for the namespace operator pod is in
        if not check_manager.targets[target].get(namespace, ""):
            check_manager.add_target(target_name=target, namespace=namespace, conditions=conditions)
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"LNM resource health for namespace {{[purple]{namespace}[/purple]}}",
                    (0, 0, 0, 6)
                )
            )

            for pod in pods:
                pod_name = pod.metadata.name
                service_label = None if pod_name.startswith("svclb-") else lnm_operator_label

                _evaluate_lnm_pod_health(
                    check_manager=check_manager,
                    target=target,
                    pod=pod.metadata.name,
                    display_padding=12,
                    service_label=service_label,
                    namespace=namespace,
                    detail_level=detail_level,
                )
    
    return pods


def _evaluate_lnm_pod_health(
    check_manager: CheckManager,
    target: str,
    pod: str,
    display_padding: int,
    service_label: str,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:

    def _decorate_pod_condition(condition: bool) -> Tuple[str, str]:
        if condition:
            return f"[green]{condition}[/green]", CheckTaskStatus.success.value
        return f"[red]{condition}[/red]", CheckTaskStatus.error.value

    target_service_pod = f"pod/{pod}"

    pod_conditions = [
        f"{target_service_pod}.status.phase",
        f"{target_service_pod}.status.conditions.ready",
        f"{target_service_pod}.status.conditions.initialized",
        f"{target_service_pod}.status.conditions.containersready",
        f"{target_service_pod}.status.conditions.podscheduled",
    ]

    diagnostics_pods = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace, label_selector=service_label)

    check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)

    if not diagnostics_pods:
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
        for pod in diagnostics_pods:
            pod_dict = pod.to_dict()
            pod_name = pod_dict["metadata"]["name"]
            pod_phase = pod_dict.get("status", {}).get("phase")
            pod_conditions = pod_dict.get("status", {}).get("conditions", {})
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
                f"- Phase: {pod_phase_deco}",
                "- Conditions:"
            ]:
                padding = 2 if "\nPod" not in text else 0
                padding += display_padding
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(text, (0, 0, 0, padding)),
                )

            for condition in pod_conditions:
                condition_type = LNM_POD_CONDITION_TEXT_MAP[condition.get("type")]
                condition_status = True if condition.get("status") == "True" else False
                pod_condition_deco, status = _decorate_pod_condition(condition=condition_status)

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target,
                    display_text=f"{condition_type}: {pod_condition_deco}",
                    eval_status=status,
                    eval_value={"name": pod_name, f"status.conditions.{condition_type.lower()}": condition_status},
                    resource_name=target_service_pod,
                    namespace=namespace,
                    padding=(0, 0, 0, display_padding + 8)
                )

                if detail_level > ResourceOutputDetailLevel.summary.value:
                    condition_reason = condition.get("message")
                    condition_reason_text = f"{condition_reason}" if condition_reason else ""

                    if condition_reason_text:
                        # remove the [ and ] to prevent console not printing the text
                        condition_reason_text = condition_reason_text.replace("[", "\\[")
                        check_manager.add_display(
                            target_name=target,
                            namespace=namespace,
                            display=Padding(
                                f"[red]Reason: {condition_reason_text}[/red]",
                                (0, 0, 0, display_padding + 8),
                            ),
                        )
