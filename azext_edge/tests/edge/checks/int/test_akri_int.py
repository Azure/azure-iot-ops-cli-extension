# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
import pytest
from knack.log import get_logger
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.common import ListableEnum
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    AkriResourceKinds, AKRI_API_V0
)
from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from ....helpers import find_extra_or_missing_names, get_kubectl_items, run
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("name_match", [None, "*otel*", "akri-opcua*", generate_names()])
@pytest.mark.parametrize("resource_kind", AkriResourceKinds.list() + [None])
def test_check(init_setup, detail_level, name_match, resource_kind):
    try:
        aio_check = run(f"kubectl api-resources --api-group={AKRI_API_V0.group}")
        akri_present = AKRI_API_V0.group in aio_check
    except CLIInternalError:
        akri_present = AKRI_API_V0.is_deployed()
    ops_service = "akri"
    # note that the text decoder really does not like the emojis
    command = f"az iot ops check --as-object --ops-service {ops_service} --detail-level {detail_level}"
    if resource_kind:
        command += f"--resources {resource_kind}"
    if name_match:
        command += f"--resource-name {name_match}"
    result = run(command)

    post_deployment = remap_post_deployment(result["postDeployment"])

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        name=ops_service,
        resource_api=AKRI_API_V0,
        resource_kinds=AkriResourceKinds,
        present=akri_present,
    )


def remap_post_deployment(post_deployment):
    remap = {}
    for cond in post_deployment:
        name = cond.pop("name")
        remap[name] = cond
    return remap


def assert_enumerate_resources(
    post_deployment: dict,
    name: str,
    resource_api: EdgeResourceApi,
    resource_kinds: ListableEnum,
    present: bool = True
):
    key = f"enumerate{name.capitalize()}Api"
    status = "success" if present else "skipped"
    assert post_deployment[key]
    assert post_deployment[key]["status"] == status
    assert post_deployment[key]["description"] == f"Enumerate {name.capitalize()} API resources"

    assert len(post_deployment[key]["targets"]) == 1
    assert resource_api.group in post_deployment[key]["targets"]
    evaluation = post_deployment[key]["targets"][resource_api.group]["_all_"]
    assert evaluation["conditions"] is None
    assert evaluation["status"] == status
    assert len(evaluation["evaluations"]) == 1
    assert evaluation["evaluations"][0]["status"] == status
    assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds.list())
    for kind in evaluation["evaluations"][0]["value"]:
        assert kind.lower() in resource_kinds.list()


def assert_eval_core_service_runtime(
    post_deployment: dict,
    resource_name: Optional[List[str]] = None,
):
    assert post_deployment["evalCoreServiceRuntime"]
    assert post_deployment["evalCoreServiceRuntime"]["description"] == "Evaluate Akri core service"
    overall_status = "success"
    runtime_resource = post_deployment["evalCoreServiceRuntime"]["targets"]["coreServiceRuntimeResource"]
    for namespace in runtime_resource.keys():
        namespace_status = "success"
        assert not runtime_resource[namespace]["conditions"]
        evals = runtime_resource[namespace]["evaluations"]
        akri_pods = get_kubectl_items(prefixes="aio-akri", service_type="pod")
        find_extra_or_missing_names(
            resource_type="pods",
            result_names=[pod["value"]["name"] for pod in evals],
            expected_names=[pod["name"] for pod in akri_pods]
        )

        for pod in evals:
            prefix, name = pod["name"].split("/")
            assert prefix == "pod"
            assert name == pod["value"]["name"]
            assert pod["value"]["status.phase"] == akri_pods[name]["status"]["phase"]
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


def assert_eval_configurations(
    post_deployment: dict,
    resource_name: Optional[List[str]] = None,
    detail_level: int = 0
):
    all_configurations = run("kubectl get configurations -A")
    status = "success"
    if not all_configurations and resource_name:
        status = "skipped"
    if not all_configurations and not resource_name:
        status = "error"
    resource = AkriResourceKinds.CONFIGURATION.value
    key = f"eval{resource.capitalize()}s"
    assert post_deployment[key]
    assert post_deployment[key]["description"] == f"Evaluate Akri {resource}s"
    assert post_deployment[key]["status"] == status
