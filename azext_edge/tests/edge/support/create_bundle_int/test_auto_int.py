# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from os import mkdir, path
from knack.log import get_logger
from typing import Dict, List, Optional, Tuple
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from .helpers import (
    assert_file_names,
    process_top_levels,
    run_bundle_command,
    BASE_ZIP_PATH,
)
from ....helpers import assert_extra_or_missing_names

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


def generate_bundle_test_cases() -> List[Tuple[str, bool, Optional[str]]]:
    # case = ops_service, mq_traces, bundle_dir
    service_list = OpsServiceType.list()
    cases = [(service, False, "support_bundles") for service in service_list]
    cases.append((OpsServiceType.mq.value, True, None))

    # test "all services" bundle
    cases.append((None, False, None))
    return cases


@pytest.mark.parametrize("ops_service, mq_traces, bundle_dir", generate_bundle_test_cases())
def test_create_bundle(cluster_connection, bundle_setup, ops_service, bundle_dir, mq_traces, tracked_files):
    """Test to focus on ops_service param."""

    # skip arccontainerstorage and azuremonitor for aio namespace check
    if ops_service in [OpsServiceType.arccontainerstorage.value, OpsServiceType.azuremonitor.value]:
        pytest.skip(f"{ops_service} is not generated in aio namespace")

    command = f"az iot ops support create-bundle --broker-traces {mq_traces} "
    if bundle_dir:
        command += f" --bundle-dir {bundle_dir} "
        try:
            mkdir(bundle_dir)
            tracked_files.append(bundle_dir)
        except FileExistsError:
            pass

    # generate second bundle as close as possible
    if ops_service:
        walk_result, _ = run_bundle_command(
            command=command + f"--ops-service {ops_service}", tracked_files=tracked_files
        )
        auto_walk_result, _ = run_bundle_command(command=command, tracked_files=tracked_files)
    else:
        walk_result, _ = run_bundle_command(command=command, tracked_files=tracked_files)

    # Level 0 - top
    namespaces = process_top_levels(walk_result, ops_service)
    aio_namespace = namespaces.get("aio")
    acs_namespace = namespaces.get("acs")
    acstor_namespace = namespaces.get("acstor")
    ssc_namespace = namespaces.get("ssc")
    arc_namespace = namespaces.get("arc")
    certmanager_namespace = namespaces.get("certmanager")

    # Level 1
    if not aio_namespace:
        raise AssertionError(f"Could not determine AIO namespace: namespaces {namespaces}")
    level_1 = walk_result.pop(path.join(BASE_ZIP_PATH, aio_namespace))
    expected_services = _get_expected_services(walk_result, ops_service, aio_namespace)
    assert sorted(level_1["folders"]) == sorted(expected_services)
    assert not level_1["files"]

    # Check and take out mq traces:
    if mq_traces and ops_service == OpsServiceType.mq.value:
        mq_level = walk_result.pop(path.join(BASE_ZIP_PATH, aio_namespace, OpsServiceType.mq.value, "traces"), {})
        if mq_level:
            assert not mq_level["folders"]
            assert_file_names(mq_level["files"])
            # make sure level 2 doesnt get messed up
            assert walk_result[path.join(BASE_ZIP_PATH, aio_namespace, OpsServiceType.mq.value)]["folders"] == [
                "traces"
            ]
            walk_result[path.join(BASE_ZIP_PATH, aio_namespace, OpsServiceType.mq.value)]["folders"] = []

    # remove other namespaces resource from aio namespace assertion
    for namespace, service in [
        (acs_namespace, "arccontainerstorage"),
        (acstor_namespace, "containerstorage"),
        (ssc_namespace, OpsServiceType.secretstore.value),
        (certmanager_namespace, OpsServiceType.certmanager.value),
    ]:
        if namespace:
            walk_result.pop(path.join(BASE_ZIP_PATH, namespace, service), {})

    # remove certmanager resources in other namespace from walk_result from aio namespace assertion

    for namespace in [arc_namespace, acstor_namespace, ssc_namespace]:
        if namespace and path.join(BASE_ZIP_PATH, namespace, OpsServiceType.certmanager.value) in walk_result:
            walk_result.pop(path.join(BASE_ZIP_PATH, namespace, OpsServiceType.certmanager.value), {})

    # remove azuremonitor resources in arc namespace from walk_result from aio namespace assertion
    if arc_namespace and path.join(BASE_ZIP_PATH, arc_namespace, OpsServiceType.azuremonitor.value) in walk_result:
        walk_result.pop(path.join(BASE_ZIP_PATH, arc_namespace, OpsServiceType.azuremonitor.value), {})

    # Level 2 and 3 - bottom
    is_billing_included = OpsServiceType.billing.value in expected_services
    actual_walk_result = len(expected_services) + int(is_billing_included) + len(ARC_AGENTS)

    assert len(walk_result) == actual_walk_result

    for directory in walk_result:
        assert not walk_result[directory]["folders"]
        assert_file_names(walk_result[directory]["files"])

    # check service is within auto
    if ops_service:
        expected_folders = [[]]
        if mq_traces and ops_service == OpsServiceType.mq.value:
            expected_folders.append(["traces"])
        for directory in walk_result:
            assert auto_walk_result[directory]["folders"] in expected_folders
            # make things easier if there is a different file
            auto_files = sorted(auto_walk_result[directory]["files"])
            ser_files = sorted(walk_result[directory]["files"])
            assert_extra_or_missing_names(
                resource_type=f"auto bundle files not found in {ops_service} bundle",
                result_names=auto_files,
                pre_expected_names=ser_files,
                post_expected_names=[],
            )


def _get_expected_services(
    walk_result: Dict[str, Dict[str, List[str]]], ops_service: str, namespace: str
) -> List[str]:
    expected_services = [ops_service] if ops_service else OpsServiceType.list()

    # remove services that are not created in aio namespace
    for monikor, service in [
        (OpsServiceType.deviceregistry.value, OpsServiceType.deviceregistry.value),
        ("arccontainerstorage", OpsServiceType.arccontainerstorage.value),
        (OpsServiceType.secretstore.value, OpsServiceType.secretstore.value),
        (OpsServiceType.azuremonitor.value, OpsServiceType.azuremonitor.value),
    ]:
        if not walk_result.get(path.join(BASE_ZIP_PATH, namespace, monikor)) and service in expected_services:
            expected_services.remove(service)

    expected_services.append("meta")
    return expected_services
