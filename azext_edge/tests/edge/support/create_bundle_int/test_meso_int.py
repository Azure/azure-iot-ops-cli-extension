# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger

from azext_edge.edge.common import OpsServiceType
from ....helpers import get_multi_kubectl_workload_items
from .helpers import BASE_ZIP_PATH, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
MESO_PREFIXES = ["aio-observability"]
MESO_WORKLOAD_TYPES = ["clusterrole", "configmap", "clusterrolebinding", "deployment", "pod", "replicaset", "service"]


def test_create_bundle_meso(cluster_connection, bundle_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS meta."""
    ops_service = OpsServiceType.meso.value

    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=MESO_WORKLOAD_TYPES,
        prefixes=MESO_PREFIXES,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    if not walk_result[BASE_ZIP_PATH]["folders"]:
        pytest.skip(f"No bundles created for {ops_service}.")

    file_map = get_file_map(walk_result, ops_service)["aio"]

    expected_types = set(MESO_WORKLOAD_TYPES).union({"crb"})
    assert set(file_map.keys()).issubset(set(expected_types))
    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=MESO_PREFIXES,
        bundle_path=bundle_path,
    )
