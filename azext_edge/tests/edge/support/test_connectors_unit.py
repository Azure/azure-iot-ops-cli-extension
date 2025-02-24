# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.support.connectors import (
    OPC_APP_LABEL,
    CONNECTORS_DIRECTORY_PATH,
    OPC_NAME_LABEL,
    OPC_NAME_VAR_LABEL,
    OPCUA_NAME_LABEL,
)
from azext_edge.tests.edge.support.test_support_unit import (
    assert_list_config_maps,
    assert_list_daemon_sets,
    assert_list_deployments,
    assert_list_pods,
    assert_list_replica_sets,
    assert_list_services,
)

from ...generators import generate_random_string

a_bundle_dir = f"support_test_{generate_random_string()}"


def test_create_bundle_connectors(
    mocked_client,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_config_maps,
    mocked_list_daemonsets,
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_namespaced_custom_objects,
    mocked_get_config_map,
):
    since_seconds = random.randint(86400, 172800)
    result = support_bundle(
        None,
        ops_services=[OpsServiceType.connectors.value],
        bundle_dir=a_bundle_dir,
        log_age_seconds=since_seconds,
    )

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    # Assert runtime resources
    for pod_name_label in [OPC_APP_LABEL, OPC_NAME_LABEL, OPC_NAME_VAR_LABEL, OPCUA_NAME_LABEL]:
        assert_list_pods(
            mocked_client,
            mocked_zipfile,
            mocked_list_pods,
            label_selector=pod_name_label,
            directory_path=CONNECTORS_DIRECTORY_PATH,
            since_seconds=since_seconds,
            include_metrics=True,
        )
        assert_list_deployments(
            mocked_client,
            mocked_zipfile,
            label_selector=None,
            directory_path=CONNECTORS_DIRECTORY_PATH,
            mock_names=[
                "aio-opc-admission-controller",
                "aio-opc-supervisor",
                "aio-opc-opc",
                "opcplc-0000000",
            ],
        )
    assert_list_config_maps(
        mocked_client,
        mocked_zipfile,
        label_selector=OPCUA_NAME_LABEL,
        directory_path=CONNECTORS_DIRECTORY_PATH,
    )

    # TODO: one-off field selector remove after label
    assert_list_daemon_sets(
        mocked_client,
        mocked_zipfile,
        field_selector="metadata.name==aio-opc-asset-discovery",
        directory_path=CONNECTORS_DIRECTORY_PATH,
    )
    assert_list_daemon_sets(
        mocked_client,
        mocked_zipfile,
        label_selector=OPCUA_NAME_LABEL,
        directory_path=CONNECTORS_DIRECTORY_PATH,
    )
    assert_list_deployments(
        mocked_client,
        mocked_zipfile,
        label_selector=OPC_NAME_LABEL,
        directory_path=CONNECTORS_DIRECTORY_PATH,
    )
    assert_list_deployments(
        mocked_client,
        mocked_zipfile,
        label_selector=OPCUA_NAME_LABEL,
        directory_path=CONNECTORS_DIRECTORY_PATH,
    )
    for label_selector in [OPC_APP_LABEL, OPC_NAME_LABEL, OPCUA_NAME_LABEL]:
        assert_list_replica_sets(
            mocked_client,
            mocked_zipfile,
            label_selector=label_selector,
            directory_path=CONNECTORS_DIRECTORY_PATH,
        )
    assert_list_services(
        mocked_client,
        mocked_zipfile,
        label_selector=None,
        directory_path=CONNECTORS_DIRECTORY_PATH,
        mock_names=["opcplc-0000000"],
    )
    assert_list_services(
        mocked_client, mocked_zipfile, label_selector=OPC_APP_LABEL, directory_path=CONNECTORS_DIRECTORY_PATH
    )
    assert_list_services(
        mocked_client,
        mocked_zipfile,
        label_selector=OPCUA_NAME_LABEL,
        directory_path=CONNECTORS_DIRECTORY_PATH,
    )
