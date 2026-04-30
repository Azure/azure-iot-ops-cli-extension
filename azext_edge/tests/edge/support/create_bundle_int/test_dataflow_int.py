# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support_bundle import COMPAT_DATAFLOW_APIS
from ....helpers import get_multi_kubectl_workload_items
from .helpers import (
    check_cluster_label_coverage,
    check_custom_resource_files,
    check_workload_resource_files,
    get_all_kinds_from_manager,
    get_file_map,
    run_bundle_command,
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
DATAFLOW_PREFIXES = ["aio-dataflow", "aio-wasm-graph-controller"]
DATAFLOW_WORKLOAD_TYPES = ["deployment", "pod", "replicaset", "service", "vwc", "mwc"]
DATAFLOW_LABEL = ("app.kubernetes.io/name", "microsoft-iotoperations-dataflows")


def test_create_bundle_dataflow(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS dataflow."""
    ops_service = OpsServiceType.dataflow.value
    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=DATAFLOW_WORKLOAD_TYPES,
        prefixes=DATAFLOW_PREFIXES,
        expected_label=DATAFLOW_LABEL,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["aio"]

    check_custom_resource_files(file_objs=file_map, resource_apis=COMPAT_DATAFLOW_APIS.resource_apis)

    expected_types = (
        set(DATAFLOW_WORKLOAD_TYPES).union(get_all_kinds_from_manager(COMPAT_DATAFLOW_APIS))
    )
    assert set(file_map.keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=DATAFLOW_PREFIXES,
        bundle_path=bundle_path,
        expected_label=DATAFLOW_LABEL,
    )
    check_cluster_label_coverage(
        prefixes=DATAFLOW_PREFIXES,
        expected_label=DATAFLOW_LABEL,
        workload_types=DATAFLOW_WORKLOAD_TYPES,
    )
