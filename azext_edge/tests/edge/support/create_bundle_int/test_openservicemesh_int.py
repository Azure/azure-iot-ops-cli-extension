# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import OPENSERVICEMESH_CONFIG_API_V1, OPENSERVICEMESH_POLICY_API_V1
from ....helpers import get_multi_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command,
)

logger = get_logger(__name__)
EXPECTED_PREFIXES = ["configmap", "deployment", "pod", "replicaset", "service"]
EXPECTED_WORKLOAD_TYPES = ["osm", "kube-root-ca", "preset-mesh-config"]


def test_create_bundle_osm(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS openservicemesh."""
    # dir for unpacked files
    ops_service = OpsServiceType.openservicemesh.value

    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=EXPECTED_WORKLOAD_TYPES,
        prefixes=EXPECTED_PREFIXES,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # arc-osm-system
    osm_file_map = file_map["osm"]

    check_custom_resource_files(file_objs=osm_file_map, resource_api=OPENSERVICEMESH_CONFIG_API_V1)
    check_custom_resource_files(file_objs=osm_file_map, resource_api=OPENSERVICEMESH_POLICY_API_V1)

    expected_types = set(EXPECTED_WORKLOAD_TYPES).union(OPENSERVICEMESH_CONFIG_API_V1.kinds)
    expected_types = expected_types.union(OPENSERVICEMESH_POLICY_API_V1.kinds)

    assert set(osm_file_map.keys()).issubset(set(expected_types))

    check_workload_resource_files(
        file_objs=osm_file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=EXPECTED_PREFIXES,
        bundle_path=bundle_path,
    )
