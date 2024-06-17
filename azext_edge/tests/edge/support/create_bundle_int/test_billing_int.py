# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import CLUSTER_CONFIG_API_V1
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)


def test_create_bundle_billing(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS billing."""
    ops_service = OpsServiceType.billing.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # AIO
    check_custom_resource_files(
        file_objs=file_map["aio"],
        resource_api=CLUSTER_CONFIG_API_V1,
        namespace=file_map["__namespaces__"]["aio"]
    )
    expected_workload_types = ["cronjob", "job", "pod"]
    expected_types = set(expected_workload_types).union(CLUSTER_CONFIG_API_V1.kinds)
    assert set(file_map["aio"].keys()).issubset(set(expected_types))
    check_workload_resource_files(
        file_objs=file_map["aio"],
        expected_workload_types=expected_workload_types,
        prefixes=["aio-usage"],
        bundle_path=bundle_path
    )

    # USAGE
    check_custom_resource_files(
        file_objs=file_map["usage"],
        resource_api=CLUSTER_CONFIG_API_V1,
        namespace=file_map["__namespaces__"]["usage"]
    )
    expected_workload_types = ["deployment", "pod", "replicaset", "service"]
    expected_types = set(expected_workload_types).union(CLUSTER_CONFIG_API_V1.kinds)
    assert set(file_map["usage"].keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map["usage"],
        expected_workload_types=expected_workload_types,
        prefixes=["billing-operator"],
        bundle_path=bundle_path
    )
