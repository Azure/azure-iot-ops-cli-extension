# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import SECRETSTORE_API_V1, SECRETSYNC_API_V1
from .helpers import check_custom_resource_files, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_ssc(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.secretsynccontroller.value

    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, "secretsynccontroller")

    # AIO
    check_custom_resource_files(
        file_objs=file_map["aio"], resource_api=SECRETSYNC_API_V1, namespace=file_map["__namespaces__"]["aio"]
    )

    # SECRETSTORE
    check_custom_resource_files(
        file_objs=file_map["secretstore"],
        resource_api=SECRETSTORE_API_V1,
        namespace=file_map["__namespaces__"]["secretstore"],
    )
    expected_workload_types = ["deployment", "pod", "replicaset", "service"]
    expected_types = set(expected_workload_types).union(SECRETSTORE_API_V1.kinds)
    assert set(file_map["secretstore"].keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map["secretstore"],
        expected_workload_types=expected_workload_types,
        prefixes=["secrets-store-sync-controller-manager", "manager-metrics-service"],
        bundle_path=bundle_path,
    )
