# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.util import get_timestamp_now_utc


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "init_scenario_test: mark tests that will run az iot ops init"
    )


@pytest.fixture
def mocked_deploy(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.deploy", autospec=True)
    yield patched


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
def mocked_verify_cli_client_connections(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.host.verify_cli_client_connections", autospec=True)
    yield patched


@pytest.fixture
def mocked_register_providers(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.rp_namespace.register_providers", autospec=True)
    yield patched


@pytest.fixture
def mocked_edge_api_keyvault_api_v1(mocker):
    patched = mocker.patch("azext_edge.edge.providers.edge_api.keyvault.KEYVAULT_API_V1", autospec=False)
    yield patched


@pytest.fixture
def mocked_verify_write_permission_against_rg(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.permissions.verify_write_permission_against_rg", autospec=True
    )
    yield patched


@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.wait_for_terminal_state", autospec=True)
    yield patched


@pytest.fixture
def mocked_file_exists(mocker):
    patched = mocker.patch("azext_edge.edge.commands_edge.exists", autospec=True)
    patched.return_value = True
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
def mocked_verify_custom_locations_enabled(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.base.verify_custom_locations_enabled", autospec=True
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


@pytest.fixture
def spy_get_current_template_copy(mocker):
    from azext_edge.edge.providers.orchestration import work

    spy = mocker.spy(work, "get_current_template_copy")

    yield spy


@pytest.fixture
def spy_work_displays(mocker):
    from azext_edge.edge.providers.orchestration.work import WorkManager

    yield {
        "render_display": mocker.spy(WorkManager, "render_display"),
        "complete_step": mocker.spy(WorkManager, "complete_step"),
    }
