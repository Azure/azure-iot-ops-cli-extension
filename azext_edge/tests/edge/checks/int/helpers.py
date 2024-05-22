# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azext_edge.edge.common import ListableEnum
from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from ....helpers import find_extra_or_missing_names, get_kubectl_items


def remap_post_deployment(post_deployment):
    remap = {}
    for cond in post_deployment:
        name = cond.pop("name")
        remap[name] = cond
    return remap


def assert_enumerate_resources(
    post_deployment: dict,
    description_name: str,
    key_name: str,
    resource_api: EdgeResourceApi,
    resource_kinds: ListableEnum,
    present: bool = True
):
    # TODO: see if description_name and key_name can be combined for services (OPCUA)
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
    assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds.list())
    for kind in evaluation["evaluations"][0]["value"]:
        assert kind.lower() in resource_kinds.list()


# Used by Akri and OPCUA
def assert_eval_core_service_runtime(
    post_deployment: dict,
    description_name: str,
    pod_prefix: str,
    resource_match: str = "*",
):
    assert post_deployment["evalCoreServiceRuntime"]
    assert post_deployment["evalCoreServiceRuntime"]["description"] == f"Evaluate {description_name} core service"
    overall_status = "success"
    runtime_resource = post_deployment["evalCoreServiceRuntime"]["targets"]["coreServiceRuntimeResource"]
    for namespace in runtime_resource.keys():
        namespace_status = "success"
        assert not runtime_resource[namespace]["conditions"]
        evals = runtime_resource[namespace]["evaluations"]
        kubectl_pods = get_kubectl_items(
            prefixes=pod_prefix,
            service_type="pod",
            resource_match=resource_match
        )
        find_extra_or_missing_names(
            resource_type="pods",
            result_names=[pod["value"]["name"] for pod in evals],
            expected_names=[pod["name"] for pod in kubectl_pods]
        )

        for pod in evals:
            prefix, name = pod["name"].split("/")
            assert prefix == "pod"
            assert name == pod["value"]["name"]
            assert pod["value"]["status.phase"] == kubectl_pods[name]["status"]["phase"]
            expected_status = "success"
            if pod["value"]["status.phase"] == "Failed":
                expected_status = "error"
                namespace_status = overall_status = "error"
            elif pod["value"]["status.phase"] in ["Pending", "Unknown"]:
                expected_status = "warning"
                if namespace_status == "success":
                    namespace_status = "warning"
                if overall_status == "success":
                    overall_status = "warning"
            assert pod["status"] == expected_status
        assert runtime_resource[namespace]["status"] == namespace_status

    assert post_deployment["evalCoreServiceRuntime"]["status"] == overall_status
