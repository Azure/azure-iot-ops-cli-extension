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

The lifecycle runs once per dataflow endpoint auth mode, system-assigned and
user-assigned, because the two differ in which principal receives the Event
Grid role assignments and not only in a config field.

Setup mirrors `scripts/mgmt-actions/quickstart.sh`.
"""

import json
from time import sleep, time
from typing import Dict, List, Optional
from uuid import uuid4

import pytest
from knack.log import get_logger

from azext_edge.edge.providers.orchestration.common import (
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
)
from azext_edge.edge.util.az_client import (
    DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION,
    DEFAULT_EVENTGRID_MGMT_API_VERSION,
)

from ...helpers import assert_role_assignment, create_file, remove_file, run

logger = get_logger(__name__)

# Pinned to a commit so the manifest itself cannot change under us. Note this
# pins the Kubernetes resources, not the workload: the deployment still resolves
# `opc-plc:latest` at pull time. The manifest also grants its service account
# access to namespace secrets, so it is applied only on the disposable CI
# cluster. Bump the ref deliberately.
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

ADR_API_VERSION = DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION.value
ENDPOINT_NAME = "anonymous-endpoint"
MGMT_GROUP_NAME = "managementGroup"
ACTION_NAME = "Switch"

# The connector has to reach the simulator, discover the method, and publish a
# schema before the action's schema reference appears on asset status. Connector
# driven schema publishing is off by default, so this normally times out and the
# schema dependent tests skip. Kept short enough that the wait is not the
# dominant cost of the run.
SCHEMA_READY_TIMEOUT = 180
SCHEMA_READY_INTERVAL = 20

# Role assignments created by enable have to reach the Event Grid data plane,
# and the topic space has to reach the broker. Both are slower than the ARM
# writes that precede them, and the broker caches denials, so retry intervals
# matter more here than attempt count.
EXECUTE_MAX_ATTEMPTS = 12
EXECUTE_INITIAL_INTERVAL = 30
EXECUTE_MAX_INTERVAL = 90
# `execute` is a long running operation, so a management action that never reaches
# a terminal state would otherwise block the whole job rather than fail. The action
# itself carries a 300 second timeout, so this only trips on a stuck poll.
EXECUTE_COMMAND_TIMEOUT = 420
# Attempt count alone does not bound wall clock. Twelve attempts each burning the
# command timeout is roughly 98 minutes per auth mode, and the CI job sets no
# timeout of its own, so a persistently stuck action would consume the runner
# rather than fail it. The deadline is checked between attempts, so the effective
# ceiling is this budget plus one backoff interval and one command timeout.
EXECUTE_TOTAL_TIMEOUT = 1800


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


def _log_connector_status(ns_id: str, asset_name: str, device_name: str) -> None:
    """Dump asset and device status so a timeout says why, not just that.

    The connector reports discovery and endpoint connection problems here, and
    they are the difference between a slow environment and a broken one.
    """
    from azure.cli.core.azclierror import CLIInternalError

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
        except CLIInternalError as e:
            logger.warning("Could not read %s status: %s", label, e)


def _assert_schema_readable(schema_ref: Dict, registry_id: str) -> None:
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
    be retried. Retries are deliberately broad: role assignment and topic space
    propagation surface as authorization failures that are indistinguishable
    from permanent ones, so narrowing the retry would reintroduce the very
    flakiness the backoff exists to absorb. Each attempt logs its outcome so a
    run that exhausts the budget says why.

    A per attempt timeout is required because this is a long running operation.
    An action that never reaches a terminal state would otherwise hang the job
    instead of failing, since the retry budget bounds failures and not hangs.
    An overall deadline bounds the case where every attempt burns that timeout.

    Returns the first result reporting ``Succeeded``.
    """
    import subprocess

    from azure.cli.core.azclierror import CLIInternalError

    deadline = time() + EXECUTE_TOTAL_TIMEOUT
    interval = EXECUTE_INITIAL_INTERVAL
    last_outcome = None
    for attempt in range(1, EXECUTE_MAX_ATTEMPTS + 1):
        try:
            result = run(command, timeout=EXECUTE_COMMAND_TIMEOUT)
            # `run` returns a str when stdout is not JSON and None when there is no
            # stdout, so guard before treating the result as the action payload.
            if isinstance(result, dict):
                if str(result.get("status", "")).casefold() == "succeeded":
                    return result
                logger.info(
                    "execute attempt %s/%s returned status=%s error=%s",
                    attempt,
                    EXECUTE_MAX_ATTEMPTS,
                    result.get("status"),
                    result.get("error"),
                )
            else:
                logger.info(
                    "execute attempt %s/%s returned an unexpected payload: %r",
                    attempt,
                    EXECUTE_MAX_ATTEMPTS,
                    result,
                )
            last_outcome = result
        except subprocess.TimeoutExpired:
            last_outcome = f"timed out after {EXECUTE_COMMAND_TIMEOUT}s without reaching a terminal state"
            logger.info("execute attempt %s/%s %s", attempt, EXECUTE_MAX_ATTEMPTS, last_outcome)
        except CLIInternalError as e:
            last_outcome = e
            logger.info("execute attempt %s/%s raised: %s", attempt, EXECUTE_MAX_ATTEMPTS, e)

        if time() >= deadline:
            raise AssertionError(
                f"Management action did not reach Succeeded before the {EXECUTE_TOTAL_TIMEOUT}s budget "
                f"was exhausted, after {attempt} attempts. Last outcome: {last_outcome}"
            )

        if attempt < EXECUTE_MAX_ATTEMPTS:
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


def _describe_existing_state(show_result: Dict) -> List[str]:
    """Name every mgmt-actions sub-resource that already exists.

    `show` reports `enabled` as the conjunction of every sub-resource, so a
    partially configured instance reports False. Enabling on top of that and
    disabling afterwards would delete resources the run did not create, so the
    fixture refuses on any trace rather than on `enabled` alone.
    """
    found: List[str] = []

    instance_section = show_result.get("instance") or {}
    for key in ("dataflowEndpoint", "requestDataflowGraph", "responseDataflow"):
        if (instance_section.get(key) or {}).get("exists"):
            found.append(f"instance.{key}")

    eg_section = show_result.get("eventGrid")
    if eg_section and (eg_section.get("topicSpace") or {}).get("exists"):
        found.append("eventGrid.topicSpace")

    adr_section = show_result.get("deviceRegistryNamespace") or {}
    if adr_section.get("managementEndpoint"):
        found.append("deviceRegistryNamespace.managementEndpoint")

    return found


def _ensure_eg_namespace(request, settings, resource_group: str, location: str) -> str:
    """Resolve the Event Grid namespace, creating a throwaway when none is supplied.

    uuid4 rather than generate_random_string, which is seeded in conftest and
    would produce the same name on every run against the shared test group.
    """
    eg_resource_id = settings.env.azext_edge_eg_resource_id
    if eg_resource_id:
        return eg_resource_id

    created_eg_name = f"mgmtact{uuid4().hex[:10]}"

    # Registered before creation, since an ARM write can succeed while the
    # command still fails client side, and an orphaned namespace is billable.
    def _delete_eg_namespace() -> None:
        try:
            run(f"az eventgrid namespace delete -n {created_eg_name} -g {resource_group} -y")
        except Exception:
            logger.error(f"Failed to delete Event Grid namespace {created_eg_name}.")

    request.addfinalizer(_delete_eg_namespace)
    # Unpinned deliberately. This is the first party Microsoft extension index,
    # and pinning it would be maintenance cost against a trusted source.
    run("az extension add --upgrade -n eventgrid -y")
    run(
        f"az eventgrid namespace create -n {created_eg_name} -g {resource_group} -l {location} "
        '--topic-spaces-configuration \'{"state":"Enabled","maximumClientSessionsPerAuthenticationName":8}\' '
        '--sku \'{"name":"Standard","capacity":1}\''
    )
    return run(f"az eventgrid namespace show -n {created_eg_name} -g {resource_group}")["id"]


def _deploy_opc_plc_simulator(request) -> None:
    """Apply the OPC PLC simulator the asset's action is invoked against."""

    def _delete_opc_plc() -> None:
        try:
            run(f"kubectl delete -f {OPC_PLC_MANIFEST} --ignore-not-found")
        except Exception:
            logger.error("Failed to delete the OPC PLC simulator manifest.")

    # CI runs on a disposable cluster, but a local or shared cluster keeps the
    # simulator and its RBAC until something removes them.
    request.addfinalizer(_delete_opc_plc)
    run(f"kubectl apply -f {OPC_PLC_MANIFEST}")
    run(
        f"kubectl wait --for=condition=available deployment/{OPC_PLC_DEPLOYMENT} "
        f"-n {AIO_CLUSTER_NAMESPACE} --timeout=300s"
    )


@pytest.fixture(scope="module")
def user_assigned_mi(request, settings) -> str:
    """A user-assigned managed identity, assigned and federated for dataflow use.

    Federation is the load-bearing part. `mgmt-actions enable --mi-user-assigned`
    only writes the client and tenant ids into the dataflow endpoint auth block,
    it does not federate anything, so an identity that has not been through
    `az iot ops identity assign` cannot obtain a token and the action never
    reaches a terminal state.

    Reuses a caller supplied identity when one is configured, otherwise creates
    a throwaway. Named with uuid4 rather than the seeded `generate_random_string`,
    which repeats across runs against the shared test resource group.
    """
    from ...settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.user_assigned_mi_id.value)
    resource_group = settings.env.azext_edge_rg
    instance_name = settings.env.azext_edge_instance

    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not mi_id:
        mi_name = f"mgmtact-mi-{uuid4().hex[:8]}"

        def _delete_mi() -> None:
            try:
                run(f"az identity delete -n {mi_name} -g {resource_group}")
            except Exception:
                logger.error(f"Failed to delete managed identity {mi_name}.")

        # Registered before creation so a client-side failure on a completed ARM
        # write still gets cleaned up.
        request.addfinalizer(_delete_mi)
        mi_id = run(f"az identity create -n {mi_name} -g {resource_group}")["id"]

        # Only unwind the assignment for an identity this fixture owns. A caller
        # supplied identity may be federated for other purposes, and removing it
        # would strip state the test did not create. Registered after _delete_mi
        # so it runs first, unassigning before the identity goes away.
        def _remove_identity() -> None:
            try:
                run(
                    f"az iot ops identity remove -n {instance_name} -g {resource_group} "
                    f'--mi-user-assigned "{mi_id}"'
                )
            except Exception:
                logger.error(f"Failed to remove user-assigned identity {mi_id} from {instance_name}.")

        request.addfinalizer(_remove_identity)

    # Defaults to the dataflow usage type, which is the path mgmt-actions uses.
    # Run for a supplied identity too, since it is what makes the identity usable
    # and re-assigning an already assigned identity is not destructive.
    run(f'az iot ops identity assign -n {instance_name} -g {resource_group} --mi-user-assigned "{mi_id}"')
    return mi_id


@pytest.fixture(scope="module")
def mgmt_actions_setup(request, settings, tracked_files):
    """Provision the prerequisite scenario and clean it up afterwards.

    Requires an existing IoT Operations instance whose cluster is reachable via
    kubectl. Creates an Event Grid namespace when one is not supplied.
    """
    from ...settings import EnvironmentVariables, convert_flag

    for var in (
        EnvironmentVariables.rg,
        EnvironmentVariables.instance,
        EnvironmentVariables.eg_resource_id,
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
    # pointing at the wrong resources. Refuse instead. `enabled` alone is not a
    # sufficient check, since it is the conjunction of every sub-resource and a
    # half configured instance reports False.
    initial_state = run(f"az iot ops mgmt-actions show -i {instance_name} -g {resource_group}")
    existing_state = _describe_existing_state(initial_state)
    if existing_state:
        pytest.skip(
            f"Instance '{instance_name}' already carries mgmt-actions state: {', '.join(existing_state)}. "
            "This test enables and disables mgmt-actions, which would delete resources it did not create. "
            "Run against a fresh instance, or disable it first."
        )

    eg_resource_id = _ensure_eg_namespace(
        request=request, settings=settings, resource_group=resource_group, location=location
    )

    device_name = f"mgmtact-device-{uuid4().hex[:8]}"
    asset_name = f"mgmtact-asset-{uuid4().hex[:8]}"
    common = f"-i {instance_name} -g {resource_group}"

    def _delete_device() -> None:
        try:
            run(f"az iot ops ns device delete -n {device_name} {common} -y")
        except Exception:
            logger.error(f"Failed to delete device {device_name}.")

    def _delete_asset() -> None:
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
        _deploy_opc_plc_simulator(request)

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
        tracked_files=tracked_files,
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


def _list_topic_space_names(eg_resource_id: str) -> List[str]:
    """Every topic space on the namespace, following pagination.

    ARM list responses page, so reading only the first page would let a
    surviving topic space pass a teardown assertion unnoticed.
    """
    url = (
        f"https://management.azure.com{eg_resource_id}/topicSpaces"
        f"?api-version={DEFAULT_EVENTGRID_MGMT_API_VERSION.value}"
    )
    names: List[str] = []
    while url:
        page = run(f'az rest --method get --url "{url}"')
        names.extend(space["name"] for space in page.get("value", []))
        url = page.get("nextLink")
    return names


def _assert_sub_resources_exist(show_result: Dict) -> None:
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
@pytest.mark.parametrize("auth_mode", ["systemAssigned", "userAssigned"])
def test_mgmt_actions_lifecycle(request, mgmt_actions_setup, auth_mode: str) -> None:
    """enable -> show -> execute -> disable, plus idempotency on both mutating commands.

    Runs once per dataflow endpoint auth mode, because the two differ in more
    than a config field: a user-assigned identity also changes which principal
    receives the Event Grid role assignments. `execute` is the load-bearing
    assertion for both, since it proves the identity actually authenticates to
    the broker rather than only proving the CLI wrote the right ARM resources.
    """
    instance_name = mgmt_actions_setup["instanceName"]
    resource_group = mgmt_actions_setup["resourceGroup"]
    eg_resource_id = mgmt_actions_setup["egResourceId"]
    asset_name = mgmt_actions_setup["assetName"]

    common = f"-i {instance_name} -g {resource_group}"

    # Only materialized for the user-assigned case, so the system-assigned run
    # does not create an identity it never uses.
    mi_id = request.getfixturevalue("user_assigned_mi") if auth_mode == "userAssigned" else None
    enable_command = f'az iot ops mgmt-actions enable {common} --eg-resource-id "{eg_resource_id}"'
    if mi_id:
        enable_command += f' --mi-user-assigned "{mi_id}"'

    # --- Baseline ---
    before = run(f"az iot ops mgmt-actions show {common}")
    assert before["enabled"] is False, "expected a clean baseline, mgmt-actions reported enabled"

    # The fixture is module scoped and this test is parametrized, so a failure after
    # enable would leave the next auth mode facing a dirty baseline. It would then
    # fail on the assertion above rather than running, losing all coverage of that
    # mode and reporting the wrong cause.
    def _ensure_disabled() -> None:
        try:
            run(f"az iot ops mgmt-actions disable {common} -y")
        except Exception:
            logger.error(f"Failed to disable mgmt-actions after the {auth_mode} lifecycle test.")

    request.addfinalizer(_ensure_disabled)

    # --- Enable ---
    enable_result = run(enable_command)
    topic_space_name = enable_result["eventGrid"]["topicSpace"]["name"]
    assert topic_space_name
    assert enable_result["instance"]["requestDataflowGraph"]["name"]

    # The endpoint auth block is the difference between the two modes.
    expected_method = "UserAssignedManagedIdentity" if mi_id else "SystemAssignedManagedIdentity"
    endpoint_auth = enable_result["instance"]["dataflowEndpoint"]["authentication"]
    assert endpoint_auth["method"] == expected_method, f"unexpected endpoint auth: {endpoint_auth}"

    # Permission bindings are created against the `$all` client group today.
    # This block is expected to be removed alongside the binding creation itself.
    assert enable_result["eventGrid"]["permissionBindings"]["publisher"]["name"]
    assert enable_result["eventGrid"]["permissionBindings"]["subscriber"]["name"]

    # --- Show reflects reality ---
    after_enable = run(f"az iot ops mgmt-actions show {common}")
    _assert_sub_resources_exist(after_enable)

    # --- Role assignments landed at Event Grid namespace scope ---
    # enable reports both principals it granted. Assert it claims the right
    # roles, then assert those claims are true at the scope. The dataflow
    # identity is the AIO extension MI or the supplied UAMI depending on mode.
    expected_roles = {EG_TOPICSPACES_PUBLISHER_ROLE_ID, EG_TOPICSPACES_SUBSCRIBER_ROLE_ID}
    role_assignments = enable_result["roleAssignments"]
    for identity_key in ("adrNamespace", "dataflowIdentity"):
        granted = role_assignments[identity_key]
        assert granted["principalId"], f"{identity_key} has no principal after enable"
        assert set(granted["roles"]) == expected_roles, f"unexpected roles for {identity_key}: {granted['roles']}"
        assert_role_assignment(
            scope=eg_resource_id,
            assignee=granted["principalId"],
            expected_role_ids=granted["roles"],
        )
    if mi_id:
        assert role_assignments["dataflowIdentity"]["principalId"] != role_assignments["adrNamespace"][
            "principalId"
        ], "user-assigned identity should not be the ADR namespace principal"

    # --- Enable is idempotent ---
    run(enable_command)
    _assert_sub_resources_exist(run(f"az iot ops mgmt-actions show {common}"))

    # --- Execute, the end to end proof ---
    execute_result = _execute_with_retry(
        f"az iot ops mgmt-actions execute {common} --asset {asset_name} "
        f"--group {MGMT_GROUP_NAME} --action {ACTION_NAME} -p '{{\"On\": true}}'"
    )
    logger.info("execute result: %s", json.dumps(execute_result, indent=2))
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
    assert topic_space_name not in _list_topic_space_names(eg_resource_id)

    # --- Disable is idempotent ---
    run(f"az iot ops mgmt-actions disable {common} -y")


@pytest.mark.mgmtactions
@pytest.mark.serial
def test_mgmt_actions_execute_show_schema(mgmt_actions_setup) -> None:
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
def test_mgmt_actions_execute_payload_validation(mgmt_actions_setup) -> None:
    """A payload that violates the request schema is rejected before any call.

    The Switch schema requires a boolean `On` and sets additionalProperties
    false, so this payload fails on both counts. Client-side validation, so it
    does not depend on mgmt-actions being enabled.

    Asserts the schema validation message specifically. `expect_failure` alone
    would also pass on a missing asset, a quoting mistake, or an auth error,
    none of which prove validation ran.
    """
    from azure.cli.core.azclierror import CLIInternalError

    instance_name = mgmt_actions_setup["instanceName"]
    resource_group = mgmt_actions_setup["resourceGroup"]
    asset_name = mgmt_actions_setup["assetName"]
    if not mgmt_actions_setup["schemaRef"]:
        pytest.skip("The connector did not publish a request schema, so there is nothing to validate against.")

    # run() surfaces stderr as the CLIInternalError message, which is where the
    # validation detail lands. expect_failure would discard it.
    with pytest.raises(CLIInternalError) as exc_info:
        run(
            f"az iot ops mgmt-actions execute -i {instance_name} -g {resource_group} "
            f"--asset {asset_name} --group {MGMT_GROUP_NAME} --action {ACTION_NAME} "
            f"-p '{{\"bad1\": true}}'"
        )

    assert "The following payload values are invalid" in str(exc_info.value), (
        f"expected schema validation to reject the payload, got: {exc_info.value}"
    )
