# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from ....helpers import get_multi_kubectl_workload_items
from .helpers import (
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
AGENT_RESOURCE_PREFIXES = {
    "cluster-identity-operator": "clusteridentityoperator",
    "clusterconnect-agent": "clusterconnect-agent",
    "config-agent": "config-agent",
    "extension-events-collector": "extension-events-collector",
    "extension-manager": "extension-manager",
    "kube-aad-proxy": "kube-aad-proxy",
    "cluster-metadata-operator": "cluster-metadata-operator",
    "metrics-agent": "metrics-agent",
    "resource-sync-agent": "resource-sync-agent"
}
AGENT_WORKLOAD_TYPES = ["deployment", "pod", "replicaset"]
AGENT_SERVICE_WORKLOAD_TYPES = AGENT_WORKLOAD_TYPES[:] + ["service"]


def test_create_bundle_arcagents(cluster_connection, bundle_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.akri.value
    agent_map = {}
    for agent, has_service in ARC_AGENTS:
        agent_map[agent] = get_multi_kubectl_workload_items(
            expected_workload_types=AGENT_SERVICE_WORKLOAD_TYPES if has_service else AGENT_WORKLOAD_TYPES,
            prefixes=AGENT_RESOURCE_PREFIXES[agent],
        )

    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    files = get_file_map(walk_result=walk_result, ops_service=ops_service)
    agents_file_map = files["arc"]

    for agent, has_service in ARC_AGENTS:
        file_map = agents_file_map[agent]

        assert set(file_map.keys()).issubset(
            set(AGENT_SERVICE_WORKLOAD_TYPES if has_service else AGENT_WORKLOAD_TYPES)
        )

        check_workload_resource_files(
            file_objs=file_map,
            pre_bundle_items=agent_map[agent],
            prefixes=AGENT_RESOURCE_PREFIXES[agent],
            bundle_path=bundle_path
        )
