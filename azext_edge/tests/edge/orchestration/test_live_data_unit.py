# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional

import pytest
import responses
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.common import (
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
    LIVE_DATA_ADR_ENDPOINT_TYPE,
    LIVE_DATA_ENDPOINT_NAME,
    LIVE_DATA_PROFILE_NAME,
    LIVE_DATA_TOPIC_TEMPLATE,
    LIVE_DATA_TOPICSPACE_PREFIX,
    LiveDataRoleScope,
)
from azext_edge.edge.providers.orchestration.eg_provider_base import EgNamespaceContext
from azext_edge.edge.providers.orchestration.live_data import (
    LiveData,
    _build_adr_observability_put_payload,
    get_live_data_topic_space_name,
)

from ...generators import BASE_URL, generate_random_string, generate_resource_id, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
DEVICEREGISTRY_RP = "Microsoft.DeviceRegistry"
DEVICEREGISTRY_API_VERSION = "2026-11-02-preview"
EVENTGRID_RP = "Microsoft.EventGrid"
EVENTGRID_API_VERSION = "2025-02-15"
IOTOPS_RP = "Microsoft.IoTOperations"
IOTOPS_API_VERSION = "2026-07-01"

MOCK_EXTENDED_LOCATION: dict = {
    "name": (
        f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/test-rg"
        f"/providers/Microsoft.ExtendedLocation/customLocations/my-cl"
    ),
    "type": "CustomLocation",
}


@pytest.fixture(autouse=True)
def suppress_workflow_display(mocker):
    """Prevent WorkflowDisplay and render_summary from writing to stderr during tests."""
    mocker.patch("azext_edge.edge.providers.orchestration.live_data.WorkflowDisplay")
    mocker.patch("azext_edge.edge.providers.orchestration.live_data.render_summary")
    mocker.patch("azext_edge.edge.providers.orchestration.live_data.console")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_eg_resource_id(
    namespace_name: str,
    resource_group_name: str,
    subscription_id: Optional[str] = None,
) -> str:
    return generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider=EVENTGRID_RP,
        resource_path=f"/namespaces/{namespace_name}",
        resource_subscription=subscription_id,
    )


def _build_eg_endpoint(
    namespace_name: str,
    resource_group_name: str,
    subscription_id: Optional[str] = None,
    sub_resource: Optional[str] = None,
) -> str:
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    url = (
        f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
        f"/providers/{EVENTGRID_RP}/namespaces/{namespace_name}"
    )
    if sub_resource:
        url += sub_resource
    url += f"?api-version={EVENTGRID_API_VERSION}"
    return url


def _build_iotops_endpoint(
    instance_name: str,
    resource_group_name: str,
    sub_resource: Optional[str] = None,
) -> str:
    url = (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
        f"/providers/{IOTOPS_RP}/instances/{instance_name}"
    )
    if sub_resource:
        url += sub_resource
    url += f"?api-version={IOTOPS_API_VERSION}"
    return url


def _build_adr_namespace_resource_id(
    namespace_name: str,
    resource_group_name: str,
    subscription_id: Optional[str] = None,
) -> str:
    return generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider=DEVICEREGISTRY_RP,
        resource_path=f"/namespaces/{namespace_name}",
        resource_subscription=subscription_id,
    )


def _build_adr_endpoint(
    namespace_name: str,
    resource_group_name: str,
    subscription_id: Optional[str] = None,
) -> str:
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    return (
        f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
        f"/providers/{DEVICEREGISTRY_RP}/namespaces/{namespace_name}"
        f"?api-version={DEVICEREGISTRY_API_VERSION}"
    )


def _build_eg_namespace_response(
    namespace_name: str,
    resource_group_name: str,
    topic_spaces_state: str = "Enabled",
    mqtt_hostname: str = "test-ns.eastus-1.ts.eventgrid.azure.net",
    subscription_id: Optional[str] = None,
) -> dict:
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    return {
        "id": (
            f"/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
            f"/providers/{EVENTGRID_RP}/namespaces/{namespace_name}"
        ),
        "name": namespace_name,
        "location": "eastus",
        "properties": {
            "provisioningState": "Succeeded",
            "topicSpacesConfiguration": {
                "state": topic_spaces_state,
                "hostname": mqtt_hostname,
            },
        },
    }


def _build_adr_namespace_response(
    namespace_name: str,
    resource_group_name: str,
    identity_type: str = "None",
    principal_id: Optional[str] = None,
    observability_endpoints: Optional[dict] = None,
    outbound_identity: Optional[dict] = None,
    subscription_id: Optional[str] = None,
) -> dict:
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    identity: dict = {"type": identity_type}
    if principal_id:
        identity["principalId"] = principal_id
    properties: dict = {"provisioningState": "Succeeded"}
    if observability_endpoints is not None:
        properties["observability"] = {"endpoints": observability_endpoints}
    if outbound_identity is not None:
        properties["outboundIdentity"] = outbound_identity
    return {
        "id": _build_adr_namespace_resource_id(namespace_name, resource_group_name, sub_id),
        "name": namespace_name,
        "location": "eastus",
        "identity": identity,
        "properties": properties,
    }


def _build_instance_response(
    instance_name: str,
    resource_group_name: str,
    adr_namespace_name: Optional[str] = None,
    include_adr_ref: bool = True,
) -> dict:
    properties: dict = {"provisioningState": "Succeeded"}
    if include_adr_ref:
        adr_ns_name = adr_namespace_name or f"{instance_name}-adr-ns"
        properties["adrNamespaceRef"] = {
            "resourceId": _build_adr_namespace_resource_id(adr_ns_name, resource_group_name)
        }
    return {
        "id": (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        ),
        "name": instance_name,
        "location": "eastus",
        "extendedLocation": MOCK_EXTENDED_LOCATION,
        "properties": properties,
    }


def _make_eg_ctx(
    namespace_name: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    mqtt_hostname: Optional[str] = None,
) -> EgNamespaceContext:
    ns = namespace_name or "test-ns"
    rg = resource_group_name or "test-rg"
    return EgNamespaceContext(
        resource_id=_build_eg_resource_id(ns, rg),
        subscription_id=ZEROED_SUBSCRIPTION,
        resource_group_name=rg,
        namespace_name=ns,
        mqtt_hostname=mqtt_hostname or "test-ns.eastus-1.ts.eventgrid.azure.net",
    )


# ---------------------------------------------------------------------------
# Deterministic naming
# ---------------------------------------------------------------------------


class TestTopicSpaceName:
    def test_deterministic_and_prefixed(self):
        rid = _build_adr_namespace_resource_id("ns", "rg")
        name1 = get_live_data_topic_space_name(rid)
        name2 = get_live_data_topic_space_name(rid)
        assert name1 == name2
        assert name1.startswith(f"{LIVE_DATA_TOPICSPACE_PREFIX}-")
        # prefix + hyphen + 8 hex chars
        assert len(name1) == len(LIVE_DATA_TOPICSPACE_PREFIX) + 1 + 8

    def test_distinct_instances_distinct_names(self):
        a = get_live_data_topic_space_name(_build_adr_namespace_resource_id("nsA", "rg"))
        b = get_live_data_topic_space_name(_build_adr_namespace_resource_id("nsB", "rg"))
        assert a != b


# ---------------------------------------------------------------------------
# _build_adr_observability_put_payload
# ---------------------------------------------------------------------------


class TestBuildObservabilityPutPayload:
    def test_removes_target_preserves_others(self):
        cl_key = "cl-1"
        other_key = "cl-2"
        other_entry = {"endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": "other"}
        adr_namespace = {
            "location": "eastus",
            "identity": {"type": "SystemAssigned", "principalId": "pid"},
            "tags": {"env": "test"},
            "properties": {
                "observability": {"endpoints": {cl_key: {"address": "mine"}, other_key: other_entry}},
                "outboundIdentity": {"type": "SystemAssigned"},
                "management": {"endpoints": {"cl-x": {"address": "mgmt"}}},
                "messaging": {"endpoints": {}},
            },
        }
        payload = _build_adr_observability_put_payload(adr_namespace, cl_key)

        endpoints = payload["properties"]["observability"]["endpoints"]
        assert cl_key not in endpoints
        assert endpoints[other_key] == other_entry
        assert payload["identity"] == {"type": "SystemAssigned", "principalId": "pid"}
        assert payload["tags"] == {"env": "test"}
        assert payload["properties"]["outboundIdentity"] == {"type": "SystemAssigned"}
        assert payload["properties"]["management"] == {"endpoints": {"cl-x": {"address": "mgmt"}}}
        assert payload["properties"]["messaging"] == {"endpoints": {}}
        assert payload["location"] == "eastus"

    def test_optional_fields_absent(self):
        adr_namespace = {
            "location": "eastus",
            "properties": {"observability": {"endpoints": {"cl-1": {"address": "mine"}}}},
        }
        payload = _build_adr_observability_put_payload(adr_namespace, "cl-1")
        assert payload["properties"]["observability"]["endpoints"] == {}
        assert "identity" not in payload
        assert "tags" not in payload
        assert "outboundIdentity" not in payload["properties"]
        assert "management" not in payload["properties"]
        assert "messaging" not in payload["properties"]


# ---------------------------------------------------------------------------
# _setup_topic_space
# ---------------------------------------------------------------------------


class TestSetupTopicSpace:
    def test_create_new(self, mocked_cmd, mocked_responses: responses):
        ns, rg = generate_random_string(), generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_adr_namespace_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns, resource_group_name=rg)
        ts_name = get_live_data_topic_space_name(instance_rid)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_eg_endpoint(ns, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={"id": f"/fake/topicSpaces/{ts_name}", "name": ts_name},
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_topic_space(
            eg_ctx=eg_ctx, instance_name=instance_name, instance_resource_id=instance_rid, wait_sec=0
        )

        assert result["name"] == ts_name
        assert result["exists"] is False
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["topicTemplates"] == [LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=instance_name)]

    def test_existing_topic_space(self, mocked_cmd, mocked_responses: responses):
        ns, rg = generate_random_string(), generate_random_string()
        instance_rid = _build_adr_namespace_resource_id(generate_random_string(), rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns, resource_group_name=rg)
        ts_name = get_live_data_topic_space_name(instance_rid)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={"id": f"/fake/topicSpaces/{ts_name}", "name": ts_name},
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_topic_space(
            eg_ctx=eg_ctx, instance_name="inst", instance_resource_id=instance_rid, wait_sec=0
        )
        assert result["exists"] is True
        assert len(mocked_responses.calls) == 1


# ---------------------------------------------------------------------------
# _setup_dataflow_profile
# ---------------------------------------------------------------------------


class TestSetupDataflowProfile:
    def test_create_new_instance_count_one(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()

        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"id": "/fake", "name": LIVE_DATA_PROFILE_NAME},
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_dataflow_profile(
            instance_name=instance_name,
            resource_group_name=rg,
            extended_location=MOCK_EXTENDED_LOCATION,
            wait_sec=0,
        )
        assert result["name"] == LIVE_DATA_PROFILE_NAME
        assert result["exists"] is False
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["instanceCount"] == 1
        assert put_body["extendedLocation"] == MOCK_EXTENDED_LOCATION

    def test_existing_profile(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"id": "/fake", "name": LIVE_DATA_PROFILE_NAME},
            status=200,
        )
        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_dataflow_profile(
            instance_name=instance_name,
            resource_group_name=rg,
            extended_location=MOCK_EXTENDED_LOCATION,
            wait_sec=0,
        )
        assert result["exists"] is True
        assert len(mocked_responses.calls) == 1


# ---------------------------------------------------------------------------
# _role_scope
# ---------------------------------------------------------------------------


class TestRoleScope:
    def test_namespace_scope(self, mocked_cmd):
        eg_ctx = _make_eg_ctx()
        provider = LiveData(cmd=mocked_cmd)
        scope = provider._role_scope(eg_ctx, LiveDataRoleScope.NAMESPACE, "live-data-ts-abc12345")
        assert scope == eg_ctx.resource_id

    def test_topic_space_scope(self, mocked_cmd):
        eg_ctx = _make_eg_ctx()
        provider = LiveData(cmd=mocked_cmd)
        scope = provider._role_scope(eg_ctx, LiveDataRoleScope.TOPIC_SPACE, "live-data-ts-abc12345")
        assert scope == f"{eg_ctx.resource_id}/topicSpaces/live-data-ts-abc12345"


# ---------------------------------------------------------------------------
# _setup_role_assignments
# ---------------------------------------------------------------------------


class TestSetupRoleAssignments:
    def test_publisher_and_subscriber(self, mocked_cmd, mocker):
        eg_ctx = _make_eg_ctx()
        mock_pm = mocker.MagicMock()
        mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager",
            return_value=mock_pm,
        )
        provider = LiveData(cmd=mocked_cmd)
        provider.permission_manager = mock_pm

        result = provider._setup_role_assignments(
            eg_ctx=eg_ctx,
            ra_scope=LiveDataRoleScope.NAMESPACE,
            topic_space_name="live-data-ts-abc12345",
            publisher_principal_id="pub-pid",
            subscriber_principal_id="sub-pid",
        )

        assert result["instance"]["principalId"] == "pub-pid"
        assert result["instance"]["roles"] == [EG_TOPICSPACES_PUBLISHER_ROLE_ID]
        assert result["adrNamespace"]["principalId"] == "sub-pid"
        assert result["adrNamespace"]["roles"] == [EG_TOPICSPACES_SUBSCRIBER_ROLE_ID]
        # publisher + subscriber, one role each
        assert mock_pm.apply_role_assignment.call_count == 2
        for call in mock_pm.apply_role_assignment.call_args_list:
            assert call.kwargs["scope"] == eg_ctx.resource_id


# ---------------------------------------------------------------------------
# _setup_adr_observability
# ---------------------------------------------------------------------------


class TestSetupAdrObservability:
    def test_single_write_existing_sami(self, mocked_cmd, mocked_responses: responses):
        """Existing system-assigned identity: single PATCH writes outboundIdentity + endpoint."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        instance = _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        cl_id = MOCK_EXTENDED_LOCATION["name"]

        # ADR GET: SAMI already enabled, no observability endpoints yet
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid", observability_endpoints={}
            ),
            status=200,
        )
        # PATCH (begin_update) returns updated namespace
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid", observability_endpoints={}
            ),
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_adr_observability(
            instance=instance,
            eg_ctx=eg_ctx,
            custom_location_id=cl_id,
            mi_resource=None,
            ra_scope=LiveDataRoleScope.NAMESPACE,
            topic_space_name="live-data-ts-abc12345",
            adr_role_ids=None,
            skip_role_assignments=False,
            wait_sec=0,
        )

        assert result["identity_exists"] is True
        assert result["endpoint_exists"] is False
        assert result["outboundIdentity"] == {"type": "SystemAssigned"}
        assert result["identity"]["principalId"] == "adr-pid"
        # GET + PATCH
        assert len(mocked_responses.calls) == 2
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        endpoints = patch_body["properties"]["observability"]["endpoints"]
        assert cl_id in endpoints
        assert endpoints[cl_id]["endpointType"] == LIVE_DATA_ADR_ENDPOINT_TYPE
        assert endpoints[cl_id]["scopeId"] == instance_name

    def test_staged_new_sami_grants_role_between_writes(self, mocked_cmd, mocked_responses: responses, mocker):
        """New system-assigned identity: staged flow — identity PATCH, grant Subscriber, endpoint PATCH."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        instance = _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        cl_id = MOCK_EXTENDED_LOCATION["name"]

        mock_pm = mocker.MagicMock()
        mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager",
            return_value=mock_pm,
        )

        # ADR GET: identity None (no SAMI yet)
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(adr_ns, rg, identity_type="None", observability_endpoints={}),
            status=200,
        )
        # PATCH #1 (enable identity) returns SAMI principalId
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="new-adr-pid", observability_endpoints={}
            ),
            status=200,
        )
        # PATCH #2 (write endpoint entry)
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="new-adr-pid", observability_endpoints={}
            ),
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        provider.permission_manager = mock_pm
        result = provider._setup_adr_observability(
            instance=instance,
            eg_ctx=eg_ctx,
            custom_location_id=cl_id,
            mi_resource=None,
            ra_scope=LiveDataRoleScope.NAMESPACE,
            topic_space_name="live-data-ts-abc12345",
            adr_role_ids=None,
            skip_role_assignments=False,
            wait_sec=0,
        )

        assert result["identity"]["principalId"] == "new-adr-pid"
        # GET + PATCH1 + PATCH2
        assert len(mocked_responses.calls) == 3
        # Subscriber role granted between the two PATCHes
        assert mock_pm.apply_role_assignment.call_count == 1
        assert mock_pm.apply_role_assignment.call_args.kwargs["principal_id"] == "new-adr-pid"
        # First PATCH has no endpoint entry; second PATCH writes it
        patch1 = json.loads(mocked_responses.calls[1].request.body)
        assert "observability" not in patch1["properties"]
        patch2 = json.loads(mocked_responses.calls[2].request.body)
        assert cl_id in patch2["properties"]["observability"]["endpoints"]

    def test_already_configured_early_return(self, mocked_cmd, mocked_responses: responses):
        """Existing SAMI and identical endpoint entry: no PATCH, early return."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        instance = _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        cl_id = MOCK_EXTENDED_LOCATION["name"]
        desired = {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE,
            "address": eg_ctx.mqtt_hostname,
            "scopeId": instance_name,
            "resourceId": eg_ctx.resource_id,
        }
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid",
                observability_endpoints={cl_id: desired},
                outbound_identity={"type": "SystemAssigned"},
            ),
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_adr_observability(
            instance=instance, eg_ctx=eg_ctx, custom_location_id=cl_id, mi_resource=None,
            ra_scope=LiveDataRoleScope.NAMESPACE, topic_space_name="live-data-ts-abc12345",
            adr_role_ids=None, skip_role_assignments=False, wait_sec=0,
        )
        assert result["identity_exists"] is True
        assert result["endpoint_exists"] is True
        assert len(mocked_responses.calls) == 1  # GET only, no PATCH

    def test_uami_single_write(self, mocked_cmd, mocked_responses: responses):
        """A user-assigned identity uses a single write with UserAssigned outboundIdentity."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        instance = _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        cl_id = MOCK_EXTENDED_LOCATION["name"]
        uami_rid = _build_uami_resource_id(generate_random_string(), rg)
        mi_resource = _build_uami_response(uami_rid, "cid", "tid", "uami-pid")

        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(adr_ns, rg, identity_type="None", observability_endpoints={}),
            status=200,
        )
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(adr_ns, rg, identity_type="None", observability_endpoints={}),
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider._setup_adr_observability(
            instance=instance, eg_ctx=eg_ctx, custom_location_id=cl_id, mi_resource=mi_resource,
            ra_scope=LiveDataRoleScope.NAMESPACE, topic_space_name="live-data-ts-abc12345",
            adr_role_ids=None, skip_role_assignments=False, wait_sec=0,
        )
        assert result["outboundIdentity"] == {"type": "UserAssigned", "userAssignedIdentity": uami_rid}
        assert result["identity"]["principalId"] == "uami-pid"
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        assert patch_body["properties"]["outboundIdentity"]["type"] == "UserAssigned"

    def test_no_adr_ref_raises(self, mocked_cmd):
        instance = _build_instance_response(generate_random_string(), generate_random_string(), include_adr_ref=False)
        provider = LiveData(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="ADR namespace reference"):
            provider._setup_adr_observability(
                instance=instance, eg_ctx=_make_eg_ctx(), custom_location_id="cl",
                mi_resource=None, ra_scope=LiveDataRoleScope.NAMESPACE, topic_space_name="ts",
                adr_role_ids=None, skip_role_assignments=False, wait_sec=0,
            )

    def test_staged_missing_principal_raises(self, mocked_cmd, mocked_responses: responses, mocker):
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        instance = _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns)
        mocker.patch("azext_edge.edge.providers.orchestration.live_data.PermissionManager")
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(adr_ns, rg, identity_type="None", observability_endpoints={}),
            status=200,
        )
        # PATCH #1 returns SystemAssigned but WITHOUT principalId
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(adr_ns, rg, identity_type="SystemAssigned", observability_endpoints={}),
            status=200,
        )
        provider = LiveData(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="no principalId"):
            provider._setup_adr_observability(
                instance=instance, eg_ctx=_make_eg_ctx(resource_group_name=rg), custom_location_id="cl",
                mi_resource=None, ra_scope=LiveDataRoleScope.NAMESPACE, topic_space_name="ts",
                adr_role_ids=None, skip_role_assignments=False, wait_sec=0,
            )


# ---------------------------------------------------------------------------
# _build_outbound_identity / _resolve_outbound_principal
# ---------------------------------------------------------------------------


class TestOutboundIdentity:
    def test_build_system_assigned(self, mocked_cmd):
        provider = LiveData(cmd=mocked_cmd)
        assert provider._build_outbound_identity(None) == {"type": "SystemAssigned"}

    def test_build_user_assigned(self, mocked_cmd):
        provider = LiveData(cmd=mocked_cmd)
        mi = {"id": "/uami/rid", "properties": {"principalId": "pid"}}
        assert provider._build_outbound_identity(mi) == {"type": "UserAssigned", "userAssignedIdentity": "/uami/rid"}

    def test_resolve_principal_uami(self, mocked_cmd):
        provider = LiveData(cmd=mocked_cmd)
        assert provider._resolve_outbound_principal({"properties": {"principalId": "pid"}}, {}) == "pid"

    def test_resolve_principal_sami(self, mocked_cmd):
        provider = LiveData(cmd=mocked_cmd)
        assert provider._resolve_outbound_principal(None, {"principalId": "sami-pid"}) == "sami-pid"

    def test_resolve_principal_missing_raises(self, mocked_cmd):
        provider = LiveData(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="outbound identity principal"):
            provider._resolve_outbound_principal(None, {})


# ---------------------------------------------------------------------------
# Role-assignment error paths
# ---------------------------------------------------------------------------


class TestRoleAssignmentErrors:
    def test_setup_role_assignments_http_error(self, mocked_cmd, mocker):
        from azure.core.exceptions import HttpResponseError

        eg_ctx = _make_eg_ctx()
        mock_pm = mocker.MagicMock()
        mock_pm.apply_role_assignment.side_effect = HttpResponseError(message="denied")
        mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager", return_value=mock_pm
        )
        provider = LiveData(cmd=mocked_cmd)
        provider.permission_manager = mock_pm
        with pytest.raises(ValidationError, match="Failed to assign role"):
            provider._setup_role_assignments(
                eg_ctx=eg_ctx, ra_scope=LiveDataRoleScope.NAMESPACE, topic_space_name="ts",
                publisher_principal_id="pub", subscriber_principal_id="sub",
            )

    def test_assign_subscriber_role_http_error(self, mocked_cmd, mocker):
        from azure.core.exceptions import HttpResponseError

        eg_ctx = _make_eg_ctx()
        mock_pm = mocker.MagicMock()
        mock_pm.apply_role_assignment.side_effect = HttpResponseError(message="denied")
        mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager", return_value=mock_pm
        )
        provider = LiveData(cmd=mocked_cmd)
        provider.permission_manager = mock_pm
        with pytest.raises(ValidationError, match="Failed to assign Subscriber role"):
            provider._assign_subscriber_role(
                eg_ctx=eg_ctx, ra_scope=LiveDataRoleScope.NAMESPACE, topic_space_name="ts",
                principal_id="sub", adr_role_ids=None,
            )


# ---------------------------------------------------------------------------
# enable()
# ---------------------------------------------------------------------------


def _register_enable_mocks(
    mocked_responses: responses,
    instance_name: str,
    rg: str,
    ns_name: str,
    adr_ns: str,
    eg_rid: str,
    hostname: str,
    instance_rid: str,
    *,
    mi_response: Optional[dict] = None,
) -> None:
    ts_name = get_live_data_topic_space_name(instance_rid)
    # 1. instance GET
    mocked_responses.add(
        method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
        json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
    )
    # 2. EG namespace GET (validation)
    mocked_responses.add(
        method=responses.GET, url=_build_eg_endpoint(ns_name, rg),
        json=_build_eg_namespace_response(ns_name, rg, mqtt_hostname=hostname), status=200,
    )
    # 3. (optional) UAMI GET
    if mi_response is not None:
        mocked_responses.add(
            method=responses.GET, url=_build_uami_endpoint(mi_response["id"]), json=mi_response, status=200,
        )
    # topic space GET 404 + PUT
    mocked_responses.add(
        method=responses.GET, url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
        json={"error": {"code": "ResourceNotFound"}}, status=404,
    )
    mocked_responses.add(
        method=responses.PUT, url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
        json={"id": "/fake", "name": ts_name}, status=200,
    )
    # dataflow profile GET 404 + PUT
    mocked_responses.add(
        method=responses.GET,
        url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
        json={"error": {"code": "ResourceNotFound"}}, status=404,
    )
    mocked_responses.add(
        method=responses.PUT,
        url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
        json={"id": "/fake", "name": LIVE_DATA_PROFILE_NAME}, status=200,
    )
    # dataflow endpoint GET 404 + PUT
    mocked_responses.add(
        method=responses.GET,
        url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
        json={"error": {"code": "ResourceNotFound"}}, status=404,
    )
    mocked_responses.add(
        method=responses.PUT,
        url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
        json={"id": "/fake", "name": LIVE_DATA_ENDPOINT_NAME}, status=200,
    )
    # ADR GET (SAMI enabled) + PATCH
    mocked_responses.add(
        method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
        json=_build_adr_namespace_response(
            adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid", observability_endpoints={}
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.PATCH, url=_build_adr_endpoint(adr_ns, rg),
        json=_build_adr_namespace_response(
            adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid", observability_endpoints={}
        ),
        status=200,
    )


class TestEnable:
    def test_happy_path_sami(self, mocked_cmd, mocked_responses: responses, mocker):
        rg = generate_random_string()
        instance_name = generate_random_string()
        ns_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        hostname = f"{ns_name}.eastus-1.ts.eventgrid.azure.net"
        instance_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        )
        mocker.patch.object(LiveData, "_resolve_ops_extension_identity", return_value="pub-pid")
        mocker.patch.object(
            LiveData, "_setup_role_assignments",
            return_value={"instance": {"principalId": "pub-pid"}, "adrNamespace": {"principalId": "adr-pid"}},
        )
        _register_enable_mocks(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, instance_rid)

        provider = LiveData(cmd=mocked_cmd)
        result = provider.enable(
            name=instance_name, resource_group_name=rg, eg_resource_id=eg_rid, wait_sec=0,
        )

        assert set(result.keys()) == {
            "instance", "eventGrid", "deviceRegistryNamespace", "roleAssignmentScope", "roleAssignments"
        }
        assert result["roleAssignmentScope"] == "namespace"
        assert result["instance"]["dataflowProfile"]["name"] == LIVE_DATA_PROFILE_NAME
        assert result["instance"]["dataflowEndpoint"]["name"] == LIVE_DATA_ENDPOINT_NAME
        assert result["eventGrid"]["namespace"]["name"] == ns_name
        assert result["deviceRegistryNamespace"]["outboundIdentity"] == {"type": "SystemAssigned"}

    def test_cloud_gate_blocks(self, mocked_cmd, mocker):
        cloud = mocker.MagicMock()
        cloud.supports_eventgrid_mqtt = False
        mocker.patch("azext_edge.edge.providers.orchestration.live_data.CloudConfig", return_value=cloud)
        provider = LiveData(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="not available in this cloud"):
            provider.enable(name="i", resource_group_name="rg", eg_resource_id="eg", wait_sec=0)

    def test_skip_role_assignments(self, mocked_cmd, mocked_responses: responses, mocker):
        rg = generate_random_string()
        instance_name = generate_random_string()
        ns_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        hostname = f"{ns_name}.eastus-1.ts.eventgrid.azure.net"
        instance_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        )
        setup_ra = mocker.patch.object(LiveData, "_setup_role_assignments")
        _register_enable_mocks(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, instance_rid)

        provider = LiveData(cmd=mocked_cmd)
        result = provider.enable(
            name=instance_name, resource_group_name=rg, eg_resource_id=eg_rid,
            skip_role_assignments=True, wait_sec=0,
        )
        assert "roleAssignments" not in result
        setup_ra.assert_not_called()

    def test_ra_scope_topic_space(self, mocked_cmd, mocked_responses: responses, mocker):
        rg = generate_random_string()
        instance_name = generate_random_string()
        ns_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        hostname = f"{ns_name}.eastus-1.ts.eventgrid.azure.net"
        instance_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        )
        mocker.patch.object(LiveData, "_resolve_ops_extension_identity", return_value="pub-pid")
        mocker.patch.object(LiveData, "_setup_role_assignments", return_value={})
        _register_enable_mocks(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, instance_rid)

        provider = LiveData(cmd=mocked_cmd)
        result = provider.enable(
            name=instance_name, resource_group_name=rg, eg_resource_id=eg_rid,
            ra_scope="topic-space", wait_sec=0,
        )
        assert result["roleAssignmentScope"] == "topic-space"


# ---------------------------------------------------------------------------
# show()
# ---------------------------------------------------------------------------


class TestShow:
    def _register_show_mocks(self, mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name):
        cl_id = MOCK_EXTENDED_LOCATION["name"]
        obs_endpoint = {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": hostname,
            "scopeId": instance_name, "resourceId": eg_rid,
        }
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid",
                observability_endpoints={cl_id: obs_endpoint}, outbound_identity={"type": "SystemAssigned"},
            ),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_eg_endpoint(ns_name, rg),
            json=_build_eg_namespace_response(ns_name, rg, mqtt_hostname=hostname), status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={
                "id": "/fake", "name": ts_name,
                "properties": {"topicTemplates": [LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=instance_name)]},
            },
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"id": "/fake", "name": LIVE_DATA_PROFILE_NAME}, status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
            json={"id": "/fake", "name": LIVE_DATA_ENDPOINT_NAME}, status=200,
        )

    def test_enabled_all_present(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        ns_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        hostname = f"{ns_name}.eastus-1.ts.eventgrid.azure.net"
        instance_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        )
        ts_name = get_live_data_topic_space_name(instance_rid)
        self._register_show_mocks(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name)

        provider = LiveData(cmd=mocked_cmd)
        result = provider.show(name=instance_name, resource_group_name=rg)
        assert result["enabled"] is True
        assert result["deviceRegistryNamespace"]["name"] == adr_ns
        assert result["eventGrid"]["topicSpace"]["exists"] is True
        assert result["instance"]["dataflowProfile"]["exists"] is True

    def test_no_adr_ref(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, include_adr_ref=False), status=200,
        )
        # show() always probes the dedicated dataflow profile + endpoint (absent here)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        provider = LiveData(cmd=mocked_cmd)
        result = provider.show(name=instance_name, resource_group_name=rg)
        assert result["enabled"] is False
        assert result["deviceRegistryNamespace"] is None

    def test_adr_not_found(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        provider = LiveData(cmd=mocked_cmd)
        result = provider.show(name=instance_name, resource_group_name=rg)
        assert result["enabled"] is False
        assert result["deviceRegistryNamespace"] is None

    def test_disabled_endpoint_absent(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        # ADR present but no observability endpoints
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid", observability_endpoints={}
            ),
            status=200,
        )
        # No EG context (obs endpoint absent) → EG skipped; dataflow profile + endpoint probed (absent)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        provider = LiveData(cmd=mocked_cmd)
        result = provider.show(name=instance_name, resource_group_name=rg)
        assert result["enabled"] is False
        assert result["eventGrid"] is None


# ---------------------------------------------------------------------------
# disable()
# ---------------------------------------------------------------------------


PROMPT_TARGET = "azext_edge.edge.providers.orchestration.live_data.should_continue_prompt"


class TestDisable:
    def _register_discovery(self, mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name):
        cl_id = MOCK_EXTENDED_LOCATION["name"]
        obs_endpoint = {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": hostname,
            "scopeId": instance_name, "resourceId": eg_rid,
        }
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid",
                observability_endpoints={cl_id: obs_endpoint},
            ),
            status=200,
        )
        # probe: profile, endpoint, topic space (all present)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            json={"id": "/fake", "name": LIVE_DATA_PROFILE_NAME}, status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
            json={"id": "/fake", "name": LIVE_DATA_ENDPOINT_NAME}, status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={"id": "/fake", "name": ts_name}, status=200,
        )

    def test_full_teardown(self, mocked_cmd, mocked_responses: responses, mocker):
        rg = generate_random_string()
        instance_name = generate_random_string()
        ns_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        hostname = f"{ns_name}.eastus-1.ts.eventgrid.azure.net"
        instance_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        )
        ts_name = get_live_data_topic_space_name(instance_rid)
        mocker.patch(PROMPT_TARGET, return_value=True)
        self._register_discovery(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name)
        # teardown: ADR PUT (remove endpoint), profile DELETE, endpoint DELETE, topic space DELETE
        mocked_responses.add(
            method=responses.PUT, url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(adr_ns, rg, observability_endpoints={}), status=200,
        )
        mocked_responses.add(
            method=responses.DELETE,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}"),
            status=204,
        )
        mocked_responses.add(
            method=responses.DELETE,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"),
            status=204,
        )
        mocked_responses.add(
            method=responses.DELETE, url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            status=204,
        )

        provider = LiveData(cmd=mocked_cmd)
        provider.disable(name=instance_name, resource_group_name=rg, confirm_yes=True, wait_sec=0)
        methods = [c.request.method for c in mocked_responses.calls]
        assert methods.count("DELETE") == 3
        assert "PUT" in methods  # endpoint entry removed via begin_create_or_replace

    def test_no_adr_ref_early_return(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, include_adr_ref=False), status=200,
        )
        provider = LiveData(cmd=mocked_cmd)
        provider.disable(name=instance_name, resource_group_name=rg, confirm_yes=True, wait_sec=0)
        assert len(mocked_responses.calls) == 1

    def test_adr_not_found_early_return(self, mocked_cmd, mocked_responses: responses):
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        provider = LiveData(cmd=mocked_cmd)
        provider.disable(name=instance_name, resource_group_name=rg, confirm_yes=True, wait_sec=0)
        assert len(mocked_responses.calls) == 2

    def test_prompt_declined(self, mocked_cmd, mocked_responses: responses, mocker):
        rg = generate_random_string()
        instance_name = generate_random_string()
        ns_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        hostname = f"{ns_name}.eastus-1.ts.eventgrid.azure.net"
        instance_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        )
        ts_name = get_live_data_topic_space_name(instance_rid)
        mocker.patch(PROMPT_TARGET, return_value=False)
        self._register_discovery(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name)

        provider = LiveData(cmd=mocked_cmd)
        provider.disable(name=instance_name, resource_group_name=rg, wait_sec=0)
        methods = [c.request.method for c in mocked_responses.calls]
        assert "DELETE" not in methods
        assert "PUT" not in methods


# ---------------------------------------------------------------------------
# Command adapters
# ---------------------------------------------------------------------------


class TestCommandAdapters:
    def test_enable_delegates(self, mocker):
        from azext_edge.edge import commands_live_data

        mock_provider = mocker.MagicMock()
        mocker.patch.object(commands_live_data, "LiveData", return_value=mock_provider)
        commands_live_data.live_data_enable(
            cmd=mocker.MagicMock(), instance_name="i", resource_group_name="rg", eg_resource_id="eg",
        )
        mock_provider.enable.assert_called_once()
        assert mock_provider.enable.call_args.kwargs["name"] == "i"

    def test_show_delegates(self, mocker):
        from azext_edge.edge import commands_live_data

        mock_provider = mocker.MagicMock()
        mocker.patch.object(commands_live_data, "LiveData", return_value=mock_provider)
        commands_live_data.live_data_show(cmd=mocker.MagicMock(), instance_name="i", resource_group_name="rg")
        mock_provider.show.assert_called_once()

    def test_disable_delegates(self, mocker):
        from azext_edge.edge import commands_live_data

        mock_provider = mocker.MagicMock()
        mocker.patch.object(commands_live_data, "LiveData", return_value=mock_provider)
        commands_live_data.live_data_disable(cmd=mocker.MagicMock(), instance_name="i", resource_group_name="rg")
        mock_provider.disable.assert_called_once()


# ---------------------------------------------------------------------------
# UAMI helpers (module-level; resolved at test run time)
# ---------------------------------------------------------------------------

UAMI_API_VERSION = "2023-01-31"


def _build_uami_resource_id(name: str, rg: str, subscription_id: Optional[str] = None) -> str:
    sub = subscription_id or ZEROED_SUBSCRIPTION
    return (
        f"/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{name}"
    )


def _build_uami_endpoint(mi_resource_id: str) -> str:
    return f"{BASE_URL}{mi_resource_id}?api-version={UAMI_API_VERSION}"


def _build_uami_response(mi_resource_id: str, client_id: str, tenant_id: str, principal_id: str) -> dict:
    return {
        "id": mi_resource_id,
        "properties": {"clientId": client_id, "tenantId": tenant_id, "principalId": principal_id},
    }
