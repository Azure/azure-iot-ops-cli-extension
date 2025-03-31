# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from rich.padding import Padding
from typing import Any, Dict, List

from ..base import get_namespaced_pods_by_prefix

from .base import (
    CheckManager,
    check_post_deployment,
    filter_resources_by_name,
    evaluate_pod_health,
    get_resources_grouped_by_namespace,
)

from .common import (
    PADDING_SIZE,
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel,
)

from ..support.connectors import OPC_NAME_VAR_LABEL, OPCUA_NAME_LABEL


def check_opcua_deployment(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> List[dict]:
    evaluate_funcs = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE: evaluate_core_service_runtime,
    }

    return check_post_deployment(
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
        resource_name=resource_name,
    )


def evaluate_core_service_runtime(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalCoreServiceRuntime", check_desc="Evaluate OPC UA broker core service")

    padding = 6
    opcua_runtime_resources: List[dict] = []
    for label_selector in [OPC_NAME_VAR_LABEL, OPCUA_NAME_LABEL]:
        opcua_runtime_resources.extend(
            get_namespaced_pods_by_prefix(
                prefix="",
                namespace="",
                label_selector=label_selector,
            )
        )

    if resource_name:
        opcua_runtime_resources = filter_resources_by_name(
            resources=opcua_runtime_resources,
            resource_name=resource_name,
        )

        if not opcua_runtime_resources:
            check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value)
            check_manager.add_display(
                target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
                display=Padding("Unable to fetch pods.", (0, 0, 0, padding + 2)),
            )

    for namespace, pods in get_resources_grouped_by_namespace(opcua_runtime_resources):
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value, namespace=namespace)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"OPC UA broker runtime resources in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)
            ),
        )

        evaluate_pod_health(
            check_manager=check_manager,
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            padding=padding + PADDING_SIZE,
            detail_level=detail_level,
            pods=pods,
        )

    return check_manager.as_dict(as_list)
