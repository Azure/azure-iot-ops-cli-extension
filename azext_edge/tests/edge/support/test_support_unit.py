# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import random
from typing import List
from os.path import abspath, expanduser, join

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError

from azext_edge.edge.commands_edge import support_bundle
from azext_edge.edge.providers.edge_api import (
    EdgeResourceApi,
    OpcuaResourceKinds,
    E4K_API_V1A2,
    E4K_API_V1A3,
    BLUEFIN_API_V1,
    OPCUA_API_V1,
    SYMPHONY_API_V1,
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
from azext_edge.edge.providers.support.symphony import (
    SYMPHONY_APP_LABEL,
    SYMPHONY_INSTANCE_LABEL,
    GENERIC_CONTROLLER_LABEL,
)

from ...generators import generate_generic_id

a_bundle_dir = f"support_test_{generate_generic_id()}"


@pytest.mark.parametrize(
    "mocked_cluster_resources",
    [
        [],
        [E4K_API_V1A2],
        [E4K_API_V1A2, E4K_API_V1A3],
        [OPCUA_API_V1],
        [E4K_API_V1A2, OPCUA_API_V1],
        [E4K_API_V1A2, BLUEFIN_API_V1],
        [E4K_API_V1A2, OPCUA_API_V1, BLUEFIN_API_V1],
        [E4K_API_V1A3, OPCUA_API_V1, BLUEFIN_API_V1, SYMPHONY_API_V1],
    ],
    indirect=True,
)
def test_create_bundle(
    mocked_client,
    mocked_cluster_resources,
    mocked_config,
    mocked_os_makedirs,
    mocked_zipfile,
    mocked_list_cluster_custom_objects,
    mocked_list_deployments,
    mocked_list_pods,
    mocked_list_replicasets,
    mocked_list_statefulsets,
    mocked_list_services,
    mocked_list_nodes,
    mocked_get_stats,
    mocked_root_logger,
):
    if not mocked_cluster_resources["param"] or all(
        [E4K_API_V1A2 not in mocked_cluster_resources["param"], E4K_API_V1A3 not in mocked_cluster_resources["param"]]
    ):
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="e4k")

    if not mocked_cluster_resources["param"] or OPCUA_API_V1 not in mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="opcua")

    if not mocked_cluster_resources["param"] or BLUEFIN_API_V1 not in mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="bluefin")

    if not mocked_cluster_resources["param"] or SYMPHONY_API_V1 not in mocked_cluster_resources["param"]:
        with pytest.raises(ResourceNotFoundError):
            support_bundle(None, bundle_dir=a_bundle_dir, edge_service="symphony")

    if mocked_cluster_resources["param"] == []:
        auto_result_no_resources = support_bundle(None, bundle_dir=a_bundle_dir)
        mocked_root_logger.warning.assert_called_once_with("No known edge services discovered on cluster.")
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
            if api in [OPCUA_API_V1]:
                if kind == OpcuaResourceKinds.MODULE_TYPE.value:
                    target_file_prefix = "module_type"
                if kind == OpcuaResourceKinds.ASSET_TYPE.value:
                    target_file_prefix = "asset_type"

            assert_list_custom_resources(
                mocked_client, mocked_zipfile, api, kind, file_prefix=target_file_prefix
            )

        if api in [E4K_API_V1A2, E4K_API_V1A3]:
            # Assert runtime resources
            assert_list_deployments(mocked_client, mocked_zipfile, label_selector=E4K_LABEL, resource_api=E4K_API_V1A2)
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=E4K_LABEL,
                resource_api=E4K_API_V1A2,
                since_seconds=since_seconds,
            )
            assert_list_replica_sets(mocked_client, mocked_zipfile, label_selector=E4K_LABEL, resource_api=E4K_API_V1A2)
            assert_list_stateful_sets(
                mocked_client, mocked_zipfile, label_selector=E4K_LABEL, resource_api=E4K_API_V1A2
            )
            assert_list_services(mocked_client, mocked_zipfile, label_selector=E4K_LABEL, resource_api=E4K_API_V1A2)
            assert_e4k_stats(mocked_zipfile)

        if api in [OPCUA_API_V1]:
            # Assert runtime resources
            assert_list_deployments(
                mocked_client, mocked_zipfile, label_selector=OPCUA_ORCHESTRATOR_LABEL, resource_api=OPCUA_API_V1
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPCUA_SUPERVISOR_LABEL,
                resource_api=OPCUA_API_V1,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=OPCUA_GENERAL_LABEL,
                resource_api=OPCUA_API_V1,
                since_seconds=since_seconds,
            )

        if api in [BLUEFIN_API_V1]:
            # Assert runtime resources
            assert_list_deployments(
                mocked_client, mocked_zipfile, label_selector=BLUEFIN_APP_LABEL, resource_api=BLUEFIN_API_V1
            )
            assert_list_deployments(
                mocked_client, mocked_zipfile, label_selector=BLUEFIN_PART_OF_LABEL, resource_api=BLUEFIN_API_V1
            )

            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=BLUEFIN_APP_LABEL,
                resource_api=BLUEFIN_API_V1,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=BLUEFIN_INSTANCE_LABEL,
                resource_api=BLUEFIN_API_V1,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=BLUEFIN_RELEASE_LABEL,
                resource_api=BLUEFIN_API_V1,
                since_seconds=since_seconds,
            )
            assert_list_pods(
                mocked_client,
                mocked_zipfile,
                mocked_list_pods,
                label_selector=BLUEFIN_ONEOFF_LABEL,
                resource_api=BLUEFIN_API_V1,
                since_seconds=since_seconds,
            )

            assert_list_replica_sets(
                mocked_client, mocked_zipfile, label_selector=BLUEFIN_APP_LABEL, resource_api=BLUEFIN_API_V1
            )
            assert_list_replica_sets(
                mocked_client, mocked_zipfile, label_selector=BLUEFIN_ONEOFF_LABEL, resource_api=BLUEFIN_API_V1
            )

            assert_list_stateful_sets(
                mocked_client,
                mocked_zipfile,
                label_selector=BLUEFIN_RELEASE_LABEL,
                resource_api=BLUEFIN_API_V1,
            )
            assert_list_stateful_sets(
                mocked_client, mocked_zipfile, label_selector=BLUEFIN_INSTANCE_LABEL, resource_api=BLUEFIN_API_V1
            )

            # @digimaun - TODO, use labels when available.
            assert_list_services(mocked_client, mocked_zipfile, label_selector=None, resource_api=BLUEFIN_API_V1)

        if api in [SYMPHONY_API_V1]:
            for symphony_label in [SYMPHONY_APP_LABEL, SYMPHONY_INSTANCE_LABEL, GENERIC_CONTROLLER_LABEL]:
                assert_list_pods(
                    mocked_client,
                    mocked_zipfile,
                    mocked_list_pods,
                    label_selector=symphony_label,
                    resource_api=SYMPHONY_API_V1,
                    since_seconds=since_seconds,
                )
                assert_list_deployments(
                    mocked_client, mocked_zipfile, label_selector=symphony_label, resource_api=SYMPHONY_API_V1
                )
                assert_list_replica_sets(
                    mocked_client, mocked_zipfile, label_selector=symphony_label, resource_api=SYMPHONY_API_V1
                )

            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=SYMPHONY_APP_LABEL, resource_api=SYMPHONY_API_V1
            )
            assert_list_services(
                mocked_client, mocked_zipfile, label_selector=SYMPHONY_APP_LABEL, resource_api=SYMPHONY_API_V1
            )
            # TODO: resolve with selector
            # assert_list_services(mocked_client, mocked_zipfile, label_selector=None, resource_api=SYMPHONY_API_V1)

        # assert shared KPIs regardless of service
        assert_shared_kpis(mocked_client, mocked_zipfile)


def assert_list_custom_resources(
    mocked_client, mocked_zipfile, api: EdgeResourceApi, kind: str, file_prefix: str = None
):
    mocked_client.CustomObjectsApi().list_cluster_custom_object.assert_any_call(
        group=api.group, version=api.version, plural=f"{kind}s"
    )
    if not file_prefix:
        file_prefix = kind

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{api.moniker}/{file_prefix}.{api.version}.mock_name.yaml",
        data=f"kind: {kind}\nmetadata:\n  name: mock_name\n  namespace: mock_namespace\n",
    )


def assert_list_deployments(mocked_client, mocked_zipfile, label_selector: str, resource_api: EdgeResourceApi):
    mocked_client.AppsV1Api().list_deployment_for_all_namespaces.assert_any_call(label_selector=label_selector)
    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{resource_api.moniker}/deployment.mock_deployment.yaml",
        data="kind: Deployment\nmetadata:\n  name: mock_deployment\n  namespace: mock_namespace\n",
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


def assert_list_replica_sets(mocked_client, mocked_zipfile, label_selector: str, resource_api: EdgeResourceApi):
    mocked_client.AppsV1Api().list_replica_set_for_all_namespaces.assert_any_call(label_selector=label_selector)

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{resource_api.moniker}/replicaset.mock_replicaset.yaml",
        data="kind: Replicaset\nmetadata:\n  name: mock_replicaset\n  namespace: mock_namespace\n",
    )


def assert_list_stateful_sets(mocked_client, mocked_zipfile, label_selector: str, resource_api: EdgeResourceApi):
    mocked_client.AppsV1Api().list_stateful_set_for_all_namespaces.assert_any_call(label_selector=label_selector)

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{resource_api.moniker}/statefulset.mock_statefulset.yaml",
        data="kind: Statefulset\nmetadata:\n  name: mock_statefulset\n  namespace: mock_namespace\n",
    )


def assert_list_services(mocked_client, mocked_zipfile, label_selector: str, resource_api: EdgeResourceApi):
    mocked_client.CoreV1Api().list_service_for_all_namespaces.assert_any_call(label_selector=label_selector)

    # @digimaun - more configurable mocks
    mock_name = "mock_service"
    if resource_api in [BLUEFIN_API_V1]:
        mock_name = "bluefin-service"

    assert_zipfile_write(
        mocked_zipfile,
        zinfo=f"mock_namespace/{resource_api.moniker}/service.{mock_name}.yaml",
        data=f"kind: Service\nmetadata:\n  name: {mock_name}\n  namespace: mock_namespace\n",
    )


def assert_e4k_stats(mocked_zipfile):
    assert_zipfile_write(mocked_zipfile, zinfo="mock_namespace/e4k/diagnostic_metrics.txt", data="metrics")


def assert_shared_kpis(mocked_client, mocked_zipfile):
    mocked_client.CoreV1Api().list_node.assert_called_once()
    assert_zipfile_write(mocked_zipfile, zinfo="nodes.yaml", data="items:\n- metadata:\n    name: mock_node\n")


# TODO: base test class?
def assert_zipfile_write(mocked_zipfile, zinfo: str, data: str):
    mocked_zipfile(file="").__enter__().writestr.assert_any_call(
        zinfo_or_arcname=zinfo,
        data=data,
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
