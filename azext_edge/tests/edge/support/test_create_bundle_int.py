# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from os import mkdir, walk
from shutil import unpack_archive, rmtree
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from ...helpers import run

logger = get_logger(__name__)


@pytest.mark.parametrize("init_setup", [{"--simulate-plc": True}], ids=["simulate plc"], indirect=True)
@pytest.mark.parametrize("bundle_dir", ["support_bundles"])
@pytest.mark.parametrize("ops_service", OpsServiceType.list())
@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle(init_setup, bundle_dir, mq_traces, ops_service, tracked_files):
    # dir for unpacked files
    extracted_path = "unpacked"
    try:
        mkdir(extracted_path)
        tracked_files.append(extracted_path)
    except FileExistsError:
        rmtree(extracted_path)
        mkdir(extracted_path)

    command = f"az iot ops support create-bundle --mq-traces {mq_traces} --ops-service {ops_service}"
    if bundle_dir:
        command += f" --bundle-dir {bundle_dir}"
        try:
            mkdir(bundle_dir)
            tracked_files.append(bundle_dir)
        except FileExistsError:
            pass
    result = run(command)
    assert result["bundlePath"]
    tracked_files.append(result["bundlePath"])
    unpack_archive(result["bundlePath"], extract_dir=extracted_path)
    walk_result = {
        directory: {
            "folders": folders, "files": files
        } for directory, folders, files in walk(extracted_path)
    }
    # Level 0 - top
    level_0 = walk_result.pop(extracted_path)
    assert "events.yaml" in level_0["files"]
    assert "nodes.yaml" in level_0["files"]
    if not level_0["folders"]:
        logger.warning(f"No bundles created for {ops_service}.")
        return
    namespace = level_0["folders"][0]

    # Level 1
    level_1 = walk_result.pop(f"{extracted_path}\\{namespace}")
    expected_services = [ops_service]
    if ops_service == OpsServiceType.auto.value:
        expected_services = ["akri", "dataprocessor", "lnm", "mq", "opcua", "orc"]
    assert level_1["folders"] == expected_services
    assert not level_1["files"]

    # Level 2 - bottom
    assert len(walk_result) == len(expected_services)
    for directory in walk_result:
        assert not walk_result[directory]["folders"]
        files = walk_result[directory]["files"]
        for name in files:
            assert name.split(".")[-1] in ["log", "txt", "yaml"]
