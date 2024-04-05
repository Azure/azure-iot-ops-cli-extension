# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import OPCUA_API_V1, OpcuaResourceKinds
from .helpers import check_custom_file_objs, check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_opcua(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS opcua."""
    ops_service = OpsServiceType.opcua.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    check_custom_file_objs(
        file_objs=file_map,
        resource_api=OPCUA_API_V1,
        resource_kinds=OpcuaResourceKinds.list(),
    )

    expected_file_objs = {
        "daemonset": [
            "aio-opc-asset-discovery"
        ],
        "deployment": [
            "aio-opc-admission-controller",
            "aio-opc-supervisor"
        ],
        "pod": [
            "aio-opc-admission-controller",
            "aio-opc-asset-discovery",
            "aio-opc-supervisor"
        ],
        "replicaset": [
            "aio-opc-admission-controller",
            "aio-opc-supervisor"
        ],
        "service": [
            "aio-opc-admission-controller"
        ]
    }

    optional_file_objs = {
        "deployment": [
            "opcplc",
            "aio-opc-opc"
        ],
        "pod": [
            "opcplc",
            "aio-opc-opc"
        ],
        "replicaset": [
            "opcplc",
            "aio-opc-opc"
        ],
        "service": [
            "opcplc"
        ]
    }
    expected_types = list(expected_file_objs.keys()) + OpcuaResourceKinds.list()
    assert set(file_map.keys()).issubset(set(expected_types))

    check_non_custom_file_objs(file_map, expected_file_objs, optional_file_objs)
