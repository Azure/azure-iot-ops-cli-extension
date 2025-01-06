# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import OPCUA_API_V1
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


def test_create_bundle_opcua(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS opcua."""
    ops_service = OpsServiceType.opcua.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["aio"]

    check_custom_resource_files(
        file_objs=file_map,
        resource_api=OPCUA_API_V1
    )

    expected_workload_types = ["daemonset", "deployment", "pod", "replicaset", "service"]
    optional_workload_types = ["podmetric"]
    expected_types = set(expected_workload_types + optional_workload_types).union(OPCUA_API_V1.kinds)
    assert set(file_map.keys()).issubset(expected_types)

    check_workload_resource_files(
        file_objs=file_map,
        expected_workload_types=expected_workload_types,
        prefixes=["aio-opc", "opcplc"],
        bundle_path=bundle_path,
        optional_workload_types=optional_workload_types
    )
