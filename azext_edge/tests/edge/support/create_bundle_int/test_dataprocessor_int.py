# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import DATA_PROCESSOR_API_V1
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_bundle_path,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)


def test_create_bundle_dataprocessor(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS dataprocessor."""
    if not DATA_PROCESSOR_API_V1.is_deployed():
        pytest.skip("Data processor is not deployed on this cluster.")
    ops_service = OpsServiceType.dataprocessor.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["aio"]

    check_custom_resource_files(
        file_objs=file_map,
        resource_api=DATA_PROCESSOR_API_V1
    )

    expected_workload_types = ["deployment", "pod", "pvc", "replicaset", "service", "statefulset"]
    expected_types = set(expected_workload_types).union(DATA_PROCESSOR_API_V1.kinds)
    assert set(file_map.keys()).issubset(expected_types)

    bundle_path = get_bundle_path(tracked_files)

    check_workload_resource_files(
        file_objs=file_map,
        expected_workload_types=expected_workload_types,
        prefixes=[
            "aio-dp", "checkpoint-store-local-aio-dp", "refdatastore-local-aio-dp", "runner-local-aio-dp"
        ],
        bundle_path=bundle_path
    )
