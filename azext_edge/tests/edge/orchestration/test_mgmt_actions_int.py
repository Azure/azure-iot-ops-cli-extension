# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Integration coverage for the `az iot ops mgmt-actions` command group.

Exercises the full lifecycle against live Azure and a live cluster: enable,
show, execute, and disable. The `execute` phase is the part that proves the
system works end to end, since it round trips a real management action through
Event Grid MQTT, the dataflow graph, and the connector.

Setup mirrors `scripts/mgmt-actions/quickstart.sh`.
"""

import json
from time import sleep, time
from typing import Dict, Optional
from uuid import uuid4

import pytest
from knack.log import get_logger

from azext_edge.edge.providers.orchestration.common import (
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
)
from azext_edge.edge.util.az_client import DEFAULT_EVENTGRID_MGMT_API_VERSION

from ...helpers import assert_role_assignment, create_file, remove_file, run

logger = get_logger(__name__)

# Pinned to a commit rather than main. This is applied with a cluster-admin
# kubeconfig on the CI runner, so a mutable ref would let upstream changes run
# arbitrary workload next to live Azure credentials. Bump deliberately.
OPC_PLC_MANIFEST_REF = "b2bc8c8d333ac7a6b42c35ba1e83a68ac5b48a42"
OPC_PLC_MANIFEST = (
    "https://raw.githubusercontent.com/Azure-Samples/explore-iot-operations"
    f"/{OPC_PLC_MANIFEST_REF}/samples/quickstarts/opc-plc-deployment.yaml"
)
OPC_PLC_ADDRESS = "opc.tcp://opcplc-000000.azure-iot-operations:50000"
OPC_PLC_DEPLOYMENT = "opc-plc-000000"
AIO_CLUSTER_NAMESPACE = "azure-iot-operations"
# Boiler node on the OPC PLC simulator, matching the quickstart.
OPC_PLC_TARGET_URI = "nsu=http://microsoft.com/Opc/OpcPlc/Boiler;i=7019"

ADR_API_VERSION = "2026-04-01"
ENDPOINT_NAME = "anonymous-endpoint"
MGMT_GROUP_NAME = "managementGroup"
ACTION_NAME = "Switch"

# The connector has to reach the simulator, discover the method, and publish a
# schema before the action's schema reference appears on asset status.
SCHEMA_READY_TIMEOUT = 600
SCHEMA_READY_INTERVAL = 20

# Role assignments created by enable have to reach the Event Grid data plane,
# and the topic space has to reach the broker. Both are slower than the ARM
# writes that precede them, and the broker caches denials, so retry intervals
# matter more here than attempt count.
EXECUTE_MAX_ATTEMPTS = 12
EXECUTE_INITIAL_INTERVAL = 30
EXECUTE_MAX_INTERVAL = 90


def _wait_for_action_schema(ns_id: str, asset_name: str, device_name: str) -> Optional[Dict]:
    """Wait for the connector to publish the action's request schema.

    Returns the reference, or None when it never appears. The connector has to
    reach the simulator and introspect the method to produce this, so treat its
    absence as a missing prerequisite rather than a failure of the commands
    under test.
    """

    def _get_schema_ref():
        asset = run(
            "az rest --method get --url "
            f'"https://management.azure.com{ns_id}/assets/{asset_name}?api-version={ADR_API_VERSION}"'
        )
        for group in asset.get("properties", {}).get("status", {}).get("managementGroups", []):
            if group.get("name") != MGMT_GROUP_NAME:
                continue
            for action in group.get("actions", []):
                if action.get("name") == ACTION_NAME:
                    return action.get("requestMessageSchemaReference")
        return None

    deadline = time() + SCHEMA_READY_TIMEOUT
    while True:
        schema_ref = _get_schema_ref()
        if schema_ref:
            return schema_ref
        if time() >= deadline:
            logger.warning(
                "No request schema reference on asset %s after %ss. Schema dependent tests will skip.",
                asset_name,
                SCHEMA_READY_TIMEOUT,
            )
            _log_connector_status(ns_id=ns_id, asset_name=asset_name, device_name=device_name)
            return None
        sleep(SCHEMA_READY_INTERVAL)


def _log_connector_status(ns_id: str, asset_name: str, device_name: str):
    """Dump asset and device status so a timeout says why, not just that.

    The connector reports discovery and endpoint connection problems here, and
    they are the difference between a slow environment and a broken one.
    """
    for label, resource_id in (
        ("asset", f"{ns_id}/assets/{asset_name}"),
        ("device", f"{ns_id}/devices/{device_name}"),
    ):
        try:
            resource = run(
                "az rest --method get --url "
                f'"https://management.azure.com{resource_id}?api-version={ADR_API_VERSION}"'
            )
            status = resource.get("properties", {}).get("status")
            logger.warning("%s status at timeout: %s", label, json.dumps(status, indent=2))
        except Exception as e:
            logger.warning("Could not read %s status: %s", label, e)


def _assert_schema_readable(schema_ref: Dict, registry_id: str):
    """Read the published schema version directly.

    The CLI resolves this same version when validating a payload, but it treats
    every failure as a soft miss and reports one message for all of them. Read
    it here so a permissions or registry problem is distinguishable from the
    connector not having published yet.
    """
    from azext_edge.edge.util.id_tools import parse_resource_id

    parsed = parse_resource_id(registry_id)
    run(
        f"az iot ops schema version show --version {schema_ref['schemaVersion']} "
        f"--schema {schema_ref['schemaName']} --registry {parsed['name']} -g {parsed['resource_group']}"
    )


def _execute_with_retry(command: str) -> Dict:
    """Run a management action, retrying while the deployment settles.

    A device-level failure comes back as a normal result carrying
    ``status: "Failed"`` rather than a non-zero exit, so both outcomes have to
    be retried. Returns the first result reporting ``Succeeded``.
    """
    from azure.cli.core.azclierror import CLIInternalError

    interval = EXECUTE_INITIAL_INTERVAL
    last_outcome = None
    for attempt in range(1, EXECUTE_MAX_ATTEMPTS + 1):
        try:
            result = run(command)
            if str(result.get("status", "")).casefold() == "succeeded":
                return result
            last_outcome = result
        except CLIInternalError as e:
            last_outcome = e

        if attempt < EXECUTE_MAX_ATTEMPTS:
            logger.info(f"execute attempt {attempt} did not succeed, retrying in {interval}s.")
            sleep(interval)
            interval = min(int(interval * 1.5), EXECUTE_MAX_INTERVAL)

    raise AssertionError(
        f"Management action did not reach Succeeded within {EXECUTE_MAX_ATTEMPTS} attempts. "
        f"Last outcome: {last_outcome}"
    )


def _build_asset_body(
    location: str,
    extended_location: str,
    asset_name: str,
    device_name: str,
) -> Dict:
    """Asset with a management group and one callable action.

    Sent as a single ARM PUT rather than three `az iot ops ns asset` commands.
    """
    topic = f"azure-iot-operations/asset-operations/{asset_name}/{MGMT_GROUP_NAME}/{ACTION_NAME}/test"
    return {
        "location": location,
        "extendedLocation": {"name": extended_location, "type": "CustomLocation"},
        "properties": {
            "enabled": True,
            "displayName": asset_name,
            "deviceRef": {"deviceName": device_name, "endpointName": ENDPOINT_NAME},
            "defaultDatasetsConfiguration": "{}",
            "defaultEventsConfiguration": "{}",
            "managementGroups": [
                {
                    "name": MGMT_GROUP_NAME,
                    "dataSource": device_name,
                    "actions": [
                        {
                            "name": ACTION_NAME,
                            "targetUri": OPC_PLC_TARGET_URI,
                            "topic": topic,
                            "actionType": "Call",
                            "timeoutInSeconds": 300,
                        }
                    ],
                }
            ],
        },
    }


@pytest.fixture(scope="module")
def mgmt_actions_setup(request, settings):
    """Provision the prerequisite scenario and clean it up afterwards.

    Requires an existing IoT Operations instance whose cluster is reachable via
    kubectl. Creates an Event Grid namespace when one is not supplied.
    """
    from ...settings import EnvironmentVariables, convert_flag

    for var in (
        EnvironmentVariables.rg,
        EnvironmentVariables.instance,
        EnvironmentVariables.eg_resource_id,
        EnvironmentVariables.user_assigned_mi_id,
    ):
        settings.add_to_config(var.value)
    settings.add_to_config(EnvironmentVariables.mgmt_actions_skip_opc_plc.value, conversion=convert_flag)

    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg
    if not all([instance_name, resource_group]):
        raise AssertionError(
            "Cannot run mgmt-actions tests without an instance and resource group. "
            f"Current settings:\n {settings}"
        )

    # Instance metadata. Devices and assets must be co-located with the ADR namespace.
    instance = run(f"az iot ops show -n {instance_name} -g {resource_group}")
    ns_id = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
    extended_location = instance.get("extendedLocation", {}).get("name")
    if not ns_id:
        raise AssertionError(
            f"Instance '{instance_name}' has no ADR namespace reference, which mgmt-actions requires."
        )

    location = run(f'az resource show --ids "{ns_id}"')["location"]

    # A pre-existing enablement cannot be faithfully restored. The original Event
    # Grid namespace, identity, dataflow profile and role settings are not all
    # recoverable from `show`, so a partial restore would leave the instance
    # pointing at the wrong resources. Refuse instead.
    initial_state = run(f"az iot ops mgmt-actions show -i {instance_name} -g {resource_group}")
    if initial_state.get("enabled"):
        pytest.skip(
            f"mgmt-actions is already enabled on instance '{instance_name}'. "
            "This test disables and re-enables it, which would not restore the original configuration. "
            "Run against a fresh instance, or disable it first."
        )

    # Event Grid namespace, created only when the caller did not supply one.
    # uuid4 rather than generate_random_string, which is seeded in conftest and
    # would produce the same name on every run against the shared test group.
    eg_resource_id = settings.env.azext_edge_eg_resource_id
    if not eg_resource_id:
        created_eg_name = f"mgmtact{uuid4().hex[:10]}"
        run("az extension add --upgrade -n eventgrid -y")
        run(
            f"az eventgrid namespace create -n {created_eg_name} -g {resource_group} -l {location} "
            '--topic-spaces-configuration \'{"state":"Enabled","maximumClientSessionsPerAuthenticationName":8}\' '
            '--sku \'{"name":"Standard","capacity":1}\''
        )

        # Registered immediately, since teardown after the yield does not run
        # when setup fails partway.
        def _delete_eg_namespace():
            try:
                run(f"az eventgrid namespace delete -n {created_eg_name} -g {resource_group} -y")
            except Exception:
                logger.error(f"Failed to delete Event Grid namespace {created_eg_name}.")

        request.addfinalizer(_delete_eg_namespace)
        eg_resource_id = run(f"az eventgrid namespace show -n {created_eg_name} -g {resource_group}")["id"]

    device_name = f"mgmtact-device-{uuid4().hex[:8]}"
    asset_name = f"mgmtact-asset-{uuid4().hex[:8]}"
    common = f"-i {instance_name} -g {resource_group}"

    def _delete_device():
        try:
            run(f"az iot ops ns device delete -n {device_name} {common} -y")
        except Exception:
            logger.error(f"Failed to delete device {device_name}.")

    def _delete_asset():
        try:
            run(
                f"az rest --method delete "
                f'--url "https://management.azure.com{ns_id}/assets/{asset_name}?api-version={ADR_API_VERSION}"'
            )
        except Exception:
            logger.error(f"Failed to delete asset {asset_name}.")

    # Ordering follows the quickstart: device, then simulator, then the endpoint
    # that points at it.
    request.addfinalizer(_delete_device)
    run(f"az iot ops ns device create -n {device_name} {common}")

    if not settings.env.azext_edge_mgmt_actions_skip_opc_plc:
        run(f"kubectl apply -f {OPC_PLC_MANIFEST}")
        run(
            f"kubectl wait --for=condition=available deployment/{OPC_PLC_DEPLOYMENT} "
            f"-n {AIO_CLUSTER_NAMESPACE} --timeout=300s"
        )

    run(
        f"az iot ops ns device endpoint inbound add opcua --name {ENDPOINT_NAME} "
        f"--device {device_name} {common} --address {OPC_PLC_ADDRESS} --ac true --ad false"
    )

    # Asset goes in via raw ARM. See _build_asset_body.
    asset_body = _build_asset_body(
        location=location,
        extended_location=extended_location,
        asset_name=asset_name,
        device_name=device_name,
    )
    body_file = create_file(
        file_name=f"mgmt_actions_asset_{asset_name}.json",
        module_file=__file__,
        tracked_files=[],
        content=json.dumps(asset_body),
    )
    request.addfinalizer(_delete_asset)
    try:
        run(
            f"az rest --method put "
            f'--url "https://management.azure.com{ns_id}/assets/{asset_name}?api-version={ADR_API_VERSION}" '
            f'--body "@{body_file}"'
        )
    finally:
        remove_file(body_file)

    schema_ref = _wait_for_action_schema(ns_id=ns_id, asset_name=asset_name, device_name=device_name)
    if schema_ref:
        registry_id = instance.get("properties", {}).get("schemaRegistryRef", {}).get("resourceId")
        assert registry_id, "Instance has no schema registry reference, which schema resolution requires."
        _assert_schema_readable(schema_ref=schema_ref, registry_id=registry_id)

    yield {
        "instanceName": instance_name,
        "resourceGroup": resource_group,
        "egResourceId": eg_resource_id,
        "deviceName": device_name,
        "assetName": asset_name,
        "schemaRef": schema_ref,
    }

    # mgmt-actions is torn down first so the asset is not in use. The resource
    # finalizers registered above run after this.
    try:
        run(f"az iot ops mgmt-actions disable {common} -y")
    except Exception:
        logger.error("Failed to disable mgmt-actions during teardown.")


def _assert_sub_resources_exist(show_result: Dict):
    """Every sub-resource `show` reports should exist once enable has completed."""
    assert show_result["enabled"] is True, f"show reported disabled after enable: {show_result}"

    instance_section = show_result["instance"]
    assert instance_section["dataflowEndpoint"]["exists"] is True
    assert instance_section["requestDataflowGraph"]["exists"] is True
    assert instance_section["responseDataflow"]["exists"] is True

    eg_section = show_result["eventGrid"]
    assert eg_section is not None, "eventGrid section was null, the management endpoint was not discoverable"
    assert eg_section["topicSpace"]["exists"] is True

    adr_section = show_result["deviceRegistryNamespace"]
    assert adr_section is not None
    assert adr_section["managementEndpoint"] is not None, "ADR management endpoint entry missing"
    assert adr_section["managementEndpoint"]["address"]


@pytest.mark.mgmtactions
@pytest.mark.serial
def test_mgmt_actions_lifecycle(mgmt_actions_setup):
    """enable -> show -> execute -> disable, plus idempotency on both mutating commands.

    `execute` is the load-bearing assertion. It proves a management action round
    trips through Event Grid MQTT rather than merely proving the CLI created the
    right ARM resources.
    """
    instance_name = mgmt_actions_setup["instanceName"]
    resource_group = mgmt_actions_setup["resourceGroup"]
    eg_resource_id = mgmt_actions_setup["egResourceId"]
    asset_name = mgmt_actions_setup["assetName"]

    common = f"-i {instance_name} -g {resource_group}"

    # --- Baseline ---
    before = run(f"az iot ops mgmt-actions show {common}")
    assert before["enabled"] is False, "expected a clean baseline, mgmt-actions reported enabled"

    # --- Enable ---
    enable_result = run(f'az iot ops mgmt-actions enable {common} --eg-resource-id "{eg_resource_id}"')
    topic_space_name = enable_result["eventGrid"]["topicSpace"]["name"]
    assert topic_space_name
    assert enable_result["instance"]["requestDataflowGraph"]["name"]

    # Permission bindings are created against the `$all` client group today.
    # This block is expected to be removed alongside the binding creation itself.
    assert enable_result["eventGrid"]["permissionBindings"]["publisher"]["name"]
    assert enable_result["eventGrid"]["permissionBindings"]["subscriber"]["name"]

    # --- Show reflects reality ---
    after_enable = run(f"az iot ops mgmt-actions show {common}")
    _assert_sub_resources_exist(after_enable)

    # --- Role assignments landed at Event Grid namespace scope ---
    adr_principal = enable_result["deviceRegistryNamespace"]["identity"]["principalId"]
    assert adr_principal, "ADR namespace has no system-assigned principal after enable"
    assert_role_assignment(
        scope=eg_resource_id,
        assignee=adr_principal,
        expected_role_ids=[EG_TOPICSPACES_PUBLISHER_ROLE_ID, EG_TOPICSPACES_SUBSCRIBER_ROLE_ID],
    )

    # --- Enable is idempotent ---
    run(f'az iot ops mgmt-actions enable {common} --eg-resource-id "{eg_resource_id}"')
    _assert_sub_resources_exist(run(f"az iot ops mgmt-actions show {common}"))

    # --- Execute, the end to end proof ---
    execute_result = _execute_with_retry(
        f"az iot ops mgmt-actions execute {common} --asset {asset_name} "
        f"--group {MGMT_GROUP_NAME} --action {ACTION_NAME} -p '{{\"On\": true}}'"
    )
    logger.info("execute result: %s", json.dumps(execute_result, indent=2))
    assert execute_result["status"] == "Succeeded", f"management action did not succeed: {execute_result}"
    assert not execute_result.get("error"), f"management action reported an error: {execute_result['error']}"

    # --- Disable tears down every sub-resource ---
    run(f"az iot ops mgmt-actions disable {common} -y")
    after_disable = run(f"az iot ops mgmt-actions show {common}")
    assert after_disable["enabled"] is False
    assert after_disable["instance"]["requestDataflowGraph"]["exists"] is False
    assert after_disable["instance"]["responseDataflow"]["exists"] is False
    assert after_disable["instance"]["dataflowEndpoint"]["exists"] is False

    # show discovers Event Grid through the ADR management endpoint, so removing that entry
    # takes the whole eventGrid section with it. Assert the endpoint is gone, then check the
    # Event Grid side directly since show can no longer reach it.
    assert after_disable["deviceRegistryNamespace"]["managementEndpoint"] is None
    assert after_disable["eventGrid"] is None

    remaining = run(
        "az rest --method get --url "
        f'"https://management.azure.com{eg_resource_id}/topicSpaces'
        f'?api-version={DEFAULT_EVENTGRID_MGMT_API_VERSION.value}"'
    )
    remaining_names = [ts["name"] for ts in remaining.get("value", [])]
    assert topic_space_name not in remaining_names, f"topic space survived disable: {remaining_names}"

    # --- Disable is idempotent ---
    run(f"az iot ops mgmt-actions disable {common} -y")


@pytest.mark.mgmtactions
@pytest.mark.serial
def test_mgmt_actions_execute_show_schema(mgmt_actions_setup):
    """`--show-schema` resolves the request schema without executing anything."""
    instance_name = mgmt_actions_setup["instanceName"]
    resource_group = mgmt_actions_setup["resourceGroup"]
    asset_name = mgmt_actions_setup["assetName"]
    if not mgmt_actions_setup["schemaRef"]:
        pytest.skip("The connector did not publish a request schema for this action.")

    result = run(
        f"az iot ops mgmt-actions execute -i {instance_name} -g {resource_group} "
        f"--asset {asset_name} --group {MGMT_GROUP_NAME} --action {ACTION_NAME} --show-schema"
    )
    assert result["type"] == "object"
    assert "On" in result["properties"], f"Switch request schema missing the On property: {result}"


@pytest.mark.mgmtactions
@pytest.mark.serial
def test_mgmt_actions_execute_payload_validation(mgmt_actions_setup):
    """A payload that violates the request schema is rejected before any call.

    The Switch schema requires a boolean `On` and sets additionalProperties
    false, so this payload fails on both counts. Client-side validation, so it
    does not depend on mgmt-actions being enabled.
    """
    instance_name = mgmt_actions_setup["instanceName"]
    resource_group = mgmt_actions_setup["resourceGroup"]
    asset_name = mgmt_actions_setup["assetName"]
    if not mgmt_actions_setup["schemaRef"]:
        pytest.skip("The connector did not publish a request schema, so there is nothing to validate against.")

    run(
        f"az iot ops mgmt-actions execute -i {instance_name} -g {resource_group} "
        f"--asset {asset_name} --group {MGMT_GROUP_NAME} --action {ACTION_NAME} "
        f'-p "{{\\"bad1\\": true}}"',
        expect_failure=True,
    )
