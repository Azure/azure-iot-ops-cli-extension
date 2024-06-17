# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from .helpers import (
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)

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


@pytest.mark.parametrize("include_arc_agents", [False, True])
def test_create_bundle_arcagents(init_setup, tracked_files, include_arc_agents):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.deviceregistry.value

    command = f"az iot ops support create-bundle --ops-service {ops_service} --arc {include_arc_agents}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    files = get_file_map(walk_result=walk_result, ops_service=ops_service, include_arc_agents=include_arc_agents)

    if not include_arc_agents:
        # No arc agents should be included
        assert not hasattr(files, "arc")
        return

    agents_file_map = files["arc"]

    for agent, has_service in ARC_AGENTS:
        file_map = agents_file_map[agent]
        expected_workload_types = ["deployment", "pod", "replicaset"]

        if has_service:
            expected_workload_types.append("service")

        assert set(file_map.keys()).issubset(set(expected_workload_types))

        check_workload_resource_files(
            file_objs=file_map,
            expected_workload_types=expected_workload_types,
            prefixes=AGENT_RESOURCE_PREFIXES[agent],
            bundle_path=bundle_path
        )
