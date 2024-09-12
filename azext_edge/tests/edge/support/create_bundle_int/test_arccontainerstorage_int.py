# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import ARCCONTAINERSTORAGE_API_V1
from .helpers import (
    check_custom_resource_files,
    BASE_ZIP_PATH,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command,
)

logger = get_logger(__name__)


def test_create_bundle_arccontainerstorage(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arccontainerstorage."""
    # dir for unpacked files
    ops_service = OpsServiceType.arccontainerstorage.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["esa"]

    expected_workload_types = ["daemonset", "deployment", "pod", "pvc", "replicaset", "service"]
    expected_types = set(expected_workload_types).union(ARCCONTAINERSTORAGE_API_V1.kinds)
    assert set(file_map.keys()).issubset(set(expected_types))
    check_workload_resource_files(
        file_objs=file_map,
        expected_workload_types=expected_workload_types,
        prefixes=[
            "esa-otel-collector",
            "csi-wyvern-controller",
            "csi-wyvern-node",
            "config-operator",
            "edgevolume-mounthelper",
            "w-adr-schema-registry",
            "wyvern-operator",
            "adr-schema-registry-cache-claimsrv",
            "adr-schema-registry-cache-claim-user-pvc",
            "adr-schema-registry-cache-claim-system-pvc",
        ],
        bundle_path=bundle_path,
    )
