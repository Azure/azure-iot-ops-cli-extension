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


def test_create_bundle_akri(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS AKRI."""
    # dir for unpacked files
    extracted_path = "unpacked"
    ensure_clean_dir(extracted_path, tracked_files)
    ops_service = OpsServiceType.akri.value

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
    akri_path = path.join(extracted_path, namespace, ops_service)
    assert not walk_result[akri_path]["folders"]
    file_map = convert_file_names(walk_result[akri_path]["files"])

    # TODO: add in expected for each
    # akri
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
