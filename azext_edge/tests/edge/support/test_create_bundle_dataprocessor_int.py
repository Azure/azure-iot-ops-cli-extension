# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from os import path, walk
from shutil import unpack_archive
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import convert_file_names, check_non_custom_file_objs, ensure_clean_dir
from ...helpers import run

logger = get_logger(__name__)


def test_create_bundle_dataprocessor(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS dataprocessor."""
    # dir for unpacked files
    extracted_path = "unpacked"
    ensure_clean_dir(extracted_path, tracked_files)
    ops_service = OpsServiceType.dataprocessor.value

    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    result = run(command)
    assert result["bundlePath"]
    tracked_files.append(result["bundlePath"])
    unpack_archive(result["bundlePath"], extract_dir=extracted_path)
    walk_result = {
        directory: {
            "folders": folders, "files": files
        } for directory, folders, files in walk(extracted_path)
    }

    # Remove all files that will not be checked
    level_0 = walk_result.pop(extracted_path)
    namespace = level_0["folders"][0]
    walk_result.pop(path.join(extracted_path, namespace))

    # Level 2 and 3 - bottom
    assert len(walk_result) == 1
    dataprocessor_path = path.join(extracted_path, namespace, ops_service)
    assert not walk_result[dataprocessor_path]["folders"]
    file_map = convert_file_names(walk_result[dataprocessor_path]["files"])

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
