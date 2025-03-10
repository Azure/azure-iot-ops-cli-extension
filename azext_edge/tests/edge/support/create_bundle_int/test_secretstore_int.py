# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import SECRETSTORE_API_V1, SECRETSYNC_API_V1
from ....helpers import get_multi_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
SSC_PREFIXES = ["secrets-store-sync-controller-manager", "manager-metrics-service"]
SSC_WORKLOAD_TYPES = ["deployment", "pod", "replicaset", "service"]


def test_create_bundle_ssc(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.secretstore.value

    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=SSC_WORKLOAD_TYPES,
        prefixes=SSC_PREFIXES,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # AIO
    check_custom_resource_files(
        file_objs=file_map["aio"], resource_api=SECRETSYNC_API_V1, namespace=file_map["__namespaces__"]["aio"]
    )
    check_custom_resource_files(
        file_objs=file_map["aio"],
        resource_api=SECRETSTORE_API_V1,
        namespace=file_map["__namespaces__"]["aio"],
    )

    # SECRETSTORE
    expected_types = set(SSC_WORKLOAD_TYPES)
    assert set(file_map[OpsServiceType.secretstore.value].keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map[OpsServiceType.secretstore.value],
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=SSC_PREFIXES,
        bundle_path=bundle_path,
    )
