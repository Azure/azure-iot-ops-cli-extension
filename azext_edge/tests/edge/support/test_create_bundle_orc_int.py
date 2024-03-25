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


def test_create_bundle_orc(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS orc."""
    # dir for unpacked files
    extracted_path = "unpacked"
    ensure_clean_dir(extracted_path, tracked_files)
    ops_service = OpsServiceType.orc.value

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
    orc_path = path.join(extracted_path, namespace, ops_service)
    assert not walk_result[orc_path]["folders"]
    file_map = convert_file_names(walk_result[orc_path]["files"])

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
