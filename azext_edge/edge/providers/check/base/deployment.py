# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from rich.padding import Padding
from typing import Any, Callable, Dict, List, Optional

from .check_manager import CheckManager
from .node import check_nodes
from .resource import enumerate_ops_service_resources
from .user_strings import UNABLE_TO_DETERMINE_VERSION_MSG
from ..common import CoreServiceResourceKinds, ResourceOutputDetailLevel
from ...base import client
from ....common import CheckTaskStatus, ListableEnum
from ....providers.edge_api import EdgeResourceApi


logger = get_logger(__name__)
# TODO: unit test


def check_pre_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
) -> None:
    result["preDeployment"] = []
    desired_checks = {}
    desired_checks.update(
        {
            "checkK8sVersion": partial(_check_k8s_version, as_list=as_list),
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
    evaluate_funcs: Dict[ListableEnum, Callable],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: Optional[List[str]] = None,
    resource_name: str = None,
    excluded_resources: Optional[List[str]] = None,
) -> List[dict]:
    resource_enumeration, api_resources = enumerate_ops_service_resources(
        api_info, check_name, check_desc, as_list, excluded_resources
    )
    results = [resource_enumeration]
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
                results.append(
                    evaluate_func(detail_level=detail_level, as_list=as_list, resource_name=resource_name)
                )
    return results


def _check_k8s_version(as_list: bool = False) -> Dict[str, Any]:
    from kubernetes.client.models import VersionInfo
    from packaging import version

    from ..common import MIN_K8S_VERSION

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
        api_error_text = UNABLE_TO_DETERMINE_VERSION_MSG
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
