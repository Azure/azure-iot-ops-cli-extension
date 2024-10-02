# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from rich.padding import Padding
from typing import Any, Dict, List

from azext_edge.edge.providers.check.base.pod import evaluate_pod_health

from ..support.akri import AKRI_NAME_LABEL_V2

from ..base import get_namespaced_pods_by_prefix
from .base import (
    CheckManager,
    check_post_deployment,
    filter_resources_by_name,
    get_resources_grouped_by_namespace,
)

from .common import (
    AKRI_PREFIX,
    PADDING_SIZE,
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel,
)


def check_akri_deployment(
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
    check_manager = CheckManager(check_name="evalCoreServiceRuntime", check_desc="Evaluate Akri core service")

    padding = 6
    akri_runtime_resources: List[dict] = get_namespaced_pods_by_prefix(
        prefix=AKRI_PREFIX,
        namespace="",
        label_selector=AKRI_NAME_LABEL_V2,
    )

    if resource_name:
        akri_runtime_resources = filter_resources_by_name(
            resources=akri_runtime_resources,
            resource_name=resource_name,
        )

        if not akri_runtime_resources:
            check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value)
            check_manager.add_display(
                target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
                display=Padding("Unable to fetch pods.", (0, 0, 0, padding + 2)),
            )

    for namespace, pods in get_resources_grouped_by_namespace(akri_runtime_resources):
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value, namespace=namespace)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"Akri runtime resources in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)
            ),
        )

        evaluate_pod_health(
            check_manager=check_manager,
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            padding=padding + PADDING_SIZE,
            pods=pods,
            detail_level=detail_level,
        )

    return check_manager.as_dict(as_list)
