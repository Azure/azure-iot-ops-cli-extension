# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from ....helpers import get_multi_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
CONNECTOR_PREFIXES = ["aio-opc", "opcplc"]
CONNECTOR_WORKLOAD_TYPES = ["daemonset", "deployment", "pod", "replicaset", "service", "configmap"]
# TODO: not tested yet - internal argument
CONNECTOR_OPTIONAL_WORKLOAD_TYPES = ["podmetric"]  # note: not an actual type


def test_create_bundle_connectors(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS connectors."""
    ops_service = OpsServiceType.connectors.value
    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=CONNECTOR_WORKLOAD_TYPES,
        prefixes=CONNECTOR_PREFIXES,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["aio"]

    expected_types = set(CONNECTOR_WORKLOAD_TYPES + CONNECTOR_OPTIONAL_WORKLOAD_TYPES)
    assert set(file_map.keys()).issubset(expected_types)

    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=CONNECTOR_PREFIXES,
        bundle_path=bundle_path,
    )
