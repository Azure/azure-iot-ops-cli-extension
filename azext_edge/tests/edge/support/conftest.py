# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import List
from ...generators import generate_generic_id

import pytest


def add_pod_to_mocked_pods(mocked_client, expected_pod_map, mock_names: List[str] = None):
    from kubernetes.client.models import V1PodList, V1Pod, V1PodSpec, V1ObjectMeta, V1Container

    current_pods = mocked_client.CoreV1Api().list_pod_for_all_namespaces.return_value
    pod_list = current_pods.items()
    namespace = pod_list[0].metadata.namespace
    # all the mocks are the same
    # need to go through pod_name and container_name (that we don't care about here)
    mock_log = list(list(expected_pod_map[namespace].values())[0].values())[0]

    for pod_name in mock_names:
        container_name = generate_generic_id()
        spec = V1PodSpec(containers=[V1Container(name=container_name)])
        pod = V1Pod(metadata=V1ObjectMeta(namespace=namespace, name=pod_name), spec=spec)
        pod_list.append(pod)
        expected_pod_map[namespace][pod_name] = {container_name: mock_log}

    pods_list = V1PodList(items=pod_list)
    mocked_client.CoreV1Api().list_pod_for_all_namespaces.return_value = pods_list
    mocked_client.CoreV1Api().read_namespaced_pod_log.return_value = mock_log

    yield expected_pod_map


@pytest.fixture
def mocked_client(mocker, mocked_client):
    patched = mocker.patch("azext_edge.edge.providers.support.base.client", autospec=True)
    yield patched


@pytest.fixture
def mocked_root_logger(mocker, mocked_client):
    patched = mocker.patch("azext_edge.edge.providers.support_bundle.logger", autospec=True)
    yield patched


@pytest.fixture
def mocked_os_makedirs(mocker):
    patched = mocker.patch("azext_edge.edge.providers.support.base.makedirs", autospec=True)
    yield patched


@pytest.fixture
def mocked_zipfile(mocker):
    patched = mocker.patch("azext_edge.edge.providers.support_bundle.ZipFile", autospec=True)
    yield patched


@pytest.fixture
def mocked_get_stats(mocker):
    patched = mocker.patch("azext_edge.edge.providers.support.mq.get_stats", autospec=True)
    patched.return_value = "metrics"
    yield patched


@pytest.fixture(scope="function")
def mocked_cluster_resources(request, mocker):
    from azure.cli.core.azclierror import ResourceNotFoundError
    from kubernetes.client.models import V1APIResource, V1APIResourceList

    from azext_edge.edge.providers.edge_api import (
        EdgeResourceApi,
        MQ_API_V1B1,
        MQ_ACTIVE_API,
        OPCUA_API_V1,
        DATA_PROCESSOR_API_V1,
        SYMPHONY_API_V1,
        AKRI_API_V0,
        LNM_API_V1B1,
        DEVICEREGISTRY_API_V1
    )

    requested_resource_apis = getattr(request, "param", [])
    resource_map = {}

    def _get_api_resource(kind: str):
        return V1APIResource(name=f"{kind.lower()}s", kind=kind, namespaced=True, singular_name=kind.lower(), verbs=[])

    for resource_api in requested_resource_apis:
        r: EdgeResourceApi = resource_api
        r_key = r.as_str()
        v1_resources: List[V1APIResource] = []

        if r == MQ_API_V1B1:
            v1_resources.append(_get_api_resource("Broker"))
            v1_resources.append(_get_api_resource("BrokerListener"))
            v1_resources.append(_get_api_resource("BrokerDiagnostic"))
            v1_resources.append(_get_api_resource("DiagnosticService"))
            v1_resources.append(_get_api_resource("BrokerAuthentication"))
            v1_resources.append(_get_api_resource("BrokerAuthorization"))
            v1_resources.append(_get_api_resource("MqttBridgeTopicMap"))
            v1_resources.append(_get_api_resource("MqttBridgeConnector"))
            v1_resources.append(_get_api_resource("DataLakeConnector"))
            v1_resources.append(_get_api_resource("DataLakeConnectorTopicMap"))
            v1_resources.append(_get_api_resource("KafkaConnector"))
            v1_resources.append(_get_api_resource("KafkaConnectorTopicMap"))

        if r == MQ_ACTIVE_API:
            v1_resources.append(_get_api_resource("Broker"))
            v1_resources.append(_get_api_resource("BrokerListener"))
            v1_resources.append(_get_api_resource("BrokerDiagnostic"))
            v1_resources.append(_get_api_resource("DiagnosticService"))
            v1_resources.append(_get_api_resource("BrokerAuthentication"))
            v1_resources.append(_get_api_resource("BrokerAuthorization"))
            v1_resources.append(_get_api_resource("MqttBridgeTopicMap"))
            v1_resources.append(_get_api_resource("MqttBridgeConnector"))
            v1_resources.append(_get_api_resource("DataLakeConnector"))
            v1_resources.append(_get_api_resource("DataLakeConnectorTopicMap"))
            v1_resources.append(_get_api_resource("KafkaConnector"))
            v1_resources.append(_get_api_resource("KafkaConnectorTopicMap"))

        if r == OPCUA_API_V1:
            # v1_resources.append(_get_api_resource("Application"))
            # v1_resources.append(_get_api_resource("ModuleType"))
            # v1_resources.append(_get_api_resource("Module"))
            v1_resources.append(_get_api_resource("AssetType"))

        if r == DATA_PROCESSOR_API_V1:
            v1_resources.append(_get_api_resource("Dataset"))
            v1_resources.append(_get_api_resource("Instance"))
            v1_resources.append(_get_api_resource("Pipeline"))

        if r == SYMPHONY_API_V1:
            v1_resources.append(_get_api_resource("Instance"))
            v1_resources.append(_get_api_resource("Solution"))
            v1_resources.append(_get_api_resource("Target"))

        if r == AKRI_API_V0:
            v1_resources.append(_get_api_resource("Instance"))
            v1_resources.append(_get_api_resource("Configuration"))

        if r == LNM_API_V1B1:
            v1_resources.append(_get_api_resource("Lnm"))
            v1_resources.append(_get_api_resource("Scale"))

        if r == DEVICEREGISTRY_API_V1:
            v1_resources.append(_get_api_resource("Asset"))
            v1_resources.append(_get_api_resource("AssetEndpointProfile"))

        resource_map[r_key] = V1APIResourceList(resources=v1_resources, group_version=r.version)

    def _handle_resource_call(*args, **kwargs):
        resource_map: dict = kwargs["context"]

        if "group" in kwargs and "version" in kwargs:
            return resource_map.get(f"{kwargs['group']}/{kwargs['version']}")

        if "raise_on_404" in kwargs and kwargs["raise_on_404"]:
            raise ResourceNotFoundError(
                f"{kwargs['resource_api'].as_str()} resource API is not detected on the cluster."
            )

    patched = mocker.patch("azext_edge.edge.providers.edge_api.base.get_cluster_custom_api", autospec=True)
    _handle_call = partial(_handle_resource_call, context=resource_map)
    patched.side_effect = _handle_call

    yield {"param": requested_resource_apis, "mock": patched, "resources": resource_map}


# TODO - @digimaun make this more useful / flexible configuration.
@pytest.fixture
def mocked_list_pods(mocked_client):
    from kubernetes.client.models import V1PodList, V1Pod, V1PodSpec, V1ObjectMeta, V1Container

    expected_pod_map = {}
    namespaces = [generate_generic_id()]
    mock_log = f"===mocked pod log {generate_generic_id()} ==="
    for namespace in namespaces:
        pod_names = [generate_generic_id(), generate_generic_id()]
        pods = []
        expected_pod_map[namespace] = {}
        for pod_name in pod_names:
            container_name = generate_generic_id()
            spec = V1PodSpec(containers=[V1Container(name=container_name)])
            pod = V1Pod(metadata=V1ObjectMeta(namespace=namespace, name=pod_name), spec=spec)
            pods.append(pod)
            expected_pod_map[namespace][pod_name] = {container_name: mock_log}

    pods_list = V1PodList(items=pods)
    mocked_client.CoreV1Api().list_pod_for_all_namespaces.return_value = pods_list
    mocked_client.CoreV1Api().read_namespaced_pod_log.return_value = mock_log

    yield expected_pod_map


@pytest.fixture
def mocked_get_custom_objects(mocker):
    patched = mocker.patch("azext_edge.edge.providers.support.base.get_custom_objects", autospec=True)

    def _handle_list_custom_object(*args, **kwargs):
        result = {}
        items = []

        items.append({"kind": kwargs["plural"][:-1], "metadata": {"namespace": "mock_namespace", "name": "mock_name"}})
        result["items"] = items
        return result

    patched.side_effect = _handle_list_custom_object
    yield patched


@pytest.fixture
def mocked_list_deployments(mocked_client):
    from kubernetes.client.models import V1DeploymentList, V1Deployment, V1ObjectMeta

    def _handle_list_deployments(*args, **kwargs):
        names = ["mock_deployment"]
        # @jiacju - currently no unique label for lnm
        # @vilit - also akri
        if "label_selector" in kwargs and kwargs["label_selector"] is None:
            names.extend([
                "aio-lnm-operator",
                "aio-akri-otel-collector",
                "aio-opc-admission-controller",
                "aio-opc-supervisor",
                "aio-opc-opc.*"
            ])

        deployment_list = []
        for name in names:
            deployment_list.append(V1Deployment(metadata=V1ObjectMeta(namespace="mock_namespace", name=name)))
        deployment_list = V1DeploymentList(items=deployment_list)

        return deployment_list

    mocked_client.AppsV1Api().list_deployment_for_all_namespaces.side_effect = _handle_list_deployments

    yield mocked_client


@pytest.fixture
def mocked_list_replicasets(mocked_client):
    from kubernetes.client.models import V1ReplicaSetList, V1ReplicaSet, V1ObjectMeta

    def _handle_list_replicasets(*args, **kwargs):
        names = ["mock_replicaset"]
        # @vilit - also akri
        if "label_selector" in kwargs and kwargs["label_selector"] is None:
            names.extend([
                "aio-akri-otel-collector-*"
            ])

        replicaset_list = []
        for name in names:
            replicaset_list.append(V1ReplicaSet(metadata=V1ObjectMeta(namespace="mock_namespace", name=name)))
        replicaset_list = V1ReplicaSetList(items=replicaset_list)

        return replicaset_list

    mocked_client.AppsV1Api().list_replica_set_for_all_namespaces.side_effect = _handle_list_replicasets

    yield mocked_client


@pytest.fixture
def mocked_list_statefulsets(mocked_client):
    from kubernetes.client.models import V1StatefulSetList, V1StatefulSet, V1ObjectMeta

    def _handle_list_statefulsets(*args, **kwargs):
        statefulset = V1StatefulSet(metadata=V1ObjectMeta(namespace="mock_namespace", name="mock_statefulset"))
        statefulset_list = V1StatefulSetList(items=[statefulset])

        return statefulset_list

    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.side_effect = _handle_list_statefulsets

    yield mocked_client


@pytest.fixture
def mocked_list_services(mocked_client):
    from kubernetes.client.models import V1ServiceList, V1Service, V1ObjectMeta

    def _handle_list_services(*args, **kwargs):
        service = V1Service(metadata=V1ObjectMeta(namespace="mock_namespace", name="mock_service"))
        service_list = V1ServiceList(items=[service])

        return service_list

    mocked_client.CoreV1Api().list_service_for_all_namespaces.side_effect = _handle_list_services

    yield mocked_client


@pytest.fixture
def mocked_list_nodes(mocked_client):
    from kubernetes.client.models import V1NodeList, V1Node, V1ObjectMeta

    def _handle_list_nodes(*args, **kwargs):
        node = V1Node(metadata=V1ObjectMeta(name="mock_node"))
        node_list = V1NodeList(items=[node])

        return node_list

    mocked_client.CoreV1Api().list_node.side_effect = _handle_list_nodes

    yield mocked_client


@pytest.fixture
def mocked_list_daemonsets(mocked_client):
    from kubernetes.client.models import V1DaemonSetList, V1DaemonSet, V1ObjectMeta

    def _handle_list_daemonsets(*args, **kwargs):
        # @jiacju - currently no unique label for lnm
        # @vilit - also akri
        daemonset_names = ["mock_daemonset"]
        if "label_selector" in kwargs and kwargs["label_selector"] is None:
            daemonset_names.extend([
                "aio-akri-agent-daemonset",
                "svclb-lnm-operator"
            ])

        daemonset_list = []
        for name in daemonset_names:
            daemonset_list.append(V1DaemonSet(metadata=V1ObjectMeta(namespace="mock_namespace", name=name)))
        daemonset_list = V1DaemonSetList(items=daemonset_list)

        return daemonset_list

    mocked_client.AppsV1Api().list_daemon_set_for_all_namespaces.side_effect = _handle_list_daemonsets

    yield mocked_client
