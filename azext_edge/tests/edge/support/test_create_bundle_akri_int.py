# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_akri(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS AKRI."""
    ops_service = OpsServiceType.akri.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # TODO: add in expected for each
    # do we always have these? What cases do they have them vs not?
    # how can names change?
    if file_map.get("configuration"):
        for config in file_map["configuration"]:
            assert config["version"] == "v0"
    if file_map.get("instance"):
        for config in file_map["instance"]:
            assert config["version"] == "v0"

    expected_file_objs = {
        "daemonset": [
            "aio-akri-agent-daemonset"
        ],
        "deployment": [
            "aio-akri-otel-collector",
            "aio-akri-webhook-configuration"
        ],
        "pod": [
            "aio-akri-agent-daemonset",
            "aio-akri-otel-collector",
            "aio-akri-webhook-configuration"
        ],
        "replicaset": [
            "aio-akri-otel-collector",
            "aio-akri-webhook-configuration"
        ],
        "service": [
            "aio-akri-agent-metrics-service",
            "aio-akri-controller-metrics-service",
            "aio-akri-webhook-configuration"
        ]
    }

    check_non_custom_file_objs(file_map, expected_file_objs)
