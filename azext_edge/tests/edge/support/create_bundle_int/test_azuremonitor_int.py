# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import AZUREMONITOR_API_V1
from ....helpers import get_multi_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
AZUREMONITOR_PREFIXES = ["diagnostics-operator", "diagnostics-v1"]
AZUREMONITOR_WORKLOAD_TYPES = ["deployment", "pod", "replicaset", "service", "statefulset", "configmap"]


def test_create_bundle_azuremonitor(cluster_connection, bundle_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.azuremonitor.value

    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=AZUREMONITOR_WORKLOAD_TYPES,
        prefixes=AZUREMONITOR_PREFIXES,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    check_custom_resource_files(
        file_objs=file_map[OpsServiceType.azuremonitor.value], resource_api=AZUREMONITOR_API_V1
    )

    # arc namespace
    expected_types = set(AZUREMONITOR_WORKLOAD_TYPES).union(AZUREMONITOR_API_V1.kinds)
    assert set(file_map[OpsServiceType.azuremonitor.value].keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map[OpsServiceType.azuremonitor.value],
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=AZUREMONITOR_PREFIXES,
        bundle_path=bundle_path,
    )
