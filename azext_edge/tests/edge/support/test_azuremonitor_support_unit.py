# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.azuremonitor import (
    MONITOR_DIRECTORY_PATH,
    MONITOR_NAMESPACE,
)
from azext_edge.tests.edge.support.conftest import add_pod_to_mocked_pods
from azext_edge.tests.edge.support.test_support_unit import (
    assert_list_config_maps,
    assert_list_deployments,
    assert_list_pods,
    assert_list_replica_sets,
    assert_list_services,
    assert_list_stateful_sets,
)

from ...generators import generate_random_string

a_bundle_dir = f"support_test_{generate_random_string()}"


def test_create_bundle_azuremonitor(
    mocked_client,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_config_maps,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_get_config_map,
):
    since_seconds = random.randint(86400, 172800)

    add_pod_to_mocked_pods(
        mocked_client=mocked_client,
        expected_pod_map=mocked_list_pods,
        mock_names=["diagnostics-operator-deployment", "diagnostics-v1-statefulset"],
        mock_init_containers=True,
    )

    result = support_bundle(
        None,
        ops_services=[OpsServiceType.azuremonitor.value],
        bundle_dir=a_bundle_dir,
        log_age_seconds=since_seconds,
    )

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    assert_list_pods(
        mocked_client,
        mocked_zipfile,
        mocked_list_pods,
        label_selector=None,
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        since_seconds=since_seconds,
    )
    assert_list_deployments(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        mock_names=["diagnostics-operator-deployment"],
    )
    assert_list_replica_sets(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        mock_names=["diagnostics-operator-deployment"],
    )
    assert_list_services(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        mock_names=["diagnostics-operator-service"],
    )
    assert_list_stateful_sets(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        mock_names=["diagnostics-v1-statefulset"],
    )
    assert_list_config_maps(
        mocked_client,
        mocked_zipfile,
        directory_path=MONITOR_DIRECTORY_PATH,
        label_selector=None,
        mock_names=["diagnostics-v1-collector-config"],
    )
