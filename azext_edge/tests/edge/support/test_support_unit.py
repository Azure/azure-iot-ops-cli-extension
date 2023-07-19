# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import random
from os.path import abspath, expanduser, join
from typing import Dict

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import (
    BLUEFIN_API_V1,
    BLUEFIN_DATASET,
    BLUEFIN_INSTANCE,
    BLUEFIN_PIPELINE,
    E4K_API_V1A2,
    E4K_BROKER,
    E4K_BROKER_AUTHENTICATION,
    E4K_BROKER_AUTHORIZATION,
    E4K_BROKER_DIAGNOSTIC,
    E4K_BROKER_LISTENER,
    E4K_DIAGNOSTIC_SERVICE,
    E4K_MQTT_BRIDGE_CONNECTOR,
    E4K_MQTT_BRIDGE_TOPIC_MAP,
    OPCUA_API_V1,
    OPCUA_APPLICATION,
    OPCUA_ASSET,
    OPCUA_ASSET_TYPE,
    OPCUA_MODULE,
    OPCUA_MODULE_TYPE,
    EdgeResource,
)
from azext_edge.edge.providers.support.base import get_bundle_path
from azext_edge.edge.providers.support.bluefin import (
    BLUEFIN_APP_LABEL,
    BLUEFIN_INSTANCE_LABEL,
    BLUEFIN_ONEOFF_LABEL,
    BLUEFIN_PART_OF_LABEL,
    BLUEFIN_RELEASE_LABEL,
)
from azext_edge.edge.providers.support.e4k import E4K_LABEL
from azext_edge.edge.providers.support.opcua import (
    OPCUA_GENERAL_LABEL,
    OPCUA_ORCHESTRATOR_LABEL,
    OPCUA_SUPERVISOR_LABEL,
)

from ...generators import generate_generic_id

a_bundle_dir = f"support_test_{generate_generic_id()}"


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        {},
        {E4K_API_V1A2: True},
        {OPCUA_API_V1: True},
        {BLUEFIN_API_V1: True},
        {E4K_API_V1A2: True, OPCUA_API_V1: True},
        {E4K_API_V1A2: True, BLUEFIN_API_V1: True},
        {E4K_API_V1A2: True, OPCUA_API_V1: True, BLUEFIN_API_V1: True},
    ],
    indirect=True,
)
def test_create_bundle(
    mocked_client, mocked_cluster_resources, mocked_config, mocked_os_makedirs, mocked_zipfile, mocked_list_pods
):
    if not mocked_cluster_resources["param"] or E4K_API_V1A2 not in mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="e4k")

    if not mocked_cluster_resources["param"] or OPCUA_API_V1 not in mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="opcua")

    if not mocked_cluster_resources["param"] or BLUEFIN_API_V1 not in mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="bluefin")

    if mocked_cluster_resources["param"] == {}:
        auto_result_no_resources = support_bundle(None, bundle_dir=a_bundle_dir)
        assert auto_result_no_resources is None
        return

    since_seconds = random.randint(86400, 172800)
    result = support_bundle(None, bundle_dir=a_bundle_dir, log_age_seconds=since_seconds)

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    expected_resources = mocked_cluster_resources["param"]
    if E4K_API_V1A2 in expected_resources:
        assert_list_custom_resources(mocked_client, E4K_BROKER)
        assert_list_custom_resources(mocked_client, E4K_BROKER_LISTENER)
        assert_list_custom_resources(mocked_client, E4K_BROKER_DIAGNOSTIC)
        assert_list_custom_resources(mocked_client, E4K_DIAGNOSTIC_SERVICE)
        assert_list_custom_resources(mocked_client, E4K_BROKER_AUTHENTICATION)
        assert_list_custom_resources(mocked_client, E4K_BROKER_AUTHORIZATION)
        assert_list_custom_resources(mocked_client, E4K_MQTT_BRIDGE_TOPIC_MAP)
        assert_list_custom_resources(mocked_client, E4K_MQTT_BRIDGE_CONNECTOR)

        assert_list_deployments(mocked_client, label_selector=E4K_LABEL)
        assert_list_pods(mocked_client, label_selector=E4K_LABEL)
        assert_list_replica_sets(mocked_client, E4K_LABEL)
        assert_list_stateful_sets(mocked_client, E4K_LABEL)
        assert_list_services(mocked_client, E4K_LABEL)

    if OPCUA_API_V1 in expected_resources:
        assert_list_custom_resources(mocked_client, OPCUA_APPLICATION)
        assert_list_custom_resources(mocked_client, OPCUA_MODULE_TYPE)
        assert_list_custom_resources(mocked_client, OPCUA_MODULE)
        assert_list_custom_resources(mocked_client, OPCUA_ASSET_TYPE)
        assert_list_custom_resources(mocked_client, OPCUA_ASSET)

        assert_list_deployments(mocked_client, label_selector=OPCUA_ORCHESTRATOR_LABEL)
        assert_list_pods(mocked_client, label_selector=OPCUA_SUPERVISOR_LABEL)
        assert_list_pods(mocked_client, label_selector=OPCUA_GENERAL_LABEL)

    if BLUEFIN_API_V1 in expected_resources:
        assert_list_custom_resources(mocked_client, BLUEFIN_PIPELINE)
        assert_list_custom_resources(mocked_client, BLUEFIN_INSTANCE)
        assert_list_custom_resources(mocked_client, BLUEFIN_DATASET)

        assert_list_deployments(mocked_client, label_selector=BLUEFIN_APP_LABEL)
        assert_list_deployments(mocked_client, label_selector=BLUEFIN_PART_OF_LABEL)

        assert_list_pods(mocked_client, label_selector=BLUEFIN_APP_LABEL)
        assert_list_pods(mocked_client, label_selector=BLUEFIN_INSTANCE_LABEL)
        assert_list_pods(mocked_client, label_selector=BLUEFIN_RELEASE_LABEL)
        assert_list_pods(mocked_client, label_selector=BLUEFIN_ONEOFF_LABEL)

        assert_list_replica_sets(mocked_client, label_selector=BLUEFIN_APP_LABEL)
        assert_list_replica_sets(mocked_client, label_selector=BLUEFIN_ONEOFF_LABEL)

        assert_list_stateful_sets(mocked_client, label_selector=BLUEFIN_RELEASE_LABEL)
        assert_list_stateful_sets(mocked_client, label_selector=BLUEFIN_INSTANCE_LABEL)

        # @digimaun - TODO, use labels when available.
        assert_list_services(mocked_client, label_selector=None)

    # assert shared KPIs regardless of service
    assert_shared_kpis(mocked_client)

    if mocked_list_pods:
        assert_pod_logs(mocked_client, expected_pods=mocked_list_pods, since_seconds=since_seconds)


def assert_list_custom_resources(mocked_client, resource: EdgeResource):
    mocked_client.CustomObjectsApi().list_cluster_custom_object.assert_any_call(
        group=resource.api.group, version=resource.api.version, plural=resource.plural
    )


def assert_list_deployments(mocked_client, label_selector: str):
    mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_any_call(label_selector=label_selector)


def assert_list_pods(mocked_client, label_selector: str):
    mocked_client.CoreV1Api().list_pod_for_all_namespaces.assert_any_call(label_selector=label_selector)


def assert_list_replica_sets(mocked_client, label_selector: str):
    mocked_client.AppsV1Api().list_replica_set_for_all_namespaces.assert_any_call(label_selector=label_selector)


def assert_list_stateful_sets(mocked_client, label_selector: str):
    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(label_selector=label_selector)


def assert_list_services(mocked_client, label_selector: str):
    mocked_client.CoreV1Api().list_service_for_all_namespaces.assert_any_call(label_selector=label_selector)


def assert_shared_kpis(mocked_client):
    mocked_client.CoreV1Api().list_node.assert_called_once()


def assert_pod_logs(mocked_client, expected_pods: Dict[str, Dict[str, dict]], since_seconds: int):
    for namespace in expected_pods:
        for pod in expected_pods[namespace]:
            for container in expected_pods[namespace][pod]:
                mocked_client.CoreV1Api().read_namespaced_pod_log.assert_any_call(
                    name=pod, namespace=namespace, since_seconds=since_seconds, container=container, previous=False
                )
                mocked_client.CoreV1Api().read_namespaced_pod_log.assert_any_call(
                    name=pod, namespace=namespace, since_seconds=since_seconds, container=container, previous=True
                )


def test_get_bundle_path(mocked_os_makedirs):
    path = get_bundle_path("~/test")
    expected = f"{join(expanduser('~'), 'test', 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_pas.zip")

    path = get_bundle_path("./test/")
    expected = f"{join(abspath('.'), 'test', 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_pas.zip")

    path = get_bundle_path("test/thing")
    expected = f"{join(abspath('test/thing'), 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_pas.zip")

    path = get_bundle_path()
    expected = f"{join(abspath('.'), 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_pas.zip")
