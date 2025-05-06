# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from kubernetes.client.models import V1Node, V1NodeList, V1NodeStatus, V1ObjectMeta
from kubernetes.utils import parse_quantity

from azext_edge.edge.providers.check.common import (
    ACSA_MIN_NODE_KERNEL_VERSION,
    AIO_SUPPORTED_ARCHITECTURES,
    DISPLAY_BYTES_PER_GIGABYTE,
    MIN_NODE_MEMORY,
    MIN_NODE_STORAGE,
    MIN_NODE_VCPU,
)

from .....edge.util.machinery import scoped_semver_import
from ....generators import generate_random_string


@pytest.fixture
def mocked_node_client(mocked_client, mocker, request):
    params = getattr(request, "param", [])

    nodes = []
    for node_params in params:
        arch = node_params.pop("architecture", generate_random_string(size=5))
        # Too annoying to make a valid one
        node_info = mocker.Mock(architecture=arch, kernel_version=node_params.pop("kernel_version", "0.0.0"))
        node = V1Node(
            metadata=V1ObjectMeta(name=generate_random_string()),
            status=V1NodeStatus(allocatable=node_params, node_info=node_info),
        )
        nodes.append(node)

    # patched_client = mocker.patch("azext_edge.edge.providers.base.client")
    mocked_client.CoreV1Api().list_node.return_value = V1NodeList(items=nodes)
    yield mocked_client


@pytest.mark.parametrize(
    "mocked_node_client",
    [
        [],
        [{"architecture": "amd64", "cpu": 4, "memory": "16G", "ephemeral-storage": "30G", "kernel_version": "5.4.0"}],
        [{"architecture": "arm64", "cpu": 6, "memory": "20G", "ephemeral-storage": "4G", "kernel_version": "6.0"}],
        [
            {
                "architecture": "amd64",
                "cpu": 5,
                "memory": "10G",
                "ephemeral-storage": "30G",
                "kernel_version": "6.0.0-azure-test",
            },
        ],
        [
            {
                "architecture": "amd64",
                "cpu": 3,
                "memory": "20G",
                "ephemeral-storage": "30G",
                "kernel_version": "5.15.1.1-test1.2",
            }
        ],
        [{"architecture": "x86", "cpu": 3, "memory": "20G", "ephemeral-storage": "30G"}],
        [
            {"architecture": "amd64", "cpu": 5, "memory": "10G", "ephemeral-storage": "30G"},
            {
                "architecture": "arm64",
            },
        ],
    ],
    ids=["none", "min reqs", "storage", "memory", "cpu", "architecture", "multi-node"],
    indirect=True,
)
@pytest.mark.parametrize(
    "kernel_version_check",
    [
        True,
        False,
    ],
)
@pytest.mark.parametrize(
    "storage_space_check",
    [
        True,
        False,
    ],
)
def test_check_nodes(mocked_node_client, kernel_version_check, storage_space_check):
    from azext_edge.edge.providers.check.base.node import check_nodes

    # no point in checking as_list is false since it just affects check manager
    result = check_nodes(
        as_list=True, kernel_version_check=kernel_version_check, storage_space_check=storage_space_check
    )
    assert result
    assert result["name"] == "evalClusterNodes"

    nodes = mocked_node_client.CoreV1Api().list_node.return_value.items
    evaluation = result["targets"]["cluster/nodes"]["_all_"]["evaluations"]
    if not nodes:
        assert result["status"] == "error"
        assert evaluation[0]["value"] == "No nodes detected."
        return
    else:
        assert result["targets"]["cluster/nodes"]["_all_"]["status"] == "success"

    assert len(result["targets"]) == (len(nodes) + 1)
    table = result["targets"]["cluster/nodes"]["_all_"]["displays"][-1].renderable
    headers = [col.header for col in table.columns]
    expected_headers = ["Name", "Architecture"]
    if kernel_version_check:
        expected_headers.append("Kernel version")
    if storage_space_check:
        expected_headers.append("Ephemeral\nStorage (GB)")
    expected_headers.extend(["CPU (vCPU)", "Memory (GB)"])
    assert headers == expected_headers

    # the generator is weird
    unpacked_cols = [list(col.cells) for col in table.columns]

    # TODO - hacky index mapping for row/col
    name_idx = 0
    arch_idx = 1
    kernel_idx = 2
    storage_idx = 3 if kernel_version_check else 2
    cpu_idx = -2
    memory_idx = -1

    # expected row
    assert "Minimum requirements" in unpacked_cols[name_idx][0]
    assert ", ".join(AIO_SUPPORTED_ARCHITECTURES) in unpacked_cols[arch_idx][0]
    if kernel_version_check:
        assert ACSA_MIN_NODE_KERNEL_VERSION in unpacked_cols[kernel_idx][0]
    if storage_space_check:
        assert MIN_NODE_STORAGE[:-1] in unpacked_cols[storage_idx][0]
    assert MIN_NODE_VCPU in unpacked_cols[cpu_idx][0]
    assert MIN_NODE_MEMORY[:-1] in unpacked_cols[memory_idx][0]

    for i in range(len(nodes)):
        node = nodes[i]
        name = node.metadata.name
        # first row is to show expected
        i = i + 1
        assert name in unpacked_cols[name_idx][i]
        arch = node.status.node_info.architecture
        assert arch in unpacked_cols[arch_idx][i]
        cpu = node.status.allocatable.get("cpu", 0)
        assert str(cpu) in unpacked_cols[cpu_idx][i]
        memory = node.status.allocatable.get("memory", 0)
        assert "%.2f" % (parse_quantity(memory) / DISPLAY_BYTES_PER_GIGABYTE) in unpacked_cols[memory_idx][i]
        if kernel_version_check:
            kernel_version = node.status.node_info.kernel_version
            assert kernel_version in unpacked_cols[kernel_idx][i]
        if storage_space_check:
            storage = node.status.allocatable.get("ephemeral-storage", 0)
            assert "%.2f" % (parse_quantity(storage) / DISPLAY_BYTES_PER_GIGABYTE) in unpacked_cols[storage_idx][i]

        assert f"cluster/nodes/{name}" in result["targets"]
        result_node = result["targets"][f"cluster/nodes/{name}"]["_all_"]

        # expected columns
        arch_col = 0
        kernel_col = 1
        storage_col = 2 if kernel_version_check else 1
        cpu_col = -2
        memory_col = -1

        arch_status = arch in AIO_SUPPORTED_ARCHITECTURES
        assert result_node["conditions"][arch_col] == f"info.architecture in ({','.join(AIO_SUPPORTED_ARCHITECTURES)})"
        assert result_node["evaluations"][arch_col]["status"] == bool_to_status(arch_status)
        assert result_node["evaluations"][arch_col]["value"]["info.architecture"] == arch

        cpu_status = cpu >= int(MIN_NODE_VCPU)
        assert result_node["conditions"][cpu_col] == f"allocatable.cpu>={MIN_NODE_VCPU}"
        assert result_node["evaluations"][cpu_col]["status"] == bool_to_status(cpu_status)
        assert result_node["evaluations"][cpu_col]["value"]["allocatable.cpu"] == cpu

        kernel_status = False
        if kernel_version_check:
            semver = scoped_semver_import()
            kernel_version = ".".join(node.status.node_info.kernel_version.split(".")[:3])
            kernel_status = semver.parse(kernel_version, True) >= semver.parse(ACSA_MIN_NODE_KERNEL_VERSION, True)
            assert result_node["conditions"][kernel_col] == f"info.kernel_version>={ACSA_MIN_NODE_KERNEL_VERSION}"
            assert result_node["evaluations"][kernel_col]["status"] == bool_to_status(kernel_status)
            assert (
                result_node["evaluations"][kernel_col]["value"]["info.kernel_version"]
                == node.status.node_info.kernel_version
            )

        storage_status = False
        if storage_space_check:
            storage_status = parse_quantity(storage) >= parse_quantity(MIN_NODE_STORAGE)
            assert result_node["conditions"][storage_col] == f"allocatable.ephemeral-storage>={MIN_NODE_STORAGE}"
            assert result_node["evaluations"][storage_col]["status"] == bool_to_status(storage_status)
            assert (
                result_node["evaluations"][storage_col]["value"]["allocatable.ephemeral-storage"]
                == f"{int(parse_quantity(storage) / DISPLAY_BYTES_PER_GIGABYTE)}G"
            )

        memory_status = parse_quantity(memory) >= parse_quantity(MIN_NODE_MEMORY)
        assert result_node["conditions"][memory_col] == f"allocatable.memory>={MIN_NODE_MEMORY}"
        assert result_node["evaluations"][memory_col]["status"] == bool_to_status(memory_status)
        assert (
            result_node["evaluations"][memory_col]["value"]["allocatable.memory"]
            == f"{int(parse_quantity(memory) / DISPLAY_BYTES_PER_GIGABYTE)}G"
        )

        overall_status = all(
            [
                arch_status,
                cpu_status,
                *([kernel_status] if kernel_version_check else []),
                *([storage_status] if storage_space_check else []),
                memory_status,
            ]
        )
        assert result_node["status"] == bool_to_status(overall_status)


def bool_to_status(status: bool):
    return "success" if status else "error"
