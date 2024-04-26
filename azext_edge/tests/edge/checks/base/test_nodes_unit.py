# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from kubernetes.client.models import V1Node, V1NodeList, V1NodeStatus, V1ObjectMeta
from kubernetes.utils import parse_quantity

from azext_edge.edge.providers.check.common import (
    AIO_SUPPORTED_ARCHITECTURES, DISPLAY_BYTES_PER_GIGABYTE, MIN_NODE_MEMORY, MIN_NODE_STORAGE, MIN_NODE_VCPU
)
from ....generators import generate_random_string


@pytest.fixture
def mocked_node_client(mocked_client, mocker, request):
    params = getattr(request, "param", [])

    nodes = []
    for node_params in params:
        arch = node_params.pop("architecture", generate_random_string(size=5))
        # Too annoying to make a valid one
        node_info = mocker.Mock(architecture=arch)
        node = V1Node(
            metadata=V1ObjectMeta(name=generate_random_string()),
            status=V1NodeStatus(
                capacity=node_params,
                node_info=node_info
            )
        )
        nodes.append(node)

    # patched_client = mocker.patch("azext_edge.edge.providers.base.client")
    mocked_client.CoreV1Api().list_node.return_value = V1NodeList(items=nodes)
    yield mocked_client


@pytest.mark.parametrize("mocked_node_client", [
    [],
    [
        {
            "architecture": "amd64",
            "cpu": 4,
            "memory": "16G",
            "ephemeral-storage": "30G"
        }
    ],
    [
        {
            "architecture": "arm64",
            "cpu": 6,
            "memory": "20G",
            "ephemeral-storage": "4G"
        }
    ],
    [
        {
            "architecture": "amd64",
            "cpu": 5,
            "memory": "10G",
            "ephemeral-storage": "30G"
        },
    ],
    [
        {
            "architecture": "amd64",
            "cpu": 3,
            "memory": "20G",
            "ephemeral-storage": "30G"
        }
    ],
    [
        {
            "architecture": "x86",
            "cpu": 3,
            "memory": "20G",
            "ephemeral-storage": "30G"
        }
    ],
    [
        {
            "architecture": "amd64",
            "cpu": 5,
            "memory": "10G",
            "ephemeral-storage": "30G"
        },
        {
            "architecture": "arm64",
        }
    ],
], ids=["none", "min reqs", "storage", "memory", "cpu", "architecture", "multi-node"], indirect=True)
def test_check_nodes(mocked_node_client):
    from azext_edge.edge.providers.check.base.node import check_nodes
    # no point in checking as_list is false since it just affects check manager
    result = check_nodes(as_list=True)
    assert result
    assert result["name"] == "evalClusterNodes"

    nodes = mocked_node_client.CoreV1Api().list_node.return_value.items
    evaluation = result["targets"]["cluster/nodes"]["_all_"]["evaluations"]
    if not nodes:
        assert result["status"] == "error"
        assert evaluation[0]["value"] == "No nodes detected."
        return
    elif len(nodes) > 1:
        warning = result["targets"]["cluster/nodes"]["_all_"]["displays"][0].renderable
        assert "Currently, only single-node clusters are officially supported for AIO deployments" in warning
        assert result["targets"]["cluster/nodes"]["_all_"]["status"] == "warning"
    else:
        assert result["targets"]["cluster/nodes"]["_all_"]["status"] == "success"

    assert len(result["targets"]) == (len(nodes) + 1)
    table = result["targets"]["cluster/nodes"]["_all_"]["displays"][-1].renderable
    headers = [col.header for col in table.columns]
    assert headers == ["Name", "Architecture", "CPU (vCPU)", "Memory (GB)", "Storage (GB)"]

    # the generator is weird
    unpacked_cols = [list(col.cells) for col in table.columns]
    
    # expected row
    assert "Minimum requirements" in unpacked_cols[0][0]
    assert ", ".join(AIO_SUPPORTED_ARCHITECTURES) in unpacked_cols[1][0]
    assert MIN_NODE_VCPU in unpacked_cols[2][0]
    assert MIN_NODE_MEMORY[:-1] in unpacked_cols[3][0]
    assert MIN_NODE_STORAGE[:-1] in unpacked_cols[4][0]

    for i in range(len(nodes)):
        node = nodes[i]
        name = node.metadata.name
        # first row is to show expected
        i = i + 1
        assert name in unpacked_cols[0][i]
        arch = node.status.node_info.architecture
        assert arch in unpacked_cols[1][i]
        cpu = node.status.capacity.get("cpu", 0)
        assert str(cpu) in unpacked_cols[2][i]
        memory = node.status.capacity.get("memory", 0)
        assert "%.2f" % (parse_quantity(memory) / DISPLAY_BYTES_PER_GIGABYTE) in unpacked_cols[3][i]
        storage = node.status.capacity.get("ephemeral-storage", 0)
        assert "%.2f" % (parse_quantity(storage) / DISPLAY_BYTES_PER_GIGABYTE) in unpacked_cols[4][i]

        assert f"cluster/nodes/{name}" in result["targets"]
        result_node = result["targets"][f"cluster/nodes/{name}"]["_all_"]

        arch_status = arch in AIO_SUPPORTED_ARCHITECTURES
        assert result_node["conditions"][0] == f"info.architecture in ({','.join(AIO_SUPPORTED_ARCHITECTURES)})"
        assert result_node["evaluations"][0]["status"] == bool_to_status(arch_status)
        assert result_node["evaluations"][0]["value"]["info.architecture"] == arch

        cpu_status = cpu >= int(MIN_NODE_VCPU)
        assert result_node["conditions"][1] == f"condition.cpu>={MIN_NODE_VCPU}"
        assert result_node["evaluations"][1]["status"] == bool_to_status(cpu_status)
        assert result_node["evaluations"][1]["value"]["condition.cpu"] == cpu

        memory_status = parse_quantity(memory) >= parse_quantity(MIN_NODE_MEMORY)
        assert result_node["conditions"][2] == f"condition.memory>={MIN_NODE_MEMORY}"
        assert result_node["evaluations"][2]["status"] == bool_to_status(memory_status)
        assert result_node["evaluations"][2]["value"]["condition.memory"] == parse_quantity(memory)

        storage_status = parse_quantity(storage) >= parse_quantity(MIN_NODE_STORAGE)
        assert result_node["conditions"][3] == f"condition.ephemeral-storage>={MIN_NODE_STORAGE}"
        assert result_node["evaluations"][3]["status"] == bool_to_status(storage_status)
        assert result_node["evaluations"][3]["value"]["condition.ephemeral-storage"] == parse_quantity(storage)

        overall_status = all([arch_status, cpu_status, storage_status, memory_status])
        assert result_node["status"] == bool_to_status(overall_status)


def bool_to_status(status: bool):
    return "success" if status else "error"
