# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import LNM_API_V1B1, LnmResourceKinds
from .helpers import check_custom_file_objs, check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_lnm(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS lnm."""
    ops_service = OpsServiceType.lnm.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    check_custom_file_objs(
        file_objs=file_map,
        resource_api=LNM_API_V1B1,
        resource_kinds=LnmResourceKinds.list(),
    )

    expected_file_objs = ["deployment", "replicaset"]
    expected_types = expected_file_objs + LnmResourceKinds.list() + ["pod"]
    assert set(file_map.keys()).issubset(set(expected_types))

    check_non_custom_file_objs(file_map, expected_file_objs, "aio-lnm")
