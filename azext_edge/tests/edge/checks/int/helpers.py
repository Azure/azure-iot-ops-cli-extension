# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Tuple
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from ....helpers import (
    PLURAL_KEY,
    find_extra_or_missing_names,
    get_kubectl_workload_items,
    run,
    sort_kubectl_items_by_namespace
)


def assert_enumerate_resources(
    post_deployment: dict,
    description_name: str,
    key_name: str,
    resource_api: EdgeResourceApi,
    resource_kinds: list,
    present: bool = True
):
    key = f"enumerate{key_name}Api"
    status = "success" if present else "skipped"
    assert post_deployment[key]
    assert post_deployment[key]["status"] == status
    assert post_deployment[key]["description"] == f"Enumerate {description_name} API resources"

    assert len(post_deployment[key]["targets"]) == 1
    target_key = f"{resource_api.group}/{resource_api.version}"
    assert target_key in post_deployment[key]["targets"]
    evaluation = post_deployment[key]["targets"][target_key]["_all_"]
    assert evaluation["conditions"] is None
    assert evaluation["status"] == status
    assert len(evaluation["evaluations"]) == 1
    assert evaluation["evaluations"][0]["status"] == status
    assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds)
    for kind in evaluation["evaluations"][0]["value"]:
        assert kind.lower() in resource_kinds


# Used by Akri and OPCUA
def assert_eval_core_service_runtime(
    post_deployment: dict,
    description_name: str,
    pod_prefix: str,
    resource_match: Optional[str] = None,
):
    assert post_deployment["evalCoreServiceRuntime"]
    assert post_deployment["evalCoreServiceRuntime"]["description"] == f"Evaluate {description_name} core service"
    overall_status = "success"
    runtime_resource = post_deployment["evalCoreServiceRuntime"]["targets"]["coreServiceRuntimeResource"]
    for namespace in runtime_resource.keys():
        namespace_status = "success"
        assert not runtime_resource[namespace]["conditions"]
        evals = runtime_resource[namespace]["evaluations"]
        kubectl_pods = get_kubectl_workload_items(
            prefixes=pod_prefix,
            service_type="pod",
            resource_match=resource_match
        )
        results = [pod["value"]["name"] for pod in evals]
        find_extra_or_missing_names(
            resource_type="pods",
            result_names=results,
            expected_names=kubectl_pods.keys()
        )

        for pod in evals:
            prefix, name = pod["name"].split("/")
            assert prefix == "pod"
            assert name == pod["value"]["name"]
            assert pod["value"]["status.phase"] == kubectl_pods[name]["status"]["phase"]
            expected_status = "success"
            if pod["value"]["status.phase"] in ["Pending", "Unknown"]:
                expected_status = "warning"
                namespace_status = overall_status = expected_status
            elif pod["value"]["status.phase"] == "Failed":
                expected_status = "error"
                if namespace_status == "success":
                    namespace_status = expected_status
                if overall_status == "success":
                    overall_status = expected_status
            assert pod["status"] == expected_status
        assert runtime_resource[namespace]["status"] == namespace_status

    assert post_deployment["evalCoreServiceRuntime"]["status"] == overall_status


def assert_general_eval_custom_resources(
    post_deployment: Dict[str, Any],
    items: Dict[str, Any],
    description_name: str,
    resource_api: EdgeResourceApi,
    resource_kind_present: bool,
    include_all_namespace: bool = False
):
    # this should check general shared attributes for different services.
    # specific target checks should be in separate functions
    resource_plural = items[PLURAL_KEY]
    key = None
    for possible_key in post_deployment:
        if possible_key.lower() == f"eval{resource_plural}":
            key = possible_key
            break

    if not resource_kind_present:
        assert key is None
        return
    assert post_deployment[key]
    assert post_deployment[key]["description"].startswith(f"Evaluate {description_name}")
    # for the ones that have spaces
    assert post_deployment[key]["description"].replace(" ", "").endswith(resource_plural)

    # check the target existence
    sorted_items = sort_kubectl_items_by_namespace(items, include_all=include_all_namespace)
    target_key = f"{resource_plural}.{resource_api.group}"
    assert target_key in post_deployment[key]["targets"]
    namespace_dict = post_deployment[key]["targets"][target_key]
    for namespace, kubectl_items in sorted_items.items():
        assert namespace in namespace_dict
        check_names = []
        for item in namespace_dict[namespace]["evaluations"]:
            if item.get("name"):
                check_names.append(item.get("names"))
        # if using resource name filter, could have missing items
        assert len(check_names) <= len(kubectl_items)
        for name in check_names:
            assert name in kubectl_items


def combine_statuses(
    status_list: List[str]
):
    final_status = "success"
    for status in status_list:
        if final_status == "success" and status in ["warning", "error", "skipped"]:
            final_status = status
        elif final_status in ["warning", "skipped"] and status == "error":
            final_status = status
    return final_status


def expected_status(
    success_or_fail: bool,
    success_or_warning: Optional[bool] = None,
    warning_or_fail: Optional[bool] = None
):
    status = "success" if success_or_fail else "error"
    if any([
        status == "success" and success_or_warning is False,
        status == "error" and warning_or_fail is True
    ]):
        status = "warning"
    return status


def run_check_command(
    detail_level: str,
    ops_service: str,
    resource_api: EdgeResourceApi,
    resource_kind: str,
    resource_match: str,
) -> Tuple[Dict[str, Any], bool]:
    try:
        aio_check = run(f"kubectl api-resources --api-group={resource_api.group}")
        service_present = resource_api.group in aio_check
    except CLIInternalError:
        service_present = resource_api.is_deployed()
    # note that the text decoder really does not like the emojis
    command = f"az iot ops check --as-object --ops-service {ops_service} --detail-level {detail_level} "
    if resource_kind:
        command += f"--resources {resource_kind} "
    if resource_match:
        command += f"--resource-name {resource_match} "
    result = run(command)

    return {cond["name"]: cond for cond in result["postDeployment"]}, service_present
