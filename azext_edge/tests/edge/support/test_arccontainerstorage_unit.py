# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.arccontainerstorage import (
    ARCCONTAINERSTORAGE_API_V1,
    ACSTOR_NAMESPACE,
    ACSTOR_DIRECTORY_PATH,
    CONTAINERSTORAGE_API_V1,
    STORAGE_NAMESPACE,
    STORAGE_DIRECTORY_PATH,
)
from azext_edge.tests.edge.support.test_support_unit import (
    assert_list_config_maps,
    assert_list_daemon_sets,
    assert_list_deployments,
    assert_list_persistent_volume_claims,
    assert_list_pods,
    assert_list_replica_sets,
    assert_list_services,
)

from ...generators import generate_random_string

a_bundle_dir = f"support_test_{generate_random_string()}"


def test_create_bundle_acsa(
    mocked_client,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_config_maps,
    mocked_list_daemonsets,
    mocked_list_deployments,
    mocked_list_persistent_volume_claims,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_get_config_map,
):
    since_seconds = random.randint(86400, 172800)
    result = support_bundle(
        None,
        ops_services=[OpsServiceType.arccontainerstorage.value],
        bundle_dir=a_bundle_dir,
        log_age_seconds=since_seconds,
    )

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    for (directory_path, namespace) in [
        (STORAGE_DIRECTORY_PATH, STORAGE_NAMESPACE),
        (ACSTOR_DIRECTORY_PATH, ACSTOR_NAMESPACE),
    ]:
        assert_list_deployments(
            mocked_client,
            mocked_zipfile,
            label_selector=None,
            directory_path=directory_path,
            namespace=namespace,
        )
        assert_list_replica_sets(
            mocked_client,
            mocked_zipfile,
            label_selector=None,
            directory_path=directory_path,
            namespace=namespace,
        )
        assert_list_services(
            mocked_client,
            mocked_zipfile,
            label_selector=None,
            directory_path=directory_path,
            namespace=namespace,
        )
        assert_list_pods(
            mocked_client,
            mocked_zipfile,
            mocked_list_pods,
            label_selector=None,
            directory_path=directory_path,
            since_seconds=since_seconds,
            namespace=namespace,
        )
        assert_list_daemon_sets(
            mocked_client,
            mocked_zipfile,
            label_selector=None,
            directory_path=directory_path,
            namespace=namespace,
        )

    assert_list_config_maps(
        mocked_client,
        mocked_zipfile,
        directory_path=CONTAINERSTORAGE_API_V1.moniker,
        label_selector=None,
        namespace=ACSTOR_NAMESPACE,
    )
    assert_list_persistent_volume_claims(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
        namespace=STORAGE_NAMESPACE,
    )
