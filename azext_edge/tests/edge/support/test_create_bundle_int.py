# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from os import mkdir, path, walk
from shutil import unpack_archive, rmtree
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import convert_file_names, check_non_custom_file_objs, ensure_clean_dir
from ...helpers import run

logger = get_logger(__name__)


@pytest.mark.parametrize("bundle_dir", ["support_bundles"])
@pytest.mark.parametrize("ops_service", OpsServiceType.list())
@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle(init_setup, bundle_dir, mq_traces, ops_service, tracked_files):
    """Test to focus on ops_service param."""
    # dir for unpacked files
    extracted_path = "unpacked"
    auto_extracted_path = "auto_" + extracted_path
    try:
        mkdir(extracted_path)
        tracked_files.append(extracted_path)
        mkdir(auto_extracted_path)
        tracked_files.append(auto_extracted_path)
    except FileExistsError:
        rmtree(extracted_path)
        mkdir(extracted_path)
        rmtree(auto_extracted_path)
        mkdir(auto_extracted_path)

    command = f"az iot ops support create-bundle --mq-traces {mq_traces} " + "--ops-service {0}"
    if bundle_dir:
        command += f" --bundle-dir {bundle_dir}"
        try:
            mkdir(bundle_dir)
            tracked_files.append(bundle_dir)
        except FileExistsError:
            pass
    result = run(command.format(ops_service))
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
    assert "storage_classes.yaml" in level_0["files"]
    if not level_0["folders"]:
        logger.warning(f"No bundles created for {ops_service}.")
        return
    namespace = level_0["folders"][0]

    # Level 1
    level_1 = walk_result.pop(path.join(extracted_path, namespace))
    expected_services = [ops_service]
    if ops_service == OpsServiceType.auto.value:
        # these should always be generated
        expected_services = OpsServiceType.list()
        expected_services.remove(OpsServiceType.auto.value)
        expected_services.append("otel")
        # device registry folder will not be created if there are no device registry resources
        if not walk_result.get(path.join(extracted_path, namespace, "deviceregistry")):
            expected_services.remove(OpsServiceType.deviceregistry.value)
        expected_services.sort()
    assert sorted(level_1["folders"]) == expected_services
    assert not level_1["files"]

    # Check and take out mq traces:
    if mq_traces and ops_service in [OpsServiceType.auto.value, OpsServiceType.mq.value]:
        mq_level = walk_result.pop(path.join(extracted_path, namespace, "mq", "traces"))
        assert not mq_level["folders"]
        for name in mq_level["files"]:
            assert name.split(".")[-1] in ["json", "pb"]
        # make sure level 2 doesnt get messed up
        assert walk_result[path.join(extracted_path, namespace, "mq")]["folders"] == ["traces"]
        walk_result[path.join(extracted_path, namespace, "mq")]["folders"] = []

    # Level 2 and 3 - bottom
    assert len(walk_result) == len(expected_services)
    for directory in walk_result:
        assert not walk_result[directory]["folders"]
        convert_file_names(walk_result[directory]["files"])

    # check service is within auto
    if ops_service != OpsServiceType.auto.value:
        auto_result = run(command.format(OpsServiceType.auto.value))
        assert auto_result["bundlePath"]
        tracked_files.append(auto_result["bundlePath"])
        unpack_archive(auto_result["bundlePath"], extract_dir=auto_extracted_path)
        auto_walk_result = {
            adir: {
                "folders": folders, "files": files
            } for adir, folders, files in walk(auto_extracted_path)
        }
        assert auto_walk_result[directory] == walk_result[directory]


@pytest.mark.parametrize("bundle_dir", ["support_bundles"])
@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_auto_otel(init_setup, bundle_dir, mq_traces, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS otel from auto."""
    # dir for unpacked files
    extracted_path = "unpacked"
    ensure_clean_dir(extracted_path, tracked_files)
    ops_service = OpsServiceType.auto.value

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
    otel_path = path.join(extracted_path, namespace, "otel")
    assert not walk_result[otel_path]["folders"]
    file_map = convert_file_names(walk_result[otel_path]["files"])

    # TODO: add in expected for each
    # otel
    # do we always have these? What cases do they have them vs not?
    # how can names change?

    expected_file_objs = {
        "deployment": [
            "aio-otel-collector",
        ],
        "pod": [
            "aio-otel-collector"
        ],
        "replicaset": [
            "aio-otel-collector"
        ],
        "service": [
            "aio-otel-collector"
        ]
    }
    check_non_custom_file_objs(file_map, expected_file_objs)


def test_create_bundle_mq_traces(init_setup, bundle_dir, tracked_files):
    """Tests for mq trace content."""
    pass
