# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import CLUSTER_CONFIG_API_V1
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    get_workload_resources,
    run_bundle_command
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


def test_create_bundle_billing(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS billing."""
    ops_service = OpsServiceType.billing.value
    expected_aio_workload_types = ["cronjob", "job", "pod"]
    aio_prefixes = ["aio-usage"]
    aio_workload_items = get_workload_resources(
        expected_workload_types=expected_aio_workload_types,
        prefixes=aio_prefixes,
    )

    expected_usage_workload_types = ["deployment", "pod", "replicaset", "service"]
    usage_prefix = ["billing-operator"]
    usage_workload_items = get_workload_resources(
        expected_workload_types=expected_usage_workload_types,
        prefixes=usage_prefix,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # AIO
    check_custom_resource_files(
        file_objs=file_map["aio"],
        resource_api=CLUSTER_CONFIG_API_V1,
        namespace=file_map["__namespaces__"]["aio"]
    )
    expected_types = set(expected_aio_workload_types).union(CLUSTER_CONFIG_API_V1.kinds)
    assert set(file_map["aio"].keys()).issubset(set(expected_types))
    check_workload_resource_files(
        file_objs=file_map["aio"],
        pre_bundle_items=aio_workload_items,
        prefixes=aio_prefixes,
        bundle_path=bundle_path
    )

    # USAGE
    check_custom_resource_files(
        file_objs=file_map["usage"],
        resource_api=CLUSTER_CONFIG_API_V1,
        namespace=file_map["__namespaces__"]["usage"]
    )
    expected_types = set(expected_usage_workload_types).union(CLUSTER_CONFIG_API_V1.kinds)
    assert set(file_map["usage"].keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map["usage"],
        pre_bundle_items=usage_workload_items,
        prefixes=usage_prefix,
        bundle_path=bundle_path
    )
