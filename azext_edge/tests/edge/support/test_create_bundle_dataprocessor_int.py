# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_dataprocessor(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS dataprocessor."""
    ops_service = OpsServiceType.dataprocessor.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    if not walk_result:
        logger.warning(f"No bundles created for {ops_service}.")
        return
    file_map = get_file_map(walk_result, ops_service)

    # TODO: add in expected for each
    # dataprocessor
    # do we always have these? What cases do they have them vs not?
    # how can names change?
    if file_map.get("instance"):
        for config in file_map["instance"]:
            assert config["version"] == "v1"

    expected_file_objs = {
        "deployment": [
            "aio-dp-operator"
        ],
        "pod": [
            "aio-dp-msg-store",
            "aio-dp-operator",
            "aio-dp-reader-worker",
            "aio-dp-refdata-store",
            "aio-dp-runner-worker"
        ],
        "pvc": [
            "aio-dp-msg-store-js-aio-dp-msg-store",
            "checkpoint-store-local-aio-dp-runner-worker",
            "refdatastore-local-aio-dp-refdata-store",
            "runner-local-aio-dp-runner-worker"
        ],
        "replicaset": [
            "aio-dp-operator"
        ],
        "service": [
            "aio-dp-msg-store-headless",
            "aio-dp-msg-store",
            "aio-dp-operator",
            "aio-dp-reader-worker",
            "aio-dp-refdata-store",
            "aio-dp-runner-worker"
        ],
        "statefulset": [
            "aio-dp-msg-store",
            "aio-dp-reader-worker",
            "aio-dp-refdata-store",
            "aio-dp-runner-worker"
        ]
    }

    check_non_custom_file_objs(file_map, expected_file_objs)
