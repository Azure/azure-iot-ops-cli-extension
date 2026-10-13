# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import re

import pytest
import responses

from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator
from azext_edge.edge.providers.orchestration.clone import CloneManager, InstanceRestore
from azext_edge.edge.providers.orchestration.connected_cluster import ConnectedCluster
from azext_edge.edge.providers.orchestration.deletion2 import DeletionManager
from azext_edge.edge.providers.orchestration.mgmt_actions import EgNamespaceContext, MgmtActions
from azext_edge.edge.providers.orchestration.migration import AssetMigrationManager
from azext_edge.edge.providers.orchestration.permissions import verify_write_permission_against_rg
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from azext_edge.edge.providers.orchestration.resources.sync_rules import SyncRules
from azext_edge.edge.providers.orchestration.rp_namespace import RP_NAMESPACE_OPTIONAL_SET, RP_NAMESPACE_SET
from azext_edge.edge.providers.orchestration.work import WorkManager
from azext_edge.edge.util.az_client import DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION
from azext_edge.edge.util.cloud_config import CloudConfig
from ...generators import get_zeroed_subscription
from ...helpers import build_mock_cmd_for_cloud
from .resources.test_instances_unit import get_mock_instance_record

SUBSCRIPTION = get_zeroed_subscription()
OTHER_SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Kubernetes/connectedClusters/cluster"
)


@pytest.fixture(params=[
    ("AzureCloud", "https://management.azure.com"),
    ("AzureUSGovernment", "https://management.usgovcloudapi.net"),
    ("AzureChinaCloud", "https://management.chinacloudapi.cn"),
])
def arm_cloud(request, mocked_cmd, mocked_azcli_cred_get_token, mocked_responses, mocker):
    cloud_name, endpoint = request.param
    mocked_cmd.cli_ctx.cloud = build_mock_cmd_for_cloud(cloud_name).cli_ctx.cloud
    mocker.patch("azext_edge.edge.providers.adr.validator.get_subscription_id", return_value=SUBSCRIPTION)
    mocked_azcli_cred_get_token.reset_mock()
    yield mocked_cmd, endpoint
    assert mocked_responses.calls
    assert all(call.request.url.startswith(f"{endpoint}/") for call in mocked_responses.calls)
    assert mocked_azcli_cred_get_token.call_args_list
    assert all(
        call.args == (f"{endpoint}/.default",)
        for call in mocked_azcli_cred_get_token.call_args_list
    )


def make_restore(cmd, mocker):
    return InstanceRestore(
        cmd=cmd,
        instances=mocker.Mock(),
        instance_record={},
        namespace="namespace",
        parsed_cluster_id={"subscription": OTHER_SUBSCRIPTION, "resource_group": "rg", "name": "cluster"},
        template_content=mocker.Mock(),
    )


@pytest.mark.parametrize("provider_type", ["work", "delete", "restore"])
def test_resource_client_cloud(arm_cloud, mocked_responses, mocker, provider_type):
    cmd, endpoint = arm_cloud
    if provider_type == "work":
        provider = WorkManager(cmd)
    elif provider_type == "delete":
        provider = DeletionManager(cmd, resource_group_name="rg", instance_name="instance")
    else:
        provider = make_restore(cmd, mocker)
    subscription = OTHER_SUBSCRIPTION if provider_type == "restore" else SUBSCRIPTION
    expected = {"name": "rg", "location": "test-location"}
    mocked_responses.add(
        responses.GET,
        f"{endpoint}/subscriptions/{subscription}/resourcegroups/rg?api-version=2024-03-01",
        json=expected,
    )
    assert provider.resource_client.resource_groups.get("rg") == expected


def test_work_provider_registration_cloud(arm_cloud, mocked_responses, mocker):
    cmd, endpoint = arm_cloud
    provider = WorkManager(cmd)
    provider._targets = mocker.Mock(instance_name=None)
    provider._pre_flight = True
    provider._apply_foundation = False
    provider._health_checks_max = 0
    provider._check_cluster = False
    mocker.patch("azext_edge.edge.providers.orchestration.host.verify_cli_client_connections")
    for method in ("_render_display", "_process_connected_cluster", "_complete_step",
                   "_get_user_result", "_stop_display"):
        mocker.patch.object(provider, method)
    url = f"{endpoint}/subscriptions/{SUBSCRIPTION}/providers"
    mocked_responses.add(responses.GET, url, json={"value": []})
    for namespace in RP_NAMESPACE_SET | RP_NAMESPACE_OPTIONAL_SET:
        mocked_responses.add(
            responses.POST, f"{url}/{namespace}/register", json={"namespace": namespace},
        )
    provider._do_work()
    assert len(mocked_responses.calls) == 1 + len(RP_NAMESPACE_SET | RP_NAMESPACE_OPTIONAL_SET)


@pytest.mark.parametrize("provider_type", ["work", "instances", "management-actions", "migration"])
def test_permission_client_cloud(arm_cloud, mocked_responses, mocker, provider_type):
    cmd, endpoint = arm_cloud
    if provider_type == "work":
        provider = WorkManager(cmd)
    elif provider_type == "instances":
        provider = Instances(cmd)
    elif provider_type == "management-actions":
        provider = MgmtActions(cmd, subscription_id=OTHER_SUBSCRIPTION)
    else:
        mocker.patch.object(Instances, "show", return_value={})
        provider = AssetMigrationManager(cmd, instance_name="instance", resource_group_name="rg")
    mocked_responses.add(
        responses.GET,
        f"{endpoint}{RESOURCE_ID}/providers/Microsoft.Authorization/roleAssignments",
        json={"value": [{"properties": {"roleDefinitionId": "role-id"}}]},
    )
    assert provider.permission_manager.apply_role_assignment(RESOURCE_ID, "principal-id", "role-id") is None
    expected_subscription = OTHER_SUBSCRIPTION if provider_type == "management-actions" else SUBSCRIPTION
    assert provider.permission_manager.authz_client._config.subscription_id == expected_subscription


def test_sync_rule_permission_cloud(arm_cloud, mocked_responses, mocker):
    cmd, endpoint = arm_cloud
    mocker.patch.object(Instances, "show", return_value={})
    mocker.patch.object(Instances, "get_associated_cl", return_value={"id": RESOURCE_ID, "name": "cl"})
    mocked_responses.add(
        responses.GET,
        f"{endpoint}{RESOURCE_ID}/providers/Microsoft.Authorization/roleAssignments",
        json={"value": [{"properties": {"roleDefinitionId": "role-id"}}]},
    )
    provider = SyncRules(cmd, resource_group_name="rg", instance_name="instance")
    assert provider.enable(custom_role_id="role-id", k8_bridge_sp_oid="principal-id") is None


def test_cross_subscription_eventgrid_permissions(arm_cloud, mocked_responses):
    cmd, endpoint = arm_cloud
    resource_id = (
        f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/eg-rg"
        "/providers/Microsoft.EventGrid/namespaces/eg"
    )
    ctx = EgNamespaceContext(
        resource_id=resource_id, subscription_id=OTHER_SUBSCRIPTION, resource_group_name="eg-rg",
        namespace_name="eg", mqtt_hostname="unused",
    )
    url = f"{endpoint}{resource_id}/providers/Microsoft.Authorization/roleAssignments"
    mocked_responses.add(responses.GET, url, json={"value": []})
    mocked_responses.add(responses.PUT, re.compile(re.escape(url) + r"/[0-9a-f-]+\?"), json={})
    MgmtActions(cmd)._setup_role_assignments(ctx, "adr-principal", "dataflow-principal")
    assert len(mocked_responses.calls) == 8


def test_permission_preflight_cloud(arm_cloud, mocked_responses):
    cmd, endpoint = arm_cloud
    mocked_responses.add(
        responses.GET,
        f"{endpoint}/subscriptions/{OTHER_SUBSCRIPTION}/resourcegroups/rg"
        "/providers/Microsoft.Authorization/permissions",
        json={"value": [{"actions": ["*"], "notActions": []}]},
    )
    verify_write_permission_against_rg(OTHER_SUBSCRIPTION, "rg", **CloudConfig(cmd).arm_client_kwargs)


def test_resource_health_cloud(arm_cloud, mocked_responses):
    cmd, endpoint = arm_cloud
    provider = ConnectedCluster(cmd, SUBSCRIPTION, "cluster", "rg")
    provider._resource_state = {"id": RESOURCE_ID}
    expected = {"properties": {"availabilityState": "Available"}}
    mocked_responses.add(
        responses.GET,
        f"{endpoint}{RESOURCE_ID}/providers/Microsoft.ResourceHealth/availabilityStatuses/current"
        "?api-version=2025-05-01",
        json=expected,
    )
    assert provider.get_availability_status() == expected


def test_clone_export_client_cloud(arm_cloud, mocked_responses, mocker):
    cmd, endpoint = arm_cloud
    record = get_mock_instance_record(name="instance", resource_group_name="rg")
    mocker.patch.object(Instances, "show", return_value=record)
    mocker.patch.object(Instances, "get_associated_cl", return_value={})
    mocker.patch.object(Instances, "get_resource_map")
    provider = CloneManager(cmd, "rg", "instance")
    mocked_responses.add(
        responses.GET,
        f"{endpoint}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg"
        "/providers/Microsoft.IoTOperations/instances/instance",
        json=record,
    )
    assert provider.iotops_mgmt_client.instance.get("rg", "instance") == record
    assert f"api-version={provider.api_config.iotops_mgmt_api}" in mocked_responses.calls[0].request.url


def test_clone_federation_client_cloud(arm_cloud, mocked_responses, mocker):
    cmd, endpoint = arm_cloud
    provider = make_restore(cmd, mocker)
    provider.user_assigned_mis = [
        f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/identity-rg"
        "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/identity"
    ]
    provider.connected_cluster._resource_state = {"id": RESOURCE_ID}
    provider.instances._ensure_oidc_issuer.return_value = "https://issuer.example/"
    mocker.patch(
        "azext_edge.edge.providers.orchestration.clone.resolve_oidc_issuer",
        return_value=("https://issuer.example/", True),
    )
    mocked_responses.add(
        responses.GET,
        f"{endpoint}{provider.user_assigned_mis[0]}/federatedIdentityCredentials?api-version=2023-01-31",
        json={"value": []},
    )
    provider._handle_federation()
    assert len(mocked_responses.calls) == 1


def test_adr_validation_clients_cloud(arm_cloud, mocked_responses, mocker):
    cmd, endpoint = arm_cloud
    mocker.patch.object(ConnectorMetadataValidator, "_METADATA_CACHE", {})
    namespace_id = (
        f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/device-rg"
        "/providers/Microsoft.DeviceRegistry/namespaces/ns"
    )
    mocked_responses.add(
        responses.GET,
        f"{endpoint}{namespace_id}/devices/device?api-version={DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION.value}",
        json={"properties": {"endpoints": {"inbound": {"ep": {"endpointType": "Microsoft.Http", "version": "1"}}}}},
    )
    mocked_responses.add(
        responses.GET,
        f"{endpoint}/subscriptions/{SUBSCRIPTION}/resourceGroups/instance-rg"
        "/providers/Microsoft.IoTOperations/instances/instance/akriConnectorTemplates",
        json={"value": []},
    )
    asset = {
        "id": f"{namespace_id}/assets/asset",
        "properties": {"deviceRef": {"deviceName": "device", "endpointName": "ep"}},
    }
    validator = ConnectorMetadataValidator.from_asset(cmd, asset, "instance", "instance-rg")
    assert validator.endpoint_type == "Microsoft.Http"
    assert validator.metadata is None
    assert len(mocked_responses.calls) == 2
