# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from kubernetes.client.models import V1Node, V1NodeList, V1NodeStatus, V1NodeSystemInfo, V1ObjectMeta
from ...generators import generate_random_string


@pytest.fixture
def mocked_check_manager(mocker):
    return mocker.patch("azext_edge.edge.providers.check.check_manager.CheckManager", autospec=True)


@pytest.fixture
def mocked_node_client(mocked_client, mocker, request):
    params = getattr(request, "param", [])

    nodes = []
    for node_params in params:
        arch = node_params.pop("architecture", generate_random_string(size=5))
        node = V1Node(
            metadata=V1ObjectMeta(name=generate_random_string()),
            status=V1NodeStatus(
                capacity=node_params,
                node_info=V1NodeSystemInfo(architecture=arch)
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
            "cpu": 4,
            "memory": "20G",
            "ephemeral-storage": "30G"
        }
    ],
], ids=["none", "min reqs", "storage", "memory", "cpu", "architecture", "multi-node"], indirect=True)
@pytest.mark.parametrize("as_list", [True, False])
def test_check_nodes(mocked_node_client, mocked_check_manager, as_list):
    from azext_edge.edge.providers.check.base_nodes import check_nodes
    result = check_nodes(as_list)
    import pdb; pdb.set_trace()

    assert result
    mocked_check_manager.add_target.call_args_list[0]

