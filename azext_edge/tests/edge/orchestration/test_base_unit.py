# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.connected_cluster import ConnectedCluster

from ...generators import generate_random_string, get_zeroed_subscription

BASE_PATH = "azext_edge.edge.providers.orchestration.base"
ZEROED_SUB = get_zeroed_subscription()


@pytest.fixture
def mocked_get_tenant_id(mocker):
    yield mocker.patch(f"{BASE_PATH}.get_tenant_id", return_value=generate_random_string())


@pytest.mark.parametrize(
    "test_scenario",
    [
        {  # fail no config map
            "failure": True,
            "config_map": None,
        },
        {  # fail config indicates diff cluster
            "failure": "cluster name",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster2",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # fail config indicates diff rg
            "failure": "resource group",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg2",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # fail config indicates diff sub
            "failure": "subscription Id",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": "8757c60a-a398-4c09-adaf-be328caf42d4",
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # success
            "failure": False,
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
    ],
)
def test_verify_arc_cluster_config(mocker, mocked_cmd, test_scenario):
    get_config_map_patch = mocker.patch(f"{BASE_PATH}.get_config_map", return_value=test_scenario["config_map"])
    from azext_edge.edge.providers.orchestration.base import verify_arc_cluster_config

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd,
        subscription_id=ZEROED_SUB,
        cluster_name="cluster1",
        resource_group_name="rg1",
    )

    failure = test_scenario["failure"]
    if failure:
        match_str = ""
        if isinstance(failure, str):
            match_str = failure
        with pytest.raises(ValidationError, match=rf".*{match_str}.*"):
            verify_arc_cluster_config(connected_cluster)
            get_config_map_patch.assert_called_once()
        return

    verify_arc_cluster_config(connected_cluster)
    get_config_map_patch.assert_called_once()


@pytest.mark.parametrize(
    "custom_location_name, namespace, get_cl_for_np_return_value",
    [
        ("mycl", "mynamespace", None),
        ("mycl", "mynamespace", {"name": "mycl"}),
        ("mycl", "mynamespace", {"name": "othercl"}),
    ],
)
def test_verify_custom_location_namespace(
    mocker, mocked_cmd, custom_location_name, namespace, get_cl_for_np_return_value
):
    mocked_get_custom_location_for_namespace = mocker.patch(
        "azext_edge.edge.providers.orchestration.connected_cluster.ConnectedCluster.get_custom_location_for_namespace"
    )
    mocked_get_custom_location_for_namespace.return_value = get_cl_for_np_return_value

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd,
        subscription_id=ZEROED_SUB,
        cluster_name="cluster1",
        resource_group_name="rg1",
    )

    from azext_edge.edge.providers.orchestration.base import (
        verify_custom_location_namespace,
    )

    if get_cl_for_np_return_value and get_cl_for_np_return_value["name"] != custom_location_name:
        with pytest.raises(ValidationError) as ve:
            verify_custom_location_namespace(
                connected_cluster=connected_cluster, custom_location_name=custom_location_name, namespace=namespace
            )
        assert (
            f"The intended namespace for deployment: {namespace}, is already referenced "
            f"by custom location: {get_cl_for_np_return_value['name']}" in str(ve.value)
        )
        return

    verify_custom_location_namespace(
        connected_cluster=connected_cluster, custom_location_name=custom_location_name, namespace=namespace
    )


@pytest.mark.parametrize(
    "registration_state",
    [
        "Registered",
        "NotRegistered",
    ],
)
@pytest.mark.parametrize("input_rp", [None, "Microsoft.DeviceRegistry"])
def test_register_providers(mocker, registration_state, input_rp):
    mocked_get_resource_client: Mock = mocker.patch(
        "azext_edge.edge.providers.orchestration.rp_namespace.get_resource_client"
    )
    from azext_edge.edge.providers.orchestration.rp_namespace import (
        RP_NAMESPACE_SET,
        register_providers,
    )

    iot_ops_rps = [
        "Microsoft.IoTOperations",
        "Microsoft.DeviceRegistry",
        "Microsoft.SecretSyncController",
    ]
    if input_rp:
        iot_ops_rps = [input_rp]
    mocked_get_resource_client().providers.list.return_value = [
        {"namespace": namespace, "registrationState": registration_state} for namespace in iot_ops_rps
    ]

    for rp in iot_ops_rps:
        assert rp in RP_NAMESPACE_SET
    assert len(iot_ops_rps) == (1 if input_rp else len(RP_NAMESPACE_SET))

    register_providers(ZEROED_SUB)
    mocked_get_resource_client().providers.list.assert_called_once()
    if registration_state == "NotRegistered":
        for rp in iot_ops_rps:
            mocked_get_resource_client().providers.register.assert_any_call(rp)
