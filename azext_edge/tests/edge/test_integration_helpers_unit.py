# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.util.az_client import DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION

from .conftest import _build_delete_command
from .orchestration import test_mgmt_actions_int as mgmt_actions


RESOURCE_GROUP_ID = "/subscriptions/test-sub/resourceGroups/test-rg"


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
