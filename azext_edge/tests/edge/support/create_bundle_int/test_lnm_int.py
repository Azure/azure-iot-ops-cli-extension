# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import LNM_API_V1B1
from .helpers import check_custom_resource_files, check_workload_resource_files, get_file_map, run_bundle_command
from ....helpers import run

logger = get_logger(__name__)


def test_create_bundle_lnm(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS lnm."""
    ops_service = OpsServiceType.lnm.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)
    lnm_instances = run("kubectl get lnm -A") or []
    lnm_present = file_map["__namespaces__"]["aio"] in lnm_instances

    # find bundle path from tracked_files that with .zip extension
    bundle_path = next((file for file in tracked_files if file.endswith(".zip")), None)

    # TODO: when adding scenarios - make sure one scenario is adding in an lnm instance
    # Note that this is structured by namespace folder instead of by if
    # AIO
    check_custom_resource_files(
        file_objs=file_map["aio"],
        resource_api=LNM_API_V1B1,
        namespace=file_map["__namespaces__"]["aio"],
    )
    # check scales
    # rule -> if there is an lnm then there is a scale with the same name
    if lnm_present:
        assert "scale" in file_map["aio"]
        assert len(file_map["aio"]["scale"]) == len(file_map["aio"]["lnm"])
        lnm_names = [file["name"] for file in file_map["aio"]["lnm"]]
        for file in file_map["aio"]["scale"]:
            assert file["name"] in lnm_names
            assert file["extension"] == "yaml"
            assert file["version"] == LNM_API_V1B1.version

    expected_workload_types = ["deployment", "pod", "replicaset"]
    if lnm_present:
        expected_workload_types.append("service")
    expected_types = set(expected_workload_types).union(LNM_API_V1B1.kinds)
    assert set(file_map["aio"].keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=file_map["aio"],
        expected_workload_types=expected_workload_types,
        prefixes=["aio-lnm"],
        bundle_path=bundle_path
    )

    # LNM svclb namespace
    if lnm_present:
        expected_workload_types = ["daemonset", "pod"]
        assert set(file_map["svclb"].keys()).issubset(expected_workload_types)
        check_workload_resource_files(
            file_objs=file_map["svclb"],
            expected_workload_types=expected_workload_types,
            prefixes=["svclb-aio-lnm"],
            bundle_path=bundle_path
        )
