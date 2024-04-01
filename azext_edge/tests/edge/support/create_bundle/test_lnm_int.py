# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_lnm(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS lnm."""
    ops_service = OpsServiceType.lnm.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # do we always have these? What cases do they have them vs not?
    # how can names change?
    for config in file_map.get("lnm", []):
        assert config["version"] == "v1beta1"

    expected_file_objs = {
        "deployment": [
            "aio-lnm-operator"
        ],
        "pod": [
            "aio-lnm-operator"
        ],
        "replicaset": [
            "aio-lnm-operator"
        ]
    }

    check_non_custom_file_objs(file_map, expected_file_objs)
