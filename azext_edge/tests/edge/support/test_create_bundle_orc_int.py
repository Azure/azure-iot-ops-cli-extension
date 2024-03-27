# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_orc(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS orc."""
    ops_service = OpsServiceType.orc.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # TODO: add in expected for each
    # orc
    # do we always have these? What cases do they have them vs not?
    # how can names change?
    if file_map.get("target"):
        for config in file_map["target"]:
            assert config["version"] == "v1"

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

    check_non_custom_file_objs(file_map, expected_file_objs)
