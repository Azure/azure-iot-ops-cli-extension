# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.akri import (
    AKRI_DIRECTORY_PATH,
    AKRI_NAME_LABEL_V2,
)
from azext_edge.tests.edge.support.test_support_unit import (
    assert_list_deployments,
    assert_list_pods,
    assert_list_replica_sets,
)

from ...generators import generate_random_string

a_bundle_dir = f"support_test_{generate_random_string()}"


def test_create_bundle_akri(
    mocked_client,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_get_config_map,
):
    since_seconds = random.randint(86400, 172800)
    result = support_bundle(
        None,
        ops_service=OpsServiceType.akri.value,
        bundle_dir=a_bundle_dir,
        log_age_seconds=since_seconds,
    )

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    assert_list_pods(
        mocked_client,
        mocked_zipfile,
        mocked_list_pods,
        label_selector=AKRI_NAME_LABEL_V2,
        directory_path=AKRI_DIRECTORY_PATH,
        since_seconds=since_seconds,
    )
    assert_list_deployments(
        mocked_client,
        mocked_zipfile,
        label_selector=AKRI_NAME_LABEL_V2,
        directory_path=AKRI_DIRECTORY_PATH,
    )
    assert_list_replica_sets(
        mocked_client,
        mocked_zipfile,
        label_selector=AKRI_NAME_LABEL_V2,
        directory_path=AKRI_DIRECTORY_PATH,
    )
