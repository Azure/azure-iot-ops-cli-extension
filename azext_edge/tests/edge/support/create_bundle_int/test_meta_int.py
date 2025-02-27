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


def test_create_bundle_meta(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS meta."""
    prefixes = ["aio-operator", "aio-pre-install-job", "aio-post-install-job"]

    expected_workload_types = ["deployment", "pod", "replicaset", "service"]
    optional_workload_types = ["job"]
    pre_bundle_workload_items = get_workload_resources(
        expected_workload_types=expected_workload_types,
        prefixes=prefixes,
    )
    pre_bundle_optional_workload_items = get_workload_resources(
        expected_workload_types=optional_workload_types,
        prefixes=prefixes,
    )
    command = "az iot ops support create-bundle"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, "meta")["aio"]

    check_custom_resource_files(file_objs=file_map, resource_api=META_API_V1)

    optional_workload_types = ["job"]
    expected_types = set(expected_workload_types + optional_workload_types).union(META_API_V1.kinds)
    assert set(file_map.keys()).issubset(set(expected_types))
    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=prefixes,
        bundle_path=bundle_path,
        pre_bundle_optional_items=pre_bundle_optional_workload_items
    )
