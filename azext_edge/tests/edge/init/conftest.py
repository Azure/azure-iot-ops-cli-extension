# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict

import pytest

from azext_edge.edge.providers.orchestration.base import KEYVAULT_ARC_EXTENSION_VERSION
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
def mocked_provision_akv_csi_driver(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.provision_akv_csi_driver", autospec=True)

    base_config_settings: Dict[str, str] = {
        "secrets-store-csi-driver.enableSecretRotation": "true",
        "secrets-store-csi-driver.rotationPollInterval": "1h",
        "secrets-store-csi-driver.syncSecret.enabled": "false",
    }

    def handle_return(*args, **kwargs):
        custom_config = kwargs.get("extension_config")
        if custom_config:
            base_config_settings.update(custom_config)

        return {
            "properties": {
                "version": kwargs.get("extension_version") or KEYVAULT_ARC_EXTENSION_VERSION,
                "configurationSettings": base_config_settings,
            }
        }

    patched.side_effect = handle_return
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

    def handle_return(*args, **kwargs):
        return ("mock_ca", "mock_private_key", "mock_secret_name", "mock_configmap")

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
def mocked_validate_keyvault_permission_model(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.base.validate_keyvault_permission_model", autospec=True
    )

    def handle_return(*args, **kwargs):
        return {
            "id": (
                "/subscriptions/ae128775-4f16-4fd2-8dff-0ceed6a6a1f3/resourceGroups/FakeRg/"
                "providers/Microsoft.KeyVault/vaults/myfakekeyvault"
            ),
            "name": "myfakekeyvault",
            "type": "Microsoft.KeyVault/vaults",
            "location": "westus3",
            "tags": {},
            "properties": {
                "sku": {"family": "A", "name": "standard"},
                "tenantId": "351f1fd9-7de2-4c5b-b730-14b54fddb737",
                "accessPolicies": [
                    {
                        "tenantId": "351f1fd9-7de2-4c5b-b730-14b54fddb737",
                        "objectId": "44e44a12-594e-464a-acbb-0038734403bf",
                        "permissions": {"keys": [], "secrets": ["Get", "List"], "certificates": [], "storage": []},
                    },
                ],
                "enableRbacAuthorization": False,
                "vaultUri": "https://myfakekeyvault.vault.azure.net/",
                "provisioningState": "Succeeded",
                "publicNetworkAccess": "Enabled",
            },
        }

    patched.side_effect = handle_return
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
def mocked_prepare_keyvault_access_policy(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.base.prepare_keyvault_access_policy", autospec=True
    )

    def handle_return(*args, **kwargs):
        return f"https://localhost/{kwargs['keyvault_resource_id']}/vault"

    patched.side_effect = handle_return
    yield patched


@pytest.fixture
def mocked_prepare_keyvault_secret(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.prepare_keyvault_secret", autospec=True)

    def handle_return(*args, **kwargs):
        return kwargs["keyvault_spc_secret_name"]

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
def mocked_eval_secret_via_sp(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.base.eval_secret_via_sp", autospec=True)
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
