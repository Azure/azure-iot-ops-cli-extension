# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_mq(init_setup, tracked_files, mq_traces):
    """Test for ensuring file names and content. ONLY CHECKS mq."""
    mq_traces = True

    ops_service = OpsServiceType.mq.value
    command = f"az iot ops support create-bundle --mq-traces {mq_traces} --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service, mq_traces=mq_traces)
    traces = file_map.pop("traces", {})

    # TODO: add in expected for each
    # mq
    # do we always have these? What cases do they have them vs not?
    # how can names change?
    if file_map.get("instance"):
        for config in file_map["instance"]:
            assert config["version"] == "v1"

    expected_file_objs = {
        "deployment": [
            "aio-mq-diagnostics-service",
            "aio-mq-operator"
        ],
        "pod": [
            "aio-mq-diagnostics-probe",
            "aio-mq-diagnostics-service",
            "aio-mq-dmqtt-authentication",
            "aio-mq-dmqtt-backend",  # could have multiple
            "aio-mq-dmqtt-frontend",  # same
            "aio-mq-dmqtt-health-manager",
            "aio-mq-operator"
        ],
        "replicaset": [
            "aio-mq-diagnostics-service",
            "aio-mq-operator"
        ],
        "service": [
            "aio-mq-diagnostics-service",
            "aio-mq-dmqtt-authentication",
            "aio-mq-dmqtt-backend",
            "aio-mq-dmqtt-frontend",
            "aio-mq-dmqtt-health-manager"
        ],
        "statefulset": [
            "aio-mq-diagnostics-probe",
            "aio-mq-dmqtt-authentication",
            "aio-mq-dmqtt-backend",  # could have multiple
            "aio-mq-dmqtt-frontend",
            "aio-mq-dmqtt-health-manager"
        ]
    }

    check_non_custom_file_objs(file_map, expected_file_objs)

    if traces:
        pass

    # mq_traces check
