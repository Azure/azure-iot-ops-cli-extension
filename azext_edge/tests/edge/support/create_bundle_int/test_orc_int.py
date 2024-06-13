# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import ORC_API_V1
from .helpers import check_custom_resource_files, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_orc(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS orc."""
    ops_service = OpsServiceType.orc.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["aio"]

    check_custom_resource_files(
        file_objs=file_map,
        resource_api=ORC_API_V1
    )

    expected_workload_types = ["deployment", "pod", "replicaset", "service"]
    expected_types = set(expected_workload_types).union(ORC_API_V1.kinds)
    assert set(file_map.keys()).issubset(expected_types)

    # find bundle path from tracked_files that with .zip extension
    bundle_path = next((file for file in tracked_files if file.endswith(".zip")), None)
    check_workload_resource_files(
        file_objs=file_map,
        expected_workload_types=expected_workload_types,
        prefixes=["aio-cert", "aio-orc"],
        bundle_path=bundle_path
    )
