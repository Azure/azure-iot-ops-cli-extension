# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import copy
import random
from os.path import abspath, expanduser, join
from typing import List, Optional, Union
from zipfile import ZipInfo
from unittest.mock import Mock

import pytest

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import (
    ARCCONTAINERSTORAGE_API_V1,
    CLUSTER_CONFIG_API_V1,
    DEVICEREGISTRY_API_V1,
    MQ_ACTIVE_API,
    MQTT_BROKER_API_V1,
    OPCUA_API_V1,
    DATAFLOW_API_V1,
    EdgeResourceApi,
)
from azext_edge.edge.providers.edge_api.meta import META_API_V1
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS, MONIKER
from azext_edge.edge.providers.support.arccontainerstorage import STORAGE_NAMESPACE
from azext_edge.edge.providers.support.base import get_bundle_path
from azext_edge.edge.providers.support.billing import (
    AIO_BILLING_USAGE_NAME_LABEL,
    ARC_BILLING_EXTENSION_COMP_LABEL,
    ARC_BILLING_DIRECTORY_PATH,
    BILLING_RESOURCE_KIND,
)
from azext_edge.edge.providers.support.meta import META_NAME_LABEL, META_PREFIX_NAMES
from azext_edge.edge.providers.support.mq import MQ_DIRECTORY_PATH, MQ_NAME_LABEL
from azext_edge.edge.providers.support.opcua import (
    OPC_APP_LABEL,
    OPC_DIRECTORY_PATH,
    OPC_NAME_LABEL,
    OPC_NAME_VAR_LABEL,
    OPCUA_NAME_LABEL,
)
from azext_edge.edge.providers.support.common import (
    COMPONENT_LABEL_FORMAT,
)
from azext_edge.edge.providers.support.schemaregistry import SCHEMAS_DIRECTORY_PATH, SCHEMAS_NAME_LABEL
from azext_edge.edge.providers.support_bundle import COMPAT_MQTT_BROKER_APIS
from azext_edge.tests.edge.support.conftest import add_pod_to_mocked_pods

from ...generators import generate_random_string

a_bundle_dir = f"support_test_{generate_random_string()}"
# @TODO: test refactor


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [MQTT_BROKER_API_V1],
        [MQTT_BROKER_API_V1, MQ_ACTIVE_API],
        [MQTT_BROKER_API_V1, OPCUA_API_V1],
        [MQTT_BROKER_API_V1, OPCUA_API_V1, DEVICEREGISTRY_API_V1],
        [MQTT_BROKER_API_V1, OPCUA_API_V1, CLUSTER_CONFIG_API_V1],
        [MQTT_BROKER_API_V1, OPCUA_API_V1, CLUSTER_CONFIG_API_V1, ARCCONTAINERSTORAGE_API_V1],
    ],
    indirect=True,
)
def test_create_bundle(
    mocked_client,
    mocked_cluster_resources,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_get_custom_objects,
    mocked_list_cron_jobs,
    mocked_list_jobs,
    mocked_list_deployments,
    mocked_list_persistent_volume_claims,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_daemonsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_mq_active_api,
    mocked_namespaced_custom_objects,
    mocked_get_config_map: Mock,
):
    if CLUSTER_CONFIG_API_V1 in mocked_cluster_resources["param"]:
        add_pod_to_mocked_pods(
            mocked_client=mocked_client,
            expected_pod_map=mocked_list_pods,
            mock_names=["aio-usage"],
            mock_init_containers=True,
        )

    since_seconds = random.randint(86400, 172800)
    result = support_bundle(None, bundle_dir=a_bundle_dir, log_age_seconds=since_seconds)

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    expected_resources: List[EdgeResourceApi] = mocked_cluster_resources["param"]

    for api in expected_resources:
        sub_group = BILLING_RESOURCE_KIND if api in [CLUSTER_CONFIG_API_V1] else ""

        for kind in api.kinds:
            target_file_prefix = None

            assert_get_custom_resources(
                mocked_get_custom_objects,
                mocked_zipfile,
                api,
                kind,
                file_prefix=target_file_prefix,
                sub_group=sub_group,
            )

        if api in [CLUSTER_CONFIG_API_V1]:
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=AIO_BILLING_USAGE_NAME_LABEL,
                directory_path=BILLING_RESOURCE_KIND,
                since_seconds=since_seconds,
                prefix_names=["aio-usage"],
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=ARC_BILLING_EXTENSION_COMP_LABEL,
                directory_path=ARC_BILLING_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_cron_jobs(
                mocked_client,
                mocked_zipfile,
                label_selector=AIO_BILLING_USAGE_NAME_LABEL,
                directory_path=BILLING_RESOURCE_KIND,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=ARC_BILLING_EXTENSION_COMP_LABEL,
                directory_path=ARC_BILLING_DIRECTORY_PATH,
            )
            assert_list_jobs(
                mocked_client,
                mocked_zipfile,
                label_selector=AIO_BILLING_USAGE_NAME_LABEL,
                directory_path=BILLING_RESOURCE_KIND,
                mock_names=["aio-usage-job"],
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=ARC_BILLING_EXTENSION_COMP_LABEL,
                directory_path=ARC_BILLING_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=ARC_BILLING_EXTENSION_COMP_LABEL,
                directory_path=ARC_BILLING_DIRECTORY_PATH,
            )

        if api in COMPAT_MQTT_BROKER_APIS.resource_apis:
            # Assert runtime resources
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=MQ_NAME_LABEL,
                directory_path=MQ_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_replica_sets(
                mocked_client, mocked_zipfile, label_selector=MQ_NAME_LABEL, directory_path=MQ_DIRECTORY_PATH
            )
            assert_list_stateful_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=MQ_NAME_LABEL,
                field_selector=None,
                directory_path=MQ_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=MQ_NAME_LABEL, directory_path=MQ_DIRECTORY_PATH
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=MQ_NAME_LABEL,
                directory_path=MQ_DIRECTORY_PATH,
            )

        if api in [OPCUA_API_V1]:
            # Assert runtime resources
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPC_APP_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
                since_seconds=since_seconds,
                include_metrics=True,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPC_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
                since_seconds=since_seconds,
                include_metrics=True,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPC_NAME_VAR_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
                since_seconds=since_seconds,
                include_metrics=True,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPCUA_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
                since_seconds=since_seconds,
                include_metrics=True,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=OPC_DIRECTORY_PATH,
                mock_names=[
                    "aio-opc-admission-controller",
                    "aio-opc-supervisor",
                    "aio-opc-opc",
                    "opcplc-0000000",
                ],
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=OPC_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=OPCUA_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=OPC_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=OPC_APP_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=OPCUA_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=OPC_DIRECTORY_PATH,
                mock_names=["opcplc-0000000"],
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=OPC_APP_LABEL, directory_path=OPC_DIRECTORY_PATH
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=OPCUA_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )
            # TODO: one-off field selector remove after label
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                field_selector="metadata.name==aio-opc-asset-discovery",
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=OPCUA_NAME_LABEL,
                directory_path=OPC_DIRECTORY_PATH,
            )

        if api in [DATAFLOW_API_V1]:
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=DATAFLOW_API_V1.label,
                directory_path=DATAFLOW_API_V1.moniker,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=DATAFLOW_API_V1.label,
                directory_path=DATAFLOW_API_V1.moniker,
                mock_names=["aio-dataflow-operator"],
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=DATAFLOW_API_V1.label,
                directory_path=DATAFLOW_API_V1.moniker,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=DATAFLOW_API_V1.label,
                directory_path=DATAFLOW_API_V1.moniker,
                since_seconds=since_seconds,
            )

        if api in [ARCCONTAINERSTORAGE_API_V1]:
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
                namespace=STORAGE_NAMESPACE,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
                namespace=STORAGE_NAMESPACE,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=None,
                directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
                since_seconds=since_seconds,
                namespace=STORAGE_NAMESPACE,
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
                namespace=STORAGE_NAMESPACE,
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
                namespace=STORAGE_NAMESPACE,
            )
            assert_list_persistent_volume_claims(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=ARCCONTAINERSTORAGE_API_V1.moniker,
                namespace=STORAGE_NAMESPACE,
            )
    # assert shared KPIs regardless of service
    assert_shared_kpis(mocked_client, mocked_zipfile)
    # assert meta KPIs
    assert_meta_kpis(mocked_client, mocked_zipfile, mocked_list_pods)
    # Using a divergent pattern for cluster config since its mock is at a higher level.
    mocked_get_config_map.assert_called_with(name="azure-clusterconfig", namespace="azure-arc")


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [],
        [MQ_ACTIVE_API],
    ],
    indirect=True,
)
def test_create_bundle_crd_work(
    mocked_client,
    mocked_cluster_resources,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_get_custom_objects,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_daemonsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_mq_active_api,
    mocked_namespaced_custom_objects,
    mocked_get_config_map: Mock,
    mocked_assemble_crd_work,
):
    support_bundle(None, ops_services=[OpsServiceType.mq.value], bundle_dir=a_bundle_dir)

    if mocked_cluster_resources["param"] == []:
        mocked_root_logger.warning.assert_called_with(
            "The following API(s) were not detected mqttbroker.iotoperations.azure.com/[v1]. "
            "CR capture for broker will be skipped. Still attempting capture of runtime resources..."
        )
        mocked_assemble_crd_work.assert_not_called()
    else:
        mocked_assemble_crd_work.assert_called_once()


def assert_get_custom_resources(
    mocked_get_custom_objects,
    mocked_zipfile,
    api: EdgeResourceApi,
    kind: str,
    file_prefix: str = None,
    sub_group: Optional[str] = None,
):
    mocked_get_custom_objects.assert_any_call(group=api.group, version=api.version, plural=f"{kind}s", use_cache=False)
    if not file_prefix:
        file_prefix = kind

    sub_group = f"{sub_group}/" if sub_group else ""

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{api.moniker}/{sub_group}{file_prefix}.{api.version}.mock_name.yaml",
        data=f"kind: {kind}\nmetadata:\n  name: mock_name\n  namespace: mock_namespace\n",
    )


def assert_list_cron_jobs(
    mocked_client,
    mocked_zipfile,
    label_selector: str,
    directory_path: str,
):
    mocked_client.BatchV1Api().list_cron_job_for_all_namespaces.assert_any_call(
        label_selector=label_selector, field_selector=None
    )

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{directory_path}/cronjob.mock_cron_job.yaml",
        data="kind: CronJob\nmetadata:\n  name: mock_cron_job\n  namespace: mock_namespace\n",
    )


def assert_list_deployments(
    mocked_client,
    mocked_zipfile,
    label_selector: str,
    directory_path: str,
    field_selector: str = None,
    mock_names: List[str] = None,
    namespace: Optional[str] = None,
):
    if MQ_DIRECTORY_PATH in directory_path:
        # regardless of MQ API, MQ_ACTIVE_API.moniker is used for support/broker/fetch_diagnostic_metrics
        from unittest.mock import call

        mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_has_calls(
            [
                # Specific for `aio-broker-operator` (no app label)
                call(label_selector=None, field_selector=field_selector),
                call(label_selector=MQ_NAME_LABEL, field_selector=None),
            ]
        )
    else:
        if namespace:
            mocked_client.AppsV1Api().list_namespaced_deployment.assert_any_call(
                namespace=namespace, label_selector=label_selector, field_selector=field_selector
            )
        else:
            mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_any_call(
                label_selector=label_selector, field_selector=field_selector
            )

    mock_names = mock_names or ["mock_deployment"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/deployment.{name}.yaml",
            data=f"kind: Deployment\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_jobs(
    mocked_client,
    mocked_zipfile,
    label_selector: str,
    directory_path: str,
    mock_names: Optional[List[str]] = None,
):
    mocked_client.BatchV1Api().list_job_for_all_namespaces.assert_any_call(
        label_selector=label_selector, field_selector=None
    )

    mock_names = mock_names or ["mock_job"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/job.{name}.yaml",
            data=f"kind: Job\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_pods(
    mocked_client,
    mocked_zipfile,
    mocked_list_pods,
    label_selector: str,
    directory_path: str,
    **kwargs,
):
    if "namespace" in kwargs:
        mocked_client.CoreV1Api().list_namespaced_pod.assert_any_call(
            namespace=kwargs["namespace"], label_selector=label_selector
        )
    else:
        mocked_client.CoreV1Api().list_pod_for_all_namespaces.assert_any_call(label_selector=label_selector)

    for namespace in mocked_list_pods:
        for pod_name in mocked_list_pods[namespace]:
            init_data = ""
            pods_with_container = copy.deepcopy(mocked_list_pods)

            # find if pod has init containers
            if "mock-init-container" in mocked_list_pods[namespace][pod_name]:
                init_data = "  initContainers:\n  - name: mock-init-container\n"
                # remove init container from pod, then do following container checks
                pods_with_container[namespace][pod_name].pop("mock-init-container")

            if "include_metrics" in kwargs and kwargs["include_metrics"]:
                mocked_client.CustomObjectsApi().get_namespaced_custom_object.assert_any_call(
                    group="metrics.k8s.io",
                    version="v1",
                    namespace=namespace,
                    plural="pods",
                    name=pod_name,
                )
                assert_zipfile_write(
                    mocked_zipfile,
                    zinfo=f"{namespace}/{directory_path}/pod.{pod_name}.metric.yaml",
                    data="apiVersion: metrics.k8s.io/v1\nkind: PodMetrics\nmetadata:\n  "
                    "creationTimestamp: '0000-00-00T00:00:00Z'\n  name: mock_custom_object\n  "
                    "namespace: namespace\ntimestamp: '0000-00-00T00:00:00Z'\n",
                )

            if pod_name not in kwargs.get("prefix_names", []):
                continue

            for container_name in pods_with_container[namespace][pod_name]:
                data = (
                    f"kind: Pod\nmetadata:\n  name: {pod_name}\n  namespace: {namespace}\nspec:\n  "
                    f"containers:\n  - name: {container_name}\n"
                )
                if pod_name == "evicted_pod":
                    status = "status:\n  phase: Failed\n  reason: Evicted\n"
                else:
                    status = "status:\n  phase: Running\n"

                data += f"{init_data}{status}"

                assert_zipfile_write(
                    mocked_zipfile,
                    zinfo=f"{namespace}/{directory_path}/pod.{pod_name}.yaml",
                    data=data,
                )

                if "since_seconds" in kwargs:
                    for previous_logs in [False, True]:
                        previous_segment = ".previous" if previous_logs else ""

                        try:
                            mocked_client.CoreV1Api().read_namespaced_pod_log.assert_any_call(
                                name=pod_name,
                                namespace=namespace,
                                since_seconds=kwargs["since_seconds"],
                                container=container_name,
                                previous=previous_logs,
                            )
                            assert_zipfile_write(
                                mocked_zipfile,
                                zinfo=f"{namespace}/{directory_path}/"
                                f"pod.{pod_name}.{container_name}{previous_segment}.log",
                                data=pods_with_container[namespace][pod_name][container_name],
                            )
                        except AssertionError:
                            # if pod is evicted, no logs are available
                            assert "evicted_pod" in pod_name


def assert_list_replica_sets(
    mocked_client,
    mocked_zipfile,
    label_selector: str,
    directory_path: str,
    mock_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
):
    if namespace:
        mocked_client.AppsV1Api().list_namespaced_replica_set.assert_any_call(
            namespace=namespace, label_selector=label_selector
        )
    else:
        mocked_client.AppsV1Api().list_replica_set_for_all_namespaces.assert_any_call(label_selector=label_selector)

    mock_names = mock_names or ["mock_replicaset"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/replicaset.{name}.yaml",
            data=f"kind: Replicaset\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_persistent_volume_claims(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: str = None,
    field_selector: str = None,
    mock_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
):
    if namespace:
        mocked_client.CoreV1Api().list_namespaced_persistent_volume_claim.assert_any_call(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        mocked_client.CoreV1Api().list_persistent_volume_claim_for_all_namespaces.assert_any_call(
            label_selector=label_selector, field_selector=field_selector
        )

    mock_names = mock_names or ["mock_pvc"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/pvc.{name}.yaml",
            data=f"kind: PersistentVolumeClaim\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_stateful_sets(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    mock_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
):
    if namespace:
        mocked_client.AppsV1Api().list_namespaced_stateful_set.assert_any_call(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(
            label_selector=label_selector, field_selector=field_selector
        )

    mock_names = mock_names or ["mock_statefulset"]

    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/statefulset.{name}.yaml",
            data=f"kind: Statefulset\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_services(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    mock_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
):

    if namespace:
        mocked_client.CoreV1Api().list_namespaced_service.assert_any_call(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        mocked_client.CoreV1Api().list_service_for_all_namespaces.assert_any_call(
            label_selector=label_selector, field_selector=field_selector
        )

    mock_names = mock_names or ["mock_service"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/service.{name}.yaml",
            data=f"kind: Service\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_config_maps(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    mock_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
):
    if namespace:
        mocked_client.CoreV1Api().list_namespaced_config_map.assert_any_call(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        mocked_client.CoreV1Api().list_config_map_for_all_namespaces.assert_any_call(
            label_selector=label_selector, field_selector=field_selector
        )

    mock_names = mock_names or ["mock_config_map"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/configmap.{name}.yaml",
            data=f"kind: ConfigMap\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_daemon_sets(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    mock_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
):
    if namespace:
        mocked_client.AppsV1Api().list_namespaced_daemon_set.assert_any_call(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        mocked_client.AppsV1Api().list_daemon_set_for_all_namespaces.assert_any_call(
            label_selector=label_selector, field_selector=field_selector
        )

    mock_names = mock_names or ["mock_daemonset"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{directory_path}/daemonset.{name}.yaml",
            data=f"kind: Daemonset\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_meta_kpis(mocked_client, mocked_zipfile, mocked_list_pods):
    for assert_func in [assert_list_pods, assert_list_deployments, assert_list_services, assert_list_jobs]:
        kwargs = {
            "mocked_client": mocked_client,
            "mocked_zipfile": mocked_zipfile,
            "label_selector": META_NAME_LABEL,
            "directory_path": META_API_V1.moniker,
        }
        if assert_func == assert_list_pods:
            kwargs["mocked_list_pods"] = mocked_list_pods
        elif assert_func == assert_list_services:
            kwargs["mock_names"] = [META_PREFIX_NAMES]

        assert_func(**kwargs)


def assert_shared_kpis(mocked_client, mocked_zipfile):
    mocked_client.CoreV1Api().list_node.assert_called_once()
    assert_zipfile_write(mocked_zipfile, zinfo="nodes.yaml", data="items:\n- metadata:\n    name: mock_node\n")
    mocked_client.CoreV1Api().list_event_for_all_namespaces.assert_called_once()
    assert_zipfile_write(
        mocked_zipfile,
        zinfo="events.yaml",
        data="items:\n- action: mock_action\n  involvedObject: mock_object\n  metadata:\n    name: mock_event\n",
    )
    mocked_client.StorageV1Api().list_storage_class.assert_called_once()
    assert_zipfile_write(
        mocked_zipfile,
        zinfo="storage-classes.yaml",
        data="items:\n- metadata:\n    name: mock_storage_class\n  provisioner: mock_provisioner\n",
    )
    assert_zipfile_write(
        mocked_zipfile,
        zinfo="azure-clusterconfig.yaml",
        data="configkey: configvalue\n",
    )


# TODO: base test class?
def assert_zipfile_write(mocked_zipfile, zinfo: Union[str, ZipInfo], data: str):
    # pylint: disable=unnecessary-dunder-call
    if isinstance(zinfo, str):
        mocked_zipfile(file="").__enter__().writestr.assert_any_call(
            zinfo_or_arcname=zinfo,
            data=data,
        )
        return

    called_with_expected_zipinfo = False
    for call in mocked_zipfile(file="").__enter__().writestr.mock_calls:
        call_kwargs = call.kwargs
        if isinstance(call_kwargs["zinfo_or_arcname"], ZipInfo):
            called_with: ZipInfo = call_kwargs["zinfo_or_arcname"]
            if zinfo.filename == called_with.filename and zinfo.date_time == called_with.date_time:
                called_with_expected_zipinfo = True

    # pylint: enable=unnecessary-dunder-call
    assert called_with_expected_zipinfo


def test_get_bundle_path(mocked_os_makedirs):
    path = get_bundle_path("~/test")
    expected = f"{join(expanduser('~'), 'test', 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_aio.zip")

    path = get_bundle_path("./test/")
    expected = f"{join(abspath('.'), 'test', 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_aio.zip")

    path = get_bundle_path("test/thing")
    expected = f"{join(abspath('test/thing'), 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_aio.zip")

    path = get_bundle_path()
    expected = f"{join(abspath('.'), 'support_bundle_')}"
    assert str(path).startswith(expected) and str(path).endswith("_aio.zip")


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [MQTT_BROKER_API_V1],
    ],
    indirect=True,
)
def test_create_bundle_mq_traces(
    mocked_client,
    mocked_cluster_resources,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_get_custom_objects,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_daemonsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_mq_active_api,
    mocked_mq_get_traces,
    mocked_get_config_map,
):
    result = support_bundle(
        None, ops_services=[OpsServiceType.mq.value], bundle_dir=a_bundle_dir, include_mq_traces=True
    )

    assert result["bundlePath"]
    mocked_mq_get_traces.assert_called_once()
    get_trace_kwargs = mocked_mq_get_traces.call_args.kwargs

    assert get_trace_kwargs["namespace"] == "mock_namespace"  # TODO: Not my favorite
    assert get_trace_kwargs["trace_ids"] == ["!support_bundle!"]  # TODO: Magic string
    test_zipinfo = ZipInfo("mock_namespace/broker/traces/trace_key")
    test_zipinfo.file_size = 0
    test_zipinfo.compress_size = 0
    assert_zipfile_write(mocked_zipfile, zinfo=test_zipinfo, data="trace_data")


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [DEVICEREGISTRY_API_V1],
    ],
    indirect=True,
)
def test_create_bundle_arc_agents(
    mocked_client,
    mocked_cluster_resources,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_get_custom_objects,
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_get_arc_services,
    mocked_get_config_map,
):
    since_seconds = random.randint(86400, 172800)
    result = support_bundle(
        None,
        ops_services=[OpsServiceType.deviceregistry.value],
        bundle_dir=a_bundle_dir,
        log_age_seconds=since_seconds,
    )

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    for component, has_service in ARC_AGENTS:
        assert_list_pods(
            mocked_client,
            mocked_zipfile,
            mocked_list_pods,
            label_selector=COMPONENT_LABEL_FORMAT.format(label=component),
            directory_path=f"{MONIKER}/{component}",
            since_seconds=since_seconds,
        )
        assert_list_replica_sets(
            mocked_client,
            mocked_zipfile,
            label_selector=COMPONENT_LABEL_FORMAT.format(label=component),
            directory_path=f"{MONIKER}/{component}",
        )
        assert_list_deployments(
            mocked_client,
            mocked_zipfile,
            label_selector=COMPONENT_LABEL_FORMAT.format(label=component),
            directory_path=f"{MONIKER}/{component}",
        )
        if has_service:
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                directory_path=f"{MONIKER}/{component}",
                mock_names=[f"{component}"],
            )


def test_create_bundle_schemas(
    mocked_client,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_pods,
    mocked_list_config_maps,
    mocked_list_statefulsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_list_persistent_volume_claims,
    mocked_root_logger,
    mocked_get_config_map,
):
    since_seconds = random.randint(86400, 172800)
    result = support_bundle(
        None,
        ops_services=[OpsServiceType.schemaregistry.value],
        bundle_dir=a_bundle_dir,
        log_age_seconds=since_seconds,
    )

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    assert_list_pods(
        mocked_client,
        mocked_zipfile,
        mocked_list_pods,
        label_selector=SCHEMAS_NAME_LABEL,
        directory_path=SCHEMAS_DIRECTORY_PATH,
        since_seconds=since_seconds,
    )
    assert_list_config_maps(
        mocked_client,
        mocked_zipfile,
        label_selector=SCHEMAS_NAME_LABEL,
        directory_path=SCHEMAS_DIRECTORY_PATH,
    )
    assert_list_stateful_sets(
        mocked_client,
        mocked_zipfile,
        label_selector=SCHEMAS_NAME_LABEL,
        directory_path=SCHEMAS_DIRECTORY_PATH,
    )
    assert_list_services(
        mocked_client,
        mocked_zipfile,
        label_selector=SCHEMAS_NAME_LABEL,
        directory_path=SCHEMAS_DIRECTORY_PATH,
    )
    assert_list_persistent_volume_claims(
        mocked_client,
        mocked_zipfile,
        directory_path=SCHEMAS_DIRECTORY_PATH,
        label_selector=SCHEMAS_NAME_LABEL,
    )
