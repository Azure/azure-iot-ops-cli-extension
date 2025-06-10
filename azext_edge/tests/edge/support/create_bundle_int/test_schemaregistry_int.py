# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from ....helpers import get_multi_kubectl_workload_items
from .helpers import check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
SCHEMA_PREFIXES = ["adr-schema-registry"]
SCHEMA_WORKLOAD_TYPES = ["configmap", "pod", "service", "statefulset", "pvc"]
SCHEMA_LABEL = ("app.kubernetes.io/name", "microsoft-iotoperations-schemas")


def test_create_bundle_schemas(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.schemaregistry.value
    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=SCHEMA_WORKLOAD_TYPES,
        prefixes=SCHEMA_PREFIXES,
        expected_label=SCHEMA_LABEL
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, "schemaregistry")["aio"]

    assert set(file_map.keys()).issubset(set(SCHEMA_WORKLOAD_TYPES))

    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=SCHEMA_PREFIXES,
        bundle_path=bundle_path,
        expected_label=SCHEMA_LABEL,
    )
