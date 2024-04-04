# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from itertools import groupby
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from enum import Enum

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1APIResource,
    V1APIResourceList,
)
from rich.console import Console, NewLine
from rich.padding import Padding

from .check_manager import CheckManager
from .base_nodes import check_nodes
from .common import ALL_NAMESPACES_TARGET, PADDING_SIZE, CoreServiceResourceKinds, ResourceOutputDetailLevel
from ...common import CheckTaskStatus, ListableEnum

from ...providers.edge_api import EdgeResourceApi

from ..base import (
    client,
    get_cluster_custom_api,
    get_namespaced_pods_by_prefix,
)

logger = get_logger(__name__)


def check_pre_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
) -> None:
    result["preDeployment"] = []
    desired_checks = {}
    desired_checks.update(
        {
            "checkK8sVersion": partial(check_k8s_version, as_list=as_list),
            "checkNodes": partial(check_nodes, as_list=as_list),
        }
    )

    for c in desired_checks:
        output = desired_checks[c]()
        result["preDeployment"].append(output)


def check_post_deployment(
    api_info: EdgeResourceApi,
    check_name: str,
    check_desc: str,
    result: Dict[str, Any],
    resource_kinds_enum: Enum,
    evaluate_funcs: Dict[ListableEnum, Callable],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: Optional[List[str]] = None,
    resource_name: str = None,
    excluded_resources: Optional[List[str]] = None,
) -> None:
    resource_enumeration, api_resources = enumerate_ops_service_resources(api_info, check_name, check_desc, as_list, excluded_resources)
    result["postDeployment"].append(resource_enumeration)
    lowercase_api_resources = {k.lower(): v for k, v in api_resources.items()}

    if lowercase_api_resources:
        for resource, evaluate_func in evaluate_funcs.items():
            should_check_resource = not resource_kinds or resource.value in resource_kinds
            append_resource = False
            # only add core service evaluation if there is no resource filter
            if resource == CoreServiceResourceKinds.RUNTIME_RESOURCE and not resource_kinds:
                append_resource = True
            elif (resource and resource.value in lowercase_api_resources and should_check_resource):
                append_resource = True

            if append_resource:
                result["postDeployment"].append(evaluate_func(detail_level=detail_level, as_list=as_list, resource_name=resource_name))


def filter_resources_by_name(
    resources: List[dict],
    resource_name: str,
) -> List[dict]:
    from fnmatch import fnmatch

    if not resource_name:
        return resources

    resource_name = resource_name.lower()
    resources = [
        resource
        for resource in resources
        if fnmatch(get_resource_metadata_property(resource, prop_name="name"), resource_name)
    ]

    return resources


def get_resources_by_name(
    api_info: EdgeResourceApi,
    kind: Union[str, Enum],
    resource_name: str,
    namespace: str = None,
) -> List[dict]:
    resources: list = api_info.get_resources(kind=kind, namespace=namespace).get("items", [])
    resources = filter_resources_by_name(resources, resource_name)
    return resources


def process_as_list(console: Console, result: Dict[str, Any]) -> None:
    success_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    skipped_count: int = 0

    def _increment_summary(status: str) -> None:
        nonlocal success_count, warning_count, error_count, skipped_count
        if not status:
            return
        if status == CheckTaskStatus.success.value:
            success_count = success_count + 1
        elif status == CheckTaskStatus.warning.value:
            warning_count = warning_count + 1
        elif status == CheckTaskStatus.error.value:
            error_count = error_count + 1
        elif status == CheckTaskStatus.skipped.value:
            skipped_count = skipped_count + 1

    def _print_summary() -> None:
        from rich.panel import Panel

        success_content = f"[green]{success_count} check(s) succeeded.[/green]"
        warning_content = f"{warning_count} check(s) raised warnings."
        warning_content = (
            f"[green]{warning_content}[/green]" if not warning_count else f"[yellow]{warning_content}[/yellow]"
        )
        error_content = f"{error_count} check(s) raised errors."
        error_content = f"[green]{error_content}[/green]" if not error_count else f"[red]{error_content}[/red]"
        skipped_content = f"[bright_white]{skipped_count} check(s) were skipped[/bright_white]."
        content = f"{success_content}\n{warning_content}\n{error_content}\n{skipped_content}"
        console.print(Panel(content, title="Check Summary", expand=False))

    def _enumerate_displays(checks: List[Dict[str, dict]]) -> None:
        for check in checks:
            status = check.get("status")
            prefix_emoji = get_emoji_from_status(status)
            console.print(Padding(f"{prefix_emoji} {check['description']}", (0, 0, 0, 4)))

            targets = check.get("targets", {})
            for type in targets:
                for namespace in targets[type]:
                    namespace_target = targets[type][namespace]
                    displays = namespace_target.get("displays", [])
                    status = namespace_target.get("status")
                    for (idx, disp) in enumerate(displays):
                        # display status indicator on each 'namespaced' grouping of displays
                        if all([idx == 0, namespace != ALL_NAMESPACES_TARGET, status]):
                            prefix_emoji = get_emoji_from_status(status)
                            console.print(Padding(f"\n{prefix_emoji} {disp.renderable}", (0, 0, 0, 6)))
                        else:
                            console.print(disp)
                    target_status = targets[type][namespace].get("status")
                    evaluations = targets[type][namespace].get("evaluations", [])
                    if not evaluations:
                        _increment_summary(target_status)
                    for e in evaluations:
                        eval_status = e.get("status")
                        _increment_summary(eval_status)
            console.print(NewLine(1))
        console.print(NewLine(1))

    title: dict = result.get("title")
    if title:
        console.print(NewLine(1))
        console.rule(title, align="center", style="blue bold")
        console.print(NewLine(1))

    pre_checks: List[dict] = result.get("preDeployment")
    if pre_checks:
        console.rule("Pre deployment checks", align="left")
        console.print(NewLine(1))
        _enumerate_displays(pre_checks)

    post_checks: List[dict] = result.get("postDeployment")
    if post_checks:
        console.rule("Post deployment checks", align="left")
        console.print(NewLine(1))
        _enumerate_displays(post_checks)

    _print_summary()


def get_emoji_from_status(status: str) -> str:
    if not status:
        return ""
    if status == CheckTaskStatus.success.value:
        return "[green]:heavy_check_mark:[/green]"
    if status == CheckTaskStatus.warning.value:
        return "[yellow]:warning:[/yellow]"
    if status == CheckTaskStatus.skipped.value:
        return ":hammer:"
    if status == CheckTaskStatus.error.value:
        return "[red]:stop_sign:[/red]"


def enumerate_ops_service_resources(
    api_info: EdgeResourceApi,
    check_name: str,
    check_desc: str,
    as_list: bool = False,
    excluded_resources: Optional[List[str]] = None,
) -> Tuple[dict, dict]:

    resource_kind_map = {}
    target_api = api_info.as_str()
    check_manager = CheckManager(check_name=check_name, check_desc=check_desc)
    check_manager.add_target(target_name=target_api)

    api_resources: V1APIResourceList = get_cluster_custom_api(
        group=api_info.group, version=api_info.version
    )

    if not api_resources:
        check_manager.add_target_eval(target_name=target_api, status=CheckTaskStatus.skipped.value)
        missing_api_text = (
            f"[bright_blue]{target_api}[/bright_blue] API resources [red]not[/red] detected."
            "\n\n[bright_white]Skipping deployment evaluation[/bright_white]."
        )
        check_manager.add_display(target_name=target_api, display=Padding(missing_api_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list), resource_kind_map

    api_header_display = Padding(f"[bright_blue]{target_api}[/bright_blue] API resources", (0, 0, 0, 8))
    check_manager.add_display(target_name=target_api, display=api_header_display)

    for resource in api_resources.resources:
        r: V1APIResource = resource
        if excluded_resources and r.name in excluded_resources:
            continue
        if r.kind not in resource_kind_map:
            resource_kind_map[r.kind] = True
            check_manager.add_display(
                target_name=target_api,
                display=Padding(f"[cyan]{r.kind}[/cyan]", (0, 0, 0, 12)),
            )

    check_manager.add_target_eval(
        target_name=target_api,
        status=CheckTaskStatus.success.value,
        value=list(resource_kind_map.keys()),
    )
    return check_manager.as_dict(as_list), resource_kind_map


def check_k8s_version(as_list: bool = False) -> Dict[str, Any]:
    from kubernetes.client.models import VersionInfo
    from packaging import version

    from .common import MIN_K8S_VERSION

    version_client = client.VersionApi()

    target_k8s_version = "k8s"
    check_manager = CheckManager(check_name="evalK8sVers", check_desc="Evaluate Kubernetes server")
    check_manager.add_target(
        target_name=target_k8s_version,
        conditions=[f"(k8s version)>={MIN_K8S_VERSION}"],
    )

    try:
        version_details: VersionInfo = version_client.get_code()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = "Unable to determine. Is there connectivity to the cluster?"
        check_manager.add_target_eval(
            target_name=target_k8s_version,
            status=CheckTaskStatus.error.value,
            value=api_error_text,
        )
        check_manager.add_display(
            target_name=target_k8s_version,
            display=Padding(api_error_text, (0, 0, 0, 8)),
        )
    else:
        major_version = version_details.major
        minor_version = version_details.minor
        semver = f"{major_version}.{minor_version}"

        if version.parse(semver) >= version.parse(MIN_K8S_VERSION):
            semver_status = CheckTaskStatus.success.value
            semver_colored = f"[green]v{semver}[/green]"
        else:
            semver_status = CheckTaskStatus.error.value
            semver_colored = f"[red]v{semver}[/red]"

        k8s_semver_text = (
            f"Require [bright_blue]k8s[/bright_blue] >=[cyan]{MIN_K8S_VERSION}[/cyan] detected {semver_colored}."
        )
        check_manager.add_target_eval(target_name=target_k8s_version, status=semver_status, value=semver)
        check_manager.add_display(
            target_name=target_k8s_version,
            display=Padding(k8s_semver_text, (0, 0, 0, 8)),
        )

    return check_manager.as_dict(as_list)


def decorate_resource_status(status: str) -> str:
    from ...common import ResourceState

    if status in [ResourceState.failed.value, ResourceState.error.value]:
        return f"[red]{status}[/red]"
    if status in [
        ResourceState.recovering.value,
        ResourceState.warn.value,
        ResourceState.starting.value,
        "N/A",
    ]:
        return f"[yellow]{status}[/yellow]"
    return f"[green]{status}[/green]"


def decorate_pod_phase(phase: str) -> Tuple[str, str]:
    from ...common import PodState

    if phase == PodState.failed.value:
        return f"[red]{phase}[/red]", CheckTaskStatus.error.value
    if not phase or phase in [PodState.unknown.value, PodState.pending.value]:
        return f"[yellow]{phase}[/yellow]", CheckTaskStatus.warning.value
    return f"[green]{phase}[/green]", CheckTaskStatus.success.value


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


def process_properties(
    check_manager: CheckManager,
    detail_level: int,
    target_name: str,
    prop_value: Dict[str, Any],
    properties: Dict[str, Any],
    namespace: str,
    padding: tuple
) -> None:
    if not prop_value:
        return

    for prop, display_name, verbose_only in properties:
        keys = prop.split('.')
        value = prop_value
        for key in keys:
            value = value.get(key)
            if value is None:
                break
        if prop == "descriptor":
            value = value if detail_level == ResourceOutputDetailLevel.verbose.value else value[:10] + "..."
        if verbose_only and detail_level != ResourceOutputDetailLevel.verbose.value:
            continue
        process_property_by_type(
            check_manager,
            target_name,
            properties=value,
            display_name=display_name,
            namespace=namespace,
            padding=padding
        )


def process_property_by_type(
    check_manager: CheckManager,
    target_name: str,
    properties: Any,
    display_name: str,
    namespace: str,
    padding: tuple
) -> None:
    padding_left = padding[3]
    if isinstance(properties, list):
        if len(properties) == 0:
            return

        display_text = f"{display_name}:"
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(display_text, padding)
        )

        for property in properties:
            display_text = f"- {display_name} {properties.index(property) + 1}"
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, padding_left + 2))
            )
            for prop, value in property.items():
                display_text = f"{prop}: [cyan]{value}[/cyan]"
                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(display_text, (0, 0, 0, padding_left + PADDING_SIZE))
                )
    elif isinstance(properties, str) or isinstance(properties, bool) or isinstance(properties, int):
        properties = str(properties) if properties else "undefined"
        if len(properties) < 50:
            display_text = f"{display_name}: [cyan]{properties}[/cyan]"
        else:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"{display_name}:", padding)
            )
            display_text = f"[cyan]{properties}[/cyan]"
            padding = (0, 0, 0, padding_left + 4)

        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(display_text, padding)
        )
    elif isinstance(properties, dict):
        display_text = f"{display_name}:"
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(display_text, padding)
        )
        for prop, value in properties.items():
            display_text = f"{prop}: [cyan]{value}[/cyan]"
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, padding_left + 2))
            )


def add_display_and_eval(
    check_manager: CheckManager,
    target_name: str,
    display_text: str,
    eval_status: str,
    eval_value: str,
    resource_name: Optional[str] = None,
    namespace: str = ALL_NAMESPACES_TARGET,
    padding: Tuple[int, int, int, int] = (0, 0, 0, 8)
) -> None:
    check_manager.add_display(
        target_name=target_name,
        namespace=namespace,
        display=Padding(display_text, padding)
    )
    check_manager.add_target_eval(
        target_name=target_name,
        namespace=namespace,
        status=eval_status,
        value=eval_value,
        resource_name=resource_name
    )


# get either name or namespace from resource that might be a object or a dict
def get_resource_metadata_property(resource: Union[dict, Any], prop_name: str) -> Union[str, None]:
    if isinstance(resource, dict):
        return resource.get("metadata", {}).get(prop_name)
    return getattr(resource.metadata, prop_name, None) if hasattr(resource, "metadata") else None


def get_namespace(resource):
    return get_resource_metadata_property(resource, prop_name="namespace")


def resources_grouped_by_namespace(resources: List[dict]):
    resources.sort(key=get_namespace)
    return groupby(resources, key=get_namespace)


def filter_by_namespace(resources: List[dict], namespace: str) -> List[dict]:
    return [resource for resource in resources if get_namespace(resource) == namespace]


def process_dict_resource(
    check_manager: CheckManager,
    target_name: str,
    resource: dict,
    namespace: str,
    padding: int,
    prop_name: Optional[str] = None
) -> None:
    if prop_name:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(f"{prop_name}:", (0, 0, 0, padding))
        )
        padding += PADDING_SIZE
    for key, value in resource.items():
        if isinstance(value, dict):
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"{key}:", (0, 0, 0, padding))
            )
            process_dict_resource(
                check_manager=check_manager,
                target_name=target_name,
                resource=value,
                namespace=namespace,
                padding=padding + PADDING_SIZE
            )
        elif isinstance(value, list):
            if len(value) == 0:
                continue

            display_text = f"{key}:"
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, padding))
            )

            process_list_resource(
                check_manager=check_manager,
                target_name=target_name,
                resource=value,
                namespace=namespace,
                padding=padding + PADDING_SIZE
            )
        else:
            display_text = f"{key}: "
            value_padding = padding
            if isinstance(value, str) and len(value) > 50:
                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(display_text, (0, 0, 0, padding))
                )
                value_padding += PADDING_SIZE
                display_text = ""
            display_text += process_value_color(
                check_manager=check_manager,
                target_name=target_name,
                key=key,
                value=value
            )
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, value_padding))
            )


def process_value_color(
    check_manager: CheckManager,
    target_name: str,
    key: Any,
    value: Any,
) -> str:
    value = value if value else "N/A"
    if "error" in str(key).lower() and str(value).lower() not in ["null", "n/a", "none", "noerror"]:
        check_manager.set_target_status(
            target_name=target_name,
            status=CheckTaskStatus.error.value
        )
        return f"[red]{value}[/red]"
    return f"[cyan]{value}[/cyan]"


def process_list_resource(
    check_manager: CheckManager,
    target_name: str,
    resource: List[dict],
    namespace: str,
    padding: int
) -> None:
    for item in resource:
        name = item.pop("name", None)

        # when name property exists, use name as header; if not, use property type and index as header
        if name:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"- name: [cyan]{name}[/cyan]", (0, 0, 0, padding))
            )
        else:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"- item {resource.index(item) + 1}", (0, 0, 0, padding))
            )

        if isinstance(item, dict):
            process_dict_resource(
                check_manager=check_manager,
                target_name=target_name,
                resource=item,
                namespace=namespace,
                padding=padding + 2
            )
        elif isinstance(item, str):
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"[cyan]{item}[/cyan]", (0, 0, 0, padding + 2))
            )


def generate_target_resource_name(api_info: EdgeResourceApi, resource_kind: str) -> str:
    resource_plural = api_info._kinds[resource_kind] if api_info._kinds else f"{resource_kind}s"
    return f"{resource_plural}.{api_info.group}"
