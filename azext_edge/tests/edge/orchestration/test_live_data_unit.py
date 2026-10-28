# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from typing import Optional
from urllib.parse import parse_qs, urlsplit

import pytest
import responses
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError, ServiceRequestError, ServiceResponseError

from azext_edge.edge.providers.orchestration.common import (
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
    LIVE_DATA_ADR_ENDPOINT_TYPE,
    LIVE_DATA_ENDPOINT_NAME,
    LIVE_DATA_PROFILE_NAME,
    LIVE_DATA_TOPIC_TEMPLATE,
    LIVE_DATA_TOPICSPACE_PREFIX,
    LIVE_DATA_USER_ROLE_ID,
    MQTT_ENDPOINT_TYPE,
    LiveDataRoleScope,
)
from azext_edge.edge.providers.orchestration.eg_provider_base import EgNamespaceContext
from azext_edge.edge.providers.orchestration.live_data import (
    LiveData,
    _build_adr_observability_put_payload,
    get_live_data_topic_space_name,
)
from azext_edge.edge.providers.orchestration.permissions import PrincipalType
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel

from ...generators import BASE_URL, generate_random_string, generate_resource_id, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
DEVICEREGISTRY_RP = "Microsoft.DeviceRegistry"
DEVICEREGISTRY_API_VERSION = "2026-11-02-preview"
EVENTGRID_RP = "Microsoft.EventGrid"
EVENTGRID_API_VERSION = "2025-02-15"
IOTOPS_RP = "Microsoft.IoTOperations"
IOTOPS_API_VERSION = get_runtime_catalog().get(RuntimeChannel.PREVIEW).iotops_api_version

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


def _register_reader_assignments(mocked_responses, namespace_id, assignments=None, endpoint=BASE_URL, **kwargs):
    url = f"{endpoint}{namespace_id}/providers/Microsoft.Authorization/roleAssignments"
    mocked_responses.add(
        responses.GET, url, json={"value": assignments or []},
        match=[responses.matchers.query_param_matcher({"$filter": "atScope()"}, strict_match=False)],
        **kwargs,
    )
    return url


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


def _build_dataflow_endpoint_response(instance_name: str, hostname: str, authentication: Optional[dict] = None) -> dict:
    return {
        "properties": {
            "endpointType": MQTT_ENDPOINT_TYPE,
            "mqttSettings": {
                "host": hostname,
                "clientIdPrefix": instance_name,
                "authentication": authentication or {
                    "method": "SystemAssignedManagedIdentity",
                    "systemAssignedManagedIdentitySettings": {"audience": "https://eventgrid.azure.net"},
                },
                "tls": {"mode": "Enabled"},
            },
        },
    }


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
    observability_enabled: Optional[bool] = None,
    outbound_identity: Optional[dict] = None,
    subscription_id: Optional[str] = None,
) -> dict:
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    identity: dict = {"type": identity_type}
    if principal_id:
        identity["principalId"] = principal_id
    properties: dict = {"provisioningState": "Succeeded"}
    observability: dict = {}
    if observability_enabled is not None:
        observability["enabled"] = observability_enabled
    if observability_endpoints is not None:
        observability["endpoints"] = observability_endpoints
    if observability:
        properties["observability"] = observability
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
    @pytest.mark.parametrize("mixed_case", [False, True])
    def test_removes_target_preserves_others(self, mixed_case):
        cl_key = "cl-1"
        other_key = "cl-2"
        other_entry = {"endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": "other"}
        adr_namespace = {
            "location": "eastus",
            "identity": {"type": "SystemAssigned", "principalId": "pid"},
            "tags": {"env": "test"},
            "properties": {
                "observability": {
                    "enabled": True,
                    "endpoints": {cl_key: {"address": "mine"}, other_key: other_entry},
                },
                "outboundIdentity": {"type": "SystemAssigned"},
                "management": {"endpoints": {"cl-x": {"address": "mgmt"}}},
                "messaging": {"endpoints": {}},
            },
        }
        payload = _build_adr_observability_put_payload(adr_namespace, cl_key.upper() if mixed_case else cl_key)

        endpoints = payload["properties"]["observability"]["endpoints"]
        assert cl_key not in endpoints
        assert endpoints[other_key] == other_entry
        assert payload["properties"]["observability"]["enabled"] is True
        assert payload["identity"] == {"type": "SystemAssigned", "principalId": "pid"}
        assert payload["tags"] == {"env": "test"}
        assert payload["properties"]["outboundIdentity"] == {"type": "SystemAssigned"}
        assert payload["properties"]["management"] == {"endpoints": {"cl-x": {"address": "mgmt"}}}
        assert payload["properties"]["messaging"] == {"endpoints": {}}
        assert payload["location"] == "eastus"

    def test_removing_last_endpoint_disables_observability_and_preserves_absent_optional_fields(self):
        adr_namespace = {
            "location": "eastus",
            "properties": {
                "observability": {
                    "enabled": True,
                    "endpoints": {"cl-1": {"address": "mine"}},
                },
            },
        }
        payload = _build_adr_observability_put_payload(adr_namespace, "cl-1")
        assert payload["properties"]["observability"]["enabled"] is False
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
        scope_id = generate_random_string()
        instance_rid = _build_adr_namespace_resource_id(scope_id, rg)
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
            eg_ctx=eg_ctx, instance_name=scope_id, instance_resource_id=instance_rid, wait_sec=0
        )

        assert result["name"] == ts_name
        assert result["exists"] is False
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["topicTemplates"] == [f"aio/live-data/{scope_id}/#"]

    def test_existing_topic_space(self, mocked_cmd, mocked_responses: responses):
        ns, rg = generate_random_string(), generate_random_string()
        instance_rid = _build_adr_namespace_resource_id(generate_random_string(), rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns, resource_group_name=rg)
        ts_name = get_live_data_topic_space_name(instance_rid)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={
                "id": f"/fake/topicSpaces/{ts_name}", "name": ts_name,
                "properties": {"topicTemplates": ["aio/live-data/inst/#"]},
            },
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
            json={
                "id": "/fake", "name": LIVE_DATA_PROFILE_NAME,
                "properties": {"instanceCount": 1, "diagnostics": {"logs": {"level": "info"}}},
            },
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


class TestSetupUserRoleAssignments:
    USER_1 = "11111111-1111-1111-1111-111111111111"
    USER_2 = "22222222-2222-2222-2222-222222222222"

    def test_assigns_reader_and_reports_ids(self, mocked_cmd, mocker):
        adr_namespace_id = _build_adr_namespace_resource_id("adr-ns", "rg")
        manager = mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager"
        ).return_value
        manager.ensure_role_assignment.side_effect = [
            ({"id": "/assignments/new"}, True),
            ({"id": "/assignments/existing"}, False),
        ]

        result = LiveData(cmd=mocked_cmd)._setup_user_role_assignments(
            adr_namespace_id=adr_namespace_id,
            user_object_ids=[self.USER_1, self.USER_2],
        )

        assert result == {
            "roleId": LIVE_DATA_USER_ROLE_ID,
            "scope": adr_namespace_id,
            "preservedOnDisable": True,
            "assignments": [
                {"principalId": self.USER_1, "assignmentId": "/assignments/new", "created": True},
                {"principalId": self.USER_2, "assignmentId": "/assignments/existing", "created": False},
            ],
        }
        assert manager.ensure_role_assignment.call_count == 2
        for call in manager.ensure_role_assignment.call_args_list:
            assert call.kwargs["scope"] == adr_namespace_id
            assert call.kwargs["principal_type"] == PrincipalType.USER.value
            assert call.kwargs["role_def_id"].endswith(LIVE_DATA_USER_ROLE_ID)

    @pytest.mark.parametrize("error_type", [HttpResponseError, ServiceRequestError, ServiceResponseError])
    def test_assignment_failure_identifies_user(self, mocked_cmd, mocker, error_type):
        adr_namespace_id = _build_adr_namespace_resource_id("adr-ns", "rg")
        manager = mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager"
        ).return_value
        manager.ensure_role_assignment.side_effect = error_type(message="denied")

        with pytest.raises(ValidationError, match=self.USER_1) as exc:
            LiveData(cmd=mocked_cmd)._setup_user_role_assignments(
                adr_namespace_id=adr_namespace_id,
                user_object_ids=[self.USER_1],
            )
        assert "'Reader'" in str(exc.value)
        assert LIVE_DATA_USER_ROLE_ID in str(exc.value)
        assert isinstance(exc.value.__cause__, error_type)
        manager.delete_role_assignment.assert_not_called()

    def test_later_failure_rolls_back_only_new_assignments(self, mocked_cmd, mocker):
        adr_namespace_id = _build_adr_namespace_resource_id("adr-ns", "rg")
        manager = mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager"
        ).return_value
        manager.ensure_role_assignment.side_effect = [
            ({"id": "/assignments/existing"}, False),
            ({"id": "/assignments/new"}, True),
            HttpResponseError(message="denied"),
        ]

        with pytest.raises(ValidationError, match="Rolled back role assignment IDs"):
            LiveData(cmd=mocked_cmd)._setup_user_role_assignments(
                adr_namespace_id=adr_namespace_id,
                user_object_ids=[
                    self.USER_1,
                    self.USER_2,
                    "33333333-3333-3333-3333-333333333333",
                ],
            )

        manager.delete_role_assignment.assert_called_once_with("/assignments/new")

    def test_rollback_failure_reports_surviving_assignment_id(self, mocked_cmd, mocker):
        adr_namespace_id = _build_adr_namespace_resource_id("adr-ns", "rg")
        manager = mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager"
        ).return_value
        manager.ensure_role_assignment.side_effect = [
            ({"id": "/assignments/new"}, True),
            HttpResponseError(message="denied"),
        ]
        manager.delete_role_assignment.side_effect = HttpResponseError(message="cleanup denied")

        with pytest.raises(ValidationError, match="/assignments/new"):
            LiveData(cmd=mocked_cmd)._setup_user_role_assignments(
                adr_namespace_id=adr_namespace_id,
                user_object_ids=[self.USER_1, self.USER_2],
            )

    def test_missing_assignment_id_raises(self, mocked_cmd, mocker):
        adr_namespace_id = _build_adr_namespace_resource_id("adr-ns", "rg")
        manager = mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager"
        ).return_value
        manager.ensure_role_assignment.return_value = ({}, True)

        with pytest.raises(ValidationError, match="no assignment Id was returned"):
            LiveData(cmd=mocked_cmd)._setup_user_role_assignments(
                adr_namespace_id=adr_namespace_id,
                user_object_ids=[self.USER_1],
            )


class TestNormalizeObjectIds:
    @pytest.mark.parametrize("principal_kind", ["user", "subscriber"])
    def test_normalizes_and_deduplicates(self, principal_kind):
        assert LiveData._normalize_object_ids(
            [
                "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ],
            principal_kind,
        ) == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]

    @pytest.mark.parametrize("principal_kind", ["user", "subscriber"])
    def test_invalid_id_raises(self, principal_kind):
        with pytest.raises(ValidationError, match=f"Invalid Microsoft Entra {principal_kind} object ID"):
            LiveData._normalize_object_ids(["not-a-guid"], principal_kind)


class TestSetupSubscriberRoleAssignments:
    PRINCIPAL_1 = "11111111-1111-1111-1111-111111111111"
    PRINCIPAL_2 = "22222222-2222-2222-2222-222222222222"

    @pytest.mark.parametrize("created", [True, False])
    def test_retained_assignment_details_distinguish_ownership(self, created):
        detail = LiveData._format_retained_subscriber_detail({
            "scope": "/namespace",
            "assignments": [{"assignmentId": "/assignment", "created": created}],
        })
        assert f"Newly created Subscriber assignment IDs: {'/assignment' if created else '(none)'}\n" in detail
        assert f"Pre-existing Subscriber assignment IDs: {'(none)' if created else '/assignment'}\n" in detail
        assert "leave pre-existing assignments unchanged" in detail

    @pytest.mark.parametrize("error_type", [HttpResponseError, ServiceRequestError, ServiceResponseError])
    def test_rollback_continues_after_sdk_delete_failure(self, mocker, error_type):
        manager = mocker.Mock()
        manager.delete_role_assignment.side_effect = [error_type(message="delete failed"), None]
        result = LiveData._rollback_role_assignments(manager, [
            {"assignmentId": "/existing", "created": False},
            {"assignmentId": "/new-first", "created": True},
            {"assignmentId": "/new-second", "created": True},
        ])
        assert result == (["/new-first"], ["/new-second"])
        assert manager.delete_role_assignment.call_args_list == [
            mocker.call("/new-second"), mocker.call("/new-first"),
        ]

    @pytest.mark.parametrize("ra_scope", list(LiveDataRoleScope))
    def test_assigns_subscribers_at_selected_scope(self, mocked_cmd, mocker, ra_scope):
        provider = LiveData(mocked_cmd)
        manager = mocker.patch.object(provider, "_permission_manager").return_value
        manager.ensure_role_assignment.side_effect = [
            ({"id": "/assignments/new"}, True),
            ({"id": "/assignments/existing"}, False),
        ]
        eg_ctx = _make_eg_ctx()
        scope = provider._role_scope(eg_ctx, ra_scope, "topic")

        result = provider._setup_subscriber_role_assignments(
            eg_ctx, ra_scope, "topic", [self.PRINCIPAL_1, self.PRINCIPAL_2],
        )

        assert result == {
            "roleId": EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
            "scope": scope,
            "preservedOnDisable": ra_scope == LiveDataRoleScope.NAMESPACE,
            "assignments": [
                {"principalId": self.PRINCIPAL_1, "assignmentId": "/assignments/new", "created": True},
                {"principalId": self.PRINCIPAL_2, "assignmentId": "/assignments/existing", "created": False},
            ],
        }
        assert [call.kwargs for call in manager.ensure_role_assignment.call_args_list] == [
            {
                "scope": scope,
                "principal_id": principal,
                "role_def_id": (
                    f"/subscriptions/{eg_ctx.subscription_id}/providers/Microsoft.Authorization/"
                    f"roleDefinitions/{EG_TOPICSPACES_SUBSCRIBER_ROLE_ID}"
                ),
                "principal_type": None,
            }
            for principal in [self.PRINCIPAL_1, self.PRINCIPAL_2]
        ]
        manager.delete_role_assignment.assert_not_called()

    @pytest.mark.parametrize("cleanup_fails", [False, True])
    @pytest.mark.parametrize("error_type", [HttpResponseError, ServiceRequestError, ServiceResponseError])
    def test_failure_rolls_back_only_new_subscribers(self, mocked_cmd, mocker, cleanup_fails, error_type):
        provider = LiveData(mocked_cmd)
        manager = mocker.patch.object(provider, "_permission_manager").return_value
        manager.ensure_role_assignment.side_effect = [
            ({"id": "/assignments/existing"}, False),
            ({"id": "/assignments/new"}, True),
            error_type(message="denied"),
        ]
        if cleanup_fails:
            manager.delete_role_assignment.side_effect = error_type(message="cleanup denied")
        principal_3 = "33333333-3333-3333-3333-333333333333"
        with pytest.raises(ValidationError) as exc:
            provider._setup_subscriber_role_assignments(
                _make_eg_ctx(), LiveDataRoleScope.NAMESPACE, "topic",
                [self.PRINCIPAL_1, self.PRINCIPAL_2, principal_3],
            )

        message = str(exc.value)
        assert principal_3 in message
        assert EG_TOPICSPACES_SUBSCRIBER_ROLE_ID in message
        assert "'Event Grid TopicSpaces Subscriber'" in message
        assert isinstance(exc.value.__cause__, error_type)
        assert "/assignments/new" in message
        assert ("Cleanup failed" if cleanup_fails else "Rolled back") in message
        manager.delete_role_assignment.assert_called_once_with("/assignments/new")

    def test_missing_assignment_id_raises(self, mocked_cmd, mocker):
        provider = LiveData(mocked_cmd)
        manager = mocker.patch.object(provider, "_permission_manager").return_value
        manager.ensure_role_assignment.return_value = ({}, True)
        with pytest.raises(ValidationError, match="no assignment Id was returned"):
            provider._setup_subscriber_role_assignments(
                _make_eg_ctx(), LiveDataRoleScope.NAMESPACE, "topic", [self.PRINCIPAL_1],
            )

    @pytest.mark.parametrize("government", [False, True])
    @pytest.mark.parametrize("ra_scope", list(LiveDataRoleScope))
    def test_requests_omit_principal_type_and_reenable_is_additive(
        self, mocked_cmd, mocked_responses, mocker, government, ra_scope,
    ):
        endpoint = BASE_URL
        if government:
            endpoint = "https://management.usgovcloudapi.net"
            mocked_cmd.cli_ctx.cloud.name = "AzureUSGovernment"
            mocked_cmd.cli_ctx.cloud.endpoints.resource_manager = endpoint + "/"
        token = mocker.patch("azext_edge.edge.util.az_client.AZURE_CLI_CREDENTIAL.get_token")
        token.return_value.token = "test-token"
        token.return_value.expires_on = 9999999999
        token.return_value.refresh_on = None
        eg_ctx = _make_eg_ctx()
        subscription = "33333333-3333-3333-3333-333333333333"
        eg_ctx = eg_ctx._replace(
            subscription_id=subscription,
            resource_id=eg_ctx.resource_id.replace(ZEROED_SUBSCRIPTION, subscription),
        )
        provider = LiveData(mocked_cmd)
        scope = provider._role_scope(eg_ctx, ra_scope, "topic")
        role_def_id = (
            f"/subscriptions/{subscription}/providers/Microsoft.Authorization/"
            f"roleDefinitions/{EG_TOPICSPACES_SUBSCRIBER_ROLE_ID}"
        )
        url = f"{endpoint}{scope}/providers/Microsoft.Authorization/roleAssignments"
        assignments = {}

        def list_assignments(request):
            principal = parse_qs(urlsplit(request.url).query)["$filter"][0].split("'")[1]
            return 200, {}, json.dumps({"value": [assignments[principal]] if principal in assignments else []})

        def create_assignment(request):
            properties = json.loads(request.body)["properties"]
            assert properties == {
                "principalId": self.PRINCIPAL_1 if not assignments else self.PRINCIPAL_2,
                "roleDefinitionId": role_def_id,
            }
            principal = properties["principalId"]
            assignment = {
                "id": f"{scope}/providers/Microsoft.Authorization/roleAssignments/{principal}",
                "properties": {**properties, "scope": scope},
            }
            assignments[principal] = assignment
            return 201, {}, json.dumps(assignment)

        mocked_responses.add_callback(responses.GET, url, callback=list_assignments)
        mocked_responses.add_callback(
            responses.PUT, re.compile(re.escape(url) + "/[^/?]+"), callback=create_assignment,
        )
        first = provider._setup_subscriber_role_assignments(
            eg_ctx, ra_scope, "topic", [self.PRINCIPAL_1],
        )
        second = provider._setup_subscriber_role_assignments(
            eg_ctx, ra_scope, "topic", [self.PRINCIPAL_1, self.PRINCIPAL_2],
        )
        third = provider._setup_subscriber_role_assignments(
            eg_ctx, ra_scope, "topic", [self.PRINCIPAL_2],
        )

        assert first["assignments"][0]["created"] is True
        assert second["assignments"][0]["assignmentId"] == first["assignments"][0]["assignmentId"]
        assert [assignment["created"] for assignment in second["assignments"]] == [False, True]
        assert third["assignments"][0]["created"] is False
        assert set(assignments) == {self.PRINCIPAL_1, self.PRINCIPAL_2}
        assert [call.request.method for call in mocked_responses.calls] == ["GET", "PUT", "GET", "GET", "PUT", "GET"]
        assert all(call.request.url.startswith(endpoint + scope) for call in mocked_responses.calls)
        assert token.call_args.args == (endpoint + "/.default",)


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
        assert patch_body["properties"]["observability"]["enabled"] is True
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
        assert patch2["properties"]["observability"]["enabled"] is True
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
                observability_enabled=True,
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

    @pytest.mark.parametrize("observability_enabled", [None, False])
    def test_repairs_namespace_observability_flag(
        self,
        mocked_cmd,
        mocked_responses: responses,
        observability_enabled: Optional[bool],
    ):
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
                adr_ns,
                rg,
                identity_type="SystemAssigned",
                principal_id="adr-pid",
                observability_endpoints={cl_id: desired},
                observability_enabled=observability_enabled,
                outbound_identity={"type": "SystemAssigned"},
            ),
            status=200,
        )
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns,
                rg,
                identity_type="SystemAssigned",
                principal_id="adr-pid",
                observability_endpoints={cl_id: desired},
                observability_enabled=True,
                outbound_identity={"type": "SystemAssigned"},
            ),
            status=200,
        )

        provider = LiveData(cmd=mocked_cmd)
        provider._setup_adr_observability(
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

        patch_body = json.loads(mocked_responses.calls[1].request.body)
        assert patch_body["properties"]["observability"]["enabled"] is True
        assert patch_body["properties"]["observability"]["endpoints"][cl_id] == desired

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
        assert patch_body["properties"]["observability"]["enabled"] is True

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
        setup_user_ra = mocker.patch.object(LiveData, "_setup_user_role_assignments")
        setup_subscriber_ra = mocker.patch.object(LiveData, "_setup_subscriber_role_assignments")
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
        setup_user_ra.assert_not_called()
        setup_subscriber_ra.assert_not_called()

    def test_cloud_gate_blocks(self, mocked_cmd, mocker):
        cloud = mocker.MagicMock()
        cloud.supports_eventgrid_mqtt = False
        mocker.patch("azext_edge.edge.providers.orchestration.live_data.CloudConfig", return_value=cloud)
        provider = LiveData(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="not available in this cloud"):
            provider.enable(name="i", resource_group_name="rg", eg_resource_id="eg", wait_sec=0)

    def test_skip_role_assignments(self, mocked_cmd, mocked_responses: responses, mocker, caplog):
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
        setup_user_ra = mocker.patch.object(LiveData, "_setup_user_role_assignments")
        setup_subscriber_ra = mocker.patch.object(LiveData, "_setup_subscriber_role_assignments")
        _register_enable_mocks(mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, instance_rid)

        provider = LiveData(cmd=mocked_cmd)
        result = provider.enable(
            name=instance_name, resource_group_name=rg, eg_resource_id=eg_rid,
            user_object_ids=["not-a-guid"],
            subscriber_object_ids=["also-not-a-guid"],
            skip_role_assignments=True, wait_sec=0,
        )
        assert "roleAssignments" not in result
        setup_ra.assert_not_called()
        setup_user_ra.assert_not_called()
        setup_subscriber_ra.assert_not_called()
        assert "--skip-ra takes precedence" in caplog.text
        assert "--subscriber-object-ids" in caplog.text

    @pytest.mark.parametrize("ra_scope", list(LiveDataRoleScope))
    def test_subscribers_in_result_preserve_adr_and_user_assignments(
        self, mocked_cmd, mocked_responses, mocker, ra_scope,
    ):
        rg, instance_name, ns_name = "rg", "instance", "eg"
        adr_ns = "adr"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        instance_rid = _build_instance_response(instance_name, rg)["id"]
        mocker.patch.object(LiveData, "_resolve_ops_extension_identity", return_value="pub-pid")
        mocker.patch.object(
            LiveData, "_setup_role_assignments",
            return_value={"instance": {"principalId": "pub-pid"}, "adrNamespace": {"principalId": "adr-pid"}},
        )
        user_ra = mocker.patch.object(LiveData, "_setup_user_role_assignments", return_value={"roleId": "reader"})
        _register_enable_mocks(
            mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, "eg.example.com", instance_rid,
        )
        provider = LiveData(mocked_cmd)
        manager = mocker.patch.object(provider, "_permission_manager").return_value
        manager.ensure_role_assignment.return_value = ({"id": "/assignments/subscriber"}, True)
        subscriber = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

        result = provider.enable(
            instance_name, rg, eg_rid, ra_scope=ra_scope.value,
            user_object_ids=[subscriber],
            subscriber_object_ids=[subscriber.upper(), subscriber],
            adr_role_ids=["custom-adr-role"],
            wait_sec=0,
        )

        assert result["roleAssignments"]["instance"]["principalId"] == "pub-pid"
        assert result["roleAssignments"]["adrNamespace"]["principalId"] == "adr-pid"
        assert result["roleAssignments"]["users"] == {"roleId": "reader"}
        subscribers = result["roleAssignments"]["subscribers"]
        assert subscribers["roleId"] == EG_TOPICSPACES_SUBSCRIBER_ROLE_ID
        assert subscribers["preservedOnDisable"] == (ra_scope == LiveDataRoleScope.NAMESPACE)
        assert subscribers["assignments"] == [
            {"principalId": subscriber, "assignmentId": "/assignments/subscriber", "created": True},
        ]
        assert subscribers["scope"] == provider._role_scope(
            _make_eg_ctx(ns_name, rg), ra_scope, result["eventGrid"]["topicSpace"]["name"],
        )
        manager.ensure_role_assignment.assert_called_once()
        user_ra.assert_called_once()

    @pytest.mark.parametrize("ra_scope", list(LiveDataRoleScope))
    @pytest.mark.parametrize("with_subscribers", [True, False])
    @pytest.mark.parametrize("reader_failure", ["first", "later", "rollback-failure", "missing-id"])
    @pytest.mark.parametrize("error_type", [HttpResponseError, ServiceRequestError, ServiceResponseError])
    def test_reader_failure_reports_retained_subscribers(
        self, mocked_cmd, mocked_responses, mocker, ra_scope, with_subscribers, reader_failure, error_type,
    ):
        rg, instance_name, ns_name, adr_ns = "rg", "instance", "eg", "adr"
        eg_rid = _build_eg_resource_id(ns_name, rg)
        instance_rid = _build_instance_response(instance_name, rg)["id"]
        mocker.patch.object(LiveData, "_resolve_ops_extension_identity", return_value="pub-pid")
        mocker.patch.object(
            LiveData, "_setup_role_assignments", return_value={"instance": {}, "adrNamespace": {}},
        )
        _register_enable_mocks(
            mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, "eg.example.com", instance_rid,
        )
        reader_manager = mocker.patch(
            "azext_edge.edge.providers.orchestration.live_data.PermissionManager",
        ).return_value
        reader_manager.ensure_role_assignment.side_effect = error_type(message="Reader denied")
        if reader_failure != "first":
            last_result = (
                ({}, True) if reader_failure == "missing-id" else error_type(message="Reader denied")
            )
            reader_manager.ensure_role_assignment.side_effect = [
                ({"id": "/assignments/new-reader"}, True),
                last_result,
            ]
        if reader_failure == "rollback-failure":
            reader_manager.delete_role_assignment.side_effect = error_type(message="cleanup denied")
        provider = LiveData(mocked_cmd)
        eg_manager = mocker.patch.object(provider, "_permission_manager").return_value
        eg_manager.ensure_role_assignment.side_effect = [
            ({"id": "/assignments/new-subscriber"}, True),
            ({"id": "/assignments/existing-subscriber"}, False),
        ]
        object_ids = [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ]

        with pytest.raises(ValidationError) as exc:
            provider.enable(
                instance_name, rg, eg_rid, ra_scope=ra_scope.value,
                user_object_ids=object_ids,
                subscriber_object_ids=object_ids if with_subscribers else None,
                wait_sec=0,
            )

        message = str(exc.value)
        assert "No role assignments were created earlier in this operation." not in message
        assert LIVE_DATA_USER_ROLE_ID in message or reader_failure == "missing-id"
        if reader_failure == "first":
            assert "No new role assignments were created earlier in this assignment batch." in message
            reader_manager.delete_role_assignment.assert_not_called()
        else:
            assert "/assignments/new-reader" in message
            assert ("Cleanup failed" if reader_failure == "rollback-failure" else "Rolled back") in message
            reader_manager.delete_role_assignment.assert_called_once_with("/assignments/new-reader")
        if with_subscribers:
            assert isinstance(exc.value.__cause__, ValidationError)
            assert "/assignments/new-subscriber" in message
            assert "/assignments/existing-subscriber" in message
            assert "Newly created Subscriber assignment IDs: /assignments/new-subscriber\n" in message
            assert "Pre-existing Subscriber assignment IDs: /assignments/existing-subscriber\n" in message
            assert "No Subscriber assignments were rolled back" in message
            assert "az role assignment delete --ids" in message
            expected_scope = eg_rid
            if ra_scope == LiveDataRoleScope.TOPIC_SPACE:
                expected_scope += f"/topicSpaces/{get_live_data_topic_space_name(instance_rid)}"
            assert f"remain in place at scope '{expected_scope}'" in message
            assert eg_manager.ensure_role_assignment.call_count == 2
        else:
            assert "Subscriber assignment IDs" not in message
            eg_manager.ensure_role_assignment.assert_not_called()
        eg_manager.delete_role_assignment.assert_not_called()

    def test_invalid_subscriber_rejected_before_any_resource_requests(self, mocked_cmd, mocked_responses):
        with pytest.raises(ValidationError, match="Invalid Microsoft Entra subscriber object ID"):
            LiveData(mocked_cmd).enable(
                "instance", "rg", "eg", subscriber_object_ids=["not-a-guid"],
            )
        assert not mocked_responses.calls

    def test_user_role_assignments_in_result(self, mocked_cmd, mocked_responses: responses, mocker):
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
        user_object_id = "11111111-1111-1111-1111-111111111111"
        mocker.patch.object(LiveData, "_resolve_ops_extension_identity", return_value="pub-pid")
        mocker.patch.object(
            LiveData,
            "_setup_role_assignments",
            return_value={"instance": {}, "adrNamespace": {}},
        )
        user_result = {
            "roleId": LIVE_DATA_USER_ROLE_ID,
            "scope": _build_adr_namespace_resource_id(adr_ns, rg),
            "preservedOnDisable": True,
            "assignments": [{"principalId": user_object_id, "assignmentId": "/assignment", "created": True}],
        }
        setup_user_ra = mocker.patch.object(
            LiveData,
            "_setup_user_role_assignments",
            return_value=user_result,
        )
        _register_enable_mocks(
            mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, instance_rid
        )

        result = LiveData(cmd=mocked_cmd).enable(
            name=instance_name,
            resource_group_name=rg,
            eg_resource_id=eg_rid,
            user_object_ids=[user_object_id],
            wait_sec=0,
        )

        assert result["roleAssignments"]["users"] == user_result
        setup_user_ra.assert_called_once_with(
            adr_namespace_id=_build_adr_namespace_resource_id(adr_ns, rg),
            user_object_ids=[user_object_id],
        )

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
    @pytest.mark.parametrize("status", [200, 403, 404])
    def test_user_reader_assignments_output(self, mocked_cmd, mocked_responses, status):
        instance = _build_instance_response("instance", "rg")
        eg_ctx = _make_eg_ctx("eg", "rg")
        self._register_show_mocks(
            mocked_responses, "instance", "rg", "eg", "instance-adr-ns", eg_ctx.resource_id,
            eg_ctx.mqtt_hostname, get_live_data_topic_space_name(instance["id"]),
        )
        namespace_id = _build_adr_namespace_resource_id("instance-adr-ns", "rg")
        url = f"{BASE_URL}{namespace_id}/providers/Microsoft.Authorization/roleAssignments"
        assignment = {
            "id": url.removeprefix(BASE_URL) + "/reader",
            "properties": {
                "principalId": "user", "principalType": "User", "scope": namespace_id,
                "roleDefinitionId": (
                    f"/subscriptions/{ZEROED_SUBSCRIPTION}/providers/Microsoft.Authorization"
                    f"/roleDefinitions/{LIVE_DATA_USER_ROLE_ID}"
                ),
            },
        }
        mocked_responses.replace(
            responses.GET, url, json={"value": [assignment]}, status=status,
            match=[responses.matchers.query_param_matcher({"$filter": "atScope()"}, strict_match=False)],
        )
        if status == 200:
            result = LiveData(mocked_cmd).show("instance", "rg")
            assert result["enabled"] is True
            assert result["deviceRegistryNamespace"]["userReaderAssignments"] == [
                {"principalId": "user", "assignmentId": assignment["id"]},
            ]
        else:
            mocked_responses.assert_all_requests_are_fired = False
            with pytest.raises(HttpResponseError):
                LiveData(mocked_cmd).show("instance", "rg")
        assert all(call.request.method == "GET" for call in mocked_responses.calls)

    @pytest.mark.parametrize("government", [False, True])
    def test_subscriber_assignments_output_and_pagination(
        self, mocked_cmd, mocked_responses, mocker, government,
    ):
        endpoint = "https://management.usgovcloudapi.net" if government else BASE_URL
        if government:
            mocked_cmd.cli_ctx.cloud.name = "AzureUSGovernment"
            mocked_cmd.cli_ctx.cloud.endpoints.resource_manager = endpoint + "/"
        token = mocker.patch("azext_edge.edge.util.az_client.AZURE_CLI_CREDENTIAL.get_token")
        token.return_value.token = "test-token"
        token.return_value.expires_on = 9999999999
        token.return_value.refresh_on = None
        subscription = "11111111-1111-1111-1111-111111111111"
        eg_id = _build_eg_resource_id("eg", "rg", subscription)
        topic_name = get_live_data_topic_space_name(_build_instance_response("instance", "rg")["id"])
        self._register_show_mocks(
            mocked_responses, "instance", "rg", "eg", "instance-adr-ns", eg_id, "eg.example.com",
            topic_name, endpoint=endpoint,
        )
        if government:
            dataflow_url = _build_iotops_endpoint(
                "instance", "rg", sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}",
            ).replace(BASE_URL, endpoint, 1)
            mocked_responses.replace(
                responses.GET, dataflow_url,
                json=_build_dataflow_endpoint_response("instance", "eg.example.com", authentication={
                    "method": "SystemAssignedManagedIdentity",
                    "systemAssignedManagedIdentitySettings": {"audience": "https://eventgrid.azure.net"},
                }),
            )
        role_id = (
            f"/subscriptions/{subscription}/providers/Microsoft.Authorization/"
            f"roleDefinitions/{EG_TOPICSPACES_SUBSCRIBER_ROLE_ID}"
        )
        expected = {}
        for scope in [eg_id, f"{eg_id}/topicSpaces/{topic_name}"]:
            def assignment(name, principal_type="User", **properties):
                return {
                    "id": f"{scope}/providers/Microsoft.Authorization/roleAssignments/{name}",
                    "properties": {
                        "principalId": name, "principalType": principal_type, "scope": scope,
                        "roleDefinitionId": role_id, **properties,
                    },
                }

            user = assignment("user", scope=scope.upper(), roleDefinitionId=role_id.upper())
            group = assignment("group", "Group")
            adr = assignment("adr", "ServicePrincipal")
            url = f"{endpoint}{scope}/providers/Microsoft.Authorization/roleAssignments"
            next_url = url + "?api-version=2022-04-01&$skiptoken=next"
            mocked_responses.replace(
                responses.GET, url,
                json={
                    "value": [
                        user,
                        assignment("wrong-role", roleDefinitionId=role_id + "-other"),
                        assignment("publisher", roleDefinitionId=role_id.replace(
                            EG_TOPICSPACES_SUBSCRIBER_ROLE_ID, EG_TOPICSPACES_PUBLISHER_ROLE_ID,
                        )),
                        assignment("inherited", scope=f"/subscriptions/{subscription}"),
                        assignment("unrelated", scope=eg_id + "/topicSpaces/other-instance"),
                    ],
                    "nextLink": next_url,
                },
                match=[responses.matchers.query_param_matcher({"$filter": "atScope()"}, strict_match=False)],
            )
            mocked_responses.add(
                responses.GET, next_url, json={"value": [group, adr]},
                match=[responses.matchers.query_param_matcher({"$skiptoken": "next"}, strict_match=False)],
            )
            expected[scope] = [
                {
                    "principalId": item["properties"]["principalId"], "assignmentId": item["id"],
                    "principalType": item["properties"]["principalType"],
                }
                for item in [user, group, adr]
            ]

        result = LiveData(mocked_cmd).show("instance", "rg")

        assert result["enabled"] is True
        assert result["eventGrid"]["namespace"]["subscriberAssignments"] == expected[eg_id]
        assert result["eventGrid"]["topicSpace"]["subscriberAssignments"] == expected[
            f"{eg_id}/topicSpaces/{topic_name}"
        ]
        assert result["deviceRegistryNamespace"]["userReaderAssignments"] == []
        role_requests = [
            call.request for call in mocked_responses.calls
            if "/Microsoft.Authorization/roleAssignments" in call.request.url
        ]
        assert len(role_requests) == 5
        assert all(request.url.startswith(endpoint) for request in role_requests)
        assert sum(f"/subscriptions/{subscription}/" in request.url for request in role_requests) == 4
        assert token.call_args.args == (endpoint + "/.default",)
        assert all(call.request.method == "GET" for call in mocked_responses.calls)

    @pytest.mark.parametrize("status", [403, 404, 500])
    @pytest.mark.parametrize("ra_scope", list(LiveDataRoleScope))
    def test_subscriber_assignment_errors_are_surfaced(
        self, mocked_cmd, mocked_responses, caplog, status, ra_scope,
    ):
        eg_id = _build_eg_resource_id("eg", "rg")
        topic_name = get_live_data_topic_space_name(_build_instance_response("instance", "rg")["id"])
        self._register_show_mocks(
            mocked_responses, "instance", "rg", "eg", "instance-adr-ns", eg_id, "eg.example.com", topic_name,
        )
        scope = eg_id if ra_scope == LiveDataRoleScope.NAMESPACE else f"{eg_id}/topicSpaces/{topic_name}"
        url = f"{BASE_URL}{scope}/providers/Microsoft.Authorization/roleAssignments"
        mocked_responses.replace(
            responses.GET, url, json={"error": {"code": "AssignmentReadFailed", "message": "unavailable"}},
            status=status,
        )
        mocked_responses.assert_all_requests_are_fired = False

        with pytest.raises(HttpResponseError) as exc:
            LiveData(mocked_cmd).show("instance", "rg")

        assert exc.value.status_code == status
        assert "Event Grid namespace 'eg' not found" not in caplog.text
        assert all(call.request.method == "GET" for call in mocked_responses.calls)

    def test_missing_topic_space_keeps_namespace_subscriber_list(self, mocked_cmd, mocked_responses):
        eg_id = _build_eg_resource_id("eg", "rg")
        topic_name = get_live_data_topic_space_name(_build_instance_response("instance", "rg")["id"])
        self._register_show_mocks(
            mocked_responses, "instance", "rg", "eg", "instance-adr-ns", eg_id, "eg.example.com", topic_name,
        )
        topic_url = f"{BASE_URL}{eg_id}/topicSpaces/{topic_name}"
        mocked_responses.replace(
            responses.GET, topic_url + f"?api-version={EVENTGRID_API_VERSION}",
            json={"error": {"code": "ResourceNotFound"}}, status=404,
        )
        assignment_url = topic_url + "/providers/Microsoft.Authorization/roleAssignments"
        mocked_responses.remove(responses.GET, assignment_url)

        result = LiveData(mocked_cmd).show("instance", "rg")

        assert result["enabled"] is False
        assert result["eventGrid"]["namespace"]["subscriberAssignments"] == []
        assert result["eventGrid"]["topicSpace"]["exists"] is False
        assert result["eventGrid"]["topicSpace"]["subscriberAssignments"] == []
        assert not any(call.request.url.startswith(assignment_url) for call in mocked_responses.calls)

    def _register_show_mocks(
        self,
        mocked_responses,
        instance_name,
        rg,
        ns_name,
        adr_ns,
        eg_rid,
        hostname,
        ts_name,
        observability_enabled: Optional[bool] = True,
        mixed_case: bool = False,
        endpoint: str = BASE_URL,
    ):
        cl_id = MOCK_EXTENDED_LOCATION["name"]
        obs_endpoint = {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": hostname,
            "scopeId": instance_name, "resourceId": eg_rid,
        }
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg).replace(BASE_URL, endpoint, 1),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg).replace(BASE_URL, endpoint, 1),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid",
                observability_endpoints={
                    cl_id.upper() if mixed_case else cl_id: obs_endpoint,
                    **({"sibling-custom-location": {"address": "keep"}} if mixed_case else {}),
                },
                observability_enabled=observability_enabled,
                outbound_identity={"type": "SystemAssigned"},
            ),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET, url=f"{endpoint}{eg_rid}?api-version={EVENTGRID_API_VERSION}",
            json=_build_eg_namespace_response(ns_name, rg, mqtt_hostname=hostname), status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=f"{endpoint}{eg_rid}/topicSpaces/{ts_name}?api-version={EVENTGRID_API_VERSION}",
            json={
                "id": "/fake", "name": ts_name,
                "properties": {"topicTemplates": [LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=instance_name)]},
            },
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name, rg, sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}",
            ).replace(BASE_URL, endpoint, 1),
            json={
                "id": "/fake", "name": LIVE_DATA_PROFILE_NAME,
                "properties": {"instanceCount": 1, "diagnostics": {"logs": {"level": "info"}}},
            }, status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name, rg, sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}",
            ).replace(BASE_URL, endpoint, 1),
            json=_build_dataflow_endpoint_response(instance_name, hostname), status=200,
        )
        _register_reader_assignments(
            mocked_responses, _build_adr_namespace_resource_id(adr_ns, rg), endpoint=endpoint,
        )
        _register_reader_assignments(mocked_responses, eg_rid, endpoint=endpoint)
        _register_reader_assignments(mocked_responses, f"{eg_rid}/topicSpaces/{ts_name}", endpoint=endpoint)

    @pytest.mark.parametrize("mixed_case", [False, True])
    def test_enabled_all_present(self, mocked_cmd, mocked_responses: responses, mixed_case):
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
        self._register_show_mocks(
            mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name, mixed_case=mixed_case,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider.show(name=instance_name, resource_group_name=rg)
        assert result["enabled"] is True
        assert result["deviceRegistryNamespace"]["name"] == adr_ns
        assert result["deviceRegistryNamespace"]["observabilityEnabled"] is True
        assert result["deviceRegistryNamespace"]["userReaderAssignments"] == []
        assert result["eventGrid"]["topicSpace"]["exists"] is True
        assert result["eventGrid"]["namespace"]["subscriberAssignments"] == []
        assert result["eventGrid"]["topicSpace"]["subscriberAssignments"] == []
        assert result["instance"]["dataflowProfile"]["exists"] is True
        assert result["instance"]["dataflowEndpoint"]["configured"] is True

    @pytest.mark.parametrize("observability_enabled", [None, False, True])
    def test_enablement_independent_of_namespace_observability_flag(
        self,
        mocked_cmd,
        mocked_responses: responses,
        observability_enabled: Optional[bool],
    ):
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
        self._register_show_mocks(
            mocked_responses,
            instance_name,
            rg,
            ns_name,
            adr_ns,
            eg_rid,
            hostname,
            ts_name,
            observability_enabled=observability_enabled,
        )

        provider = LiveData(cmd=mocked_cmd)
        result = provider.show(name=instance_name, resource_group_name=rg)

        assert result["enabled"] is True
        assert result["deviceRegistryNamespace"]["observabilityEnabled"] is (observability_enabled is True)
        assert result["deviceRegistryNamespace"]["observabilityEndpoint"] is not None
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

    @pytest.mark.parametrize("sibling_endpoint", [False, True])
    def test_disabled_endpoint_absent(self, mocked_cmd, mocked_responses: responses, sibling_endpoint: bool):
        rg = generate_random_string()
        instance_name = generate_random_string()
        adr_ns = f"{instance_name}-adr-ns"
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, adr_namespace_name=adr_ns), status=200,
        )
        endpoints = {"sibling-custom-location": {"address": "keep"}} if sibling_endpoint else {}
        _register_reader_assignments(mocked_responses, _build_adr_namespace_resource_id(adr_ns, rg))
        mocked_responses.add(
            method=responses.GET, url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns, rg, identity_type="SystemAssigned", principal_id="adr-pid",
                observability_endpoints=endpoints, observability_enabled=True,
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
        assert result["deviceRegistryNamespace"]["observabilityEnabled"] is True
        assert result["deviceRegistryNamespace"]["observabilityEndpoint"] is None
        assert result["eventGrid"] is None


# ---------------------------------------------------------------------------
# disable()
# ---------------------------------------------------------------------------


PROMPT_TARGET = "azext_edge.edge.providers.orchestration.live_data.should_continue_prompt"


class TestDisable:
    def _register_discovery(
        self, mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name, mixed_case=False,
    ):
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
                observability_endpoints={
                    cl_id.upper() if mixed_case else cl_id: obs_endpoint,
                    **({"sibling-custom-location": {"address": "keep"}} if mixed_case else {}),
                },
                observability_enabled=True,
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

    @pytest.mark.parametrize("mixed_case", [False, True])
    def test_full_teardown(self, mocked_cmd, mocked_responses: responses, mocker, mixed_case):
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
        self._register_discovery(
            mocked_responses, instance_name, rg, ns_name, adr_ns, eg_rid, hostname, ts_name, mixed_case=mixed_case,
        )
        # teardown: ADR PUT (remove endpoint), profile DELETE, endpoint DELETE, topic space DELETE
        mocked_responses.add(
            method=responses.PUT, url=_build_adr_endpoint(adr_ns, rg),
            json=_build_adr_namespace_response(
                adr_ns,
                rg,
                observability_endpoints=(
                    {"sibling-custom-location": {"address": "keep"}} if mixed_case else {}
                ),
                observability_enabled=mixed_case,
            ),
            status=200,
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
        put_call = next(call for call in mocked_responses.calls if call.request.method == "PUT")
        put_body = json.loads(put_call.request.body)
        expected_endpoints = {"sibling-custom-location": {"address": "keep"}} if mixed_case else {}
        assert put_body["properties"]["observability"]["enabled"] is bool(expected_endpoints)
        assert put_body["properties"]["observability"]["endpoints"] == expected_endpoints

    def test_no_adr_ref_cleans_instance_resources(self, mocked_cmd, mocked_responses: responses, caplog):
        rg = generate_random_string()
        instance_name = generate_random_string()
        mocked_responses.add(
            method=responses.GET, url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, include_adr_ref=False), status=200,
        )
        self._register_instance_cleanup(mocked_responses, instance_name, rg)
        provider = LiveData(cmd=mocked_cmd)
        provider.disable(name=instance_name, resource_group_name=rg, confirm_yes=True, wait_sec=0)
        assert sum(call.request.method == "DELETE" for call in mocked_responses.calls) == 2
        assert "remove the topic space manually" in caplog.text

    def test_adr_not_found_cleans_instance_resources(self, mocked_cmd, mocked_responses: responses, caplog):
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
        self._register_instance_cleanup(mocked_responses, instance_name, rg)
        provider = LiveData(cmd=mocked_cmd)
        provider.disable(name=instance_name, resource_group_name=rg, confirm_yes=True, wait_sec=0)
        assert sum(call.request.method == "DELETE" for call in mocked_responses.calls) == 2
        assert "remove the topic space manually" in caplog.text

    @staticmethod
    def _register_instance_cleanup(mocked_responses, instance_name, rg):
        for resource in (
            f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}", f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}",
        ):
            endpoint = _build_iotops_endpoint(instance_name, rg, sub_resource=resource)
            mocked_responses.add(responses.GET, endpoint, json={"properties": {}}, status=200)
            mocked_responses.add(responses.DELETE, endpoint, status=204)

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


@pytest.mark.parametrize("missing", ["reference", "namespace"])
def test_enable_validates_adr_before_any_write(mocked_cmd, mocked_responses, missing):
    instance = _build_instance_response("instance", "rg", include_adr_ref=missing != "reference")
    mocked_responses.add(responses.GET, _build_iotops_endpoint("instance", "rg"), json=instance)
    if missing == "namespace":
        mocked_responses.add(responses.GET, _build_adr_endpoint("instance-adr-ns", "rg"), status=404)
    with pytest.raises((ValidationError, ResourceNotFoundError)):
        LiveData(mocked_cmd).enable(
            "instance", "rg", _build_eg_resource_id("eg", "rg"), skip_role_assignments=True,
        )
    assert all(call.request.method == "GET" for call in mocked_responses.calls)


@pytest.mark.parametrize("operation", ["enable", "show"])
def test_live_data_uses_arm_instance_name_for_configuration(mocked_cmd, mocked_responses, operation):
    canonical_name = "MixedInstance"
    caller_name = canonical_name.upper()
    rg, eg_name, adr_name = "rg", "eg", "namespace"
    instance = _build_instance_response(canonical_name, rg, adr_namespace_name=adr_name)
    eg_id = _build_eg_resource_id(eg_name, rg)
    hostname = "eg.eastus-1.ts.eventgrid.azure.net"
    if operation == "enable":
        _register_enable_mocks(
            mocked_responses, canonical_name, rg, eg_name, adr_name, eg_id, hostname, instance["id"],
        )
    else:
        TestShow()._register_show_mocks(
            mocked_responses, canonical_name, rg, eg_name, adr_name, eg_id, hostname,
            get_live_data_topic_space_name(instance["id"]),
        )
    mocked_responses.remove(responses.GET, _build_iotops_endpoint(canonical_name, rg))
    mocked_responses.add(responses.GET, _build_iotops_endpoint(caller_name, rg), json=instance)
    provider = LiveData(mocked_cmd)
    if operation == "enable":
        result = provider.enable(caller_name, rg, eg_id, skip_role_assignments=True, wait_sec=0)
        assert result["deviceRegistryNamespace"]["observabilityEndpoint"]["scopeId"] == canonical_name
        topic_put = next(
            call for call in mocked_responses.calls
            if call.request.method == "PUT" and "/topicSpaces/" in call.request.url
        )
        assert json.loads(topic_put.request.body)["properties"]["topicTemplates"] == [
            LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=canonical_name),
        ]
    else:
        result = provider.show(caller_name, rg)
        assert result["enabled"] is True
        assert result["eventGrid"]["topicSpace"]["configured"] is True
        assert result["instance"]["dataflowEndpoint"]["configured"] is True


@pytest.mark.parametrize("resource", ["topic", "profile", "profile-null-diagnostics", "profile-null-logs"])
def test_enable_reconciles_owned_fields_without_losing_customization(mocked_cmd, mocked_responses, resource):
    provider = LiveData(mocked_cmd)
    if resource == "topic":
        instance_id = _build_instance_response("instance", "rg")["id"]
        name = get_live_data_topic_space_name(instance_id)
        endpoint = _build_eg_endpoint("eg", "rg", sub_resource=f"/topicSpaces/{name}")
        existing = {"properties": {"description": "keep", "topicTemplates": ["stale/#"]}}
    else:
        endpoint = _build_iotops_endpoint("instance", "rg", sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}")
        existing = {
            "tags": {"owner": "keep"},
            "properties": {
                "instanceCount": 2, "diagnostics": {"logs": {"level": "debug"}, "metrics": {"enabled": True}},
            },
        }
        if resource == "profile-null-diagnostics":
            existing["properties"]["diagnostics"] = None
        elif resource == "profile-null-logs":
            existing["properties"]["diagnostics"]["logs"] = None
    mocked_responses.add(responses.GET, endpoint, json=existing)
    mocked_responses.add(responses.PUT, endpoint, json=existing)
    if resource == "topic":
        result = provider._setup_topic_space(_make_eg_ctx("eg", "rg"), "instance", instance_id, wait_sec=0)
    else:
        result = provider._setup_dataflow_profile("instance", "rg", MOCK_EXTENDED_LOCATION, wait_sec=0)
    assert result["exists"] is True
    assert result["updated"] is True
    payload = json.loads(mocked_responses.calls[1].request.body)
    if resource == "topic":
        assert payload["properties"] == {"description": "keep", "topicTemplates": ["aio/live-data/instance/#"]}
    else:
        assert payload["tags"] == existing["tags"]
        assert payload["properties"]["instanceCount"] == 1
        expected_diagnostics = {"logs": {"level": "info"}}
        if resource != "profile-null-diagnostics":
            expected_diagnostics["metrics"] = {"enabled": True}
        assert payload["properties"]["diagnostics"] == expected_diagnostics


@pytest.mark.parametrize("failed_step", ["topic", "profile", "endpoint", "adr"])
def test_disable_after_partial_enable_cleans_created_instance_resources(
    mocked_cmd, mocked_responses, caplog, failed_step,
):
    mocked_responses.assert_all_requests_are_fired = False
    instance = _build_instance_response("instance", "rg")
    eg_id = _build_eg_resource_id("eg", "rg")
    _register_enable_mocks(
        mocked_responses, "instance", "rg", "eg", "instance-adr-ns", eg_id,
        "eg.eastus-1.ts.eventgrid.azure.net", instance["id"],
    )
    topic = _build_eg_endpoint(
        "eg", "rg", sub_resource=f"/topicSpaces/{get_live_data_topic_space_name(instance['id'])}",
    )
    profile = _build_iotops_endpoint("instance", "rg", sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}")
    endpoint = _build_iotops_endpoint("instance", "rg", sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}")
    adr = _build_adr_endpoint("instance-adr-ns", "rg")
    failure_url = {"topic": topic, "profile": profile, "endpoint": endpoint, "adr": adr}[failed_step]
    mocked_responses.replace(
        responses.PATCH if failed_step == "adr" else responses.PUT, failure_url,
        json={"error": {"code": "InvalidRequest", "message": "injected failure"}}, status=400,
    )
    provider = LiveData(mocked_cmd)
    with pytest.raises(HttpResponseError):
        provider.enable("instance", "rg", eg_id, skip_role_assignments=True, wait_sec=0)
    created = [url for url in (profile, endpoint) if any(
        call.request.method == "PUT" and call.request.url == url and call.response.status_code == 200
        for call in mocked_responses.calls
    )]
    for url in created:
        mocked_responses.replace(responses.GET, url, json={"properties": {}}, status=200)
        mocked_responses.add(responses.DELETE, url, status=204)
    provider.disable("instance", "rg", confirm_yes=True, wait_sec=0)
    deletes = [call.request.url for call in mocked_responses.calls if call.request.method == "DELETE"]
    assert deletes == created
    assert "remove the topic space manually" in caplog.text
    for url in created:
        mocked_responses.replace(responses.GET, url, status=404)
    provider.disable("instance", "rg", confirm_yes=True, wait_sec=0)
    assert [call.request.url for call in mocked_responses.calls if call.request.method == "DELETE"] == created


@pytest.mark.parametrize("resource", [
    "topic", "profile", "endpoint-type", "endpoint-tls", "endpoint-auth", "endpoint-host", "endpoint-prefix",
])
def test_show_reports_stale_configuration_as_disabled(mocked_cmd, mocked_responses, resource):
    instance = _build_instance_response("instance", "rg")
    topic_name = get_live_data_topic_space_name(instance["id"])
    TestShow()._register_show_mocks(
        mocked_responses, "instance", "rg", "eg", "instance-adr-ns",
        _build_eg_resource_id("eg", "rg"), "eg.eastus-1.ts.eventgrid.azure.net", topic_name,
    )
    if resource == "topic":
        endpoint = _build_eg_endpoint("eg", "rg", sub_resource=f"/topicSpaces/{topic_name}")
        stale = {"properties": {"topicTemplates": ["stale/#"]}}
    elif resource == "profile":
        endpoint = _build_iotops_endpoint("instance", "rg", sub_resource=f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}")
        stale = {"properties": {"instanceCount": 2, "diagnostics": {"logs": {"level": "info"}}}}
    else:
        endpoint = _build_iotops_endpoint(
            "instance", "rg", sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}",
        )
        stale = _build_dataflow_endpoint_response("instance", "eg.eastus-1.ts.eventgrid.azure.net")
        _set_endpoint_drift(stale, resource.split("-", 1)[1])
    mocked_responses.replace(responses.GET, endpoint, json=stale)
    result = LiveData(mocked_cmd).show("instance", "rg")
    assert result["enabled"] is False
    if resource == "topic":
        section = result["eventGrid"]["topicSpace"]
    else:
        section = result["instance"]["dataflowProfile" if resource == "profile" else "dataflowEndpoint"]
    assert section["exists"] is True
    assert section["configured"] is False


def _set_endpoint_drift(endpoint: dict, field: str) -> None:
    properties = endpoint["properties"]
    mqtt = properties["mqttSettings"]
    if field == "type":
        properties["endpointType"] = "Kafka"
    elif field == "tls":
        mqtt["tls"]["mode"] = "Disabled"
    elif field == "auth":
        mqtt["authentication"] = {"method": "Anonymous"}
    elif field == "host":
        mqtt["host"] = "stale.example.com"
    elif field == "prefix":
        mqtt["clientIdPrefix"] = "stale-prefix"
    elif field == "audience":
        authentication = mqtt["authentication"]
        method = authentication["method"]
        settings = authentication[method[0].lower() + method[1:] + "Settings"]
        if method == "UserAssignedManagedIdentity":
            settings["scope"] = "https://eventgrid.azure.us/.default"
        else:
            settings["audience"] = "https://eventgrid.azure.us"
    else:
        raise AssertionError(f"Unknown drift field {field}")


@pytest.mark.parametrize("government", [False, True])
@pytest.mark.parametrize("field", ["type", "tls", "auth", "host", "prefix", "audience"])
@pytest.mark.parametrize("identity", ["systemAssigned", "userAssigned"])
def test_enable_repairs_all_endpoint_drift(mocked_cmd, mocked_responses, field, identity, government):
    arm_endpoint = "https://management.usgovcloudapi.net" if government else BASE_URL
    if government:
        mocked_cmd.cli_ctx.cloud.name = "AzureUSGovernment"
        mocked_cmd.cli_ctx.cloud.endpoints.resource_manager = arm_endpoint + "/"
    provider = LiveData(mocked_cmd)
    eg_ctx = _make_eg_ctx(
        "eg", "rg", mqtt_hostname="eg.usgovvirginia-1.ts.eventgrid.azure.us" if government else None,
    )
    mi_resource = None
    authentication = None
    if identity == "userAssigned":
        mi_resource = {"properties": {"clientId": "client", "tenantId": "tenant"}}
        authentication = {
            "method": "UserAssignedManagedIdentity",
            "userAssignedManagedIdentitySettings": {
                "clientId": "client", "tenantId": "tenant", "scope": "https://eventgrid.azure.net/.default",
            },
        }
    desired = _build_dataflow_endpoint_response("instance", eg_ctx.mqtt_hostname, authentication)
    existing = deepcopy(desired)
    _set_endpoint_drift(existing, field)
    endpoint = _build_iotops_endpoint(
        "instance", "rg", sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}",
    ).replace(BASE_URL, arm_endpoint, 1)
    mocked_responses.add(responses.GET, endpoint, json=existing)
    mocked_responses.add(responses.PUT, endpoint, json=desired)
    result = provider._setup_eg_dataflow_endpoint(
        eg_ctx, "instance", "rg", MOCK_EXTENDED_LOCATION, LIVE_DATA_ENDPOINT_NAME, mi_resource, wait_sec=0,
    )
    assert result["updated"] is True
    assert len(mocked_responses.calls) == 2
    payload = json.loads(mocked_responses.calls[1].request.body)
    assert payload["properties"] == desired["properties"]


@pytest.mark.parametrize("entrypoint", ["enable", "adr"])
@pytest.mark.parametrize("identity_change", ["system-to-user", "user-to-system", "different-user", "unknown"])
@pytest.mark.parametrize("endpoint_kind", ["observability", "management"])
def test_shared_adr_identity_conflict_is_rejected_before_writes(
    mocked_cmd, mocked_responses, entrypoint, identity_change, endpoint_kind,
):
    instance = _build_instance_response("instance", "rg")
    old_id = generate_resource_id(resource_group_name="rg", resource_provider="Microsoft.ManagedIdentity",
                                  resource_path="/userAssignedIdentities/old")
    new_id = old_id.replace("/old", "/new")
    current = {"type": "SystemAssigned"} if identity_change == "system-to-user" else {
        "type": "UserAssigned", "userAssignedIdentity": old_id,
    }
    if identity_change == "unknown":
        current = None
    mi_resource = None if identity_change in ("user-to-system", "unknown") else {
        "id": new_id, "properties": {"clientId": "client", "tenantId": "tenant"},
    }
    namespace = _build_adr_namespace_response("instance-adr-ns", "rg", outbound_identity=current)
    namespace["properties"][endpoint_kind] = {"endpoints": {"sibling-custom-location": {"address": "keep"}}}
    mocked_responses.add(responses.GET, _build_adr_endpoint("instance-adr-ns", "rg"), json=namespace)
    provider = LiveData(mocked_cmd)
    if entrypoint == "enable":
        mocked_responses.add(responses.GET, _build_iotops_endpoint("instance", "rg"), json=instance)
        mocked_responses.add(
            responses.GET, _build_eg_endpoint("eg", "rg"), json=_build_eg_namespace_response("eg", "rg"),
        )
        if mi_resource:
            mocked_responses.add(responses.GET, _build_uami_endpoint(new_id), json=mi_resource)
        with pytest.raises(ValidationError, match="coordinated migration"):
            provider.enable("instance", "rg", _build_eg_resource_id("eg", "rg"),
                            mi_user_assigned=new_id if mi_resource else None, skip_role_assignments=True)
    else:
        with pytest.raises(ValidationError, match="coordinated migration"):
            provider._setup_adr_observability(
                instance, _make_eg_ctx("eg", "rg"), MOCK_EXTENDED_LOCATION["name"], mi_resource,
                LiveDataRoleScope.NAMESPACE, "topic", None, True,
            )
    assert all(call.request.method == "GET" for call in mocked_responses.calls)


@pytest.mark.parametrize("sharing", ["none", "own", "sibling"])
def test_adr_identity_changes_only_when_not_shared(mocked_cmd, mocked_responses, sharing):
    instance = _build_instance_response("instance", "rg")
    cl_id = MOCK_EXTENDED_LOCATION["name"]
    existing_mi_id = generate_resource_id(
        resource_group_name="rg",
        resource_provider="Microsoft.ManagedIdentity",
        resource_path="/userAssignedIdentities/existing-mi",
    )
    mi_id = generate_resource_id(
        resource_group_name="rg", resource_provider="Microsoft.ManagedIdentity",
        resource_path="/userAssignedIdentities/mi",
    )
    mi_resource = {"id": mi_id, "properties": {"clientId": "client", "tenantId": "tenant", "principalId": "principal"}}
    existing_endpoints = {}
    if sharing == "own":
        existing_endpoints[cl_id] = {"address": "old"}
    elif sharing == "sibling":
        existing_endpoints["sibling-cl"] = {"address": "keep"}
    current_identity = (
        {"type": "userassigned", "userAssignedIdentity": mi_id.upper()}
        if sharing == "sibling" else {"type": "SystemAssigned"}
    )
    namespace = _build_adr_namespace_response(
        "instance-adr-ns",
        "rg",
        identity_type="SystemAssigned",
        principal_id="system-principal",
        observability_endpoints=existing_endpoints,
        outbound_identity=current_identity,
    )
    namespace["identity"] = {
        "type": "SystemAssigned, UserAssigned",
        "principalId": "system-principal",
        "userAssignedIdentities": {existing_mi_id: {}},
    }
    url = _build_adr_endpoint("instance-adr-ns", "rg")
    mocked_responses.add(responses.GET, url, json=namespace)
    mocked_responses.add(responses.PATCH, url, json=namespace)
    result = LiveData(mocked_cmd)._setup_adr_observability(
        instance, _make_eg_ctx("eg", "rg"), cl_id, mi_resource, LiveDataRoleScope.NAMESPACE, "topic", None, True,
        wait_sec=0,
    )
    assert result["outboundIdentity"] == {"type": "UserAssigned", "userAssignedIdentity": mi_id}
    payload = json.loads(mocked_responses.calls[1].request.body)
    assert payload["identity"] == {
        "type": "SystemAssigned, UserAssigned",
        "userAssignedIdentities": {
            existing_mi_id: {},
            mi_id: {},
        },
    }
    for key, endpoint in existing_endpoints.items():
        if key != cl_id:
            assert payload["properties"]["observability"]["endpoints"][key] == endpoint
    assert payload["properties"]["observability"]["endpoints"][cl_id]["scopeId"] == "instance"


@pytest.mark.parametrize("state", ["matching", "drift", "staged"])
def test_adr_reconciliation_preserves_mixed_case_owned_key(mocked_cmd, mocked_responses, mocker, state):
    instance = _build_instance_response("instance", "rg")
    cl_id = MOCK_EXTENDED_LOCATION["name"]
    stored_key = cl_id.upper()
    sibling_key = cl_id.rsplit("/", 1)[0] + "/other-instance"
    sibling = {"address": "keep", "scopeId": "other-instance"}
    eg_ctx = _make_eg_ctx("eg", "rg")
    desired = {
        "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": eg_ctx.mqtt_hostname,
        "scopeId": "instance", "resourceId": eg_ctx.resource_id,
    }
    namespace = _build_adr_namespace_response(
        "instance-adr-ns", "rg", identity_type="None" if state == "staged" else "SystemAssigned",
        principal_id="principal", outbound_identity={"type": "SystemAssigned"}, observability_enabled=True,
        observability_endpoints={stored_key: desired if state == "matching" else {"address": "stale"},
                                 sibling_key: sibling},
    )
    url = _build_adr_endpoint("instance-adr-ns", "rg")
    mocked_responses.add(responses.GET, url, json=namespace)
    if state != "matching":
        updated = dict(namespace, identity={"type": "SystemAssigned", "principalId": "principal"})
        mocked_responses.add(responses.PATCH, url, json=updated)
    provider = LiveData(mocked_cmd)
    mocker.patch.object(provider, "_assign_subscriber_role")
    provider._setup_adr_observability(
        instance, eg_ctx, cl_id, None, LiveDataRoleScope.NAMESPACE, "topic", None,
        state != "staged", wait_sec=0,
    )
    patches = [call for call in mocked_responses.calls if call.request.method == "PATCH"]
    assert len(patches) == {"matching": 0, "drift": 1, "staged": 2}[state]
    if patches:
        payload = json.loads(patches[-1].request.body)
        assert payload["properties"]["observability"]["endpoints"] == {stored_key: desired, sibling_key: sibling}


@pytest.mark.parametrize("outcome", ["matching", "stale-auth", "missing-identity", "permission-denied"])
def test_show_verifies_user_assigned_endpoint_authentication(mocked_cmd, mocked_responses, caplog, outcome):
    instance = _build_instance_response("instance", "rg")
    eg_ctx = _make_eg_ctx("eg", "rg")
    TestShow()._register_show_mocks(
        mocked_responses, "instance", "rg", "eg", "instance-adr-ns", eg_ctx.resource_id,
        eg_ctx.mqtt_hostname, get_live_data_topic_space_name(instance["id"]),
    )
    mi_id = generate_resource_id(
        resource_group_name="identities", resource_provider="Microsoft.ManagedIdentity",
        resource_path="/userAssignedIdentities/mi", resource_subscription="11111111-1111-1111-1111-111111111111",
    )
    namespace = _build_adr_namespace_response(
        "instance-adr-ns", "rg", observability_enabled=True,
        observability_endpoints={MOCK_EXTENDED_LOCATION["name"]: {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": eg_ctx.mqtt_hostname,
            "scopeId": "instance", "resourceId": eg_ctx.resource_id,
        }},
        outbound_identity={"type": "UserAssigned", "userAssignedIdentity": mi_id},
    )
    mocked_responses.replace(responses.GET, _build_adr_endpoint("instance-adr-ns", "rg"), json=namespace)
    authentication = {
        "method": "UserAssignedManagedIdentity",
        "userAssignedManagedIdentitySettings": {
            "clientId": "wrong-client" if outcome == "stale-auth" else "client",
            "tenantId": "tenant", "scope": "https://eventgrid.azure.net/.default",
        },
    }
    endpoint = _build_iotops_endpoint("instance", "rg", sub_resource=f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}")
    mocked_responses.replace(
        responses.GET, endpoint,
        json=_build_dataflow_endpoint_response("instance", eg_ctx.mqtt_hostname, authentication),
    )
    status = {"missing-identity": 404, "permission-denied": 403}.get(outcome, 200)
    mocked_responses.add(
        responses.GET, _build_uami_endpoint(mi_id),
        json={"id": mi_id, "properties": {"clientId": "client", "tenantId": "tenant"}}, status=status,
    )
    if outcome == "permission-denied":
        with pytest.raises(HttpResponseError):
            LiveData(mocked_cmd).show("instance", "rg")
    else:
        result = LiveData(mocked_cmd).show("instance", "rg")
        assert result["enabled"] is (outcome == "matching")
        assert result["instance"]["dataflowEndpoint"]["configured"] is (outcome == "matching")
        if outcome == "missing-identity":
            assert "endpoint configuration cannot be verified" in caplog.text
    assert all(call.request.method == "GET" for call in mocked_responses.calls)


@pytest.mark.parametrize("government", [False, True])
def test_user_reader_assignments_filter_and_pagination(mocked_cmd, mocked_responses, mocker, government):
    subscription = "11111111-1111-1111-1111-111111111111"
    namespace_id = _build_adr_namespace_resource_id("namespace", "rg", subscription)
    endpoint = "https://management.usgovcloudapi.net" if government else BASE_URL
    if government:
        mocked_cmd.cli_ctx.cloud.name = "AzureUSGovernment"
        mocked_cmd.cli_ctx.cloud.endpoints.resource_manager = endpoint + "/"
    token = mocker.patch("azext_edge.edge.util.az_client.AZURE_CLI_CREDENTIAL.get_token")
    token.return_value.token = "test-token"
    token.return_value.expires_on = 9999999999
    token.return_value.refresh_on = None
    role_id = (
        f"/subscriptions/{subscription}/providers/Microsoft.Authorization/roleDefinitions/{LIVE_DATA_USER_ROLE_ID}"
    )

    def assignment(name, **properties):
        return {
            "id": f"{namespace_id}/providers/Microsoft.Authorization/roleAssignments/{name}",
            "properties": {
                "principalId": name, "principalType": "User", "roleDefinitionId": role_id,
                "scope": namespace_id, **properties,
            },
        }

    first = assignment("first", scope=namespace_id.upper(), roleDefinitionId=role_id.upper(), principalType="user")
    second = assignment("second")
    url = f"{endpoint}{namespace_id}/providers/Microsoft.Authorization/roleAssignments"
    next_url = url + "?api-version=2022-04-01&$skiptoken=next"
    mocked_responses.add(
        responses.GET, url,
        json={
            "value": [
                first, assignment("group", principalType="Group"),
                assignment("service", principalType="ServicePrincipal"),
                assignment("inherited", scope=f"/subscriptions/{subscription}"),
                assignment("child", scope=namespace_id + "/assets/child"),
                assignment("wrong-role", roleDefinitionId=role_id + "-other"),
                assignment("unknown", principalType=None),
            ],
            "nextLink": next_url,
        },
        match=[responses.matchers.query_param_matcher({"$filter": "atScope()"}, strict_match=False)],
    )
    mocked_responses.add(
        responses.GET, next_url, json={"value": [second]},
        match=[responses.matchers.query_param_matcher({"$skiptoken": "next"}, strict_match=False)],
    )
    assert LiveData(mocked_cmd)._get_user_reader_assignments(namespace_id, subscription) == [
        {"principalId": "first", "assignmentId": first["id"]},
        {"principalId": "second", "assignmentId": second["id"]},
    ]
    assert len(mocked_responses.calls) == 2
    assert all(call.request.url.startswith(endpoint + namespace_id) for call in mocked_responses.calls)
    assert token.call_args.args == (endpoint + "/.default",)


def test_adr_lifecycle_uses_referenced_subscription(mocked_cmd, mocked_responses):
    other_subscription = "11111111-1111-1111-1111-111111111111"
    instance = _build_instance_response("instance", "rg", adr_namespace_name="namespace")
    namespace_id = _build_adr_namespace_resource_id("namespace", "rg", other_subscription)
    instance["properties"]["adrNamespaceRef"]["resourceId"] = namespace_id
    adr_url = _build_adr_endpoint("namespace", "rg", other_subscription)
    cl_id = MOCK_EXTENDED_LOCATION["name"]
    eg_ctx = _make_eg_ctx("eg", "rg")
    desired_endpoint = {
        "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE, "address": eg_ctx.mqtt_hostname,
        "scopeId": "instance", "resourceId": eg_ctx.resource_id,
    }
    namespace = _build_adr_namespace_response(
        "namespace", "rg", subscription_id=other_subscription,
        identity_type="SystemAssigned", principal_id="adr-pid", observability_endpoints={},
    )
    mocked_responses.add(responses.GET, adr_url, json=namespace)
    mocked_responses.add(responses.PATCH, adr_url, json=namespace)
    provider = LiveData(mocked_cmd)
    provider._setup_adr_observability(
        instance, eg_ctx, cl_id, None, LiveDataRoleScope.NAMESPACE, "topic", None, True, wait_sec=0,
    )
    namespace["properties"]["observability"] = {"enabled": True, "endpoints": {cl_id: desired_endpoint}}
    mocked_responses.replace(responses.GET, adr_url, json=namespace)
    mocked_responses.add(responses.GET, _build_iotops_endpoint("instance", "rg"), json=instance)
    mocked_responses.add(
        responses.GET, _build_eg_endpoint("eg", "rg"), json=_build_eg_namespace_response("eg", "rg"),
    )
    topic_name = get_live_data_topic_space_name(instance["id"])
    mocked_responses.add(
        responses.GET, _build_eg_endpoint("eg", "rg", sub_resource=f"/topicSpaces/{topic_name}"),
        json={"properties": {"topicTemplates": ["aio/live-data/instance/#"]}},
    )
    for path in (f"/dataflowProfiles/{LIVE_DATA_PROFILE_NAME}", f"/dataflowEndpoints/{LIVE_DATA_ENDPOINT_NAME}"):
        endpoint = _build_iotops_endpoint("instance", "rg", sub_resource=path)
        mocked_responses.add(
            responses.GET, endpoint,
            json={"properties": {"instanceCount": 1, "diagnostics": {"logs": {"level": "info"}}}},
        )
        mocked_responses.add(responses.DELETE, endpoint, status=204)
    _register_reader_assignments(mocked_responses, namespace_id)
    _register_reader_assignments(mocked_responses, eg_ctx.resource_id)
    _register_reader_assignments(mocked_responses, f"{eg_ctx.resource_id}/topicSpaces/{topic_name}")
    assert provider.show("instance", "rg")["deviceRegistryNamespace"]["subscriptionId"] == other_subscription
    mocked_responses.add(
        responses.DELETE, _build_eg_endpoint("eg", "rg", sub_resource=f"/topicSpaces/{topic_name}"), status=204,
    )
    mocked_responses.add(responses.PUT, adr_url, json=namespace)
    provider.disable("instance", "rg", confirm_yes=True, wait_sec=0)
    adr_calls = [
        call.request for call in mocked_responses.calls if DEVICEREGISTRY_RP.lower() in call.request.url.lower()
    ]
    assert {call.method for call in adr_calls} == {"GET", "PATCH", "PUT"}
    assert all(f"/subscriptions/{other_subscription}/" in call.url for call in adr_calls)
    assert len(provider._registry_clients) == 2


def test_government_live_data_role_requests_use_active_cloud(mocked_cmd, mocked_responses, mocker):
    from azext_edge.edge.providers.orchestration.permissions import PermissionManager

    endpoint = "https://management.usgovcloudapi.net"
    mocked_cmd.cli_ctx.cloud.name = "AzureUSGovernment"
    mocked_cmd.cli_ctx.cloud.endpoints.resource_manager = endpoint + "/"
    token = mocker.patch("azext_edge.edge.util.az_client.AZURE_CLI_CREDENTIAL.get_token")
    token.return_value.token = "test-token"
    token.return_value.expires_on = 9999999999
    token.return_value.refresh_on = None
    provider = LiveData(mocked_cmd)
    eg_ctx = _make_eg_ctx("eg", "rg")
    other_subscription = "11111111-1111-1111-1111-111111111111"
    other_ctx = eg_ctx._replace(
        subscription_id=other_subscription,
        resource_id=eg_ctx.resource_id.replace(ZEROED_SUBSCRIPTION, other_subscription),
    )
    for manager, context in (
        (provider.permission_manager, eg_ctx), (provider._permission_manager(other_ctx), other_ctx),
    ):
        scope = context.resource_id
        url = f"{endpoint}{scope}/providers/Microsoft.Authorization/roleAssignments"
        mocked_responses.add(responses.GET, url, json={"value": []})
        mocked_responses.add(
            responses.PUT, re.compile(re.escape(url) + "/[^/?]+"), json={"id": scope + "/roleAssignments/test"},
        )
        manager.ensure_role_assignment(scope, "principal", "/roleDefinitions/test")
    namespace_id = _build_adr_namespace_resource_id("ns", "rg", other_subscription)
    url = f"{endpoint}{namespace_id}/providers/Microsoft.Authorization/roleAssignments"
    mocked_responses.add(responses.GET, url, json={"value": []})
    mocked_responses.add(
        responses.PUT, re.compile(re.escape(url) + "/[^/?]+"), json={"id": namespace_id + "/roleAssignments/test"},
    )
    provider._setup_user_role_assignments(namespace_id, ["11111111-1111-1111-1111-111111111111"])
    assert len(mocked_responses.calls) == 6
    assert all(call.request.url.startswith(endpoint) for call in mocked_responses.calls)
    assert token.call_args.args == (endpoint + "/.default",)
    assert isinstance(provider.permission_manager, PermissionManager)


class TestCommandAdapters:
    def test_subscriber_argument_registration(self, mocker):
        from azure.cli.core import AzCli
        from azext_edge import OpsExtensionCommandsLoader
        from azext_edge.edge import _help
        from knack.help_files import helps

        cli = mocker.Mock(spec=AzCli)
        cli.cloud = mocker.Mock(profile="latest")
        cli.data = {"completer_active": False}
        cli.enable_color = False
        cli.config = mocker.Mock()
        cli.invocation = mocker.Mock(data={})
        loader = OpsExtensionCommandsLoader(cli)
        cli.invocation.commands_loader = loader
        loader.load_command_table([])
        name = "iot ops live-data enable"
        loader.command_name = name
        cli.invocation.data["command_string"] = name
        loader.load_arguments(name)

        option = loader.argument_registry.get_cli_argument(name, "subscriber_object_ids").settings
        assert option["options_list"] == ["--subscriber-object-ids"]
        assert option["nargs"] == "+"
        assert option["arg_group"] == "Role Assignment"
        assert "--ra-scope" in option["help"]
        assert "--skip-ra" in option["help"]
        _help.load_iotops_help()
        assert "--subscriber-object-ids" in helps[name]
        assert "--subscriber-object-ids" in helps["iot ops live-data disable"]

    def test_enable_delegates(self, mocker):
        from azext_edge.edge import commands_live_data

        mock_provider = mocker.MagicMock()
        mocker.patch.object(commands_live_data, "LiveData", return_value=mock_provider)
        commands_live_data.live_data_enable(
            cmd=mocker.MagicMock(),
            instance_name="i",
            resource_group_name="rg",
            eg_resource_id="eg",
            user_object_ids=["11111111-1111-1111-1111-111111111111"],
            subscriber_object_ids=["22222222-2222-2222-2222-222222222222"],
        )
        mock_provider.enable.assert_called_once()
        assert mock_provider.enable.call_args.kwargs["name"] == "i"
        assert mock_provider.enable.call_args.kwargs["user_object_ids"] == [
            "11111111-1111-1111-1111-111111111111"
        ]
        assert mock_provider.enable.call_args.kwargs["subscriber_object_ids"] == [
            "22222222-2222-2222-2222-222222222222"
        ]

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
