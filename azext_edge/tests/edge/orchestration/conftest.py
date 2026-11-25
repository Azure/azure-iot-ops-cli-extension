# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from pathlib import Path
from typing import List
from uuid import uuid4

import pytest
from azure.cli.core.azclierror import CLIInternalError
from knack.log import get_logger

from ...generators import generate_random_string
from ...helpers import run, wait_for_expected_count

MOCK_BROKER_CONFIG_PATH = Path(__file__).parent.joinpath("./broker_config.json")

logger = get_logger(__name__)


# Not used
@pytest.fixture
def mocked_verify_write_permission_against_rg(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.permissions.verify_write_permission_against_rg", autospec=True
    )
    yield patched


@pytest.fixture
def mocked_permission_manager(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.PermissionManager", autospec=True)
    yield patched


##


@pytest.fixture
def mocked_resource_graph(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.connected_cluster.ResourceGraph", autospec=True)
    yield patched


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.get_resource_client", autospec=True)
    yield patched


@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.wait_for_terminal_state", autospec=True)
    yield patched


@pytest.fixture
def mocked_register_providers(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.rp_namespace.register_providers", autospec=True)
    yield patched


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.IoTOperationsResourceMap")
    yield patched


@pytest.fixture(scope="module")
def mock_broker_config():
    custom_config = {generate_random_string(): generate_random_string()}
    MOCK_BROKER_CONFIG_PATH.write_text(json.dumps(custom_config), encoding="utf-8")
    yield custom_config
    MOCK_BROKER_CONFIG_PATH.unlink()


@pytest.fixture
def mocked_sleep(mocker):
    patched = {
        "az_client.sleep": mocker.patch("azext_edge.edge.util.az_client.sleep", autospec=True),
        "work.sleep": mocker.patch("azext_edge.edge.providers.orchestration.work.sleep", autospec=True),
        "upgrade.sleep": mocker.patch("azext_edge.edge.providers.orchestration.upgrade2.sleep", autospec=True),
    }
    yield patched


@pytest.fixture
def spy_work_displays(mocker):
    from azext_edge.edge.providers.orchestration.work import WorkManager

    yield {
        "render_display": mocker.spy(WorkManager, "_render_display"),
        "complete_step": mocker.spy(WorkManager, "_complete_step"),
    }


@pytest.fixture
def mock_prechecks(mocker):
    from azext_edge.edge.providers.check.base import deployment

    yield {
        "validate_cluster_prechecks": mocker.spy(deployment, "check_pre_deployment"),
        "check_k8s_version": mocker.patch(
            "azext_edge.edge.providers.check.base.deployment._check_k8s_version", autospec=True
        ),
        "check_storage_classes": mocker.patch(
            "azext_edge.edge.providers.check.base.deployment._check_storage_classes", autospec=True
        ),
        "check_nodes": mocker.patch("azext_edge.edge.providers.check.base.deployment.check_nodes", autospec=True),
    }


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.logger", autospec=True)
    yield patched


@pytest.fixture
def mocked_verify_arc_cluster_config(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.verify_arc_cluster_config", autospec=True)
    yield patched


@pytest.fixture
def mocked_feature_keys(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.instances.COMPAT_FEAT_KEY_SET",
        {"connectors.settings.preview"},
    )
    yield patched


# Shared by the test_secretsync_secret*_int.py modules, which run on different trustbundle shards.
@pytest.fixture
def secretsync_secret_int_setup(settings, tracked_resources: List[str]):
    """
    Setup fixture that ensures:
    - An instance with secretsync enabled exists.
    - A test AKV secret is available for syncing.
    Returns dict with resourceGroup, instanceName, keyvaultName, etc.
    """
    from ...settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.user_assigned_mi_id.value)

    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        pytest.skip("Cannot run secretsync secret tests without an instance and resource group.")
    if not settings.env.azext_edge_kv:
        pytest.skip("Cannot run secretsync secret tests without a keyvault id.")

    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg
    kv_id = settings.env.azext_edge_kv
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]

    # Verify secretsync is enabled; enable it with the provided identity when it is not.
    list_cmd = f"az iot ops secretsync list -n {instance_name} -g {resource_group}"
    list_result = run(list_cmd)
    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not list_result and mi_id:
        run(
            f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
            f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --skip-ra"
        )
        list_result = wait_for_expected_count(list_cmd, expected_count=1, max_retries=20, initial_interval=5)
    if not list_result:
        pytest.skip("Secretsync is not enabled on the instance. Enable it first.")

    # Create test AKV secrets for use in tests
    test_secrets = {}
    for _ in range(3):
        secret_name = f"clitest{str(uuid4()).replace('-', '')[:12]}"
        secret_value = generate_random_string(size=32)
        try:
            run(
                f"az keyvault secret set --vault-name {kv_name} --name {secret_name} "
                f"--value {secret_value}"
            )
            test_secrets[secret_name] = secret_value
        except CLIInternalError as e:
            logger.warning(f"Failed to create test secret {secret_name}: {e.error_msg}")

    if len(test_secrets) < 2:
        pytest.skip("Could not create enough test secrets in the Key Vault.")

    yield {
        "resourceGroup": resource_group,
        "instanceName": instance_name,
        "keyvaultName": kv_name,
        "testSecrets": test_secrets,
    }

    # Cleanup: remove test secrets from AKV
    for secret_name in test_secrets:
        try:
            run(f"az keyvault secret delete --vault-name {kv_name} --name {secret_name}")
        except CLIInternalError:
            logger.warning(f"Failed to delete test secret {secret_name}")
            continue
        try:
            # Best-effort purge to avoid soft-delete accumulation and naming collisions on re-runs
            run(f"az keyvault secret purge --vault-name {kv_name} --name {secret_name}")
        except CLIInternalError:
            logger.warning(f"Failed to purge test secret {secret_name} (vault may not support purge)")
