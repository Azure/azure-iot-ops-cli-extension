# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random
from os.path import abspath, expanduser, join
from typing import List, Optional, Union
from zipfile import ZipInfo

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.common import AIO_MQ_OPERATOR, AIO_MQ_RESOURCE_PREFIX
from azext_edge.edge.providers.edge_api import (
    AKRI_API_V0,
    DATA_PROCESSOR_API_V1,
    DEVICEREGISTRY_API_V1,
    LNM_API_V1B1,
    MQ_ACTIVE_API,
    MQ_API_V1B1,
    OPCUA_API_V1,
    ORC_API_V1,
    EdgeResourceApi,
)
from azext_edge.edge.providers.support.akri import (
    AKRI_APP_LABEL,
    AKRI_INSTANCE_LABEL,
    AKRI_SERVICE_LABEL,
)
from azext_edge.edge.providers.support.base import get_bundle_path
from azext_edge.edge.providers.support.dataprocessor import (
    DATA_PROCESSOR_LABEL,
    DATA_PROCESSOR_NAME_LABEL,
)
from azext_edge.edge.providers.support.lnm import LNM_APP_LABELS
from azext_edge.edge.providers.support.mq import MQ_LABEL
from azext_edge.edge.providers.support.opcua import (
    OPC_APP_LABEL,
    OPC_NAME_LABEL,
)
from azext_edge.edge.providers.support.orc import (
    ORC_APP_LABEL,
    ORC_CONTROLLER_LABEL,
    ORC_INSTANCE_LABEL,
)
from azext_edge.edge.providers.support.otel import OTEL_API, OTEL_NAME_LABEL
from azext_edge.edge.providers.support_bundle import COMPAT_MQ_APIS

from ...generators import generate_generic_id

a_bundle_dir = f"support_test_{generate_generic_id()}"


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [],
        [MQ_API_V1B1],
        [MQ_API_V1B1, MQ_ACTIVE_API],
        [MQ_API_V1B1, OPCUA_API_V1],
        [MQ_API_V1B1, DATA_PROCESSOR_API_V1],
        [MQ_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1],
        [MQ_API_V1B1, OPCUA_API_V1, DEVICEREGISTRY_API_V1],
        [MQ_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1],
        [MQ_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1, AKRI_API_V0],
        [MQ_API_V1B1, OPCUA_API_V1, DATA_PROCESSOR_API_V1, ORC_API_V1, LNM_API_V1B1],
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
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_daemonsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_list_cluster_events,
    mocked_get_stats,
    mocked_root_logger,
    mocked_mq_active_api,
):
    asset_raises_not_found_error(mocked_cluster_resources)

    if mocked_cluster_resources["param"] == []:
        auto_result_no_resources = support_bundle(None, bundle_dir=a_bundle_dir)
        mocked_root_logger.warning.assert_called_once_with("No known IoT Operations services discovered on cluster.")
        assert auto_result_no_resources is None
        return

    since_seconds = random.randint(86400, 172800)
    result = support_bundle(None, bundle_dir=a_bundle_dir, log_age_seconds=since_seconds)

    assert "bundlePath" in result
    assert a_bundle_dir in result["bundlePath"]

    expected_resources: List[EdgeResourceApi] = mocked_cluster_resources["param"]

    for api in expected_resources:
        for kind in api.kinds:
            target_file_prefix = None

            assert_get_custom_resources(
                mocked_get_custom_objects, mocked_zipfile, api, kind, file_prefix=target_file_prefix
            )

        if api in COMPAT_MQ_APIS.resource_apis:
            # Assert runtime resources
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=MQ_LABEL,
                resource_api=MQ_API_V1B1,
                field_selector=f"metadata.name={AIO_MQ_OPERATOR}",
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=MQ_LABEL,
                resource_api=MQ_API_V1B1,
                since_seconds=since_seconds,
            )
            assert_list_replica_sets(mocked_client, mocked_zipfile, label_selector=MQ_LABEL, resource_api=MQ_API_V1B1)
            assert_list_stateful_sets(
                mocked_client, mocked_zipfile, label_selector=MQ_LABEL, field_selector=None, resource_api=MQ_API_V1B1
            )
            assert_list_services(mocked_client, mocked_zipfile, label_selector=MQ_LABEL, resource_api=MQ_API_V1B1)
            assert_mq_stats(mocked_zipfile)

        if api in [OPCUA_API_V1]:
            # Assert runtime resources
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPC_APP_LABEL,
                resource_api=OPCUA_API_V1,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPC_NAME_LABEL,
                resource_api=OPCUA_API_V1,
                since_seconds=since_seconds,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                resource_api=OPCUA_API_V1,
                mock_names=["aio-opc-admission-controller", "aio-opc-supervisor", "aio-opc-opc", "opcplc-0000000"],
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=OPC_NAME_LABEL,
                resource_api=OPCUA_API_V1,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=OPC_APP_LABEL,
                resource_api=OPCUA_API_V1,
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                resource_api=OPCUA_API_V1,
                mock_names=["opcplc-0000000"],
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=OPC_APP_LABEL, resource_api=OPCUA_API_V1
            )
            # TODO: one-off field selector remove after label
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                field_selector="metadata.name==aio-opc-asset-discovery",
                resource_api=OPCUA_API_V1,
            )

        if api in [DATA_PROCESSOR_API_V1]:
            # Assert runtime resources
            assert_list_deployments(
                mocked_client, mocked_zipfile, label_selector=DATA_PROCESSOR_LABEL, resource_api=DATA_PROCESSOR_API_V1
            )

            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=DATA_PROCESSOR_LABEL,
                resource_api=DATA_PROCESSOR_API_V1,
                since_seconds=since_seconds,
            )

            assert_list_replica_sets(
                mocked_client, mocked_zipfile, label_selector=DATA_PROCESSOR_LABEL, resource_api=DATA_PROCESSOR_API_V1
            )

            assert_list_stateful_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_LABEL,
                resource_api=DATA_PROCESSOR_API_V1,
            )

            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=DATA_PROCESSOR_LABEL, resource_api=DATA_PROCESSOR_API_V1
            )
            assert_list_services(
                mocked_client,
                mocked_zipfile,
                label_selector=DATA_PROCESSOR_NAME_LABEL,
                resource_api=DATA_PROCESSOR_API_V1,
            )

        if api in [ORC_API_V1]:
            for orc_label in [ORC_APP_LABEL, ORC_INSTANCE_LABEL, ORC_CONTROLLER_LABEL]:
                assert_list_pods(
                    mocked_client,
                    mocked_zipfile,
                    mocked_list_pods,
                    label_selector=orc_label,
                    resource_api=ORC_API_V1,
                    since_seconds=since_seconds,
                )
                assert_list_deployments(
                    mocked_client, mocked_zipfile, label_selector=orc_label, resource_api=ORC_API_V1
                )
                assert_list_replica_sets(
                    mocked_client, mocked_zipfile, label_selector=orc_label, resource_api=ORC_API_V1
                )
                assert_list_services(mocked_client, mocked_zipfile, label_selector=orc_label, resource_api=ORC_API_V1)

        if api in [AKRI_API_V0]:
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=AKRI_INSTANCE_LABEL,
                resource_api=AKRI_API_V0,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=AKRI_APP_LABEL,
                resource_api=AKRI_API_V0,
                since_seconds=since_seconds,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_INSTANCE_LABEL,
                resource_api=AKRI_API_V0,
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_APP_LABEL,
                resource_api=AKRI_API_V0,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_INSTANCE_LABEL,
                resource_api=AKRI_API_V0,
            )
            assert_list_replica_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_APP_LABEL,
                resource_api=AKRI_API_V0,
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=AKRI_SERVICE_LABEL, resource_api=AKRI_API_V0
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=AKRI_INSTANCE_LABEL, resource_api=AKRI_API_V0
            )
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=AKRI_INSTANCE_LABEL,
                resource_api=AKRI_API_V0,
            )

        if api in [LNM_API_V1B1]:
            lnm_app_label = f"app in ({','.join(LNM_APP_LABELS)})"
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=lnm_app_label,
                resource_api=LNM_API_V1B1,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=None,
                resource_api=LNM_API_V1B1,
                since_seconds=since_seconds,
                mock_names=["svclb-aio-lnm-operator"],
            )
            assert_list_deployments(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                resource_api=LNM_API_V1B1,
                mock_names=["aio-lnm-operator"],
            )
            assert_list_replica_sets(
                mocked_client, mocked_zipfile, label_selector=lnm_app_label, resource_api=LNM_API_V1B1
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=lnm_app_label, resource_api=LNM_API_V1B1
            )
            # TODO: test both without or with lnm instance
            assert_list_daemon_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=None,
                resource_api=LNM_API_V1B1,
                mock_names=["svclb-aio-lnm-operator"],
            )

    if expected_resources:
        assert_otel_kpis(mocked_client, mocked_zipfile, mocked_list_pods)

    # assert shared KPIs regardless of service
    assert_shared_kpis(mocked_client, mocked_zipfile)


def asset_raises_not_found_error(mocked_cluster_resources):
    for api, moniker in [
        (MQ_API_V1B1, "mq"),
        (OPCUA_API_V1, "opcua"),
        (DATA_PROCESSOR_API_V1, "dataprocessor"),
        (ORC_API_V1, "orc"),
        (LNM_API_V1B1, "lnm"),
        (DEVICEREGISTRY_API_V1, "deviceregistry"),
        (AKRI_API_V0, "akri"),
    ]:
        if not mocked_cluster_resources["param"] or api not in mocked_cluster_resources["param"]:
            with pytest.raises(ResourceNotFoundError):
                support_bundle(None, bundle_dir=a_bundle_dir, ops_service=moniker)


def assert_get_custom_resources(
    mocked_get_custom_objects, mocked_zipfile, api: EdgeResourceApi, kind: str, file_prefix: str = None
):
    mocked_get_custom_objects.assert_any_call(group=api.group, version=api.version, plural=f"{kind}s", use_cache=False)
    if not file_prefix:
        file_prefix = kind

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{api.moniker}/{file_prefix}.{api.version}.mock_name.yaml",
        data=f"kind: {kind}\nmetadata:\n  name: mock_name\n  namespace: mock_namespace\n",
    )


def assert_list_deployments(
    mocked_client,
    mocked_zipfile,
    label_selector: str,
    resource_api: EdgeResourceApi,
    field_selector: str = None,
    mock_names: List[str] = None,
):
    moniker = resource_api.moniker
    if resource_api in COMPAT_MQ_APIS.resource_apis:
        # regardless of MQ API, MQ_ACTIVE_API.moniker is used for support/mq/fetch_diagnostic_metrics
        moniker = MQ_ACTIVE_API.moniker
        from unittest.mock import call

        mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_has_calls(
            [
                # MQ deployments
                call(label_selector=MQ_LABEL, field_selector=None),
                # Specific for `aio-mq-operator` (no app label)
                call(label_selector=None, field_selector=field_selector),
            ]
        )
    else:
        mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_any_call(
            label_selector=label_selector, field_selector=field_selector
        )

    # @jiacju - no label for lnm
    mock_names = mock_names or ["mock_deployment"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{moniker}/deployment.{name}.yaml",
            data=f"kind: Deployment\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_pods(
    mocked_client,
    mocked_zipfile,
    mocked_list_pods,
    label_selector: str,
    resource_api: EdgeResourceApi,
    **kwargs,
):
    mocked_client.CoreV1Api().list_pod_for_all_namespaces.assert_any_call(label_selector=label_selector)

    for namespace in mocked_list_pods:
        for pod_name in mocked_list_pods[namespace]:
            for container_name in mocked_list_pods[namespace][pod_name]:
                assert_zipfile_write(
                    mocked_zipfile,
                    zinfo=f"{namespace}/{resource_api.moniker}/pod.{pod_name}.yaml",
                    data=f"kind: Pod\nmetadata:\n  name: {pod_name}\n  "
                    f"namespace: {namespace}\nspec:\n  containers:\n  - name: {container_name}\n",
                )

                if "since_seconds" in kwargs:
                    for previous_logs in [False, True]:
                        mocked_client.CoreV1Api().read_namespaced_pod_log.assert_any_call(
                            name=pod_name,
                            namespace=namespace,
                            since_seconds=kwargs["since_seconds"],
                            container=container_name,
                            previous=previous_logs,
                        )
                        previous_segment = ".previous" if previous_logs else ""
                        assert_zipfile_write(
                            mocked_zipfile,
                            zinfo=f"{namespace}/{resource_api.moniker}/"
                            f"pod.{pod_name}.{container_name}{previous_segment}.log",
                            data=mocked_list_pods[namespace][pod_name][container_name],
                        )


def assert_list_replica_sets(
    mocked_client,
    mocked_zipfile,
    label_selector: str,
    resource_api: EdgeResourceApi,
    mock_names: Optional[List[str]] = None,
):
    mocked_client.AppsV1Api().list_replica_set_for_all_namespaces.assert_any_call(label_selector=label_selector)

    mock_names = mock_names or ["mock_replicaset"]
    for name in mock_names:
        assert_zipfile_write(
            mocked_zipfile,
            zinfo=f"mock_namespace/{resource_api.moniker}/replicaset.{name}.yaml",
            data=f"kind: Replicaset\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_stateful_sets(
    mocked_client,
    mocked_zipfile,
    resource_api: EdgeResourceApi,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
):
    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(
        label_selector=label_selector, field_selector=field_selector
    )
    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{resource_api.moniker}/statefulset.mock_statefulset.yaml",
        data="kind: Statefulset\nmetadata:\n  name: mock_statefulset\n  namespace: mock_namespace\n",
    )


def assert_list_services(
    mocked_client,
    mocked_zipfile,
    resource_api: EdgeResourceApi,
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
            zinfo=f"mock_namespace/{resource_api.moniker}/service.{name}.yaml",
            data=f"kind: Service\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_list_daemon_sets(
    mocked_client,
    mocked_zipfile,
    resource_api: EdgeResourceApi,
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
            zinfo=f"mock_namespace/{resource_api.moniker}/daemonset.{name}.yaml",
            data=f"kind: Daemonset\nmetadata:\n  name: {name}\n  namespace: mock_namespace\n",
        )


def assert_mq_stats(mocked_zipfile):
    assert_zipfile_write(mocked_zipfile, zinfo="mock_namespace/mq/diagnostic_metrics.txt", data="metrics")


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
            "resource_api": OTEL_API,
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
    [[MQ_API_V1B1]],
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
):

    # mock MQ support bundle to return connectors
    mocked_mq_support_active_api = mocker.patch("azext_edge.edge.providers.support.mq.MQ_ACTIVE_API")
    mocked_mq_support_active_api.get_resources.return_value = custom_objects
    result = support_bundle(None, bundle_dir=a_bundle_dir, ops_service="mq")
    assert result

    # assert initial call to list stateful sets
    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(
        label_selector=MQ_LABEL, field_selector=None
    )

    # TODO - assert zipfile write of generic statefulset
    if not custom_objects["items"]:
        mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_called_once()

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
        [MQ_API_V1B1],
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
    test_zipinfo = ZipInfo("mock_namespace/mq/traces/trace_key")
    test_zipinfo.file_size = 0
    test_zipinfo.compress_size = 0
    assert_zipfile_write(mocked_zipfile, zinfo=test_zipinfo, data="trace_data")
