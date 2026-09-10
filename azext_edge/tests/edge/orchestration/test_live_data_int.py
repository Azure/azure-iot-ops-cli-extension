# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Integration coverage for the `az iot ops live-data` command group.

Exercises the full lifecycle against live Azure: enable, show, and disable,
including idempotency on both mutating commands and role-assignment landing at
the selected scope.

The lifecycle runs once per outbound identity mode, system-assigned and
user-assigned, because the two differ in which principal the Event Grid role
assignments target and in the ADR namespace outbound identity written, not only
in a config field. Unlike mgmt-actions there is no CLI `execute` equivalent —
per-session data flow is owned by DOE — so the assertions cover the ARM
resources the CLI provisions and the role assignments it grants.
"""

from typing import Dict, List
from uuid import uuid4

import pytest
from knack.log import get_logger

from azext_edge.edge.providers.orchestration.common import (
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
)
from azext_edge.edge.util.az_client import DEFAULT_EVENTGRID_MGMT_API_VERSION

from ...helpers import assert_role_assignment, run

logger = get_logger(__name__)


def _describe_existing_state(show_result: Dict) -> List[str]:
    """Name every Live Data sub-resource that already exists.

    `show` reports `enabled` as the conjunction of every sub-resource, so a
    partially configured instance reports False. Enabling on top of that and
    disabling afterwards would delete resources the run did not create, so the
    fixture refuses on any trace rather than on `enabled` alone.
    """
    found: List[str] = []

    instance_section = show_result.get("instance") or {}
    for key in ("dataflowProfile", "dataflowEndpoint"):
        if (instance_section.get(key) or {}).get("exists"):
            found.append(f"instance.{key}")

    eg_section = show_result.get("eventGrid")
    if eg_section and (eg_section.get("topicSpace") or {}).get("exists"):
        found.append("eventGrid.topicSpace")

    adr_section = show_result.get("deviceRegistryNamespace") or {}
    if adr_section.get("observabilityEndpoint"):
        found.append("deviceRegistryNamespace.observabilityEndpoint")

    return found


def _assert_sub_resources_exist(show_result: Dict) -> None:
    """Every sub-resource `show` reports should exist once enable has completed."""
    assert show_result["enabled"] is True, f"show reported disabled after enable: {show_result}"

    instance_section = show_result["instance"]
    assert instance_section["dataflowProfile"]["exists"] is True
    assert instance_section["dataflowEndpoint"]["exists"] is True

    eg_section = show_result["eventGrid"]
    assert eg_section is not None, "eventGrid section was null, the observability endpoint was not discoverable"
    assert eg_section["topicSpace"]["exists"] is True

    adr_section = show_result["deviceRegistryNamespace"]
    assert adr_section is not None
    assert adr_section["observabilityEndpoint"] is not None, "ADR observability endpoint entry missing"
    assert adr_section["observabilityEndpoint"]["address"]


def _list_topic_space_names(eg_resource_id: str) -> List[str]:
    """Every topic space on the namespace, following pagination."""
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


def _ensure_eg_namespace(request, settings, resource_group: str, location: str) -> str:
    """Resolve the Event Grid namespace, creating a throwaway when none is supplied."""
    eg_resource_id = settings.env.azext_edge_eg_resource_id
    if eg_resource_id:
        return eg_resource_id

    created_eg_name = f"livedata{uuid4().hex[:10]}"

    def _delete_eg_namespace() -> None:
        try:
            run(f"az eventgrid namespace delete -n {created_eg_name} -g {resource_group} -y")
        except Exception:
            logger.error(f"Failed to delete Event Grid namespace {created_eg_name}.")

    request.addfinalizer(_delete_eg_namespace)
    run("az extension add --upgrade -n eventgrid -y")
    run(
        f"az eventgrid namespace create -n {created_eg_name} -g {resource_group} -l {location} "
        '--topic-spaces-configuration \'{"state":"Enabled","maximumClientSessionsPerAuthenticationName":8}\' '
        '--sku \'{"name":"Standard","capacity":1}\''
    )
    return run(f"az eventgrid namespace show -n {created_eg_name} -g {resource_group}")["id"]


@pytest.fixture(scope="module")
def user_assigned_mi(request, settings) -> str:
    """A user-assigned managed identity, assigned to the instance for dataflow use.

    Reuses a caller-supplied identity when configured, otherwise creates a
    throwaway. Named with uuid4 rather than the seeded generate_random_string,
    which repeats across runs against the shared test resource group.
    """
    from ...settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.user_assigned_mi_id.value)
    resource_group = settings.env.azext_edge_rg
    instance_name = settings.env.azext_edge_instance

    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not mi_id:
        mi_name = f"livedata-mi-{uuid4().hex[:8]}"

        def _delete_mi() -> None:
            try:
                run(f"az identity delete -n {mi_name} -g {resource_group}")
            except Exception:
                logger.error(f"Failed to delete managed identity {mi_name}.")

        request.addfinalizer(_delete_mi)
        mi_id = run(f"az identity create -n {mi_name} -g {resource_group}")["id"]

        def _remove_identity() -> None:
            try:
                run(
                    f"az iot ops identity remove -n {instance_name} -g {resource_group} "
                    f'--mi-user-assigned "{mi_id}"'
                )
            except Exception:
                logger.error(f"Failed to remove user-assigned identity {mi_id} from {instance_name}.")

        request.addfinalizer(_remove_identity)

    run(f'az iot ops identity assign -n {instance_name} -g {resource_group} --mi-user-assigned "{mi_id}"')
    return mi_id


@pytest.fixture(scope="module")
def live_data_setup(request, settings):
    """Resolve prerequisites and guarantee a clean baseline for the lifecycle.

    Requires an existing IoT Operations instance backed by an ADR namespace.
    Creates an Event Grid namespace when one is not supplied.
    """
    from ...settings import EnvironmentVariables

    for var in (
        EnvironmentVariables.rg,
        EnvironmentVariables.instance,
        EnvironmentVariables.eg_resource_id,
    ):
        settings.add_to_config(var.value)

    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg
    if not all([instance_name, resource_group]):
        raise AssertionError(
            "Cannot run live-data tests without an instance and resource group. "
            f"Current settings:\n {settings}"
        )

    instance = run(f"az iot ops show -n {instance_name} -g {resource_group}")
    ns_id = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
    if not ns_id:
        raise AssertionError(
            f"Instance '{instance_name}' has no ADR namespace reference, which Live Data requires."
        )

    location = run(f'az resource show --ids "{ns_id}"')["location"]

    # A pre-existing enablement cannot be faithfully restored, so refuse rather
    # than run on top of it. `enabled` alone is insufficient, since a half
    # configured instance reports False; refuse on any trace.
    initial_state = run(f"az iot ops live-data show -i {instance_name} -g {resource_group}")
    existing = _describe_existing_state(initial_state)
    if existing:
        raise AssertionError(
            f"Instance '{instance_name}' already has Live Data traces: {existing}. "
            "Refusing to run so the test does not delete resources it did not create."
        )

    eg_resource_id = _ensure_eg_namespace(
        request=request, settings=settings, resource_group=resource_group, location=location
    )
    common = f"-i {instance_name} -g {resource_group}"

    yield {
        "instanceName": instance_name,
        "resourceGroup": resource_group,
        "egResourceId": eg_resource_id,
    }

    try:
        run(f"az iot ops live-data disable {common} -y")
    except Exception:
        logger.error("Failed to disable live-data during teardown.")


@pytest.mark.livedata
@pytest.mark.serial
@pytest.mark.parametrize("auth_mode", ["systemAssigned", "userAssigned"])
def test_live_data_lifecycle(request, live_data_setup, auth_mode: str) -> None:
    """enable -> show -> disable, plus idempotency on both mutating commands.

    Runs once per outbound identity mode. A user-assigned identity changes both
    the dataflow endpoint auth block and the ADR namespace outbound identity, and
    which principal receives the Event Grid role assignments.
    """
    instance_name = live_data_setup["instanceName"]
    resource_group = live_data_setup["resourceGroup"]
    eg_resource_id = live_data_setup["egResourceId"]
    common = f"-i {instance_name} -g {resource_group}"

    mi_id = request.getfixturevalue("user_assigned_mi") if auth_mode == "userAssigned" else None
    enable_command = f'az iot ops live-data enable {common} --eg-resource-id "{eg_resource_id}"'
    if mi_id:
        enable_command += f' --mi-user-assigned "{mi_id}"'

    # --- Baseline ---
    before = run(f"az iot ops live-data show {common}")
    assert before["enabled"] is False, "expected a clean baseline, live-data reported enabled"

    def _ensure_disabled() -> None:
        try:
            run(f"az iot ops live-data disable {common} -y")
        except Exception:
            logger.error(f"Failed to disable live-data after the {auth_mode} lifecycle test.")

    request.addfinalizer(_ensure_disabled)

    # --- Enable ---
    enable_result = run(enable_command)
    topic_space_name = enable_result["eventGrid"]["topicSpace"]["name"]
    assert topic_space_name
    assert enable_result["instance"]["dataflowProfile"]["name"]
    assert enable_result["instance"]["dataflowEndpoint"]["name"]

    expected_method = "UserAssignedManagedIdentity" if mi_id else "SystemAssignedManagedIdentity"
    endpoint_auth = enable_result["instance"]["dataflowEndpoint"]["authentication"]
    assert endpoint_auth["method"] == expected_method, f"unexpected endpoint auth: {endpoint_auth}"

    expected_outbound = "UserAssigned" if mi_id else "SystemAssigned"
    outbound_identity = enable_result["deviceRegistryNamespace"]["outboundIdentity"]
    assert outbound_identity["type"] == expected_outbound, f"unexpected outbound identity: {outbound_identity}"

    # --- Role assignments landed at Event Grid namespace scope (default) ---
    assert enable_result["roleAssignmentScope"] == "namespace"
    role_assignments = enable_result["roleAssignments"]
    instance_grant = role_assignments["instance"]
    adr_grant = role_assignments["adrNamespace"]
    assert instance_grant["roles"] == [EG_TOPICSPACES_PUBLISHER_ROLE_ID]
    assert adr_grant["roles"] == [EG_TOPICSPACES_SUBSCRIBER_ROLE_ID]
    assert_role_assignment(
        scope=eg_resource_id,
        assignee=instance_grant["principalId"],
        expected_role_ids=instance_grant["roles"],
    )
    assert_role_assignment(
        scope=eg_resource_id,
        assignee=adr_grant["principalId"],
        expected_role_ids=adr_grant["roles"],
    )

    # --- Show reflects reality ---
    _assert_sub_resources_exist(run(f"az iot ops live-data show {common}"))

    # --- Enable is idempotent ---
    run(enable_command)
    _assert_sub_resources_exist(run(f"az iot ops live-data show {common}"))

    # --- Disable tears down every sub-resource ---
    run(f"az iot ops live-data disable {common} -y")
    after_disable = run(f"az iot ops live-data show {common}")
    assert after_disable["enabled"] is False
    assert after_disable["instance"]["dataflowProfile"]["exists"] is False
    assert after_disable["instance"]["dataflowEndpoint"]["exists"] is False

    # show discovers Event Grid through the ADR observability endpoint, so removing that
    # entry takes the whole eventGrid section with it. Assert the endpoint is gone, then
    # check the Event Grid side directly since show can no longer reach it.
    assert after_disable["deviceRegistryNamespace"]["observabilityEndpoint"] is None
    assert after_disable["eventGrid"] is None
    assert topic_space_name not in _list_topic_space_names(eg_resource_id)

    # --- Disable is idempotent ---
    run(f"az iot ops live-data disable {common} -y")


@pytest.mark.livedata
@pytest.mark.serial
def test_live_data_ra_scope_topic_space(request, live_data_setup) -> None:
    """--ra-scope topic-space grants roles at the topic-space resource and removes them on disable."""
    instance_name = live_data_setup["instanceName"]
    resource_group = live_data_setup["resourceGroup"]
    eg_resource_id = live_data_setup["egResourceId"]
    common = f"-i {instance_name} -g {resource_group}"

    before = run(f"az iot ops live-data show {common}")
    assert before["enabled"] is False, "expected a clean baseline, live-data reported enabled"

    def _ensure_disabled() -> None:
        try:
            run(f"az iot ops live-data disable {common} -y")
        except Exception:
            logger.error("Failed to disable live-data after the topic-space scope test.")

    request.addfinalizer(_ensure_disabled)

    enable_result = run(
        f'az iot ops live-data enable {common} --eg-resource-id "{eg_resource_id}" --ra-scope topic-space'
    )
    assert enable_result["roleAssignmentScope"] == "topic-space"
    topic_space_name = enable_result["eventGrid"]["topicSpace"]["name"]
    ts_scope = f"{eg_resource_id}/topicSpaces/{topic_space_name}"

    role_assignments = enable_result["roleAssignments"]
    for key in ("instance", "adrNamespace"):
        grant = role_assignments[key]
        assert grant["principalId"], f"{key} has no principal after enable"
        assert_role_assignment(
            scope=ts_scope,
            assignee=grant["principalId"],
            expected_role_ids=grant["roles"],
        )

    # Disable removes the topic space, which takes the topic-space-scoped role
    # assignments with it — nothing left orphaned.
    run(f"az iot ops live-data disable {common} -y")
    assert topic_space_name not in _list_topic_space_names(eg_resource_id)
