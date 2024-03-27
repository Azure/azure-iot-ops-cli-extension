# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from os import mkdir, path
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import (
    check_non_custom_file_objs,
    convert_file_names,
    get_file_map,
    run_bundle_command,
    AUTO_EXTRACTED_PATH,
    EXTRACTED_PATH
)

logger = get_logger(__name__)


@pytest.mark.parametrize("bundle_dir", ["support_bundles"])
@pytest.mark.parametrize("ops_service", OpsServiceType.list())
@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle(init_setup, bundle_dir, mq_traces, ops_service, tracked_files):
    """Test to focus on ops_service param."""

    command = f"az iot ops support create-bundle --mq-traces {mq_traces} " + "--ops-service {0}"
    if bundle_dir:
        command += f" --bundle-dir {bundle_dir}"
        try:
            mkdir(bundle_dir)
            tracked_files.append(bundle_dir)
        except FileExistsError:
            pass
    walk_result = run_bundle_command(command=command.format(ops_service), tracked_files=tracked_files)

    # Level 0 - top
    level_0 = walk_result.pop(EXTRACTED_PATH)
    for file in ["events.yaml", "nodes.yaml", "storage_classes.yaml"]:
        assert file in level_0["files"]
    if not level_0["folders"]:
        logger.warning(f"No bundles created for {ops_service}.")
        return
    namespace = level_0["folders"][0]

    # Level 1
    level_1 = walk_result.pop(path.join(EXTRACTED_PATH, namespace))
    expected_services = [ops_service]
    if ops_service == OpsServiceType.auto.value:
        # these should always be generated
        expected_services = OpsServiceType.list()
        expected_services.remove(OpsServiceType.auto.value)
        expected_services.append("otel")
        # device registry folder will not be created if there are no device registry resources
        if not walk_result.get(path.join(EXTRACTED_PATH, namespace, OpsServiceType.deviceregistry.value)):
            expected_services.remove(OpsServiceType.deviceregistry.value)
        expected_services.sort()
    assert sorted(level_1["folders"]) == expected_services
    assert not level_1["files"]

    # Check and take out mq traces:
    if mq_traces and ops_service in [OpsServiceType.auto.value, OpsServiceType.mq.value]:
        mq_level = walk_result.pop(path.join(EXTRACTED_PATH, namespace, "mq", "traces"), {})
        if mq_level:
            assert not mq_level["folders"]
            for name in mq_level["files"]:
                assert name.split(".")[-1] in ["json", "pb"]
            # make sure level 2 doesnt get messed up
            assert walk_result[path.join(EXTRACTED_PATH, namespace, "mq")]["folders"] == ["traces"]
            walk_result[path.join(EXTRACTED_PATH, namespace, "mq")]["folders"] = []

    # Level 2 and 3 - bottom
    assert len(walk_result) == len(expected_services)
    for directory in walk_result:
        assert not walk_result[directory]["folders"]
        convert_file_names(walk_result[directory]["files"])

    # check service is within auto
    if ops_service != OpsServiceType.auto.value:
        auto_walk_result = run_bundle_command(
            command=command.format(OpsServiceType.auto.value),
            tracked_files=tracked_files,
            extracted_path=AUTO_EXTRACTED_PATH
        )
        assert auto_walk_result[f"auto_{directory}"]["folders"] == walk_result[directory]["folders"]
        # make things easier if there is a different file
        auto_files = sorted(auto_walk_result[f"auto_{directory}"]["files"])
        ser_files = sorted(walk_result[directory]["files"])
        for file in auto_files:
            assert file in ser_files
        assert len(auto_files) == len(ser_files)


def test_create_bundle_otel(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS otel."""
    # dir for unpacked files
    ops_service = OpsServiceType.auto.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, "otel")

    # TODO: add in expected for each
    # otel
    # do we always have these? What cases do they have them vs not?
    # how can names change?
    if file_map.get("configuration"):
        for config in file_map["configuration"]:
            assert config["version"] == "v0"
    if file_map.get("instance"):
        for config in file_map["instance"]:
            assert config["version"] == "v0"

    expected_file_objs = {
        "deployment": [
            "aio-otel-collector"
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
