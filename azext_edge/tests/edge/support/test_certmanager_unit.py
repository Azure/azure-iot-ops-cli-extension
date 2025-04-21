# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.certmanager import (
    CERT_DIRECTORY_PATH,
    CERT_MANAGER_NAMESPACE,
    TRUST_BUNDLE_LABEL,
)
from azext_edge.tests.edge.support.test_support_unit import (
    assert_list_config_maps,
    assert_list_deployments,
    assert_list_pods,
    assert_list_replica_sets,
    assert_list_services,
)

from ...generators import generate_random_string

a_bundle_dir = f"support_test_{generate_random_string()}"


def test_create_bundle_certmanager(
    mocked_client,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_config_maps,
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
        ops_services=[OpsServiceType.certmanager.value],
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
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
        since_seconds=since_seconds,
    )
    assert_list_deployments(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )
    assert_list_replica_sets(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )
    assert_list_services(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )
    assert_list_config_maps(
        mocked_client,
        mocked_zipfile,
        label_selector=TRUST_BUNDLE_LABEL,
        directory_path=CERT_DIRECTORY_PATH,
    )
    assert_list_config_maps(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )
