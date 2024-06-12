# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import MQ_ACTIVE_API
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from .helpers import (
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)


@pytest.mark.parametrize("ops_service", [
    OpsServiceType.mq.value,
])
@pytest.mark.parametrize("include_arc_agents", [True])
def test_create_bundle_arcagents(init_setup, tracked_files, include_arc_agents, ops_service):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""

    command = f"az iot ops support create-bundle --ops-service {ops_service.value} --arc {include_arc_agents}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    agents_file_map = get_file_map(walk_result, ops_service)["arc"]
    
    for agent, has_service in ARC_AGENTS:
        file_map = agents_file_map[agent]
        expected_workload_types = ["deployment", "pod", "replicaset"]

        if has_service:
            expected_workload_types.append("service")

        assert set(file_map.keys()).issubset(set(expected_workload_types))
        check_workload_resource_files(file_map, expected_workload_types, agent)
