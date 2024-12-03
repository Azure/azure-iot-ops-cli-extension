# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.util import get_timestamp_now_utc


def pytest_configure(config):
    config.addinivalue_line("markers", "init_scenario_test: mark tests that will run az iot ops init")


@pytest.fixture
def mocked_deploy_template(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.deploy_template", autospec=True)

    def handle_return(*args, **kwargs):
        return (
            {
                "deploymentName": kwargs["deployment_name"],
                "resourceGroup": kwargs["resource_group_name"],
                "clusterName": kwargs["cluster_name"],
                "clusterNamespace": kwargs["cluster_namespace"],
                "deploymentLink": "https://localhost/deployment",
                "deploymentState": {"status": "pending", "timestampUtc": {"started": get_timestamp_now_utc()}},
            },
            mocker.MagicMock(),
        )

    patched.side_effect = handle_return
    yield patched


@pytest.fixture
def mocked_connected_cluster_location(mocker, request):
    return_value = getattr(request, "param", None) or "mock_location"
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.connected_cluster.ConnectedCluster.location",
        return_value=return_value,
        new_callable=mocker.PropertyMock,
    )
    yield patched


@pytest.fixture
def mocked_connected_cluster_extensions(mocker, request):
    return_value = getattr(request, "param", None) or []
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.connected_cluster.ConnectedCluster.extensions",
        return_value=return_value,
        new_callable=mocker.PropertyMock,
    )
    yield patched


@pytest.fixture
def mocked_verify_arc_cluster_config(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.verify_arc_cluster_config", autospec=True)
    yield patched


@pytest.fixture
def mocked_verify_custom_location_namespace(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.base.verify_custom_location_namespace", autospec=True
    )
    yield patched
