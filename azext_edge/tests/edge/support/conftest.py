# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import List
from ...generators import generate_random_string

import pytest


def add_pod_to_mocked_pods(
    mocked_client,
    expected_pod_map,
    mock_names: List[str] = None,
    mock_init_containers: bool = False
):
    from kubernetes.client.models import V1PodList, V1Pod, V1PodSpec, V1ObjectMeta, V1Container

    current_pods = mocked_client.CoreV1Api().list_pod_for_all_namespaces.return_value
    pod_list = current_pods.items
    namespace = pod_list[0].metadata.namespace
    # all the mocks are the same
    # need to go through pod_name and container_name (that we don't care about here)
    mock_log = list(list(expected_pod_map[namespace].values())[0].values())[0]

    for pod_name in mock_names:
        container_name = generate_random_string()
        spec = V1PodSpec(containers=[V1Container(name=container_name)])
        pod = V1Pod(metadata=V1ObjectMeta(namespace=namespace, name=pod_name), spec=spec)

        if mock_init_containers:
            pod.spec.init_containers = [V1Container(name="mock-init-container")]
            expected_pod_map[namespace][pod_name] = {"mock-init-container": mock_log}
        pod_list.append(pod)

        if pod_name in expected_pod_map[namespace]:
            expected_pod_map[namespace][pod_name][container_name] = mock_log
        else:
            expected_pod_map[namespace][pod_name] = {container_name: mock_log}

    pods_list = V1PodList(items=pod_list)
    mocked_client.CoreV1Api().list_pod_for_all_namespaces.return_value = pods_list
    mocked_client.CoreV1Api().read_namespaced_pod_log.return_value = mock_log


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
    patched = mocker.patch("os.makedirs", autospec=True)
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
        MQ_ACTIVE_API,
        MQTT_BROKER_API_V1B1,
        OPCUA_API_V1,
        ORC_API_V1,
        AKRI_API_V0,
        DEVICEREGISTRY_API_V1,
        CLUSTER_CONFIG_API_V1,
    )

    requested_resource_apis = getattr(request, "param", [])
    resource_map = {}

    def _get_api_resource(kind: str):
        return V1APIResource(name=f"{kind.lower()}s", kind=kind, namespaced=True, singular_name=kind.lower(), verbs=[])

    for resource_api in requested_resource_apis:
        r: EdgeResourceApi = resource_api
        r_key = r.as_str()
        v1_resources: List[V1APIResource] = []

        if r == MQTT_BROKER_API_V1B1:
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
            v1_resources.append(_get_api_resource("AssetType"))

        if r == ORC_API_V1:
            v1_resources.append(_get_api_resource("Instance"))
            v1_resources.append(_get_api_resource("Solution"))
            v1_resources.append(_get_api_resource("Target"))

        if r == AKRI_API_V0:
            v1_resources.append(_get_api_resource("Instance"))
            v1_resources.append(_get_api_resource("Configuration"))

        if r == DEVICEREGISTRY_API_V1:
            v1_resources.append(_get_api_resource("Asset"))
            v1_resources.append(_get_api_resource("AssetEndpointProfile"))

        if r == CLUSTER_CONFIG_API_V1:
            v1_resources.append(_get_api_resource("BillingError"))
            v1_resources.append(_get_api_resource("BillingSettings"))
            v1_resources.append(_get_api_resource("BillingUsage"))
            v1_resources.append(_get_api_resource("BillingStorage"))

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
    namespaces = [generate_random_string()]
    mock_log = f"===mocked pod log {generate_random_string()} ==="
    for namespace in namespaces:
        pod_names = [generate_random_string(), generate_random_string()]
        pods = []
        expected_pod_map[namespace] = {}
        for pod_name in pod_names:
            container_name = generate_random_string()
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
def mocked_namespaced_custom_objects(mocked_client):
    def _handle_namespaced_custom_object(*args, **kwargs):
        custom_object = {
            'kind': 'PodMetrics',
            'apiVersion': 'metrics.k8s.io/v1beta1',
            'metadata': {
                'name': 'mock_custom_object',
                'namespace': 'namespace',
                'creationTimestamp': '0000-00-00T00:00:00Z',
            },
            'timestamp': '0000-00-00T00:00:00Z'
        }

        return custom_object

    mocked_client.CustomObjectsApi().get_namespaced_custom_object.side_effect = _handle_namespaced_custom_object

    yield mocked_client


@pytest.fixture
def mocked_list_cron_jobs(mocked_client):
    from kubernetes.client.models import V1CronJobList, V1CronJob, V1ObjectMeta

    def _handle_list_cron_jobs(*args, **kwargs):
        cron_job = V1CronJob(metadata=V1ObjectMeta(namespace="mock_namespace", name="mock_cron_job"))
        cron_job_list = V1CronJobList(items=[cron_job])

        return cron_job_list

    mocked_client.BatchV1Api().list_cron_job_for_all_namespaces.side_effect = _handle_list_cron_jobs

    yield mocked_client


@pytest.fixture
def mocked_list_jobs(mocked_client):
    from kubernetes.client.models import V1JobList, V1Job, V1ObjectMeta

    def _handle_list_jobs(*args, **kwargs):
        job = V1Job(metadata=V1ObjectMeta(namespace="mock_namespace", name="mock_job"))
        job_list = V1JobList(items=[job])

        return job_list

    mocked_client.BatchV1Api().list_job_for_all_namespaces.side_effect = _handle_list_jobs

    yield mocked_client


@pytest.fixture
def mocked_list_deployments(mocked_client):
    from kubernetes.client.models import V1DeploymentList, V1Deployment, V1ObjectMeta

    def _handle_list_deployments(*args, **kwargs):
        names = ["mock_deployment"]
        if "label_selector" in kwargs and kwargs["label_selector"] is None:
            names.extend(
                [
                    "aio-opc-admission-controller",
                    "aio-opc-supervisor",
                    "aio-opc-opc",
                    "opcplc-0000000",
                ]
            )

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
        service_names = ["mock_service"]
        if "label_selector" in kwargs and kwargs["label_selector"] is None:
            service_names.extend(
                [
                    "opcplc-0000000",
                ]
            )

        service_list = []
        for name in service_names:
            service_list.append(V1Service(metadata=V1ObjectMeta(namespace="mock_namespace", name=name)))
        service_list = V1ServiceList(items=service_list)

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
def mocked_list_cluster_events(mocked_client):
    from kubernetes.client.models import CoreV1EventList, CoreV1Event, V1ObjectMeta

    def _handle_list_cluster_events(*args, **kwargs):
        event = CoreV1Event(
            action="mock_action", involved_object="mock_object", metadata=V1ObjectMeta(name="mock_event")
        )
        event_list = CoreV1EventList(items=[event])

        return event_list

    mocked_client.CoreV1Api().list_event_for_all_namespaces.side_effect = _handle_list_cluster_events

    yield mocked_client


@pytest.fixture
def mocked_list_storage_classes(mocked_client):
    from kubernetes.client.models import V1StorageClassList, V1StorageClass, V1ObjectMeta

    def _handle_list_storage_classes(*args, **kwargs):
        storage_class = V1StorageClass(
            provisioner="mock_provisioner", metadata=V1ObjectMeta(name="mock_storage_class")
        )
        storage_class_list = V1StorageClassList(items=[storage_class])

        return storage_class_list

    mocked_client.StorageV1Api().list_storage_class.side_effect = _handle_list_storage_classes

    yield mocked_client


@pytest.fixture
def mocked_list_daemonsets(mocked_client):
    from kubernetes.client.models import V1DaemonSetList, V1DaemonSet, V1ObjectMeta

    def _handle_list_daemonsets(*args, **kwargs):
        daemonset_names = ["mock_daemonset"]
        daemonset_list = []
        for name in daemonset_names:
            daemonset_list.append(V1DaemonSet(metadata=V1ObjectMeta(namespace="mock_namespace", name=name)))
        daemonset_list = V1DaemonSetList(items=daemonset_list)

        return daemonset_list

    mocked_client.AppsV1Api().list_daemon_set_for_all_namespaces.side_effect = _handle_list_daemonsets

    yield mocked_client


@pytest.fixture
def mocked_list_persistent_volume_claims(mocked_client):
    from kubernetes.client.models import V1PersistentVolumeClaimList, V1PersistentVolumeClaim, V1ObjectMeta

    def _handle_list_persistent_volume_claims(*args, **kwargs):
        pvc = V1PersistentVolumeClaim(metadata=V1ObjectMeta(namespace="mock_namespace", name="mock_pvc"))
        pvc_list = V1PersistentVolumeClaimList(items=[pvc])

        return pvc_list

    mocked_client.CoreV1Api().list_persistent_volume_claim_for_all_namespaces.side_effect = (
        _handle_list_persistent_volume_claims
    )

    yield mocked_client


@pytest.fixture
def mocked_mq_active_api(mocker):
    # Supports fetching events in support bundle as its based on MQ deployment
    patched_active_mq_api = mocker.patch("azext_edge.edge.providers.edge_api.MQ_ACTIVE_API")
    patched_active_mq_api.get_resources.return_value = {"items": [{"metadata": {"namespace": "mock_namespace"}}]}
    yield patched_active_mq_api


@pytest.fixture
def mocked_mq_get_traces(mocker):
    from zipfile import ZipInfo

    test_zipinfo = ZipInfo("trace_key")
    test_zipinfo.file_size = 0
    test_zipinfo.compress_size = 0

    # Supports --mq-traces
    patched_get_traces = mocker.patch("azext_edge.edge.providers.support.mq.get_traces")
    patched_get_traces.return_value = [(test_zipinfo, "trace_data")]
    yield patched_get_traces
