# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from kubernetes.utils import parse_quantity
from azure.cli.core.azclierror import CLIInternalError
from ....helpers import run
from azext_edge.edge.providers.check.common import (
    AIO_SUPPORTED_ARCHITECTURES,
    MIN_NODE_MEMORY,
    MIN_NODE_STORAGE,
    MIN_NODE_VCPU
)

logger = get_logger(__name__)


@pytest.mark.parametrize("post", [None, False, True])
@pytest.mark.parametrize("pre", [None, False, True])
def test_check_pre_post(init_setup, post, pre):
    command = "az iot ops check --as-object "
    if pre is not None:
        command += f" --pre {pre}"
    if post is not None:
        command += f" --post {post}"
    result = run(command)

    # default service title
    expected_title = "Evaluation for {[bright_blue]mq[/bright_blue]} service deployment"
    expected_precheck_title = "[bright_blue]IoT Operations readiness[/bright_blue]"
    expected_pre = not post if pre is None else pre
    expected_post = not pre if post is None else post
    assert result["title"] == expected_title if expected_post else expected_precheck_title

    if pre is None and not post:
        try:
            aio_check = run("kubectl api-resources --api-group=orchestrator.iotoperations.azure.com")
            expected_pre = "orchestrator.iotoperations.azure.com" not in aio_check
        except CLIInternalError:
            from azext_edge.edge.providers.edge_api.orc import ORC_API_V1
            expected_pre = not ORC_API_V1.is_deployed()

    assert bool(result.get("preDeployment")) == expected_pre
    assert bool(result.get("postDeployment")) == expected_post

    if not expected_pre:
        # only check the pre results since the post results will be checked per service
        return

    assert len(result["preDeployment"]) == 2
    k8s_result, node_result = result["preDeployment"]

    # k8s evaluation
    assert k8s_result["description"] == "Evaluate Kubernetes server"
    assert k8s_result["name"] == "evalK8sVers"
    assert "k8s" in k8s_result["targets"]
    assert "_all_" in k8s_result["targets"]["k8s"]
    k8s_target_result = k8s_result["targets"]["k8s"]["_all_"]
    assert k8s_target_result["conditions"] == ["(k8s version)>=1.20"]
    k8s_version = run("kubectl version -o json").get("serverVersion")

    k8s_status = k8s_target_result["evaluations"][0]["status"]
    if k8s_version:
        expected_version = f"{k8s_version.get('major')}.{k8s_version.get('minor')}"
        assert k8s_target_result["evaluations"][0]["value"] == expected_version
        assert k8s_status == expected_status(expected_version >= "1.20")
    assert k8s_result["status"] == k8s_target_result["status"] == k8s_status

    # cluster node evaluation
    assert node_result["description"] == "Evaluate cluster nodes"
    assert node_result["name"] == "evalClusterNodes"
    kubectl_nodes = run("kubectl get nodes -o json")["items"]

    # num nodes
    assert "cluster/nodes" in node_result["targets"]
    assert "_all_" in node_result["targets"]["cluster/nodes"]
    node_count_target = node_result["targets"]["cluster/nodes"]["_all_"]
    assert node_count_target["conditions"] == ["len(cluster/nodes)>=1"]
    assert node_count_target["evaluations"][0]["value"] == len(kubectl_nodes)
    final_status = expected_status(len(kubectl_nodes) >= 1)
    assert node_count_target["evaluations"][0]["status"] == node_count_target["status"] == final_status

    # node eval
    for node in kubectl_nodes:
        node_name = node["metadata"]["name"]
        node_key = f"cluster/nodes/{node_name}"
        assert node_key in node_result["targets"]
        assert "_all_" in node_result["targets"][node_key]
        node_target = node_result["targets"][node_key]["_all_"]

        assert node_target["conditions"] == [
            f"info.architecture in ({','.join(AIO_SUPPORTED_ARCHITECTURES)})",
            f"condition.cpu>={MIN_NODE_VCPU}",
            f"condition.memory>={MIN_NODE_MEMORY}",
            f"condition.ephemeral-storage>={MIN_NODE_STORAGE}"
        ]

        node_arch = node_target["evaluations"][0]["value"]["info.architecture"]
        assert node_arch == node["status"]["nodeInfo"]["architecture"]
        assert node_target["evaluations"][0]["status"] == expected_status(
            node_arch in AIO_SUPPORTED_ARCHITECTURES
        )

        node_capacity = node["status"]["capacity"]
        node_cpu = node_target["evaluations"][1]["value"]["condition.cpu"]
        assert node_cpu == int(node_capacity["cpu"])
        assert node_target["evaluations"][1]["status"] == expected_status(
            node_cpu >= int(MIN_NODE_VCPU)
        )

        node_memory = node_target["evaluations"][2]["value"]["condition.memory"]
        assert node_memory == int(parse_quantity(node_capacity["memory"]))
        assert node_target["evaluations"][1]["status"] == expected_status(
            node_memory >= parse_quantity(MIN_NODE_MEMORY)
        )

        node_storage = node_target["evaluations"][3]["value"]["condition.ephemeral-storage"]
        assert node_storage == int(parse_quantity(node_capacity["ephemeral-storage"]))
        assert node_target["evaluations"][1]["status"] == expected_status(
            node_storage >= parse_quantity(MIN_NODE_STORAGE)
        )

        node_status = expected_status(
            all([cond["status"] == "success" for cond in node_target["evaluations"]])
        )
        assert node_status == node_target["status"]
        final_status = expected_status(
            (final_status == "success") and (node_status == "success")
        )

    assert final_status == node_result["status"]


def expected_status(success_condition: bool):
    return "success" if success_condition else "error"
