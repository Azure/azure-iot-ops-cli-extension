# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import ORC_API_V1, OrcResourceKinds
from .helpers import check_custom_file_objs, check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_orc(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS orc."""
    ops_service = OpsServiceType.orc.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    check_custom_file_objs(
        file_objs=file_map,
        resource_api=ORC_API_V1,
        resource_kinds=OrcResourceKinds.list(),
    )

    expected_file_objs = {
        "deployment": [
            "aio-cert-manager-cainjector",
            "aio-cert-manager-webhook",
            "aio-cert-manager",
            "aio-orc-api",
            "aio-orc-controller-manager"
        ],
        "pod": [
            "aio-cert-manager",
            "aio-cert-manager-cainjector",
            "aio-cert-manager-webhook",
            "aio-orc-api",
            "aio-orc-controller-manager"
        ],
        "replicaset": [
            "aio-cert-manager",
            "aio-cert-manager-cainjector",
            "aio-cert-manager-webhook",
            "aio-orc-api",
            "aio-orc-controller-manager"
        ],
        "service": [
            "aio-cert-manager-webhook",
            "aio-cert-manager",
            "aio-orc-service",
            "aio-orc-webhook-service"
        ]
    }
    expected_types = list(expected_file_objs.keys()) + OrcResourceKinds.list()
    assert set(file_map.keys()).issubset(set(expected_types))

    check_non_custom_file_objs(file_map, expected_file_objs)
