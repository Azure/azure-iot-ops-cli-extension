# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_workload_resource_files, get_file_map, get_workload_resources, run_bundle_command

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


def test_create_bundle_schemas(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.schemaregistry.value
    expected_workload_types = ["configmap", "pod", "service", "statefulset", "pvc"]
    expected_label = ("app.kubernetes.io/name", "microsoft-iotoperations-schemas")
    prefixes = "adr-schema-registry"
    pre_bundle_workload_items = get_workload_resources(
        expected_workload_types=expected_workload_types,
        prefixes=prefixes,
        expected_label=expected_label
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, "schemaregistry")["aio"]

    assert set(file_map.keys()).issubset(set(expected_workload_types))

    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=prefixes,
        bundle_path=bundle_path,
        expected_label=expected_label,
    )
