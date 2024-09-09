# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from itertools import groupby
from knack.log import get_logger
from kubernetes.client.models import (
    V1APIResource,
    V1APIResourceList,
)
from rich.padding import Padding
from typing import Any, Dict, List, Optional, Tuple, Union

from .check_manager import CheckManager
from .display import process_value_color
from ..common import COLOR_STR_FORMAT, PADDING_SIZE, ResourceOutputDetailLevel
from ...base import get_cluster_custom_api
from ...edge_api import EdgeResourceApi
from ....common import CheckTaskStatus, ResourceState

# TODO: refactor
logger = get_logger(__name__)


def decorate_resource_status(status: str) -> str:
    from ....common import ResourceState

    return COLOR_STR_FORMAT.format(color=ResourceState.map_to_color(status), value=status)


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

    api_resources: V1APIResourceList = get_cluster_custom_api(group=api_info.group, version=api_info.version)

    if not api_resources:
        check_manager.add_target_eval(target_name=target_api, status=CheckTaskStatus.error.value)
        missing_api_text = f"[bright_blue]{target_api}[/bright_blue] API resources [red]not[/red] detected."
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


def filter_resources_by_namespace(resources: List[dict], namespace: str) -> List[dict]:
    return [resource for resource in resources if _get_namespace(resource) == namespace]


def generate_target_resource_name(api_info: EdgeResourceApi, resource_kind: str) -> str:
    resource_plural = api_info._kinds[resource_kind] if api_info._kinds else f"{resource_kind}s"
    return f"{resource_plural}.{api_info.group}"


def _get_namespace(resource):
    return get_resource_metadata_property(resource, prop_name="namespace")


def get_resources_by_name(
    api_info: EdgeResourceApi,
    kind: Union[str, Enum],
    resource_name: str,
    namespace: str = None,
) -> List[dict]:
    resources: list = api_info.get_resources(kind=kind, namespace=namespace).get("items", [])
    resources = filter_resources_by_name(resources, resource_name)
    return resources


def get_resources_grouped_by_namespace(resources: List[dict]):
    resources.sort(key=_get_namespace)
    return groupby(resources, key=_get_namespace)


# get either name or namespace from resource that might be a object or a dict
def get_resource_metadata_property(resource: Union[dict, Any], prop_name: str) -> Union[str, None]:
    if isinstance(resource, dict):
        return resource.get("metadata", {}).get(prop_name)
    return getattr(resource.metadata, prop_name, None) if hasattr(resource, "metadata") else None


def process_dict_resource(
    check_manager: CheckManager,
    target_name: str,
    resource: dict,
    namespace: str,
    padding: int,
    prop_name: Optional[str] = None,
) -> None:
    if prop_name:
        check_manager.add_display(
            target_name=target_name, namespace=namespace, display=Padding(f"{prop_name}:", (0, 0, 0, padding))
        )
        padding += PADDING_SIZE
    for key, value in resource.items():
        if isinstance(value, dict):
            check_manager.add_display(
                target_name=target_name, namespace=namespace, display=Padding(f"{key}:", (0, 0, 0, padding))
            )
            process_dict_resource(
                check_manager=check_manager,
                target_name=target_name,
                resource=value,
                namespace=namespace,
                padding=padding + PADDING_SIZE,
            )
        elif isinstance(value, list):
            if len(value) == 0:
                continue

            display_text = f"{key}:"
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, padding)),
            )

            process_list_resource(
                check_manager=check_manager,
                target_name=target_name,
                resource=value,
                namespace=namespace,
                padding=padding + PADDING_SIZE,
            )
        else:
            display_text = f"{key}: "
            value_padding = padding
            if isinstance(value, str) and len(value) > 50:
                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(display_text, (0, 0, 0, padding)),
                )
                value_padding += PADDING_SIZE
                display_text = ""
            display_text += process_value_color(
                check_manager=check_manager, target_name=target_name, key=key, value=value
            )
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, value_padding)),
            )


def process_list_resource(
    check_manager: CheckManager, target_name: str, resource: List[dict], namespace: str, padding: int
) -> None:
    for item in resource:
        name = ""

        if isinstance(item, dict):
            name = item.pop("name", None)

        # when name property exists, use name as header; if not, use property type and index as header
        if name:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"- name: [cyan]{name}[/cyan]", (0, 0, 0, padding)),
            )
        else:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"- item {resource.index(item) + 1}", (0, 0, 0, padding)),
            )

        if isinstance(item, dict):
            process_dict_resource(
                check_manager=check_manager,
                target_name=target_name,
                resource=item,
                namespace=namespace,
                padding=padding + 2,
            )
        elif isinstance(item, str):
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(f"[cyan]{item}[/cyan]", (0, 0, 0, padding + 2)),
            )


def process_resource_properties(
    check_manager: CheckManager,
    detail_level: int,
    target_name: str,
    prop_value: Dict[str, Any],
    properties: Dict[str, Any],
    namespace: str,
    padding: tuple,
) -> None:
    if not prop_value:
        return

    for prop, display_name, verbose_only in properties:
        keys = prop.split(".")
        value = prop_value
        for key in keys:
            value = value.get(key)
            if value is None:
                break
        if prop == "descriptor":
            value = value if detail_level == ResourceOutputDetailLevel.verbose.value else value[:10] + "..."
        if verbose_only and detail_level != ResourceOutputDetailLevel.verbose.value:
            continue
        process_resource_property_by_type(
            check_manager=check_manager,
            target_name=target_name,
            properties=value,
            display_name=display_name,
            namespace=namespace,
            padding=padding,
        )


def process_resource_property_by_type(
    check_manager: CheckManager,
    target_name: str,
    properties: Any,
    display_name: str,
    namespace: str,
    padding: tuple,
) -> None:
    padding_left = padding[3]
    if isinstance(properties, list):
        if len(properties) == 0:
            return

        display_text = f"{display_name}:"
        check_manager.add_display(
            target_name=target_name, namespace=namespace, display=Padding(display_text, padding)
        )

        for property in properties:
            display_text = f"- {display_name} {properties.index(property) + 1}"
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, padding_left + 2)),
            )
            for prop, value in property.items():
                display_text = f"{prop}: [cyan]{value}[/cyan]"
                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(display_text, (0, 0, 0, padding_left + PADDING_SIZE)),
                )
    elif isinstance(properties, str) or isinstance(properties, bool) or isinstance(properties, int):
        properties = str(properties) if properties else "undefined"
        if len(properties) < 50:
            display_text = f"{display_name}: [cyan]{properties}[/cyan]"
        else:
            check_manager.add_display(
                target_name=target_name, namespace=namespace, display=Padding(f"{display_name}:", padding)
            )
            display_text = f"[cyan]{properties}[/cyan]"
            padding = (0, 0, 0, padding_left + 4)

        check_manager.add_display(
            target_name=target_name, namespace=namespace, display=Padding(display_text, padding)
        )
    elif isinstance(properties, dict):
        display_text = f"{display_name}:"
        check_manager.add_display(
            target_name=target_name, namespace=namespace, display=Padding(display_text, padding)
        )
        for prop, value in properties.items():
            display_text = f"{prop}: [cyan]{value}[/cyan]"
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(display_text, (0, 0, 0, padding_left + 2)),
            )


def validate_one_of_conditions(
    conditions: List[tuple],
    check_manager: CheckManager,
    eval_value: dict,
    namespace: str,
    target_name: str,
    padding: int,
    resource_name: Optional[str] = None,
) -> None:
    if len(conditions) == 1:
        return

    non_empty_conditions_count = len([condition for condition in conditions if condition[1]])

    eval_status = CheckTaskStatus.success.value
    conditions_names = ", ".join([f"'{condition[0]}'" for condition in conditions])
    if non_empty_conditions_count == 0:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(
                f"One of {conditions_names} should be specified",
                (0, 0, 0, padding),
            ),
        )
        eval_status = CheckTaskStatus.error.value
    elif non_empty_conditions_count > 1:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(
                f"Only one of {conditions_names} should be specified",
                (0, 0, 0, padding),
            ),
        )
        eval_status = CheckTaskStatus.error.value

    one_of_condition = f"oneOf({conditions_names})"
    check_manager.add_target_conditions(
        target_name=target_name, namespace=namespace, conditions=[one_of_condition]
    )
    check_manager.add_target_eval(
        target_name=target_name,
        namespace=namespace,
        status=eval_status,
        value=eval_value,
        resource_name=resource_name,
    )


def combine_statuses(status_list: List[str]):
    # lower case status list
    status_list = [status.lower() for status in status_list]
    final_status = "success"
    for status in status_list:
        if final_status == "success" and status not in ["running", "succeeded", "ok"]:
            final_status = status
        elif final_status in ["warning", "skipped", "warn", "starting", "recovering"] and status == "error":
            final_status = status
    return final_status


def calculate_status(resource_state: str) -> str:
    return ResourceState.map_to_status(resource_state).value


def process_custom_resource_status(
    check_manager: CheckManager,
    status: dict,
    target_name: str,
    namespace: str,
    resource_name: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    runtime_status = status.get("runtimeStatus", {})
    provisioning_status = status.get("provisioningStatus", {})
    check_manager.add_target_conditions(
        target_name=target_name,
        conditions=["status"],
        namespace=namespace,
    )

    if not runtime_status and not provisioning_status:
        # if no status for both runtime and provisioning, set status to error
        check_manager.add_target_eval(
            target_name=target_name,
            namespace=namespace,
            status=CheckTaskStatus.error.value,
            value={"status": status},
            resource_name=resource_name,
        )
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding("Status [red]not found[/red].", (0, 0, 0, padding)),
        )
        return

    status_eval_value = {"status": status}
    status_list = []
    if runtime_status:
        runtime_status_state = runtime_status.get("status")
        status_list.append(calculate_status(runtime_status_state))

    if provisioning_status:
        provisioning_status_state = provisioning_status.get("status")
        status_list.append(calculate_status(provisioning_status_state))

    # combine runtime and provisioning status
    status_eval_status = combine_statuses(status_list)
    check_manager.add_target_eval(
        target_name=target_name,
        namespace=namespace,
        status=status_eval_status,
        value=status_eval_value,
        resource_name=resource_name,
    )

    if detail_level == ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(
                f"Status {{{decorate_resource_status(status_eval_status)}}}.",
                (0, 0, 0, padding),
            ),
        )
    else:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding("Status:", (0, 0, 0, padding)),
        )

        for prop_name, prop_value in {
            "Provisioning Status": provisioning_status,
            "Runtime Status": runtime_status,
        }.items():
            if prop_value:
                status_text = f"{prop_name} {{{decorate_resource_status(prop_value.get('status'))}}}."
                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    status_description = prop_value.get("statusDescription") or prop_value.get(
                        "output", {}
                    ).get("message")
                    if status_description:
                        status_text = status_text.replace(".", f", [cyan]{status_description}[/cyan].")

                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(status_text, (0, 0, 0, padding + 4)),
                )
