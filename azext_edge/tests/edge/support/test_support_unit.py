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

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import AIO_MQ_RESOURCE_PREFIX
from azext_edge.edge.providers.edge_api import (
    AKRI_API_V0,
    CLUSTER_CONFIG_API_V1,
    DATA_PROCESSOR_API_V1,
    DEVICEREGISTRY_API_V1,
    MQ_ACTIVE_API,
    MQTT_BROKER_API_V1B1,
    OPCUA_API_V1,
    ORC_API_V1,
    EdgeResourceApi,
)
from azext_edge.edge.providers.support.akri import (
    AKRI_AGENT_LABEL,
    AKRI_APP_LABEL,
    AKRI_DIRECTORY_PATH,
    AKRI_INSTANCE_LABEL,
    AKRI_NAME_LABEL_V2,
    AKRI_SERVICE_LABEL,
    AKRI_WEBHOOK_LABEL,
)
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS, ARC_AGENTS_SERVICE_LABEL, MONIKER
from azext_edge.edge.providers.support.base import get_bundle_path
from azext_edge.edge.providers.support.billing import (
    AIO_BILLING_USAGE_NAME_LABEL,
    ARC_BILLING_EXTENSION_COMP_LABEL,
    ARC_BILLING_DIRECTORY_PATH,
    BILLING_RESOURCE_KIND,
)
from azext_edge.edge.providers.support.dataprocessor import (
    DATA_PROCESSOR_DIRECTORY_PATH,
    DATA_PROCESSOR_INSTANCE_LABEL,
    DATA_PROCESSOR_LABEL,
    DATA_PROCESSOR_NAME_LABEL,
    DATA_PROCESSOR_NAME_LABEL_V2,
    DATA_PROCESSOR_ONEOFF_LABEL,
    DATA_PROCESSOR_PVC_APP_LABEL,
)
from azext_edge.edge.providers.support.mq import MQ_DIRECTORY_PATH, MQ_LABEL, MQ_NAME_LABEL
from azext_edge.edge.providers.support.opcua import (
    OPC_APP_LABEL,
    OPC_DIRECTORY_PATH,
    OPC_NAME_LABEL,
    OPC_NAME_VAR_LABEL,
    OPCUA_NAME_LABEL,
)
from azext_edge.edge.providers.support.orc import (
    ORC_DIRECTORY_PATH,
    ORC_APP_LABEL,
    ORC_CONTROLLER_LABEL,
)
from azext_edge.edge.providers.support.otel import OTEL_API, OTEL_NAME_LABEL
from azext_edge.edge.providers.support.shared import COMPONENT_LABEL_FORMAT, NAME_LABEL_FORMAT
from azext_edge.edge.providers.support_bundle import COMPAT_MQTT_BROKER_APIS

from ...generators import generate_random_string
from .conftest import add_pod_to_mocked_pods

a_bundle_dir = f"support_test_{generate_random_string()}"


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [],
        [MQTT_BROKER_API_V1B1],
        [MQTT_BROKER_API_V1B1, MQ_ACTIVE_API],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1],
        [MQTT_BROKER_API_V1B1, DATA_PROCESSOR_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DEVICEREGISTRY_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1, AKRI_API_V0],
        # TODO: re-enable billing once service is available post 0.6.0 release
        # [MQ_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1, CLUSTER_CONFIG_API_V1],
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
    mocked_get_stats,
    mocked_root_logger,
    mocked_mq_active_api,
    mocked_namespaced_custom_objects,
):
    # TODO: clean up label once all service labels become stable
    asset_raises_not_found_error(mocked_cluster_resources)

    if mocked_cluster_resources["param"] == []:
        auto_result_no_resources = support_bundle(None, bundle_dir=a_bundle_dir)
        mocked_root_logger.warning.assert_called_once_with("No known IoT Operations services discovered on cluster.")
        assert auto_result_no_resources is None
        return

    if DATA_PROCESSOR_API_V1 in mocked_cluster_resources["param"]:
        add_pod_to_mocked_pods(
            mocked_client=mocked_client,
            expected_pod_map=mocked_list_pods,
            mock_names=["aio-runner"],
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
                label_selector=ARC_BILLING_EXTENSION_COMP_LABEL,
                directory_path=ARC_BILLING_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_cron_jobs(
                mocked_client,
                mocked_zipfile,
                label_selector=AIO_BILLING_USAGE_NAME_LABEL,
                directory_path=ARC_BILLING_DIRECTORY_PATH,
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
                directory_path=ARC_BILLING_DIRECTORY_PATH,
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
                label_selector=MQ_LABEL,
                directory_path=MQ_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=MQ_NAME_LABEL,
                directory_path=MQ_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=MQ_LABEL,
                directory_path=MQ_DIRECTORY_PATH
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
                mocked_client,
                mocked_zipfile,
                label_selector=MQ_LABEL,
                directory_path=MQ_DIRECTORY_PATH
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=MQ_NAME_LABEL,
                directory_path=MQ_DIRECTORY_PATH
            )
            assert_mq_stats(mocked_zipfile)

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
                mock_names=["aio-opc-admission-controller", "aio-opc-supervisor", "aio-opc-opc", "opcplc-0000000"],
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
                mocked_client, mocked_zipfile, label_selector=OPCUA_NAME_LABEL, directory_path=OPC_DIRECTORY_PATH
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

        if api in [DATA_PROCESSOR_API_V1]:

            # Assert runtime resources
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )

            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=DATA_PROCESSOR_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
                since_seconds=since_seconds,
                pod_prefix_for_init_container_logs=["aio-"],
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
                since_seconds=since_seconds,
                pod_prefix_for_init_container_logs=["aio-"],
            )

            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )

            assert_list_stateful_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_stateful_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )

            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )

            assert_list_persistent_volume_claims(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_INSTANCE_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_persistent_volume_claims(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_PVC_APP_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_persistent_volume_claims(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_persistent_volume_claims(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_ONEOFF_LABEL,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )
            assert_list_persistent_volume_claims(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
                directory_path=DATA_PROCESSOR_DIRECTORY_PATH,
            )

        if api in [ORC_API_V1]:
            for orc_label in [ORC_APP_LABEL, ORC_CONTROLLER_LABEL]:
                assert_list_pods(
                    mocked_client,
                    mocked_zipfile,
                    mocked_list_pods,
                    label_selector=orc_label,
                    directory_path=ORC_DIRECTORY_PATH,
                    since_seconds=since_seconds,
                )
                assert_list_deployments(
                    mocked_client, mocked_zipfile, label_selector=orc_label, directory_path=ORC_DIRECTORY_PATH
                )
                assert_list_replica_sets(
                    mocked_client, mocked_zipfile, label_selector=orc_label, directory_path=ORC_DIRECTORY_PATH
                )
                assert_list_services(
                    mocked_client,
                    mocked_zipfile,
                    label_selector=orc_label,
                    directory_path=ORC_DIRECTORY_PATH
                )

        if api in [AKRI_API_V0]:
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=AKRI_INSTANCE_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=AKRI_APP_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=NAME_LABEL_FORMAT.format(label=f"{AKRI_AGENT_LABEL}, {AKRI_WEBHOOK_LABEL}"),
                directory_path=AKRI_DIRECTORY_PATH,
                since_seconds=since_seconds,
            )
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
                label_selector=AKRI_INSTANCE_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_APP_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
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
                label_selector=AKRI_INSTANCE_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_APP_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=NAME_LABEL_FORMAT.format(label=AKRI_WEBHOOK_LABEL),
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_NAME_LABEL_V2,
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=AKRI_SERVICE_LABEL, directory_path=AKRI_DIRECTORY_PATH
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=AKRI_INSTANCE_LABEL, directory_path=AKRI_DIRECTORY_PATH
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=NAME_LABEL_FORMAT.format(label=AKRI_WEBHOOK_LABEL),
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=AKRI_NAME_LABEL_V2, directory_path=AKRI_DIRECTORY_PATH
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_INSTANCE_LABEL,
                directory_path=AKRI_DIRECTORY_PATH,
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=NAME_LABEL_FORMAT.format(label=AKRI_AGENT_LABEL),
                directory_path=OPC_DIRECTORY_PATH,
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_NAME_LABEL_V2,
                directory_path=AKRI_DIRECTORY_PATH,
            )

    if expected_resources:
        assert_otel_kpis(mocked_client, mocked_zipfile, mocked_list_pods)

    # assert shared KPIs regardless of service
    assert_shared_kpis(mocked_client, mocked_zipfile)


def asset_raises_not_found_error(mocked_cluster_resources):
    for api, moniker in [
        (MQTT_BROKER_API_V1B1, "broker"),
        (OPCUA_API_V1, "opcua"),
        (DATA_PROCESSOR_API_V1, "dataprocessor"),
        (ORC_API_V1, "orc"),
        (DEVICEREGISTRY_API_V1, "deviceregistry"),
        (AKRI_API_V0, "akri"),
    ]:
        if not mocked_cluster_resources["param"] or api not in mocked_cluster_resources["param"]:
            with pytest.raises(ResourceNotFoundError):
                support_bundle(None, bundle_dir=a_bundle_dir, ops_service=moniker)


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
):
    if MQ_DIRECTORY_PATH in directory_path:
        # regardless of MQ API, MQ_ACTIVE_API.moniker is used for support/broker/fetch_diagnostic_metrics
        from unittest.mock import call

        mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_has_calls(
            [
                # MQ deployments
                call(label_selector=MQ_LABEL, field_selector=None),
                # Specific for `aio-mq-operator` (no app label)
                call(label_selector=None, field_selector=field_selector),
                call(label_selector=MQ_NAME_LABEL, field_selector=None),
            ]
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
):
    mocked_client.BatchV1Api().list_job_for_all_namespaces.assert_any_call(
        label_selector=label_selector, field_selector=None
    )

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{directory_path}/job.mock_job.yaml",
        data="kind: Job\nmetadata:\n  name: mock_job\n  namespace: mock_namespace\n",
    )


def assert_list_pods(
    mocked_client,
    mocked_zipfile,
    mocked_list_pods,
    label_selector: str,
    directory_path: str,
    **kwargs,
):
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
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                    name=pod_name,
                )
                assert_zipfile_write(
                    mocked_zipfile,
                    zinfo=f"{namespace}/{directory_path}/pod.{pod_name}.metric.yaml",
                    data="apiVersion: metrics.k8s.io/v1beta1\nkind: PodMetrics\nmetadata:\n  "
                    "creationTimestamp: '0000-00-00T00:00:00Z'\n  name: mock_custom_object\n  "
                    "namespace: namespace\ntimestamp: '0000-00-00T00:00:00Z'\n",
                )

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
):
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
):
    mocked_client.CoreV1Api().list_persistent_volume_claim_for_all_namespaces.assert_any_call(
        label_selector=label_selector, field_selector=field_selector
    )

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{directory_path}/pvc.mock_pvc.yaml",
        data="kind: PersistentVolumeClaim\nmetadata:\n  name: mock_pvc\n  namespace: mock_namespace\n",
    )


def assert_list_stateful_sets(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
):
    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(
        label_selector=label_selector, field_selector=field_selector
    )

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{directory_path}/statefulset.mock_statefulset.yaml",
        data="kind: Statefulset\nmetadata:\n  name: mock_statefulset\n  namespace: mock_namespace\n",
    )


def assert_list_services(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    mock_names: Optional[List[str]] = None,
):
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


def assert_list_daemon_sets(
    mocked_client,
    mocked_zipfile,
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    mock_names: Optional[List[str]] = None,
):
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


def assert_mq_stats(mocked_zipfile):
    assert_zipfile_write(mocked_zipfile, zinfo="mock_namespace/broker/diagnostic_metrics.txt", data="metrics")


def assert_otel_kpis(
    mocked_client,
    mocked_zipfile,
    mocked_list_pods,
):
    for assert_func in [assert_list_pods, assert_list_deployments, assert_list_services, assert_list_replica_sets]:
        kwargs = {
            "mocked_client": mocked_client,
            "mocked_zipfile": mocked_zipfile,
            "label_selector": OTEL_NAME_LABEL,
            "directory_path": OTEL_API.moniker,
        }
        if assert_func == assert_list_pods:
            kwargs["mocked_list_pods"] = mocked_list_pods

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
        zinfo="storage_classes.yaml",
        data="items:\n- metadata:\n    name: mock_storage_class\n  provisioner: mock_provisioner\n",
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


# TODO - test zipfile write for specific resources
# MQ connector stateful sets need labels based on connector names
@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [[MQTT_BROKER_API_V1B1]],
    indirect=True,
)
@pytest.mark.parametrize(
    "custom_objects",
    [
        # connectors present
        {
            "items": [
                {
                    "metadata": {"name": "mock-connector", "namespace": "mock-namespace"},
                },
                {
                    "metadata": {"name": "mock-connector2", "namespace": "mock-namespace2"},
                },
            ]
        },
        # no connectors
        {"items": []},
    ],
)
def test_mq_list_stateful_sets(
    mocker,
    mocked_config,
    mocked_client,
    mocked_cluster_resources,
    custom_objects,
    mocked_zipfile,
    mocked_os_makedirs,
):

    # mock MQ support bundle to return connectors
    mocked_mq_support_active_api = mocker.patch("azext_edge.edge.providers.support.mq.MQ_ACTIVE_API")
    mocked_mq_support_active_api.get_resources.return_value = custom_objects
    result = support_bundle(None, bundle_dir=a_bundle_dir, ops_service="broker")
    assert result

    # assert initial call to list stateful sets
    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(
        label_selector=MQ_NAME_LABEL, field_selector=None
    )

    # TODO - assert zipfile write of generic statefulset
    if not custom_objects["items"]:
        # TODO - will revert to initial call once the old label is removed
        # mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_called_once()
        mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_called()

    # assert secondary connector calls to list stateful sets
    for item in custom_objects["items"]:
        item_name = item["metadata"]["name"]
        statefulset_name = f"{AIO_MQ_RESOURCE_PREFIX}{item_name}"
        selector = f"metadata.name={statefulset_name}"
        mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(
            label_selector=None, field_selector=selector
        )
        # TODO - assert zipfile write of individual connector statefulset


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [MQTT_BROKER_API_V1B1],
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
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_daemonsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_get_stats,
    mocked_list_storage_classes,
    mocked_root_logger,
    mocked_mq_active_api,
    mocked_mq_get_traces,
):
    result = support_bundle(None, bundle_dir=a_bundle_dir, include_mq_traces=True)

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
        [],
        [MQTT_BROKER_API_V1B1],
        [MQTT_BROKER_API_V1B1, MQ_ACTIVE_API],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1],
        [MQTT_BROKER_API_V1B1, DATA_PROCESSOR_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DEVICEREGISTRY_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1, AKRI_API_V0],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1],
        [MQTT_BROKER_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1, CLUSTER_CONFIG_API_V1],
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
    mocked_list_cron_jobs,
    mocked_list_jobs,
    mocked_list_deployments,
    mocked_list_persistent_volume_claims,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_daemonsets,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_list_storage_classes,
    mocked_get_stats,
    mocked_root_logger,
    mocked_mq_active_api,
    mocked_namespaced_custom_objects,
    mocked_get_arc_services
):
    since_seconds = random.randint(86400, 172800)
    result = support_bundle(None, bundle_dir=a_bundle_dir, include_arc_agents=True, log_age_seconds=since_seconds)

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    for component, has_service in ARC_AGENTS:
        assert_list_pods(
            mocked_client,
            mocked_zipfile,
            mocked_list_pods,
            label_selector=COMPONENT_LABEL_FORMAT.format(label=component),
            directory_path=f"{MONIKER}/{component}",
            since_seconds=since_seconds
        )
        assert_list_replica_sets(
            mocked_client,
            mocked_zipfile,
            label_selector=COMPONENT_LABEL_FORMAT.format(label=component),
            directory_path=f"{MONIKER}/{component}"
        )
        assert_list_deployments(
            mocked_client,
            mocked_zipfile,
            label_selector=COMPONENT_LABEL_FORMAT.format(label=component),
            directory_path=f"{MONIKER}/{component}"
        )
        if has_service:
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=ARC_AGENTS_SERVICE_LABEL,
                directory_path=f"{MONIKER}/{component}",
                mock_names=[f"{component}"]
            )
