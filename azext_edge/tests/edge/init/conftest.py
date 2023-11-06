# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.util import get_timestamp_now_utc


@pytest.fixture
def mocked_deploy(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.deploy", autospec=True)
    yield patched


@pytest.fixture
def mocked_provision_akv_csi_driver(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.provision_akv_csi_driver", autospec=True)
    yield patched


@pytest.fixture
def mocked_configure_cluster_secrets(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.configure_cluster_secrets", autospec=True)
    yield patched


@pytest.fixture
def mocked_cluster_tls(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.configure_cluster_tls", autospec=True)
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
def mocked_prepare_ca(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.prepare_ca", autospec=True)
    patched.return_value = ("mock_ca", "mock_private_key", "mock_secret_name", "mock_configmap")
    yield patched


@pytest.fixture
def mocked_prepare_keyvault_access_policy(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.prepare_keyvault_access_policy", autospec=True)

    def handle_return(*args, **kwargs):
        return f"https://localhost/{kwargs['keyvault_resource_id']}/vault"

    patched.side_effect = handle_return
    yield patched


@pytest.fixture
def mocked_prepare_keyvault_secret(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.prepare_keyvault_secret", autospec=True)

    def handle_return(*args, **kwargs):
        return kwargs["keyvault_sat_secret_name"]

    patched.side_effect = handle_return
    yield patched


@pytest.fixture
def mocked_prepare_sp(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.prepare_sp", autospec=True)
    yield patched


@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.wait_for_terminal_state", autospec=True)
    yield patched


@pytest.fixture
def mocked_file_exists(mocker):
    patched = mocker.patch("azext_edge.edge.commands_edge.exists", autospec=True)
    patched.return_value = True
    yield patched
