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
from azext_edge.edge.common import BROKER_RESOURCE, OPCUA_RESOURCE, IotEdgeBrokerResource
from azext_edge.edge.providers.support.base import get_bundle_path
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
    [{}, {BROKER_RESOURCE: True}, {OPCUA_RESOURCE: True}, {BROKER_RESOURCE: True, OPCUA_RESOURCE: True}],
    indirect=True,
)
def test_create_bundle(
    mocked_client, mocked_cluster_resources, mocked_config, mocked_os_makedirs, mocked_zipfile, mocked_list_pods
):
    if not mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="e4k")
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="opcua")
        auto_result_no_resources = support_bundle(None, bundle_dir=a_bundle_dir)
        assert auto_result_no_resources is None
        return

    since_seconds = random.randint(86400, 172800)
    result = support_bundle(None, bundle_dir=a_bundle_dir, log_age_seconds=since_seconds)

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    expected_resources = mocked_cluster_resources["param"]
    if BROKER_RESOURCE in expected_resources:
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "brokers")
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "brokerlisteners")
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "brokerdiagnostics")
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "brokerauthentications")
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "brokerauthorizations")
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "mqttbridgetopicmaps")
        assert_list_custom_resources(mocked_client, BROKER_RESOURCE, "mqttbridgeconnectors")

        assert_list_deployments(mocked_client, label_selector=E4K_LABEL)
        assert_list_pods(mocked_client, label_selector=E4K_LABEL)
        assert_list_replica_sets(mocked_client, E4K_LABEL)
        assert_list_stateful_sets(mocked_client, E4K_LABEL)
        assert_list_services(mocked_client, E4K_LABEL)

    if OPCUA_RESOURCE in expected_resources:
        assert_list_custom_resources(mocked_client, OPCUA_RESOURCE, "applications")
        assert_list_custom_resources(mocked_client, OPCUA_RESOURCE, "moduletypes")
        assert_list_custom_resources(mocked_client, OPCUA_RESOURCE, "modules")
        assert_list_custom_resources(mocked_client, OPCUA_RESOURCE, "assettypes")
        assert_list_custom_resources(mocked_client, OPCUA_RESOURCE, "assets")
        assert_list_custom_resources(mocked_client, OPCUA_RESOURCE, "assets")

        assert_list_deployments(mocked_client, label_selector=OPCUA_ORCHESTRATOR_LABEL)
        assert_list_pods(mocked_client, label_selector=OPCUA_SUPERVISOR_LABEL)
        assert_list_pods(mocked_client, label_selector=OPCUA_GENERAL_LABEL)

    if mocked_list_pods:
        assert_pod_logs(mocked_client, expected_pods=mocked_list_pods, since_seconds=since_seconds)


def assert_list_custom_resources(mocked_client, resource: IotEdgeBrokerResource, plural: str):
    mocked_client.CustomObjectsApi().list_cluster_custom_object.assert_any_call(
        group=resource.group, version=resource.version, plural=plural
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


def assert_pod_logs(mocked_client, expected_pods: Dict[str, Dict[str, dict]], since_seconds: int):
    for namespace in expected_pods:
        for pod in expected_pods[namespace]:
            for container in expected_pods[namespace][pod]:
                mocked_client.CoreV1Api().read_namespaced_pod_log.assert_any_call(
                    name=pod, namespace=namespace, since_seconds=since_seconds, container=container
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
