# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from collections import defaultdict
from functools import partial
from typing import Any, Callable, Dict, List, Optional

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from rich.padding import Padding

from ....common import CheckTaskStatus, ListableEnum
from ....providers.edge_api import EdgeResourceApi
from ...base import client, load_config_context
from ..common import NON_ERROR_STATUSES, CoreServiceResourceKinds, ResourceOutputDetailLevel
from .check_manager import CheckManager
from .node import check_nodes
from .resource import enumerate_ops_service_resources
from .user_strings import UNABLE_TO_DETERMINE_VERSION_MSG

logger = get_logger(__name__)


def validate_cluster_prechecks(**kwargs) -> None:
    context_name = kwargs.get("context_name")
    load_config_context(context_name=context_name)

    acs_config = kwargs.get("acs_config")
    storage_space_check = kwargs.get("storage_space_check")

    pre_checks = check_pre_deployment(acs_config=acs_config, storage_space_check=storage_space_check)
    errors = defaultdict(list)
    for check in pre_checks:
        for target in check["targets"]:
            for namespace in check["targets"][target]:  # for all prechecks, namespace is currently _all_
                for idx, check_eval in enumerate(check["targets"][target][namespace]["evaluations"]):
                    if check_eval["status"] not in NON_ERROR_STATUSES:
                        # TODO - relies on same order and count of conditions / evaluations
                        expected_condition = (
                            check["targets"][target][namespace]["conditions"][idx]
                            if idx < len(check["targets"][target][namespace]["conditions"])
                            else "N/A"
                        )
                        errors[target].append(f"Expected: '{expected_condition}', Actual: '{check_eval['value']}'")

    if errors:
        error_str = ""
        for target in errors:
            error_str += f"\tTarget '{target}':\n"
            for error in errors[target]:
                error_str += f"\t\t{error}\n"

        raise ValidationError("Cluster readiness pre-checks failed:\n" + error_str)


def check_pre_deployment(
    as_list: bool = False, acs_config: Optional[dict] = None, storage_space_check: Optional[bool] = True
) -> List[dict]:
    result = []
    desired_checks = {}
    kernel_version_check = bool(acs_config)
    desired_checks.update(
        {
            "checkK8sVersion": partial(_check_k8s_version, as_list=as_list),
            "checkNodes": partial(
                check_nodes,
                as_list=as_list,
                kernel_version_check=kernel_version_check,
                storage_space_check=storage_space_check,
            ),
        }
    )
    if acs_config:
        desired_checks.update(
            {
                "checkStorageClasses": partial(_check_storage_classes, acs_config=acs_config, as_list=as_list),
            }
        )
    for c in desired_checks:
        output = desired_checks[c]()
        result.append(output)
    return result


def check_post_deployment(
    evaluate_funcs: Dict[ListableEnum, Callable],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    api_info: Optional[EdgeResourceApi] = None,
    check_name: Optional[str] = None,
    check_desc: Optional[str] = None,
    resource_kinds: Optional[List[str]] = None,
    resource_name: str = None,
    excluded_resources: Optional[List[str]] = None,
) -> List[dict]:
    results = []
    lowercase_api_resources = {}

    if api_info:
        resource_enumeration, api_resources = enumerate_ops_service_resources(
            api_info, check_name, check_desc, as_list, excluded_resources
        )
        results = [resource_enumeration]
        lowercase_api_resources = {k.lower(): v for k, v in api_resources.items()}

    for resource, evaluate_func in evaluate_funcs.items():
        should_check_resource = not resource_kinds or resource.value in resource_kinds
        append_resource = False
        # only add core service evaluation if there is no resource filter
        if resource == CoreServiceResourceKinds.RUNTIME_RESOURCE and not resource_kinds:
            append_resource = True
        elif (
            resource and lowercase_api_resources and resource.value in lowercase_api_resources and should_check_resource
        ):
            append_resource = True

        if append_resource:
            results.append(evaluate_func(detail_level=detail_level, as_list=as_list, resource_name=resource_name))
    return results


def _check_k8s_version(as_list: bool = False) -> Dict[str, Any]:
    from kubernetes.client.models import VersionInfo

    from ..common import MIN_K8S_VERSION

    version_client = client.VersionApi()

    target_k8s_version = "k8s"
    check_manager = CheckManager(check_name="evalK8sVers", check_desc="Evaluate Kubernetes server")
    check_manager.add_target(
        target_name=target_k8s_version,
        conditions=[f"(k8s version)>={MIN_K8S_VERSION}"],
    )

    try:
        from packaging import version

        version_details: VersionInfo = version_client.get_code()
    except (ApiException, ImportError) as ae:
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


def _check_storage_classes(acs_config: dict, as_list: bool = False) -> Dict[str, Any]:
    from kubernetes.client.models import V1StorageClassList

    expected_classes = acs_config.get("feature.diskStorageClass", "")
    check_manager = CheckManager(check_name="evalStorageClasses", check_desc="Evaluate storage classes")
    target = "cluster/storage-classes"
    check_manager.add_target(
        target_name=target,
        conditions=[
            "len(cluster/storage-classes)>=1",
            f"contains(cluster/storage-classes, any({expected_classes}))",
        ],
    )

    try:
        storage_client = client.StorageV1Api()
        storage_classes: V1StorageClassList = storage_client.list_storage_class()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = "Unable to fetch storage classes"
        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.error.value,
            value=api_error_text,
        )
    else:
        if not storage_classes or not storage_classes.items:
            check_manager.add_target_eval(
                target_name=target, status=CheckTaskStatus.error.value, value="No storage classes available"
            )
            return check_manager.as_dict()

        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.success.value,
            value={"len(cluster/storage-classes)": len(storage_classes.items)},
        )

        expected_class_names = expected_classes.split(",")
        storage_class_names = [sc.metadata.name for sc in storage_classes.items]
        matches = [sc for sc in storage_class_names if sc in expected_class_names]
        storage_status = CheckTaskStatus.success if matches else CheckTaskStatus.error
        check_manager.add_target_eval(
            target_name=target,
            status=storage_status.value,
            value=",".join(storage_class_names),
        )

    return check_manager.as_dict(as_list)
