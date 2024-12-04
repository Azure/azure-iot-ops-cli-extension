# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import ARCCONTAINERSTORAGE_API_V1
from azext_edge.tests.helpers import get_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command,
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


def test_create_bundle_arccontainerstorage(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arccontainerstorage."""
    # dir for unpacked files
    ops_service = OpsServiceType.arccontainerstorage.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["acs"]

    check_custom_resource_files(file_objs=file_map, resource_api=ARCCONTAINERSTORAGE_API_V1)

    expected_workload_types = ["daemonset", "deployment", "pod", "pvc", "replicaset", "service"]
    expected_types = set(expected_workload_types).union(ARCCONTAINERSTORAGE_API_V1.kinds)
    assert set(file_map.keys()).issubset(set(expected_types))

    workload_resource_prefixes = [
        "acsa-otel",
        "csi-wyvern-controller",
        "csi-wyvern-node",
        "config-operator",
        "edgevolume-mounthelper",
        "wyvern-operator",
    ]

    schemas_pods = get_kubectl_workload_items(
        prefixes="adr-schema-registry",
        service_type="pod",
        label_match=("app.kubernetes.io/name", "microsoft-iotoperations-schemas"),
    )

    # add following workload prefixes if schema registry is deployed
    if len(schemas_pods.items()) > 0:
        workload_resource_prefixes.extend(
            [
                "w-adr-schema-registry",
                "adr-schema-registry-cache-claimsrv",
                "adr-schema-registry-cache-claim-user-pvc",
                "adr-schema-registry-cache-claim-system-pvc",
            ]
        )

    check_workload_resource_files(
        file_objs=file_map,
        expected_workload_types=expected_workload_types,
        prefixes=workload_resource_prefixes,
        bundle_path=bundle_path,
    )
