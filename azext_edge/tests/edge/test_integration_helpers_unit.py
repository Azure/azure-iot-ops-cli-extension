# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from importlib import import_module

import pytest
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.util.az_client import DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION

from .conftest import _build_delete_command
from .orchestration import test_mgmt_actions_int as mgmt_actions


RESOURCE_GROUP_ID = "/subscriptions/test-sub/resourceGroups/test-rg"
OPCUA_MODULE = "azext_edge.tests.edge.orchestration.resources.connector.opcua.int"
opcua_helpers = import_module(f"{OPCUA_MODULE}.helpers")


@pytest.mark.parametrize("resource_path", [
    "Microsoft.DeviceRegistry/namespaces/test-ns",
    "Microsoft.DeviceRegistry/schemaRegistries/test-registry",
    "Microsoft.DeviceRegistry/namespaces/test-ns/assets/test-asset",
    "Microsoft.DeviceRegistry/namespaces/test-ns/devices/test-device",
    "Microsoft.DeviceRegistry/assets/test-asset",
    "Microsoft.DeviceRegistry/assetEndpointProfiles/test-aep",
    "mIcRoSoFt.DeViCeReGiStRy/namespaces/test-ns",
])
@pytest.mark.parametrize("context", [{}, {"instance_name": "test-instance"}, {"resource_group": "test-rg"}])
def test_build_delete_command_pins_adr_fallback(resource_path, context):
    resource_id = f"{RESOURCE_GROUP_ID}/providers/{resource_path}"

    assert _build_delete_command(resource_id, **context) == (
        f"az resource delete --id {resource_id} -v "
        f"--api-version {DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION.value}"
    )


@pytest.mark.parametrize("resource_path", [
    "Microsoft.Storage/storageAccounts/test-storage",
    "Microsoft.Kubernetes/connectedClusters/test-cluster",
    "Microsoft.IoTOperations/instances/test-instance",
    "Microsoft.DeviceRegistry/namespaces/test-ns/providers/Microsoft.Authorization/locks/test-lock",
])
def test_build_delete_command_leaves_other_providers_unpinned(resource_path):
    resource_id = f"{RESOURCE_GROUP_ID}/providers/{resource_path}"

    assert _build_delete_command(resource_id) == f"az resource delete --id {resource_id} -v"


@pytest.mark.parametrize("resource_type, command_group", [("assets", "asset"), ("devices", "device")])
def test_build_delete_command_preserves_namespace_commands(resource_type, command_group):
    resource_id = f"{RESOURCE_GROUP_ID}/providers/Microsoft.DeviceRegistry/namespaces/test-ns/{resource_type}/test-name"

    assert _build_delete_command(resource_id, "test-instance", "test-rg") == (
        f"az iot ops ns {command_group} delete --name test-name --instance test-instance -g test-rg -y"
    )


def test_mgmt_actions_setup_pins_namespace_read(mocker):
    namespace_id = f"{RESOURCE_GROUP_ID}/providers/Microsoft.DeviceRegistry/namespaces/test-ns"
    settings = mocker.Mock()
    settings.env.azext_edge_instance = "test-instance"
    settings.env.azext_edge_rg = "test-rg"
    run = mocker.patch.object(mgmt_actions, "run", side_effect=[
        {"properties": {"adrNamespaceRef": {"resourceId": namespace_id}}},
        {"location": "westus2"},
        {},
    ])
    # Stop before provisioning anything: only the metadata reads above are exercised.
    mocker.patch.object(mgmt_actions, "_describe_existing_state", return_value=["existing enablement"])
    setup = mgmt_actions.mgmt_actions_setup.__wrapped__(mocker.Mock(), settings, [])

    with pytest.raises(pytest.skip.Exception, match="already carries mgmt-actions state"):
        next(setup)

    assert run.call_args_list == [
        mocker.call("az iot ops show -n test-instance -g test-rg"),
        mocker.call(
            f'az resource show --ids "{namespace_id}" '
            f"--api-version {DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION.value}"
        ),
        mocker.call("az iot ops mgmt-actions show -i test-instance -g test-rg"),
    ]


@pytest.fixture
def opcua_context(mocker):
    settings = mocker.Mock()
    settings.env.azext_edge_instance = "instance"
    settings.env.azext_edge_rg = "group"
    settings.env.azext_edge_kv = None
    settings.env.azext_edge_sp_object_id = "principal"
    run = mocker.patch.object(opcua_helpers, "run")
    mocker.patch.object(opcua_helpers, "sleep")
    mocker.patch("azext_edge.tests.helpers.sleep")
    return settings, run


def _spc(vault="vault"):
    return {
        "type": opcua_helpers.SPC_RESOURCE_TYPE,
        "name": "spc",
        "properties": {"keyvaultName": vault},
    }


@pytest.mark.parametrize("old_resources", [
    [_spc("previous-vault")],
    [{"type": "microsoft.secretsync/secretsyncs", "name": "orphan"}],
])
def test_opcua_secretsync_waits_for_discovery_before_enable(opcua_context, mocker, old_resources):
    settings, run = opcua_context
    run.side_effect = [old_resources, None, old_resources, [], _spc()]

    assert opcua_helpers.ensure_secretsync_enabled(settings, "instance", "group", "/vault", "/identity") == "spc"

    assert run.call_args_list == [
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az iot ops secretsync disable -n instance -g group -y"),
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call(
            "az iot ops secretsync enable -n instance -g group "
            "--mi-user-assigned /identity --kv-resource-id /vault"
        ),
    ]


def test_opcua_secretsync_reuses_only_requested_vault(opcua_context, mocker):
    settings, run = opcua_context
    run.side_effect = [[_spc("VAULT")], {"id": "/vault"}]

    assert opcua_helpers.ensure_secretsync_enabled(settings, "instance", "group", "/vault", "/identity") == "spc"

    assert run.call_args_list == [
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az keyvault show --id /vault"),
    ]


@pytest.mark.parametrize("failure", ["disable", "convergence"])
def test_opcua_secretsync_does_not_enable_after_failed_removal(opcua_context, failure):
    settings, run = opcua_context

    def command_result(command):
        if "secretsync list" in command:
            return [_spc("previous-vault")]
        if "secretsync disable" in command:
            if failure == "disable":
                raise CLIInternalError("disable failed")
            return None
        pytest.fail(f"Unexpected mutation: {command}")

    run.side_effect = command_result
    error, message = (
        (CLIInternalError, "disable failed") if failure == "disable"
        else (AssertionError, "Expected 0 items but got 1")
    )
    with pytest.raises(error, match=message):
        opcua_helpers.ensure_secretsync_enabled(settings, "instance", "group", "/vault", "/identity")
    assert sum("secretsync disable" in call.args[0] for call in run.call_args_list) == 1


def test_opcua_cleanup_removes_secretsync_before_its_vault(opcua_context, mocker):
    settings, run = opcua_context
    run.side_effect = [[_spc()], None, [_spc()], [], None, None]

    opcua_helpers.cleanup_test_resources(settings, "vault")

    assert run.call_args_list == [
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az iot ops secretsync disable -n instance -g group -y"),
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az keyvault delete -n vault -g group"),
        mocker.call("az keyvault purge -n vault"),
    ]


@pytest.mark.parametrize("resources", [[], [_spc("another-vault")]])
def test_opcua_cleanup_does_not_disable_another_vault(opcua_context, mocker, resources):
    settings, run = opcua_context
    run.side_effect = [resources, None, None]

    opcua_helpers.cleanup_test_resources(settings, "vault")

    assert run.call_args_list == [
        mocker.call("az iot ops secretsync list -n instance -g group"),
        mocker.call("az keyvault delete -n vault -g group"),
        mocker.call("az keyvault purge -n vault"),
    ]


def test_opcua_cleanup_refuses_mixed_vaults(opcua_context):
    settings, run = opcua_context
    run.return_value = [_spc(), _spc("another-vault")]

    with pytest.raises(AssertionError, match="another fixture's Key Vault"):
        opcua_helpers.cleanup_test_resources(settings, "vault")
    assert run.call_count == 1


def test_opcua_vault_cleanup_registered_before_role_assignment(opcua_context, mocker):
    settings, run = opcua_context
    request = mocker.Mock()
    cleanup = mocker.patch.object(opcua_helpers, "cleanup_test_resources")
    run.side_effect = [{"id": "/vault"}, CLIInternalError("role assignment failed")]

    with pytest.raises(CLIInternalError, match="role assignment failed"):
        opcua_helpers.ensure_key_vault(settings, request)

    request.addfinalizer.assert_called_once()
    request.addfinalizer.call_args.args[0]()
    vault_name = run.call_args_list[0].args[0].split()[4]
    cleanup.assert_called_once_with(settings, vault_name)


@pytest.mark.parametrize("kind", ["client", "issuer", "trust"])
@pytest.mark.parametrize("failure", ["ensure_managed_identity", "ensure_secretsync_enabled"])
def test_opcua_fixtures_register_cleanup_before_setup_failure(opcua_context, mocker, kind, failure):
    settings, run = opcua_context
    module = import_module(f"{OPCUA_MODULE}.test_opcua_certs_{kind}_int")
    request = mocker.Mock()
    run.side_effect = [{"id": "/vault"}, None]
    cleanup = mocker.patch.object(opcua_helpers, "cleanup_test_resources")
    mocker.patch.object(module, "ensure_managed_identity", return_value="/identity")
    mocker.patch.object(module, failure, side_effect=CLIInternalError("setup failed"))
    setup = getattr(module, f"opcua_certs_{kind}_test_setup").__wrapped__(settings, [], request)

    with pytest.raises(CLIInternalError, match="setup failed"):
        next(setup)

    request.addfinalizer.assert_called_once()
    request.addfinalizer.call_args.args[0]()
    vault_name = run.call_args_list[0].args[0].split()[4]
    cleanup.assert_called_once_with(settings, vault_name)
