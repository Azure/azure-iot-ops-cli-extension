# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import DATA_PROCESSOR_API_V1, DataProcessorResourceKinds
from .helpers import check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_dataprocessor(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS dataprocessor."""
    ops_service = OpsServiceType.dataprocessor.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # do we always have these? What cases do they have them vs not?
    # how can names change?
    for config in file_map.get(DataProcessorResourceKinds.DATASET.value, []):
        assert config["version"] == DATA_PROCESSOR_API_V1.version
    # should be one right?
    for config in file_map[DataProcessorResourceKinds.INSTANCE.value]:
        assert config["version"] == DATA_PROCESSOR_API_V1.version
    assert len(file_map[DataProcessorResourceKinds.INSTANCE.value])
    for config in file_map.get(DataProcessorResourceKinds.PIPELINE.value, []):
        assert config["version"] == DATA_PROCESSOR_API_V1.version

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
    expected_types = list(expected_file_objs.keys()) + DataProcessorResourceKinds.list()
    assert set(file_map.keys()).issubset(set(expected_types))

    check_non_custom_file_objs(file_map, expected_file_objs)
