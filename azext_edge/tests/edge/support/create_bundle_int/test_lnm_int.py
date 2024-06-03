# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import LNM_API_V1B1
from .helpers import check_custom_resource_files, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_lnm(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS lnm."""
    ops_service = OpsServiceType.lnm.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)
    lnm_file_map = file_map.get("lnm", None)

    # AIO
    check_custom_resource_files(
        file_objs=file_map["aio"],
        resource_api=LNM_API_V1B1,
        namespace=file_map["__namespaces__"]["aio"],
        excluded_kinds=["scale", "status"],
    )

    expected_workload_types = ["deployment", "pod", "replicaset"]

    if lnm_file_map:
        expected_workload_types.append("service")
    expected_types = set(expected_workload_types).union(LNM_API_V1B1.kinds)
    assert set(file_map["aio"].keys()).issubset(expected_types)
    check_workload_resource_files(file_map["aio"], expected_workload_types, ["aio-lnm"])

    # LNM
    if lnm_file_map:
        expected_workload_types = ["daemonset", "pod"]
        assert set(lnm_file_map.keys()).issubset(expected_workload_types)
        check_workload_resource_files(file_map["lnm"], expected_workload_types, ["svclb-aio-lnm"])

