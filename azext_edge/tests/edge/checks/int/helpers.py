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
    assert_extra_or_missing_names,
    get_kubectl_workload_items,
    run,
    sort_kubectl_items_by_namespace,
)

# use this to replace a kubectl pod body in checks to avoid key errors/minimize code
MISSING_POD_BODY = {"status": {"phase": {}}}


def assert_enumerate_resources(
    post_deployment: dict,
    description_name: str,
    key_name: str,
    resource_api: EdgeResourceApi,
    resource_kinds: list,
    present: bool = True,
):
    key = f"enumerate{key_name}Api"
    status = "success" if present else "error"
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

    if present and resource_kinds:
        assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds)
        for kind in evaluation["evaluations"][0]["value"]:
            assert kind.lower() in resource_kinds


# Used by Akri and OPCUA and Dataflow
def assert_eval_core_service_runtime(
    check_results: dict,
    description_name: str,
    pod_prefix: str,
    pre_check_pods: dict,
    resource_match: Optional[str] = None,
):
    assert check_results["evalCoreServiceRuntime"]
    assert check_results["evalCoreServiceRuntime"]["description"] == f"Evaluate {description_name} core service"
    overall_status = "skipped"
    runtime_resource = check_results["evalCoreServiceRuntime"]["targets"]["coreServiceRuntimeResource"]
    for namespace in runtime_resource.keys():
        namespace_status = "skipped"
        evals = runtime_resource[namespace]["evaluations"]
        post_check_pods = get_pods(pod_prefix=pod_prefix, resource_match=resource_match)

        if post_check_pods:
            assert runtime_resource[namespace]["conditions"]
        else:
            assert not runtime_resource[namespace]["conditions"]

        results = list(set(pod["name"].replace("pod/", "") for pod in evals))
        assert_extra_or_missing_names(
            resource_type="pods",
            result_names=results,
            pre_expected_names=pre_check_pods.keys(),
            post_expected_names=post_check_pods.keys(),
        )

        # note that missing/extra pod case should be caught by the assert_extra_or_missing_names
        for pod_name in results:
            pre_pod = pre_check_pods.get(pod_name)
            post_pod = post_check_pods.get(pod_name)

            # preference for using pre-check kubectl results
            try:
                namespace_status, overall_status = _assert_pod_conditions(
                    pod_name=pod_name,
                    evals=evals,
                    kubectl_pod=pre_pod,
                    namespace_status=namespace_status,
                    overall_status=overall_status
                )
            except AssertionError:
                namespace_status, overall_status = _assert_pod_conditions(
                    pod_name=pod_name,
                    evals=evals,
                    kubectl_pod=post_pod,
                    namespace_status=namespace_status,
                    overall_status=overall_status
                )

        assert runtime_resource[namespace]["status"] == namespace_status
    assert check_results["evalCoreServiceRuntime"]["status"] == overall_status


def assert_pod_conditions(pod_conditions, phase_conditions_eval, expected_status):
    if phase_conditions_eval:
        for condition in pod_conditions:
            condition_type = condition["type"]
            condition_status = condition.get("status") == "True"
            assert phase_conditions_eval["value"][f"status.conditions.{condition_type.lower()}"] == condition_status

        assert phase_conditions_eval["status"] == expected_status
    else:
        assert not pod_conditions


def assert_pod_condition(pod_conditions, pod_evals, condition_type, condition_key):
    condition_eval = next((pod for pod in pod_evals if condition_key in pod["value"]), None)
    if condition_eval:
        condition_status = [
            condition.get("status") for condition in pod_conditions if condition["type"] == condition_type
        ]
        assert str(condition_eval["value"][condition_key]) == condition_status.pop()
        if not condition_eval["value"][condition_key]:
            assert condition_eval["status"] == "error"
        else:
            assert condition_eval["status"] == "success"
        return condition_eval["status"]


def assert_general_eval_custom_resources(
    post_deployment: Dict[str, Any],
    items: Dict[str, Any],
    description_name: str,
    resource_api: EdgeResourceApi,
    resource_kind_present: bool,
    include_all_namespace: bool = False,
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
    assert post_deployment[key]["description"].replace(" ", "").lower().endswith(resource_plural.lower())

    # check the target existence
    sorted_items = sort_kubectl_items_by_namespace(items, include_all=include_all_namespace)
    target_key = f"{resource_plural}.{resource_api.group}"
    assert target_key in post_deployment[key]["targets"]
    namespace_dict = post_deployment[key]["targets"][target_key]
    for namespace, kubectl_items in sorted_items.items():
        assert namespace in namespace_dict
        # filter out the kubernetes runtime resource evals using /, only check the CRD evals
        crd_evals = [item for item in namespace_dict[namespace]["evaluations"] if "/" not in item.get("name", "")]
        # filter checks by unique checks per item name
        check_names = {item.get("name") for item in crd_evals if item.get("name")}
        # if using resource name filter, could have missing items
        assert len(check_names) <= len(kubectl_items)
        for name in check_names:
            assert name in kubectl_items


def combine_statuses(status_list: List[str]):
    final_status = "success"
    for status in status_list:
        if final_status == "success" and status in ["warning", "error", "skipped"]:
            final_status = status
        elif final_status in ["warning", "skipped"] and status == "error":
            final_status = status
    return final_status


def get_expected_status(
    success_or_fail: bool, success_or_warning: Optional[bool] = None, warning_or_fail: Optional[bool] = None
):
    status = "success" if success_or_fail else "error"
    if any([status == "success" and success_or_warning is False, status == "error" and warning_or_fail is True]):
        status = "warning"
    return status


def get_pods(pod_prefix: str, resource_match: Optional[str] = None) -> dict:
    return get_kubectl_workload_items(
        prefixes=pod_prefix, service_type="pod", resource_match=resource_match
    )


def run_check_command(
    detail_level: str,
    ops_service: str,
    resource_api: Optional[EdgeResourceApi] = None,
    resource_kind: Optional[str] = None,
    resource_match: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    service_present = False

    if resource_api:
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


def _all_known_conditions_true(
    conditions: list,
    known_conditions: list,
) -> bool:
    for condition in conditions:
        if condition["type"] in known_conditions and condition["status"] != "True":
            return False
    return True


def _assert_pod_conditions(
    pod_name: str, evals: dict, kubectl_pod: dict, namespace_status: str, overall_status: str
) -> Tuple[str, str]:
    # find all evals entries for this pod
    pod_evals = [pod for pod in evals if pod_name in pod["name"]]

    assert kubectl_pod, f"Pod {pod_name} could not be fetched via kubectl"
    assert pod_evals, f"Pod {pod_name} has no check evaluations"
    assert pod_evals[0]["name"] == f"pod/{pod_name}"

    # check phase and conditions
    phase_conditions_eval = next(pod_eval for pod_eval in pod_evals if "status.phase" in pod_eval["value"])
    assert phase_conditions_eval["value"]["status.phase"] == kubectl_pod["status"]["phase"]
    expected_status = "success"
    if phase_conditions_eval["value"]["status.phase"] in ["Pending", "Unknown"]:
        expected_status = "warning"
        namespace_status = overall_status = expected_status
    elif phase_conditions_eval["value"]["status.phase"] == "Failed":
        expected_status = "error"
        if namespace_status == "success":
            namespace_status = expected_status
        if overall_status == "success":
            overall_status = expected_status

    # check conditions
    conditions_to_evaluate = [
        ("Initialized", "status.conditions.initialized"),
        ("Ready", "status.conditions.ready"),
        ("ContainersReady", "status.conditions.containersready"),
        ("PodScheduled", "status.conditions.podscheduled"),
        ("PodReadyToStartContainers", "status.conditions.podreadytostartcontainers"),
    ]
    pod_conditions = kubectl_pod["status"].get("conditions", {})

    known_conditions = [condition[0] for condition in conditions_to_evaluate]
    unknown_conditions = [
        condition["type"] for condition in pod_conditions if condition["type"] not in known_conditions
    ]
    # if all known conditions in pod_conditions are "True", set is_known_success to True
    is_known_success = False
    if _all_known_conditions_true(pod_conditions, known_conditions):
        is_known_success = True

    if not is_known_success:
        expected_status = "error"

    if is_known_success and unknown_conditions:
        # if all known conditions are True, but there are unknown conditions, set status to warning
        expected_status = "warning"

    assert_pod_conditions(pod_conditions, phase_conditions_eval, expected_status)
    assert phase_conditions_eval["status"] == expected_status

    if namespace_status != "error":
        namespace_status = expected_status
    if overall_status != "error":
        overall_status = expected_status

    return namespace_status, overall_status
