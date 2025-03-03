# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.providers.edge_api import META_API_V1
from .helpers import check_custom_resource_files, check_workload_resource_files, get_file_map, get_workload_resources, run_bundle_command

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
META_PREFIXES = ["aio-operator", "aio-pre-install-job", "aio-post-install-job"]
META_WORKLOAD_TYPES = ["deployment", "pod", "replicaset", "service"]
META_OPTIONAL_WORKLOAD_TYPES = ["job"]


def test_create_bundle_meta(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS meta."""
    pre_bundle_workload_items = get_workload_resources(
        expected_workload_types=META_WORKLOAD_TYPES,
        prefixes=META_PREFIXES,
    )
    pre_bundle_optional_workload_items = get_workload_resources(
        expected_workload_types=META_OPTIONAL_WORKLOAD_TYPES,
        prefixes=META_PREFIXES,
    )
    command = "az iot ops support create-bundle"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, "meta")["aio"]

    check_custom_resource_files(file_objs=file_map, resource_api=META_API_V1)

    expected_types = set(META_WORKLOAD_TYPES + META_OPTIONAL_WORKLOAD_TYPES).union(META_API_V1.kinds)
    assert set(file_map.keys()).issubset(set(expected_types))
    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=META_PREFIXES,
        bundle_path=bundle_path,
        pre_bundle_optional_items=pre_bundle_optional_workload_items
    )
