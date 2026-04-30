# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional

import pytest
import responses
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from azext_edge.edge.providers.orchestration.common import (
    CUSTOM_LOCATIONS_API_VERSION,
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
    EXTENSION_TYPE_OPS,
    MANAGED_IDENTITY_API_VERSION,
    MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
    MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE,
    MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP,
    MGMT_ACTIONS_DEFAULT_MQTT_ENDPOINT,
    MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT,
    MGMT_ACTIONS_EG_AUDIENCE,
    MGMT_ACTIONS_GRAPH_ARTIFACT,
    MGMT_ACTIONS_GRAPH_RULES_VERSION,
    MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE,
    MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE,
    MIN_EG_CLIENT_SESSIONS_PER_AUTH_NAME,
    MIN_INSTANCE_VERSION_MGMT_ACTIONS,
    MQTT_ENDPOINT_TYPE,
)
from azext_edge.edge.providers.orchestration.permissions import ROLE_DEF_FORMAT_STR
from azext_edge.edge.util.az_client import (
    DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION,
    DEFAULT_EVENTGRID_MGMT_API_VERSION,
    DEFAULT_IOTOPS_MGMT_API_VERSION,
)
from azext_edge.edge.providers.orchestration.mgmt_actions import (
    EgNamespaceContext,
    MgmtActions,
    _build_graph_rules_config,
    get_mgmt_actions_resource_name,
)

from ...generators import BASE_URL, generate_random_string, generate_resource_id, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
DEVICEREGISTRY_RP = "Microsoft.DeviceRegistry"
DEVICEREGISTRY_API_VERSION = DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION.value
EVENTGRID_RP = "Microsoft.EventGrid"
EVENTGRID_API_VERSION = DEFAULT_EVENTGRID_MGMT_API_VERSION.value
IOTOPS_RP = "Microsoft.IoTOperations"
IOTOPS_API_VERSION = DEFAULT_IOTOPS_MGMT_API_VERSION.value
UAMI_API_VERSION = MANAGED_IDENTITY_API_VERSION
# Vendored KubernetesConfigurationClient bakes this version internally — no exported constant.
K8S_EXTENSIONS_API_VERSION = "2023-05-01"


# ---------------------------------------------------------------------------
# Autouse fixture — suppress Rich display for all tests in this module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def suppress_workflow_display(mocker):
    """Prevent WorkflowDisplay and render_summary from writing to stderr during tests."""
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.WorkflowDisplay")
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.render_summary")
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.console")


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
    """Build a full management endpoint URL for an EG namespace or sub-resource."""
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
    """Build a full management endpoint URL for an IoT Operations instance or sub-resource."""
    url = (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
        f"/providers/{IOTOPS_RP}/instances/{instance_name}"
    )
    if sub_resource:
        url += sub_resource
    url += f"?api-version={IOTOPS_API_VERSION}"
    return url


def _build_uami_endpoint(mi_resource_id: str) -> str:
    """Build a full management endpoint URL for a user-assigned managed identity GET."""
    return f"{BASE_URL}{mi_resource_id}?api-version={UAMI_API_VERSION}"


def _build_uami_resource_id(
    identity_name: str,
    resource_group_name: str,
    subscription_id: Optional[str] = None,
) -> str:
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    return (
        f"/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{identity_name}"
    )


def _build_uami_response(
    mi_resource_id: str,
    client_id: str,
    tenant_id: str,
) -> dict:
    return {
        "id": mi_resource_id,
        "properties": {
            "clientId": client_id,
            "tenantId": tenant_id,
            "principalId": "00000000-0000-0000-0000-aaaaaaaaaaaa",
        },
    }


def _build_namespace_response(
    namespace_name: str,
    resource_group_name: str,
    topic_spaces_state: str = "Enabled",
    mqtt_hostname: str = "test-ns.eastus-1.ts.eventgrid.azure.net",
    subscription_id: Optional[str] = None,
    max_client_sessions: int = MIN_EG_CLIENT_SESSIONS_PER_AUTH_NAME,
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
                "maximumClientSessionsPerAuthenticationName": max_client_sessions,
            },
        },
    }


def _build_topic_space_response(
    topic_space_name: str,
    topic_templates: list,
    description: str = "",
) -> dict:
    return {
        "id": f"/fake/path/topicSpaces/{topic_space_name}",
        "name": topic_space_name,
        "properties": {
            "description": description,
            "provisioningState": "Succeeded",
            "topicTemplates": topic_templates,
        },
    }


def _build_permission_binding_response(
    binding_name: str,
    permission: str,
    topic_space_name: str,
    client_group_name: str = "$all",
) -> dict:
    return {
        "id": f"/fake/path/permissionBindings/{binding_name}",
        "name": binding_name,
        "properties": {
            "clientGroupName": client_group_name,
            "permission": permission,
            "topicSpaceName": topic_space_name,
            "provisioningState": "Succeeded",
            "description": "",
        },
    }


def _get_expected_topic_templates(instance_name: str) -> list:
    return [
        MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE.format(scope_id=instance_name),
        MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE.format(scope_id=instance_name),
    ]


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
    """Build a full management endpoint URL for an ADR namespace."""
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    return (
        f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
        f"/providers/{DEVICEREGISTRY_RP}/namespaces/{namespace_name}"
        f"?api-version={DEVICEREGISTRY_API_VERSION}"
    )


def _build_adr_namespace_response(
    namespace_name: str,
    resource_group_name: str,
    identity_type: str = "None",
    principal_id: Optional[str] = None,
    management_endpoints: Optional[dict] = None,
    subscription_id: Optional[str] = None,
) -> dict:
    """Build a mock ADR namespace GET response."""
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    result: dict = {
        "id": (
            f"/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
            f"/providers/{DEVICEREGISTRY_RP}/namespaces/{namespace_name}"
        ),
        "name": namespace_name,
        "location": "eastus",
        "identity": {
            "type": identity_type,
        },
        "properties": {
            "provisioningState": "Succeeded",
        },
    }
    if principal_id:
        result["identity"]["principalId"] = principal_id
    if management_endpoints is not None:
        result["properties"]["management"] = {"endpoints": management_endpoints}
    return result


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


MOCK_EXTENDED_LOCATION: dict = {
    "name": (
        f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/test-rg"
        f"/providers/Microsoft.ExtendedLocation/customLocations/my-cl"
    ),
    "type": "CustomLocation",
}


def _build_instance_response(
    instance_name: str,
    resource_group_name: str,
    version: str = MIN_INSTANCE_VERSION_MGMT_ACTIONS,
    adr_namespace_name: Optional[str] = None,
    include_adr_ref: bool = True,
) -> dict:
    extended_location = MOCK_EXTENDED_LOCATION
    properties: dict = {
        "version": version,
        "provisioningState": "Succeeded",
    }
    if include_adr_ref:
        adr_ns_name = adr_namespace_name or f"{instance_name}-adr-ns"
        adr_ns_rid = _build_adr_namespace_resource_id(adr_ns_name, resource_group_name)
        properties["adrNamespaceRef"] = {"resourceId": adr_ns_rid}
    return {
        "id": (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
            f"/providers/{IOTOPS_RP}/instances/{instance_name}"
        ),
        "name": instance_name,
        "location": "eastus",
        "extendedLocation": extended_location,
        "properties": properties,
    }


def _make_base_fixtures() -> dict:
    """Build the common fixture core shared by enable, disable, and show tests.

    Returns instance identity fields and the 6 deterministic management-actions
    resource names derived from the instance resource ID.
    """
    instance_name = generate_random_string()
    rg = generate_random_string()
    instance_rid = _build_instance_response(instance_name, rg)["id"]
    return {
        "instance_name": instance_name,
        "rg": rg,
        "adr_ns_name": f"{instance_name}-adr-ns",
        "instance_rid": instance_rid,
        "ts_name": get_mgmt_actions_resource_name("ops", instance_rid),
        "pub_name": get_mgmt_actions_resource_name("pub", instance_rid),
        "sub_name": get_mgmt_actions_resource_name("sub", instance_rid),
        "ep_name": get_mgmt_actions_resource_name("eg", instance_rid),
        "graph_name": get_mgmt_actions_resource_name("req", instance_rid),
        "resp_name": get_mgmt_actions_resource_name("resp", instance_rid),
    }


# ---------------------------------------------------------------------------
# Resource naming tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "purpose, expected_len",
    [("ops", 25), ("eg", 24), ("req", 25), ("resp", 26)],
    ids=["topic-space", "dataflow-endpoint", "dataflow-graph", "response-dataflow"],
)
def test_deterministic_naming(purpose: str, expected_len: int):
    """Resource name is deterministic and uses the expected purpose prefix."""
    instance_rid = _build_eg_resource_id("some-instance", "some-rg")
    name_a = get_mgmt_actions_resource_name(purpose, instance_rid)
    name_b = get_mgmt_actions_resource_name(purpose, instance_rid)
    assert name_a == name_b
    assert name_a.startswith(f"mgmt-actions-{purpose}-")
    assert len(name_a) == expected_len


# ---------------------------------------------------------------------------
# _validate_eg_namespace tests
# ---------------------------------------------------------------------------


class TestValidateEgNamespace:
    """Tests for MgmtActions._validate_eg_namespace()."""

    def test_happy_path(self, mocked_cmd, mocked_responses: responses):
        """Valid EG namespace with topic spaces enabled returns correct EgNamespaceContext."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        eg_resource_id = _build_eg_resource_id(ns_name, rg)
        hostname = "myns.eastus-1.ts.eventgrid.azure.net"

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg),
            json=_build_namespace_response(ns_name, rg, mqtt_hostname=hostname),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        ctx = provider._validate_eg_namespace(eg_resource_id)

        assert isinstance(ctx, EgNamespaceContext)
        assert ctx.resource_id == eg_resource_id
        assert ctx.subscription_id == ZEROED_SUBSCRIPTION
        assert ctx.resource_group_name == rg
        assert ctx.namespace_name == ns_name
        assert ctx.mqtt_hostname == hostname
        assert len(mocked_responses.calls) == 1

    @pytest.mark.parametrize(
        "bad_resource_id",
        [
            # Wrong resource provider
            "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Storage/storageAccounts/sa1",
            # Wrong resource type under EventGrid
            "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.EventGrid/topics/mytopic",
            # Completely malformed
            "/subscriptions/sub1/resourceGroups/rg1",
        ],
    )
    def test_invalid_resource_type(self, mocked_cmd, mocked_responses: responses, bad_resource_id: str):
        """Non-EventGrid/namespaces resource IDs raise InvalidArgumentValueError."""
        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(InvalidArgumentValueError, match="Microsoft.EventGrid/namespaces"):
            provider._validate_eg_namespace(bad_resource_id)
        # No HTTP calls should be made for format validation failures
        assert len(mocked_responses.calls) == 0

    def test_namespace_not_found(self, mocked_cmd, mocked_responses: responses):
        """404 from namespace GET raises InvalidArgumentValueError."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        eg_resource_id = _build_eg_resource_id(ns_name, rg)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(InvalidArgumentValueError, match="not found"):
            provider._validate_eg_namespace(eg_resource_id)

    @pytest.mark.parametrize(
        "state, expected_snippet",
        [
            ("Disabled", "Current state: 'Disabled'"),
            ("", "MQTT broker has not been configured"),
        ],
    )
    def test_topic_spaces_not_enabled(
        self,
        mocked_cmd,
        mocked_responses: responses,
        state: str,
        expected_snippet: str,
    ):
        """Namespace with topic spaces not enabled raises ValidationError with appropriate detail."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        eg_resource_id = _build_eg_resource_id(ns_name, rg)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg),
            json=_build_namespace_response(ns_name, rg, topic_spaces_state=state),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match=expected_snippet):
            provider._validate_eg_namespace(eg_resource_id)

    def test_missing_mqtt_hostname(self, mocked_cmd, mocked_responses: responses):
        """Namespace with topic spaces enabled but no hostname raises ValidationError."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        eg_resource_id = _build_eg_resource_id(ns_name, rg)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg),
            json=_build_namespace_response(ns_name, rg, mqtt_hostname=""),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="no MQTT hostname"):
            provider._validate_eg_namespace(eg_resource_id)

    @pytest.mark.parametrize("session_count", [0, 1])
    def test_insufficient_client_sessions(
        self,
        mocked_cmd,
        mocked_responses: responses,
        session_count: int,
    ):
        """Namespace with maximumClientSessionsPerAuthenticationName below threshold raises ValidationError."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        eg_resource_id = _build_eg_resource_id(ns_name, rg)

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg),
            json=_build_namespace_response(ns_name, rg, max_client_sessions=session_count),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="maximumClientSessionsPerAuthenticationName"):
            provider._validate_eg_namespace(eg_resource_id)

    def test_cross_subscription(self, mocked_cmd, mocked_responses: responses):
        """EG namespace in a different subscription creates a cross-subscription client."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        cross_sub = "11111111-1111-1111-1111-111111111111"
        eg_resource_id = _build_eg_resource_id(ns_name, rg, subscription_id=cross_sub)
        hostname = "cross-sub.eastus-1.ts.eventgrid.azure.net"

        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, subscription_id=cross_sub),
            json=_build_namespace_response(ns_name, rg, mqtt_hostname=hostname, subscription_id=cross_sub),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        original_client = provider.eventgrid_mgmt_client
        ctx = provider._validate_eg_namespace(eg_resource_id)

        assert ctx.subscription_id == cross_sub
        assert ctx.mqtt_hostname == hostname
        # Client should have been replaced
        assert provider.eventgrid_mgmt_client is not original_client
        assert len(mocked_responses.calls) == 1


# ---------------------------------------------------------------------------
# _setup_eg_topic_space tests
# ---------------------------------------------------------------------------


class TestSetupEgTopicSpace:
    """Tests for MgmtActions._setup_eg_topic_space()."""

    def test_create_new_topic_space(self, mocked_cmd, mocked_responses: responses):
        """When topic space does not exist, creates it and returns status 'Created'."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)

        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        expected_templates = _get_expected_topic_templates(instance_name)

        # GET returns 404 (doesn't exist)
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT creates it
        ts_response = _build_topic_space_response(ts_name, expected_templates)
        mocked_responses.add(
            method=responses.PUT,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json=ts_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_topic_space(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            wait_sec=0,
        )

        assert result["name"] == ts_name
        assert result["topicTemplates"] == expected_templates
        assert result["scopeId"] == instance_name
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["topicTemplates"] == expected_templates
        assert instance_name in put_body["properties"]["description"]

    def test_existing_topic_space(self, mocked_cmd, mocked_responses: responses):
        """When topic space already exists, returns status 'Exists' without PUT."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)

        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        expected_templates = _get_expected_topic_templates(instance_name)

        # GET returns 200 (already exists)
        ts_response = _build_topic_space_response(ts_name, expected_templates)
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json=ts_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_topic_space(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            wait_sec=0,
        )

        assert result["name"] == ts_name
        assert result["topicTemplates"] == expected_templates
        assert result["scopeId"] == instance_name
        # Only the GET call, no PUT
        assert len(mocked_responses.calls) == 1

    def test_topic_templates_use_instance_name_as_scope(self, mocked_cmd):
        """Topic templates substitute scope_id with the instance name."""
        instance_name = "my-iot-instance"
        templates = _get_expected_topic_templates(instance_name)
        assert templates[0] == f"actions/requests/{instance_name}/#"
        assert templates[1] == f"actions/responses/{instance_name}/#"


# ---------------------------------------------------------------------------
# _setup_eg_permission_bindings tests
# ---------------------------------------------------------------------------


class TestSetupEgPermissionBindings:
    """Tests for MgmtActions._setup_eg_permission_bindings()."""

    def test_create_both_bindings(self, mocked_cmd, mocked_responses: responses):
        """When neither binding exists, creates both and returns status 'Created'."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        pub_name = get_mgmt_actions_resource_name("pub", instance_rid)
        sub_name = get_mgmt_actions_resource_name("sub", instance_rid)

        # Publisher: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{pub_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{pub_name}"),
            json=_build_permission_binding_response(pub_name, "Publisher", ts_name),
            status=200,
        )
        # Subscriber: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{sub_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{sub_name}"),
            json=_build_permission_binding_response(sub_name, "Subscriber", ts_name),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_rid,
            topic_space_name=ts_name,
            wait_sec=0,
        )

        assert result["publisher"]["name"] == pub_name
        assert result["publisher"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert result["subscriber"]["name"] == sub_name
        assert result["subscriber"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert len(mocked_responses.calls) == 4

        # Verify publisher PUT payload
        pub_body = json.loads(mocked_responses.calls[1].request.body)
        assert pub_body["properties"]["permission"] == "Publisher"
        assert pub_body["properties"]["topicSpaceName"] == ts_name
        assert pub_body["properties"]["clientGroupName"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP

        # Verify subscriber PUT payload
        sub_body = json.loads(mocked_responses.calls[3].request.body)
        assert sub_body["properties"]["permission"] == "Subscriber"
        assert sub_body["properties"]["topicSpaceName"] == ts_name

    def test_both_bindings_exist(self, mocked_cmd, mocked_responses: responses):
        """When both bindings exist, returns status 'Exists' without any PUTs."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        pub_name = get_mgmt_actions_resource_name("pub", instance_rid)
        sub_name = get_mgmt_actions_resource_name("sub", instance_rid)

        # Both return 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{pub_name}"),
            json=_build_permission_binding_response(pub_name, "Publisher", ts_name),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{sub_name}"),
            json=_build_permission_binding_response(sub_name, "Subscriber", ts_name),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_rid,
            topic_space_name=ts_name,
            wait_sec=0,
        )

        assert result["publisher"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert result["subscriber"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        # Only GET calls, no PUTs
        assert len(mocked_responses.calls) == 2

    def test_mixed_exists_and_create(self, mocked_cmd, mocked_responses: responses):
        """Publisher exists, subscriber does not — creates only subscriber."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        pub_name = get_mgmt_actions_resource_name("pub", instance_rid)
        sub_name = get_mgmt_actions_resource_name("sub", instance_rid)

        # Publisher: GET 200 (exists)
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{pub_name}"),
            json=_build_permission_binding_response(pub_name, "Publisher", ts_name),
            status=200,
        )
        # Subscriber: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{sub_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{sub_name}"),
            json=_build_permission_binding_response(sub_name, "Subscriber", ts_name),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_rid,
            topic_space_name=ts_name,
            wait_sec=0,
        )

        assert result["publisher"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert result["subscriber"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        # 1 GET (pub) + 1 GET (sub 404) + 1 PUT (sub create) = 3
        assert len(mocked_responses.calls) == 3

    @pytest.mark.parametrize(
        "eg_client_group, expected_group",
        [("myCustomGroup", "myCustomGroup"), (None, MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP)],
        ids=["custom-group", "default-group"],
    )
    def test_client_group_passthrough(
        self,
        mocked_cmd,
        mocked_responses: responses,
        eg_client_group: Optional[str],
        expected_group: str,
    ):
        """Client group value is correctly passed through to binding payloads."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        pub_name = get_mgmt_actions_resource_name("pub", instance_rid)
        sub_name = get_mgmt_actions_resource_name("sub", instance_rid)

        # Both GET 404, both PUT 200
        for name, perm in [(pub_name, "Publisher"), (sub_name, "Subscriber")]:
            mocked_responses.add(
                method=responses.GET,
                url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{name}"),
                json={"error": {"code": "ResourceNotFound"}},
                status=404,
            )
            mocked_responses.add(
                method=responses.PUT,
                url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{name}"),
                json=_build_permission_binding_response(name, perm, ts_name, client_group_name=expected_group),
                status=200,
            )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_rid,
            topic_space_name=ts_name,
            eg_client_group=eg_client_group,
            wait_sec=0,
        )

        assert result["publisher"]["clientGroup"] == expected_group
        assert result["subscriber"]["clientGroup"] == expected_group

        # Verify client group in PUT payloads
        pub_body = json.loads(mocked_responses.calls[1].request.body)
        assert pub_body["properties"]["clientGroupName"] == expected_group
        sub_body = json.loads(mocked_responses.calls[3].request.body)
        assert sub_body["properties"]["clientGroupName"] == expected_group


# ---------------------------------------------------------------------------
# _setup_eg_dataflow_endpoint tests
# ---------------------------------------------------------------------------


class TestSetupEgDataflowEndpoint:
    """Tests for MgmtActions._setup_eg_dataflow_endpoint()."""

    def test_create_new_system_assigned(self, mocked_cmd, mocked_responses: responses):
        """When endpoint does not exist and no UAMI, creates with SystemAssigned MI."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        # GET returns 404 (doesn't exist)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT creates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            wait_sec=0,
        )

        assert result["name"] == ep_name
        assert result["authentication"]["method"] == "SystemAssignedManagedIdentity"
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["extendedLocation"] == extended_location
        props = put_body["properties"]
        assert props["endpointType"] == MQTT_ENDPOINT_TYPE
        mqtt = props["mqttSettings"]
        assert mqtt["host"] == eg_ctx.mqtt_hostname
        assert mqtt["tls"] == {"mode": "Enabled"}
        auth = mqtt["authentication"]
        assert auth["method"] == "SystemAssignedManagedIdentity"
        assert auth["systemAssignedManagedIdentitySettings"]["audience"] == MGMT_ACTIONS_EG_AUDIENCE

    def test_create_new_includes_client_id_prefix(self, mocked_cmd, mocked_responses: responses):
        """The created MQTT dataflow endpoint sets clientIdPrefix to the AIO instance name."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=MOCK_EXTENDED_LOCATION,
            wait_sec=0,
        )

        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["mqttSettings"]["clientIdPrefix"] == instance_name
        assert len(mocked_responses.calls) == 2

    def test_create_new_user_assigned(self, mocked_cmd, mocked_responses: responses):
        """When endpoint does not exist and pre-resolved UAMI is provided, creates with UserAssigned MI."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)
        uami_name = generate_random_string()
        uami_rid = _build_uami_resource_id(uami_name, rg)
        uami_client_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        uami_tenant_id = "tttttttt-tttt-tttt-tttt-tttttttttttt"
        uami_resource = _build_uami_response(uami_rid, uami_client_id, uami_tenant_id)

        # GET dataflow endpoint returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT creates endpoint
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            mi_resource=uami_resource,
            wait_sec=0,
        )

        assert result["name"] == ep_name
        result_auth = result["authentication"]
        assert result_auth["method"] == "UserAssignedManagedIdentity"
        assert result_auth["userAssignedManagedIdentitySettings"]["clientId"] == uami_client_id
        assert result_auth["userAssignedManagedIdentitySettings"]["tenantId"] == uami_tenant_id
        # GET endpoint (404) + PUT endpoint (200) = 2 (UAMI already resolved by caller)
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload
        put_body = json.loads(mocked_responses.calls[1].request.body)
        auth = put_body["properties"]["mqttSettings"]["authentication"]
        assert auth["method"] == "UserAssignedManagedIdentity"
        uami_settings = auth["userAssignedManagedIdentitySettings"]
        assert uami_settings["clientId"] == uami_client_id
        assert uami_settings["tenantId"] == uami_tenant_id
        assert uami_settings["scope"] == f"{MGMT_ACTIONS_EG_AUDIENCE}/.default"

    def test_existing_endpoint_same_config(self, mocked_cmd, mocked_responses: responses):
        """When endpoint already exists with matching host and auth, returns without PUT."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        existing_auth = {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {"audience": MGMT_ACTIONS_EG_AUDIENCE},
        }
        # GET returns 200 with matching host, auth, and clientIdPrefix
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={
                "id": f"/fake/path/dataflowEndpoints/{ep_name}",
                "name": ep_name,
                "properties": {
                    "mqttSettings": {
                        "host": eg_ctx.mqtt_hostname,
                        "clientIdPrefix": instance_name,
                        "authentication": existing_auth,
                    },
                },
            },
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            wait_sec=0,
        )

        assert result["name"] == ep_name
        assert result["authentication"] == existing_auth
        assert result["exists"] is True
        assert "updated" not in result
        # Only the GET call, no PUT
        assert len(mocked_responses.calls) == 1

    @pytest.mark.parametrize(
        "existing_prefix",
        [
            pytest.param(None, id="missing-client-id-prefix"),
            pytest.param("stale-prefix", id="different-client-id-prefix"),
        ],
    )
    def test_existing_endpoint_client_id_prefix_updates(
        self, mocked_cmd, mocked_responses: responses, existing_prefix
    ):
        """Endpoint with a missing or stale clientIdPrefix is updated to the current instance name."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        existing_auth = {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {"audience": MGMT_ACTIONS_EG_AUDIENCE},
        }
        existing_mqtt = {
            "host": eg_ctx.mqtt_hostname,
            "authentication": existing_auth,
        }
        if existing_prefix is not None:
            existing_mqtt["clientIdPrefix"] = existing_prefix

        # GET returns 200 with matching host/auth but a missing or stale clientIdPrefix
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={
                "id": f"/fake/path/dataflowEndpoints/{ep_name}",
                "name": ep_name,
                "properties": {"mqttSettings": existing_mqtt},
            },
            status=200,
        )
        # PUT updates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            wait_sec=0,
        )

        assert result["exists"] is True
        assert result["updated"] is True
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload sets clientIdPrefix to the instance name
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["mqttSettings"]["clientIdPrefix"] == instance_name

    def test_existing_endpoint_different_host(self, mocked_cmd, mocked_responses: responses):
        """When endpoint exists with a different host, updates via PUT."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        new_hostname = "new-ns.westus2-1.ts.eventgrid.azure.net"
        eg_ctx = _make_eg_ctx(resource_group_name=rg, mqtt_hostname=new_hostname)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        existing_auth = {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {"audience": MGMT_ACTIONS_EG_AUDIENCE},
        }
        # GET returns 200 with OLD host but matching auth
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={
                "id": f"/fake/path/dataflowEndpoints/{ep_name}",
                "name": ep_name,
                "properties": {
                    "mqttSettings": {
                        "host": "old-ns.eastus-1.ts.eventgrid.azure.net",
                        "authentication": existing_auth,
                    },
                },
            },
            status=200,
        )
        # PUT updates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            wait_sec=0,
        )

        assert result["name"] == ep_name
        assert result["exists"] is True
        assert result["updated"] is True
        assert result["authentication"]["method"] == "SystemAssignedManagedIdentity"
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload has the new host
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["mqttSettings"]["host"] == new_hostname

    def test_existing_endpoint_sami_to_uami(self, mocked_cmd, mocked_responses: responses):
        """When endpoint exists with SAMI but UAMI is now provided, updates auth via PUT."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        uami_client_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        uami_tenant_id = "tttttttt-tttt-tttt-tttt-tttttttttttt"
        uami_resource = _build_uami_response(
            _build_uami_resource_id("my-uami", rg), uami_client_id, uami_tenant_id
        )

        existing_auth = {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {"audience": MGMT_ACTIONS_EG_AUDIENCE},
        }
        # GET returns 200 with matching host but SAMI auth
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={
                "id": f"/fake/path/dataflowEndpoints/{ep_name}",
                "name": ep_name,
                "properties": {
                    "mqttSettings": {
                        "host": eg_ctx.mqtt_hostname,
                        "authentication": existing_auth,
                    },
                },
            },
            status=200,
        )
        # PUT updates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            mi_resource=uami_resource,
            wait_sec=0,
        )

        assert result["exists"] is True
        assert result["updated"] is True
        assert result["authentication"]["method"] == "UserAssignedManagedIdentity"
        assert result["authentication"]["userAssignedManagedIdentitySettings"]["clientId"] == uami_client_id
        assert len(mocked_responses.calls) == 2

    def test_existing_endpoint_uami_to_sami(self, mocked_cmd, mocked_responses: responses):
        """When endpoint exists with UAMI but no mi_resource provided, updates to SAMI via PUT."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = _make_eg_ctx(resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        existing_auth = {
            "method": "UserAssignedManagedIdentity",
            "userAssignedManagedIdentitySettings": {
                "clientId": "old-client-id",
                "tenantId": "old-tenant-id",
                "scope": f"{MGMT_ACTIONS_EG_AUDIENCE}/.default",
            },
        }
        # GET returns 200 with matching host but UAMI auth
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={
                "id": f"/fake/path/dataflowEndpoints/{ep_name}",
                "name": ep_name,
                "properties": {
                    "mqttSettings": {
                        "host": eg_ctx.mqtt_hostname,
                        "authentication": existing_auth,
                    },
                },
            },
            status=200,
        )
        # PUT updates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            wait_sec=0,
        )

        assert result["exists"] is True
        assert result["updated"] is True
        assert result["authentication"]["method"] == "SystemAssignedManagedIdentity"
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload has SAMI auth
        put_body = json.loads(mocked_responses.calls[1].request.body)
        auth = put_body["properties"]["mqttSettings"]["authentication"]
        assert auth["method"] == "SystemAssignedManagedIdentity"

    def test_existing_endpoint_host_and_auth_mismatch(self, mocked_cmd, mocked_responses: responses):
        """When both host and auth differ, updates both via PUT."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        new_hostname = "new-ns.westus2-1.ts.eventgrid.azure.net"
        eg_ctx = _make_eg_ctx(resource_group_name=rg, mqtt_hostname=new_hostname)
        extended_location = MOCK_EXTENDED_LOCATION

        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        uami_client_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        uami_tenant_id = "tttttttt-tttt-tttt-tttt-tttttttttttt"
        uami_resource = _build_uami_response(
            _build_uami_resource_id("my-uami", rg), uami_client_id, uami_tenant_id
        )

        # Existing has OLD host + SAMI auth
        existing_auth = {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {"audience": MGMT_ACTIONS_EG_AUDIENCE},
        }
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={
                "id": f"/fake/path/dataflowEndpoints/{ep_name}",
                "name": ep_name,
                "properties": {
                    "mqttSettings": {
                        "host": "old-ns.eastus-1.ts.eventgrid.azure.net",
                        "authentication": existing_auth,
                    },
                },
            },
            status=200,
        )
        # PUT updates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            mi_resource=uami_resource,
            wait_sec=0,
        )

        assert result["exists"] is True
        assert result["updated"] is True
        assert result["authentication"]["method"] == "UserAssignedManagedIdentity"
        assert len(mocked_responses.calls) == 2

        # Verify the PUT payload has both new host and new auth
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["mqttSettings"]["host"] == new_hostname
        assert put_body["properties"]["mqttSettings"]["authentication"]["method"] == "UserAssignedManagedIdentity"

    def _create_endpoint_and_get_put_body(
        self,
        mocked_cmd,
        mocked_responses: responses,
        eg_ctx: Optional[EgNamespaceContext] = None,
    ) -> dict:
        """Register GET 404 + PUT 200 mocks, call _setup_eg_dataflow_endpoint, return the PUT body."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        if eg_ctx is None:
            eg_ctx = _make_eg_ctx(resource_group_name=rg)
        extended_location = MOCK_EXTENDED_LOCATION
        ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider._setup_eg_dataflow_endpoint(
            eg_ctx=eg_ctx,
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            wait_sec=0,
        )

        return json.loads(mocked_responses.calls[1].request.body)

    def test_host_is_raw_hostname(self, mocked_cmd, mocked_responses: responses):
        """Host in the MQTT settings is the raw MQTT hostname without port."""
        hostname = "my-ns.westus2-1.ts.eventgrid.azure.net"
        eg_ctx = _make_eg_ctx(namespace_name="my-ns", mqtt_hostname=hostname)
        put_body = self._create_endpoint_and_get_put_body(mocked_cmd, mocked_responses, eg_ctx=eg_ctx)
        assert put_body["properties"]["mqttSettings"]["host"] == hostname
        assert ":" not in put_body["properties"]["mqttSettings"]["host"]

    def test_tls_enabled_no_custom_ca(self, mocked_cmd, mocked_responses: responses):
        """TLS is enabled without a custom CA configmap for EG public endpoints."""
        put_body = self._create_endpoint_and_get_put_body(mocked_cmd, mocked_responses)
        tls = put_body["properties"]["mqttSettings"]["tls"]
        assert tls["mode"] == "Enabled"
        assert "trustedCaCertificateConfigMapRef" not in tls

    def test_uami_not_found(self, mocked_cmd, mocked_responses: responses):
        """When UAMI resource is not found, _resolve_user_assigned_mi raises InvalidArgumentValueError."""
        rg = generate_random_string()
        uami_rid = _build_uami_resource_id("missing-identity", rg)

        # GET UAMI returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_uami_endpoint(uami_rid),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(InvalidArgumentValueError, match="not found"):
            provider._resolve_user_assigned_mi(uami_rid)

        assert len(mocked_responses.calls) == 1


# ---------------------------------------------------------------------------
# _setup_adr_management_endpoint tests
# ---------------------------------------------------------------------------


class TestSetupAdrManagementEndpoint:
    """Tests for MgmtActions._setup_adr_management_endpoint()."""

    def _make_instance(
        self,
        instance_name: str,
        rg: str,
        adr_ns_name: str,
    ) -> dict:
        """Build a minimal instance dict with adrNamespaceRef and extendedLocation."""
        return _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns_name)

    def test_create_new_identity_and_endpoint(self, mocked_cmd, mocked_responses: responses):
        """ADR namespace has no identity and no management endpoint — enables both."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = generate_random_string()
        eg_ctx = _make_eg_ctx()

        instance = self._make_instance(instance_name, rg, adr_ns_name)
        principal_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # GET: no identity, no management endpoints
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(adr_ns_name, rg, identity_type="None"),
            status=200,
        )
        # PATCH: returns SystemAssigned with principalId
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints={
                    instance["extendedLocation"]["name"]: {
                        "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                        "address": eg_ctx.mqtt_hostname,
                        "scopeId": instance_name,
                        "resourceId": eg_ctx.resource_id,
                    },
                },
            ),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_adr_management_endpoint(
            instance=instance,
            eg_ctx=eg_ctx,
            wait_sec=0,
        )

        assert "principalId" not in result
        assert result["name"] == adr_ns_name
        assert result["identity"]["type"] == "SystemAssigned"
        assert result["identity"]["principalId"] == principal_id
        cl_id = instance["extendedLocation"]["name"]
        assert cl_id in result["managementEndpoints"]
        assert result["managementEndpoints"][cl_id]["endpointType"] == MGMT_ACTIONS_ADR_ENDPOINT_TYPE
        assert result["managementEndpoints"][cl_id]["address"] == eg_ctx.mqtt_hostname
        assert "resourceId" not in result

        # Verify PATCH payload
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        assert patch_body["identity"]["type"] == "SystemAssigned"
        mgmt_endpoints = patch_body["properties"]["management"]["endpoints"]
        cl_id = instance["extendedLocation"]["name"]
        assert cl_id in mgmt_endpoints
        assert mgmt_endpoints[cl_id]["endpointType"] == MGMT_ACTIONS_ADR_ENDPOINT_TYPE
        assert mgmt_endpoints[cl_id]["address"] == eg_ctx.mqtt_hostname
        assert mgmt_endpoints[cl_id]["scopeId"] == instance_name
        assert mgmt_endpoints[cl_id]["resourceId"] == eg_ctx.resource_id

        assert len(mocked_responses.calls) == 2

    def test_already_configured_skips_update(self, mocked_cmd, mocked_responses: responses):
        """ADR namespace already has SystemAssigned identity and matching endpoint — returns Exists."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = generate_random_string()
        eg_ctx = _make_eg_ctx()

        instance = self._make_instance(instance_name, rg, adr_ns_name)
        cl_id = instance["extendedLocation"]["name"]
        principal_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # GET: already has matching identity and endpoint
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints={
                    cl_id: {
                        "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                        "address": eg_ctx.mqtt_hostname,
                        "scopeId": instance_name,
                        "resourceId": eg_ctx.resource_id,
                    },
                },
            ),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_adr_management_endpoint(
            instance=instance,
            eg_ctx=eg_ctx,
        )

        assert "principalId" not in result
        assert result["name"] == adr_ns_name
        assert result["identity"]["type"] == "SystemAssigned"
        assert result["identity"]["principalId"] == principal_id
        assert cl_id in result["managementEndpoints"]
        assert result["managementEndpoints"][cl_id]["endpointType"] == MGMT_ACTIONS_ADR_ENDPOINT_TYPE

        # Only GET — no PATCH
        assert len(mocked_responses.calls) == 1

    def test_identity_exists_endpoint_missing(self, mocked_cmd, mocked_responses: responses):
        """ADR namespace has SystemAssigned identity but no management endpoint entry."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = generate_random_string()
        eg_ctx = _make_eg_ctx()

        instance = self._make_instance(instance_name, rg, adr_ns_name)
        principal_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # GET: has identity, no management endpoints
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
            ),
            status=200,
        )
        # PATCH: add endpoint
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints={
                    instance["extendedLocation"]["name"]: {
                        "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                        "address": eg_ctx.mqtt_hostname,
                        "scopeId": instance_name,
                        "resourceId": eg_ctx.resource_id,
                    },
                },
            ),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_adr_management_endpoint(
            instance=instance,
            eg_ctx=eg_ctx,
            wait_sec=0,
        )

        assert "principalId" not in result
        assert result["identity"]["type"] == "SystemAssigned"
        assert result["identity"]["principalId"] == principal_id
        cl_id = instance["extendedLocation"]["name"]
        assert cl_id in result["managementEndpoints"]

        # Verify PATCH does NOT include identity block (already SystemAssigned)
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        assert "identity" not in patch_body

        assert len(mocked_responses.calls) == 2

    def test_preserves_existing_endpoints(self, mocked_cmd, mocked_responses: responses):
        """PATCH payload includes existing management endpoints from other custom locations."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = generate_random_string()
        eg_ctx = _make_eg_ctx()

        instance = self._make_instance(instance_name, rg, adr_ns_name)
        cl_id = instance["extendedLocation"]["name"]
        principal_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # Pre-existing endpoint from a different custom location
        other_cl_id = (
            "/subscriptions/other-sub/resourceGroups/other-rg"
            "/providers/Microsoft.ExtendedLocation/customLocations/other-cl"
        )
        existing_endpoints = {
            other_cl_id: {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": "other-host.eastus-1.ts.eventgrid.azure.net",
                "scopeId": "other-instance",
                "resourceId": (
                    "/subscriptions/other-sub/resourceGroups/other-rg"
                    "/providers/Microsoft.EventGrid/namespaces/other-ns"
                ),
            },
        }

        # GET: has identity but endpoint is for a different CL
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints=existing_endpoints,
            ),
            status=200,
        )
        # PATCH: merge endpoints — response includes both endpoints
        merged_endpoints = dict(existing_endpoints)
        merged_endpoints[cl_id] = {
            "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
            "address": eg_ctx.mqtt_hostname,
            "scopeId": instance_name,
            "resourceId": eg_ctx.resource_id,
        }
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints=merged_endpoints,
            ),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_adr_management_endpoint(
            instance=instance,
            eg_ctx=eg_ctx,
            wait_sec=0,
        )

        # Both our entry and the other CL's entry should be in the result
        assert cl_id in result["managementEndpoints"]
        assert other_cl_id in result["managementEndpoints"]

        # Verify PATCH payload preserves the other CL's endpoint
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        mgmt_endpoints = patch_body["properties"]["management"]["endpoints"]
        assert other_cl_id in mgmt_endpoints
        assert cl_id in mgmt_endpoints
        # Other endpoint data unchanged
        assert mgmt_endpoints[other_cl_id] == existing_endpoints[other_cl_id]

        assert len(mocked_responses.calls) == 2

    def test_endpoint_value_changed_reports_updated(self, mocked_cmd, mocked_responses: responses):
        """When the CL key exists but values differ, reports 'Updated'."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = generate_random_string()
        eg_ctx = _make_eg_ctx()

        instance = self._make_instance(instance_name, rg, adr_ns_name)
        cl_id = instance["extendedLocation"]["name"]
        principal_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # Existing endpoint has a stale address
        stale_endpoint = {
            cl_id: {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": "old-host.eventgrid.azure.net",
                "scopeId": instance_name,
                "resourceId": eg_ctx.resource_id,
            },
        }

        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints=stale_endpoint,
            ),
            status=200,
        )
        # PATCH response includes the updated endpoint
        updated_endpoint = {
            cl_id: {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": eg_ctx.mqtt_hostname,
                "scopeId": instance_name,
                "resourceId": eg_ctx.resource_id,
            },
        }
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=principal_id,
                management_endpoints=updated_endpoint,
            ),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_adr_management_endpoint(
            instance=instance,
            eg_ctx=eg_ctx,
            wait_sec=0,
        )

        assert result["identity"]["type"] == "SystemAssigned"
        assert cl_id in result["managementEndpoints"]
        # Address should be the updated value from the PATCH response
        assert result["managementEndpoints"][cl_id]["address"] == eg_ctx.mqtt_hostname
        assert len(mocked_responses.calls) == 2

    def test_missing_adr_namespace_ref(self, mocked_cmd, mocked_responses: responses):
        """Instance without adrNamespaceRef raises ValidationError."""
        instance = _build_instance_response("test-inst", "test-rg")
        # Remove adrNamespaceRef
        instance["properties"].pop("adrNamespaceRef", None)
        eg_ctx = _make_eg_ctx()

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="adrNamespaceRef"):
            provider._setup_adr_management_endpoint(instance=instance, eg_ctx=eg_ctx)

        assert len(mocked_responses.calls) == 0

    def test_no_principal_id_in_response_raises(self, mocked_cmd, mocked_responses: responses):
        """When PATCH returns no principalId, raises ValidationError."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = generate_random_string()
        eg_ctx = _make_eg_ctx()

        instance = self._make_instance(instance_name, rg, adr_ns_name)

        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(adr_ns_name, rg, identity_type="None"),
            status=200,
        )
        # PATCH response without principalId
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(adr_ns_name, rg, identity_type="SystemAssigned"),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="principalId"):
            provider._setup_adr_management_endpoint(instance=instance, eg_ctx=eg_ctx, wait_sec=0)

        assert len(mocked_responses.calls) == 2


# ---------------------------------------------------------------------------
# _setup_dataflow_graph tests
# ---------------------------------------------------------------------------


class TestSetupDataflowGraph:
    """Tests for MgmtActions._setup_dataflow_graph()."""

    def test_create_new(self, mocked_cmd, mocked_responses: responses):
        """When graph does not exist, creates with correct nodes and connections."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        profile_name = "default"
        eg_ep_name = get_mgmt_actions_resource_name("eg", instance_rid)
        graph_name = get_mgmt_actions_resource_name("req", instance_rid)

        # GET returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflowGraphs/{graph_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT creates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflowGraphs/{graph_name}",
            ),
            json={"id": f"/fake/path/dataflowGraphs/{graph_name}", "name": graph_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_dataflow_graph(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name=eg_ep_name,
            dataflow_profile_name=profile_name,
            registry_endpoint_name=MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT,
            wait_sec=0,
        )

        assert result["name"] == graph_name
        assert len(mocked_responses.calls) == 2

        # Verify PUT payload structure
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["extendedLocation"] == extended_location
        props = put_body["properties"]
        assert props["mode"] == "Enabled"

        # Verify 3 nodes
        nodes = props["nodes"]
        assert len(nodes) == 3

        source_node = nodes[0]
        assert source_node["name"] == "source"
        assert source_node["nodeType"] == "Source"
        assert source_node["sourceSettings"]["endpointRef"] == eg_ep_name
        assert source_node["sourceSettings"]["dataSources"] == [f"actions/requests/{instance_name}/#"]

        graph_node = nodes[1]
        assert graph_node["name"] == "graph"
        assert graph_node["nodeType"] == "Graph"
        gs = graph_node["graphSettings"]
        assert gs["registryEndpointRef"] == MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT
        assert gs["artifact"] == MGMT_ACTIONS_GRAPH_ARTIFACT
        # Verify configuration is a list with key-value structure
        config = gs["configuration"]
        assert isinstance(config, list)
        assert len(config) == 1
        assert config[0]["key"] == "rules"
        rules_value = json.loads(config[0]["value"])
        assert rules_value["version"] == MGMT_ACTIONS_GRAPH_RULES_VERSION
        assert len(rules_value["map"]) == 2
        assert f"^actions/requests/{instance_name}/" in rules_value["map"][0]["expression"]

        dest_node = nodes[2]
        assert dest_node["name"] == "destination"
        assert dest_node["nodeType"] == "Destination"
        assert dest_node["destinationSettings"]["endpointRef"] == MGMT_ACTIONS_DEFAULT_MQTT_ENDPOINT
        assert dest_node["destinationSettings"]["dataDestination"] == "${outputTopic}"

        # Verify 2 connections
        conns = props["nodeConnections"]
        assert len(conns) == 2
        assert conns[0]["from"]["name"] == "source"
        assert conns[0]["to"]["name"] == "graph"
        assert conns[1]["from"]["name"] == "graph"
        assert conns[1]["to"]["name"] == "destination"

    def test_already_exists(self, mocked_cmd, mocked_responses: responses):
        """When graph already exists, returns 'Exists' without PUT."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        profile_name = "default"
        graph_name = get_mgmt_actions_resource_name("req", instance_rid)
        eg_ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        # GET returns 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflowGraphs/{graph_name}",
            ),
            json={"id": f"/fake/path/dataflowGraphs/{graph_name}", "name": graph_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_dataflow_graph(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name=eg_ep_name,
            dataflow_profile_name=profile_name,
            registry_endpoint_name=MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT,
            wait_sec=0,
        )

        assert result["name"] == graph_name
        assert len(mocked_responses.calls) == 1

    def test_custom_dataflow_profile(self, mocked_cmd, mocked_responses: responses):
        """Graph is created under the specified dataflow profile, not just 'default'."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        custom_profile = "my-custom-profile"
        graph_name = get_mgmt_actions_resource_name("req", instance_rid)
        eg_ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        # GET returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{custom_profile}/dataflowGraphs/{graph_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT creates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{custom_profile}/dataflowGraphs/{graph_name}",
            ),
            json={"id": f"/fake/path/dataflowGraphs/{graph_name}", "name": graph_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_dataflow_graph(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name=eg_ep_name,
            dataflow_profile_name=custom_profile,
            registry_endpoint_name=MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT,
            wait_sec=0,
        )

        assert result["name"] == graph_name
        assert len(mocked_responses.calls) == 2

    def test_custom_registry_endpoint(self, mocked_cmd, mocked_responses: responses):
        """Graph node uses the specified registry endpoint ref, not just 'default'."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        profile_name = "default"
        custom_registry_ep = "my-custom-registry-ep"
        graph_name = get_mgmt_actions_resource_name("req", instance_rid)
        eg_ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        # GET returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflowGraphs/{graph_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT creates it
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflowGraphs/{graph_name}",
            ),
            json={"id": f"/fake/path/dataflowGraphs/{graph_name}", "name": graph_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_dataflow_graph(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name=eg_ep_name,
            dataflow_profile_name=profile_name,
            registry_endpoint_name=custom_registry_ep,
            wait_sec=0,
        )

        assert result["name"] == graph_name
        assert len(mocked_responses.calls) == 2

        # Verify the graph node uses the custom registry endpoint
        put_body = json.loads(mocked_responses.calls[1].request.body)
        graph_node = put_body["properties"]["nodes"][1]
        assert graph_node["graphSettings"]["registryEndpointRef"] == custom_registry_ep


# ---------------------------------------------------------------------------
# _build_graph_rules_config tests
# ---------------------------------------------------------------------------


class TestBuildGraphRulesConfig:
    """Tests for the _build_graph_rules_config module-level helper."""

    def test_produces_valid_config_list(self):
        """Output is a key-value list with a JSON string rules value."""
        result = _build_graph_rules_config(topic_prefix_regex="^actions/requests/myinst/")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["key"] == "rules"
        rules_value = json.loads(result[0]["value"])
        assert rules_value["version"] == MGMT_ACTIONS_GRAPH_RULES_VERSION
        assert rules_value["datasets"] == []
        assert len(rules_value["map"]) == 2

    def test_topic_prefix_regex_in_expression(self):
        """The topic prefix regex is embedded in the regex_replace expression."""
        regex = "^actions/requests/[^/]+/"
        result = _build_graph_rules_config(topic_prefix_regex=regex)
        rules_value = json.loads(result[0]["value"])
        strip_entry = rules_value["map"][0]
        assert strip_entry["description"] == "Strip the topic prefix"
        assert strip_entry["inputs"] == ["$metadata.topic"]
        assert strip_entry["output"] == "$metadata.topic"
        assert regex in strip_entry["expression"]

    def test_copy_payload_entry(self):
        """The second map entry copies the full payload through."""
        result = _build_graph_rules_config(topic_prefix_regex="^test/")
        rules_value = json.loads(result[0]["value"])
        copy_entry = rules_value["map"][1]
        assert copy_entry["description"] == "Copy the payload"
        assert copy_entry["inputs"] == ["*"]
        assert copy_entry["output"] == "*"


# ---------------------------------------------------------------------------
# _setup_response_dataflow tests
# ---------------------------------------------------------------------------


class TestSetupResponseDataflow:
    """Tests for MgmtActions._setup_response_dataflow — response (edge→cloud) dataflow resource."""

    def test_create_new(self, mocked_cmd, mocked_responses: responses):
        """Creates a new response dataflow with correct operations payload."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        profile_name = "default"
        eg_ep_name = get_mgmt_actions_resource_name("eg", instance_rid)
        dataflow_name = get_mgmt_actions_resource_name("resp", instance_rid)

        # GET returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflows/{dataflow_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT returns 200
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflows/{dataflow_name}",
            ),
            json={"id": f"/fake/path/dataflows/{dataflow_name}", "name": dataflow_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_response_dataflow(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name=eg_ep_name,
            dataflow_profile_name=profile_name,
            wait_sec=0,
        )

        assert result["name"] == dataflow_name

        # Verify PUT body
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["extendedLocation"] == extended_location
        props = put_body["properties"]
        assert props["mode"] == "Enabled"

        ops = props["operations"]
        assert len(ops) == 2

        # Source operation — local MQTT broker
        source_op = ops[0]
        assert source_op["operationType"] == "Source"
        assert source_op["sourceSettings"]["endpointRef"] == MGMT_ACTIONS_DEFAULT_MQTT_ENDPOINT
        expected_topic = MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE.format(scope_id=instance_name)
        assert source_op["sourceSettings"]["dataSources"] == [expected_topic]

        # Destination operation — EG endpoint
        dest_op = ops[1]
        assert dest_op["operationType"] == "Destination"
        assert dest_op["destinationSettings"]["endpointRef"] == eg_ep_name
        assert dest_op["destinationSettings"]["dataDestination"] == "${inputTopic}"

        assert len(mocked_responses.calls) == 2

    def test_already_exists(self, mocked_cmd, mocked_responses: responses):
        """Returns Exists status when the response dataflow already exists."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        profile_name = "default"
        dataflow_name = get_mgmt_actions_resource_name("resp", instance_rid)

        # GET returns 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{profile_name}/dataflows/{dataflow_name}",
            ),
            json={"id": f"/fake/path/dataflows/{dataflow_name}", "name": dataflow_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_response_dataflow(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name="some-ep",
            dataflow_profile_name=profile_name,
            wait_sec=0,
        )

        assert result["name"] == dataflow_name
        assert len(mocked_responses.calls) == 1

    def test_custom_dataflow_profile(self, mocked_cmd, mocked_responses: responses):
        """Response dataflow is created under the specified dataflow profile."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        extended_location = MOCK_EXTENDED_LOCATION
        custom_profile = "my-custom-profile"
        dataflow_name = get_mgmt_actions_resource_name("resp", instance_rid)
        eg_ep_name = get_mgmt_actions_resource_name("eg", instance_rid)

        # GET returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{custom_profile}/dataflows/{dataflow_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # PUT returns 200
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name,
                rg,
                sub_resource=f"/dataflowProfiles/{custom_profile}/dataflows/{dataflow_name}",
            ),
            json={"id": f"/fake/path/dataflows/{dataflow_name}", "name": dataflow_name},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_response_dataflow(
            instance_name=instance_name,
            instance_resource_id=instance_rid,
            resource_group_name=rg,
            extended_location=extended_location,
            eg_dataflow_endpoint_name=eg_ep_name,
            dataflow_profile_name=custom_profile,
            wait_sec=0,
        )

        assert result["name"] == dataflow_name

        # Verify the PUT went to the custom profile URL
        put_url = mocked_responses.calls[1].request.url
        assert f"/dataflowProfiles/{custom_profile}/" in put_url

        assert len(mocked_responses.calls) == 2


# ---------------------------------------------------------------------------
# _resolve_dataflow_auth_identity tests
# ---------------------------------------------------------------------------


class TestResolveDataflowAuthIdentity:
    """Tests for MgmtActions._resolve_dataflow_auth_identity()."""

    def test_uami_returns_principal_id(self, mocked_cmd, mocked_responses: responses):
        """When mi_resource is provided, returns its principalId directly."""
        provider = MgmtActions(cmd=mocked_cmd)
        mi_resource = _build_uami_response(
            mi_resource_id=_build_uami_resource_id("test-mi", "test-rg"),
            client_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            tenant_id="tttttttt-tttt-tttt-tttt-tttttttttttt",
        )

        result = provider._resolve_dataflow_auth_identity(
            instance=_build_instance_response("inst", "test-rg"),
            mi_resource=mi_resource,
        )

        assert result == "00000000-0000-0000-0000-aaaaaaaaaaaa"
        # No HTTP calls — UAMI resource already resolved
        assert len(mocked_responses.calls) == 0

    def test_uami_missing_principal_id_raises(self, mocked_cmd, mocked_responses: responses):
        """When mi_resource has no principalId, raises ValidationError."""
        provider = MgmtActions(cmd=mocked_cmd)
        mi_resource = {
            "id": _build_uami_resource_id("test-mi", "test-rg"),
            "properties": {
                "clientId": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "tenantId": "tttttttt-tttt-tttt-tttt-tttttttttttt",
            },
        }

        with pytest.raises(ValidationError, match="missing 'principalId'"):
            provider._resolve_dataflow_auth_identity(
                instance=_build_instance_response("inst", "test-rg"),
                mi_resource=mi_resource,
            )

    def test_system_mi_resolves_via_connected_cluster(self, mocked_cmd, mocked_responses: responses):
        """Default path: resolves AIO extension MI via custom location → connected cluster."""
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance = _build_instance_response(instance_name, rg)
        cl_id = instance["extendedLocation"]["name"]
        cluster_name = "my-cluster"
        cluster_rg = rg
        cluster_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{cluster_rg}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
        )
        ext_principal_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

        # GET custom location → returns hostResourceId
        mocked_responses.add(
            method=responses.GET,
            url=f"{BASE_URL}{cl_id}?api-version={CUSTOM_LOCATIONS_API_VERSION}",
            json={
                "id": cl_id,
                "properties": {"hostResourceId": cluster_rid},
            },
            status=200,
        )
        # GET extensions list → returns AIO extension with identity
        mocked_responses.add(
            method=responses.GET,
            url=(
                f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{cluster_rg}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
                f"/providers/Microsoft.KubernetesConfiguration/extensions"
                f"?api-version={K8S_EXTENSIONS_API_VERSION}"
            ),
            json={
                "value": [
                    {
                        "name": "aio-ext",
                        "properties": {"extensionType": EXTENSION_TYPE_OPS},
                        "identity": {"principalId": ext_principal_id},
                    },
                ],
            },
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._resolve_dataflow_auth_identity(instance=instance)

        assert result == ext_principal_id

    def test_extension_not_found_raises(self, mocked_cmd, mocked_responses: responses):
        """When AIO extension is not found on the cluster, raises ValidationError."""
        rg = generate_random_string()
        instance = _build_instance_response("inst", rg)
        cl_id = instance["extendedLocation"]["name"]
        cluster_name = "my-cluster"
        cluster_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
        )

        # GET custom location
        mocked_responses.add(
            method=responses.GET,
            url=f"{BASE_URL}{cl_id}?api-version={CUSTOM_LOCATIONS_API_VERSION}",
            json={"id": cl_id, "properties": {"hostResourceId": cluster_rid}},
            status=200,
        )
        # GET extensions list → no AIO extension
        mocked_responses.add(
            method=responses.GET,
            url=(
                f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
                f"/providers/Microsoft.KubernetesConfiguration/extensions"
                f"?api-version={K8S_EXTENSIONS_API_VERSION}"
            ),
            json={"value": [{"name": "other-ext", "properties": {"extensionType": "other.type"}}]},
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="IoT Operations extension not found"):
            provider._resolve_dataflow_auth_identity(instance=instance)

    def test_extension_missing_principal_id_raises(self, mocked_cmd, mocked_responses: responses):
        """When AIO extension has no principalId, raises ValidationError."""
        rg = generate_random_string()
        instance = _build_instance_response("inst", rg)
        cl_id = instance["extendedLocation"]["name"]
        cluster_name = "my-cluster"
        cluster_rid = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
        )

        # GET custom location
        mocked_responses.add(
            method=responses.GET,
            url=f"{BASE_URL}{cl_id}?api-version={CUSTOM_LOCATIONS_API_VERSION}",
            json={"id": cl_id, "properties": {"hostResourceId": cluster_rid}},
            status=200,
        )
        # GET extensions list → AIO extension present but no principalId
        mocked_responses.add(
            method=responses.GET,
            url=(
                f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
                f"/providers/Microsoft.KubernetesConfiguration/extensions"
                f"?api-version={K8S_EXTENSIONS_API_VERSION}"
            ),
            json={
                "value": [
                    {
                        "name": "aio-ext",
                        "properties": {"extensionType": EXTENSION_TYPE_OPS},
                        "identity": {},
                    },
                ],
            },
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="missing 'identity.principalId'"):
            provider._resolve_dataflow_auth_identity(instance=instance)


# ---------------------------------------------------------------------------
# _setup_role_assignments tests
# ---------------------------------------------------------------------------


class TestSetupRoleAssignments:
    """Tests for MgmtActions._setup_role_assignments()."""

    def test_assigns_default_roles_both_principals(self, mocked_cmd, mocker):
        """Both identity principals get Publisher + Subscriber roles using defaults."""
        mock_pm = mocker.patch(
            "azext_edge.edge.providers.orchestration.mgmt_actions.PermissionManager"
        ).return_value
        mock_pm.apply_role_assignment.return_value = None  # existing (idempotent)

        eg_ctx = _make_eg_ctx()
        adr_pid = "aaaa-bbbb-cccc-dddd"
        df_pid = "eeee-ffff-1111-2222"

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_role_assignments(
            eg_ctx=eg_ctx,
            adr_principal_id=adr_pid,
            dataflow_auth_principal_id=df_pid,
        )

        assert set(result.keys()) == {"adrNamespace", "dataflowIdentity"}

        assert result["adrNamespace"]["principalId"] == adr_pid
        assert result["adrNamespace"]["roles"] == [
            EG_TOPICSPACES_PUBLISHER_ROLE_ID,
            EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
        ]

        assert result["dataflowIdentity"]["principalId"] == df_pid
        assert result["dataflowIdentity"]["roles"] == [
            EG_TOPICSPACES_PUBLISHER_ROLE_ID,
            EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
        ]

        # 2 principals × 2 roles = 4 apply_role_assignment calls
        assert mock_pm.apply_role_assignment.call_count == 4

    def test_custom_role_ids(self, mocked_cmd, mocker):
        """Custom role IDs override defaults for each identity principal."""
        mock_pm = mocker.patch(
            "azext_edge.edge.providers.orchestration.mgmt_actions.PermissionManager"
        ).return_value
        mock_pm.apply_role_assignment.return_value = None

        eg_ctx = _make_eg_ctx()
        adr_pid = "aaaa-bbbb-cccc-dddd"
        df_pid = "eeee-ffff-1111-2222"
        custom_adr_roles = ["custom-role-adr-1"]
        custom_ops_roles = ["custom-role-ops-1", "custom-role-ops-2", "custom-role-ops-3"]

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_role_assignments(
            eg_ctx=eg_ctx,
            adr_principal_id=adr_pid,
            dataflow_auth_principal_id=df_pid,
            adr_role_ids=custom_adr_roles,
            ops_role_ids=custom_ops_roles,
        )

        assert result["adrNamespace"]["roles"] == custom_adr_roles
        assert result["dataflowIdentity"]["roles"] == custom_ops_roles
        # 1 + 3 = 4 apply_role_assignment calls
        assert mock_pm.apply_role_assignment.call_count == 4

    def test_role_def_id_uses_eg_subscription(self, mocked_cmd, mocker):
        """Role definition IDs are scoped to the EG namespace subscription."""
        mock_pm = mocker.patch(
            "azext_edge.edge.providers.orchestration.mgmt_actions.PermissionManager"
        ).return_value
        mock_pm.apply_role_assignment.return_value = None

        eg_sub = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        eg_ctx = _make_eg_ctx()
        # Override subscription to simulate cross-sub
        eg_ctx = EgNamespaceContext(
            resource_id=eg_ctx.resource_id,
            subscription_id=eg_sub,
            resource_group_name=eg_ctx.resource_group_name,
            namespace_name=eg_ctx.namespace_name,
            mqtt_hostname=eg_ctx.mqtt_hostname,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider._setup_role_assignments(
            eg_ctx=eg_ctx,
            adr_principal_id="adr-pid",
            dataflow_auth_principal_id="df-pid",
        )

        # Check that the first call used a role_def_id scoped to the EG subscription
        first_call = mock_pm.apply_role_assignment.call_args_list[0]
        expected_role_def = ROLE_DEF_FORMAT_STR.format(
            subscription_id=eg_sub,
            role_id=EG_TOPICSPACES_PUBLISHER_ROLE_ID,
        )
        assert first_call.kwargs["role_def_id"] == expected_role_def

    def test_cross_subscription_creates_new_permission_manager(self, mocked_cmd, mocker):
        """When EG is in a different subscription, a new PermissionManager is created."""
        pm_cls = mocker.patch(
            "azext_edge.edge.providers.orchestration.mgmt_actions.PermissionManager"
        )
        pm_cls.return_value.apply_role_assignment.return_value = None

        cross_sub = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        eg_ctx = EgNamespaceContext(
            resource_id=_build_eg_resource_id("ns", "rg", subscription_id=cross_sub),
            subscription_id=cross_sub,
            resource_group_name="rg",
            namespace_name="ns",
            mqtt_hostname="ns.eastus.ts.eventgrid.azure.net",
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider._setup_role_assignments(
            eg_ctx=eg_ctx,
            adr_principal_id="adr-pid",
            dataflow_auth_principal_id="df-pid",
        )

        # PermissionManager should be constructed twice:
        # once in __init__ (default sub) and once for the cross-sub EG
        assert pm_cls.call_count == 2
        cross_sub_call = pm_cls.call_args_list[1]
        assert cross_sub_call.kwargs["subscription_id"] == cross_sub

    def test_http_error_raises_validation_error(self, mocked_cmd, mocker):
        """HttpResponseError from apply_role_assignment raises ValidationError."""
        mock_pm = mocker.patch(
            "azext_edge.edge.providers.orchestration.mgmt_actions.PermissionManager"
        ).return_value
        mock_pm.apply_role_assignment.side_effect = HttpResponseError(
            message="Authorization failed"
        )

        eg_ctx = _make_eg_ctx()

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="Failed to assign role"):
            provider._setup_role_assignments(
                eg_ctx=eg_ctx,
                adr_principal_id="adr-pid",
                dataflow_auth_principal_id="df-pid",
            )

    def test_same_principal_both_identities(self, mocked_cmd, mocker):
        """When both identity principals share the same ID, roles are still assigned independently."""
        mock_pm = mocker.patch(
            "azext_edge.edge.providers.orchestration.mgmt_actions.PermissionManager"
        ).return_value
        mock_pm.apply_role_assignment.return_value = None

        same_pid = "shared-principal-id"

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_role_assignments(
            eg_ctx=_make_eg_ctx(),
            adr_principal_id=same_pid,
            dataflow_auth_principal_id=same_pid,
        )

        assert result["adrNamespace"]["principalId"] == same_pid
        assert result["dataflowIdentity"]["principalId"] == same_pid
        # Still 4 calls (idempotency handled by apply_role_assignment)
        assert mock_pm.apply_role_assignment.call_count == 4


# ---------------------------------------------------------------------------
# enable() orchestration tests
# ---------------------------------------------------------------------------


class TestEnable:
    """Tests for MgmtActions.enable() — orchestration wiring and return structure.

    Individual sub-method logic (payloads, error paths, naming) is tested in
    the dedicated Test* classes above. These tests focus on how enable() ties
    the stages together and the shape of the return object.
    """

    def _make_enable_fixtures(self, dataflow_profile: str = "default") -> dict:
        """Build common test fixtures for enable tests."""
        base = _make_base_fixtures()
        ns_name = generate_random_string()
        instance_response = _build_instance_response(base["instance_name"], base["rg"])
        return {
            **base,
            "ns_name": ns_name,
            "hostname": f"{ns_name}.eastus-1.ts.eventgrid.azure.net",
            "instance_response": instance_response,
            "cl_id": instance_response["extendedLocation"]["name"],
            "eg_rid": _build_eg_resource_id(ns_name, base["rg"]),
            "adr_principal_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "dataflow_profile": dataflow_profile,
        }

    def _register_enable_mocks(
        self,
        mocked_responses: responses,
        f: dict,
        *,
        mi_response: Optional[dict] = None,
    ) -> None:
        """Register HTTP mocks for an enable() call.

        Registers 16 calls (or 17 with mi_response) in the exact order
        the enable() method issues them:
          Instance GET → EG namespace GET → (UAMI GET) → topic space → permission bindings
          → ADR namespace GET/PATCH → dataflow endpoint → dataflow graph → response dataflow.
        """
        instance_name, rg = f["instance_name"], f["rg"]
        ns_name, hostname = f["ns_name"], f["hostname"]
        instance_response = f["instance_response"]
        cl_id, eg_rid = f["cl_id"], f["eg_rid"]
        adr_ns_name, adr_principal_id = f["adr_ns_name"], f["adr_principal_id"]
        dataflow_profile = f["dataflow_profile"]
        ts_name, pub_name, sub_name = f["ts_name"], f["pub_name"], f["sub_name"]
        ep_name, graph_name, resp_name = f["ep_name"], f["graph_name"], f["resp_name"]
        # 1. GET instance
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg),
            json=instance_response,
            status=200,
        )
        # 2. GET EG namespace
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg),
            json=_build_namespace_response(ns_name, rg, mqtt_hostname=hostname),
            status=200,
        )
        # 3. (optional) GET user-assigned managed identity
        if mi_response is not None:
            mocked_responses.add(
                method=responses.GET,
                url=_build_uami_endpoint(mi_response["id"]),
                json=mi_response,
                status=200,
            )
        # Topic space: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/topicSpaces/{ts_name}"),
            json=_build_topic_space_response(ts_name, _get_expected_topic_templates(instance_name)),
            status=200,
        )
        # Permission bindings (pub + sub): each GET 404, PUT 200
        for name, perm in [(pub_name, "Publisher"), (sub_name, "Subscriber")]:
            mocked_responses.add(
                method=responses.GET,
                url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{name}"),
                json={"error": {"code": "ResourceNotFound"}},
                status=404,
            )
            mocked_responses.add(
                method=responses.PUT,
                url=_build_eg_endpoint(ns_name, rg, sub_resource=f"/permissionBindings/{name}"),
                json=_build_permission_binding_response(name, perm, ts_name),
                status=200,
            )
        # ADR namespace: GET, PATCH 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(adr_ns_name, rg, identity_type="None"),
            status=200,
        )
        mocked_responses.add(
            method=responses.PATCH,
            url=_build_adr_endpoint(adr_ns_name, rg),
            json=_build_adr_namespace_response(
                adr_ns_name,
                rg,
                identity_type="SystemAssigned",
                principal_id=adr_principal_id,
                management_endpoints={
                    cl_id: {
                        "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                        "address": hostname,
                        "scopeId": instance_name,
                        "resourceId": eg_rid,
                    },
                },
            ),
            status=200,
        )
        # Dataflow endpoint: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}"),
            json={"id": f"/fake/path/dataflowEndpoints/{ep_name}", "name": ep_name},
            status=200,
        )
        # Dataflow graph: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name, rg,
                sub_resource=f"/dataflowProfiles/{dataflow_profile}/dataflowGraphs/{graph_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name, rg,
                sub_resource=f"/dataflowProfiles/{dataflow_profile}/dataflowGraphs/{graph_name}",
            ),
            json={"id": f"/fake/path/dataflowGraphs/{graph_name}", "name": graph_name},
            status=200,
        )
        # Response dataflow: GET 404, PUT 200
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name, rg,
                sub_resource=f"/dataflowProfiles/{dataflow_profile}/dataflows/{resp_name}",
            ),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_iotops_endpoint(
                instance_name, rg,
                sub_resource=f"/dataflowProfiles/{dataflow_profile}/dataflows/{resp_name}",
            ),
            json={"id": f"/fake/path/dataflows/{resp_name}", "name": resp_name},
            status=200,
        )

    def test_happy_path_return_structure(self, mocked_cmd, mocked_responses: responses, mocker):
        """All resources created fresh — validates return object shape and key data flow."""
        f = self._make_enable_fixtures()
        df_auth_pid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        mock_role_result = {
            "adrNamespace": {"principalId": f["adr_principal_id"], "roles": ["pub-role", "sub-role"]},
            "dataflowIdentity": {"principalId": df_auth_pid, "roles": ["pub-role", "sub-role"]},
        }
        mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity", return_value=df_auth_pid)
        mocker.patch.object(MgmtActions, "_setup_role_assignments", return_value=mock_role_result)
        self._register_enable_mocks(mocked_responses, f)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.enable(
            name=f["instance_name"],
            resource_group_name=f["rg"],
            eg_resource_id=f["eg_rid"],
            wait_sec=0,
        )

        # -- Assert top-level keys --
        assert set(result.keys()) == {"instance", "eventGrid", "deviceRegistryNamespace", "roleAssignments"}

        # -- Assert instance section --
        inst = result["instance"]
        assert "name" not in inst  # user-supplied echo field
        assert "resourceGroup" not in inst  # user-supplied echo field
        assert "resourceId" not in inst
        assert "version" not in inst  # user-supplied echo field
        assert inst["dataflowProfile"] == MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE
        # dataflowEndpoint is an instance child resource, not under eventGrid
        assert "dataflowEndpoint" in inst
        assert inst["dataflowEndpoint"]["name"] == f["ep_name"]
        assert inst["requestDataflowGraph"]["name"] == f["graph_name"]
        assert inst["responseDataflow"]["name"] == f["resp_name"]
        # Internal `exists` and `updated` flags must be stripped from consumer-facing return (desired-state semantics)
        assert "exists" not in inst["dataflowEndpoint"]
        assert "updated" not in inst["dataflowEndpoint"]
        assert "exists" not in inst["requestDataflowGraph"]
        assert "exists" not in inst["responseDataflow"]

        # -- Assert eventGrid section --
        eg = result["eventGrid"]
        assert eg["namespace"]["name"] == f["ns_name"]
        assert "resourceId" not in eg["namespace"]
        assert eg["namespace"]["resourceGroup"] == f["rg"]
        assert eg["namespace"]["subscriptionId"] == ZEROED_SUBSCRIPTION
        assert eg["namespace"]["mqttHostname"] == f["hostname"]
        assert "dataflowEndpoint" not in eg  # must not be here

        assert eg["topicSpace"]["name"] == f["ts_name"]
        assert eg["topicSpace"]["scopeId"] == f["instance_name"]
        assert "exists" not in eg["topicSpace"]  # internal flag stripped

        assert eg["permissionBindings"]["publisher"]["name"] == f["pub_name"]
        assert eg["permissionBindings"]["publisher"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert eg["permissionBindings"]["subscriber"]["name"] == f["sub_name"]
        assert eg["permissionBindings"]["subscriber"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP

        # -- Assert deviceRegistryNamespace section --
        adr = result["deviceRegistryNamespace"]
        assert "principalId" not in adr
        assert adr["resourceGroup"] == f["rg"]
        assert adr["subscriptionId"] == ZEROED_SUBSCRIPTION
        assert adr["identity"]["type"] == "SystemAssigned"
        assert adr["identity"]["principalId"] == f["adr_principal_id"]
        assert adr["managementEndpoint"]["endpointType"] == MGMT_ACTIONS_ADR_ENDPOINT_TYPE
        assert adr["managementEndpoint"]["address"] == f["hostname"]
        assert adr["managementEndpoint"]["scopeId"] == f["instance_name"]
        assert "managementEndpoints" not in adr

        # -- Assert roleAssignments section --
        assert result["roleAssignments"] == mock_role_result

        # -- Assert total HTTP call count: 16 --
        assert len(mocked_responses.calls) == 16

    @pytest.mark.parametrize("version", ["1.0.0", ""], ids=["below-minimum", "empty-string"])
    def test_invalid_version(self, mocked_cmd, mocked_responses: responses, version: str):
        """enable() raises ValidationError when instance version is below minimum or empty."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        ns_name = generate_random_string()
        eg_rid = _build_eg_resource_id(ns_name, rg)

        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg),
            json=_build_instance_response(instance_name, rg, version=version),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="does not meet the minimum"):
            provider.enable(
                name=instance_name,
                resource_group_name=rg,
                eg_resource_id=eg_rid,
                wait_sec=0,
            )

        assert len(mocked_responses.calls) == 1

    @pytest.mark.parametrize(
        "version",
        [
            "1.3.0-main.20260307.5",
            "1.0.0-alpha.1",
            "1.3.14-rc.1",
            "2.0.0-beta.1",
        ],
        ids=[
            "ci-build-below-min-patch",
            "prerelease-well-below-min",
            "prerelease-at-exact-min",
            "prerelease-above-min-major",
        ],
    )
    def test_prerelease_version_skips_gate(self, mocked_cmd, mocked_responses: responses, mocker, version: str):
        """enable() skips the minimum version check when instance version has a pre-release component."""
        f = self._make_enable_fixtures()
        f["instance_response"]["properties"]["version"] = version
        mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity", return_value="df-pid")
        mocker.patch.object(MgmtActions, "_setup_role_assignments", return_value={})
        self._register_enable_mocks(mocked_responses, f)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.enable(
            name=f["instance_name"],
            resource_group_name=f["rg"],
            eg_resource_id=f["eg_rid"],
            wait_sec=0,
        )

        assert result  # Flow completed without ValidationError

    def test_custom_dataflow_profile(self, mocked_cmd, mocked_responses: responses, mocker):
        """enable() uses a custom dataflow profile name when provided."""
        custom_profile = "my-custom-profile"
        f = self._make_enable_fixtures(dataflow_profile=custom_profile)
        mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity", return_value="df-pid")
        mocker.patch.object(MgmtActions, "_setup_role_assignments", return_value={})
        self._register_enable_mocks(mocked_responses, f)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.enable(
            name=f["instance_name"],
            resource_group_name=f["rg"],
            eg_resource_id=f["eg_rid"],
            dataflow_profile=custom_profile,
            wait_sec=0,
        )

        assert result["instance"]["requestDataflowGraph"]["name"] == f["graph_name"]
        assert result["instance"]["responseDataflow"]["name"] == f["resp_name"]
        assert result["instance"]["dataflowProfile"] == custom_profile

        # Verify the response dataflow PUT went to the custom profile URL
        resp_put_url = mocked_responses.calls[-1].request.url
        assert f"/dataflowProfiles/{custom_profile}/" in resp_put_url

        assert len(mocked_responses.calls) == 16

    def test_user_assigned_mi(self, mocked_cmd, mocked_responses: responses, mocker):
        """enable() configures UserAssignedManagedIdentity auth when mi_user_assigned is provided."""
        f = self._make_enable_fixtures()
        mi_name = generate_random_string()
        mi_client_id = "11111111-1111-1111-1111-111111111111"
        mi_tenant_id = "22222222-2222-2222-2222-222222222222"
        mi_rid = _build_uami_resource_id(mi_name, f["rg"])
        mi_response = _build_uami_response(mi_rid, mi_client_id, mi_tenant_id)

        mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity", return_value="df-pid")
        mocker.patch.object(MgmtActions, "_setup_role_assignments", return_value={})
        self._register_enable_mocks(mocked_responses, f, mi_response=mi_response)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.enable(
            name=f["instance_name"],
            resource_group_name=f["rg"],
            eg_resource_id=f["eg_rid"],
            mi_user_assigned=mi_rid,
            wait_sec=0,
        )

        assert result["instance"]["dataflowEndpoint"]["name"] == f["ep_name"]

        # Verify the endpoint PUT body contains UserAssignedManagedIdentity auth
        # Index 12: UAMI GET(2) + topic space(3-4) + bindings(5-8) + ADR(9-10) + ep GET(11) + ep PUT(12)
        endpoint_put_call = mocked_responses.calls[12]
        endpoint_body = json.loads(endpoint_put_call.request.body)
        auth = endpoint_body["properties"]["mqttSettings"]["authentication"]
        assert auth["method"] == "UserAssignedManagedIdentity"
        uami_settings = auth["userAssignedManagedIdentitySettings"]
        assert uami_settings["clientId"] == mi_client_id
        assert uami_settings["tenantId"] == mi_tenant_id
        assert uami_settings["scope"] == f"{MGMT_ACTIONS_EG_AUDIENCE}/.default"

        assert len(mocked_responses.calls) == 17

    def test_skip_role_assignments(self, mocked_cmd, mocked_responses: responses, mocker):
        """When skip_role_assignments=True, roleAssignments key is absent from result."""
        f = self._make_enable_fixtures()
        mock_resolve = mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity")
        mock_setup_ra = mocker.patch.object(MgmtActions, "_setup_role_assignments")
        self._register_enable_mocks(mocked_responses, f)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.enable(
            name=f["instance_name"],
            resource_group_name=f["rg"],
            eg_resource_id=f["eg_rid"],
            skip_role_assignments=True,
            wait_sec=0,
        )

        # roleAssignments key should be absent when skipped
        assert "roleAssignments" not in result
        assert set(result.keys()) == {"instance", "eventGrid", "deviceRegistryNamespace"}

        # Verify identity resolution and role setup were NOT called
        mock_resolve.assert_not_called()
        mock_setup_ra.assert_not_called()

        assert len(mocked_responses.calls) == 16


# ---------------------------------------------------------------------------
# disable() tests
# ---------------------------------------------------------------------------


class TestDisable:
    """Tests for MgmtActions.disable().

    Validates the teardown orchestration: AIO resources (response dataflow, graph,
    endpoint), ADR management endpoint removal, and EG resources (permission bindings,
    topic space). EG discovery is auto-derived from the ADR namespace management endpoint.
    """

    PROMPT_TARGET = "azext_edge.edge.providers.orchestration.mgmt_actions.should_continue_prompt"

    def _make_disable_fixtures(
        self,
        eg_subscription_id: Optional[str] = None,
        include_mgmt_endpoint: bool = True,
        include_adr_namespace_ref: bool = True,
    ) -> dict:
        """Build common test fixtures for disable tests."""
        base = _make_base_fixtures()
        instance_name, rg = base["instance_name"], base["rg"]
        eg_ns_name = generate_random_string()
        eg_rg = generate_random_string()
        eg_sub = eg_subscription_id or ZEROED_SUBSCRIPTION
        hostname = f"{eg_ns_name}.eastus-1.ts.eventgrid.azure.net"
        custom_location_id = MOCK_EXTENDED_LOCATION["name"]

        instance_response = _build_instance_response(
            instance_name, rg, adr_namespace_name=base["adr_ns_name"]
        )
        if not include_adr_namespace_ref:
            instance_response["properties"].pop("adrNamespaceRef", None)

        eg_rid = _build_eg_resource_id(eg_ns_name, eg_rg, subscription_id=eg_sub)

        mgmt_endpoints = {}
        if include_mgmt_endpoint:
            mgmt_endpoints[custom_location_id] = {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": hostname,
                "scopeId": instance_name,
                "resourceId": eg_rid,
            }

        return {
            **base,
            "adr_rg": rg,
            "eg_ns_name": eg_ns_name,
            "eg_rg": eg_rg,
            "eg_sub": eg_sub,
            "hostname": hostname,
            "custom_location_id": custom_location_id,
            "instance_response": instance_response,
            "eg_rid": eg_rid,
            "mgmt_endpoints": mgmt_endpoints,
        }

    def _register_disable_mocks(
        self,
        mocked_responses: responses,
        f: dict,
        adr_not_found: bool = False,
        graph_profile: str = MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE,
        graph_not_found_in_default: bool = False,
        graph_not_found_anywhere: bool = False,
        resp_dataflow_orphaned: bool = False,
        aio_resources_not_found: bool = False,
        eg_not_found: bool = False,
        ep_not_found: bool = False,
        extra_adr_endpoints: Optional[dict] = None,
    ) -> None:
        """Register HTTP mocks for a disable() call.

        Mock insertion order mirrors the exact HTTP call sequence of disable().
        """
        # 1. GET instance
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=f["instance_response"],
            status=200,
        )

        # 2. GET ADR namespace
        mgmt_endpoints = dict(f["mgmt_endpoints"])
        if extra_adr_endpoints:
            mgmt_endpoints.update(extra_adr_endpoints)

        if adr_not_found:
            mocked_responses.add(
                method=responses.GET,
                url=_build_adr_endpoint(f["adr_ns_name"], f["adr_rg"]),
                json={"error": {"code": "ResourceNotFound"}},
                status=404,
            )
            return

        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["adr_ns_name"], f["adr_rg"]),
            json=_build_adr_namespace_response(
                f["adr_ns_name"], f["adr_rg"],
                identity_type="SystemAssigned",
                principal_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
                management_endpoints=mgmt_endpoints,
            ),
            status=200,
        )

        # 3. Profile auto-detection: GET graph under default profile
        if graph_not_found_anywhere:
            # Graph not in default profile
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                    f"/dataflowGraphs/{f['graph_name']}",
                ),
                json={"error": {"code": "ResourceNotFound"}},
                status=404,
            )
            # List profiles returns empty
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource="/dataflowProfiles",
                ),
                json={"value": []},
                status=200,
            )
        elif graph_not_found_in_default and graph_profile != MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE:
            # Graph not in default profile
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                    f"/dataflowGraphs/{f['graph_name']}",
                ),
                json={"error": {"code": "ResourceNotFound"}},
                status=404,
            )
            # List profiles returns the custom profile
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource="/dataflowProfiles",
                ),
                json={"value": [{"name": graph_profile}]},
                status=200,
            )
            # Graph found in custom profile
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{graph_profile}/dataflowGraphs/{f['graph_name']}",
                ),
                json={"name": f["graph_name"]},
                status=200,
            )
        else:
            # Graph found in default profile (common case)
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{graph_profile}/dataflowGraphs/{f['graph_name']}",
                ),
                json={"name": f["graph_name"]},
                status=200,
            )

        # 3b. Response dataflow discovery (only when graph not found anywhere)
        if graph_not_found_anywhere:
            if resp_dataflow_orphaned:
                # Orphaned response dataflow found in default profile
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_iotops_endpoint(
                        f["instance_name"], f["rg"],
                        sub_resource=f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                        f"/dataflows/{f['resp_name']}",
                    ),
                    json={"name": f["resp_name"]},
                    status=200,
                )
            else:
                # Response dataflow also not found — second discovery pass
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_iotops_endpoint(
                        f["instance_name"], f["rg"],
                        sub_resource=f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                        f"/dataflows/{f['resp_name']}",
                    ),
                    json={"error": {"code": "ResourceNotFound"}},
                    status=404,
                )
                # list_by_resource_group reuses the existing profiles mock from step 3

        # 3c. Endpoint existence check GET
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                f["instance_name"], f["rg"],
                sub_resource=f"/dataflowEndpoints/{f['ep_name']}",
            ),
            json={"name": f["ep_name"]} if not ep_not_found else {"error": {"code": "ResourceNotFound"}},
            status=200 if not ep_not_found else 404,
        )

        # 3d. EG resource existence GETs (topic space + pub + sub)
        if f["mgmt_endpoints"]:
            eg_probe_status = 404 if eg_not_found else 200
            mocked_responses.add(
                method=responses.GET,
                url=_build_eg_endpoint(
                    f["eg_ns_name"], f["eg_rg"],
                    subscription_id=f["eg_sub"],
                    sub_resource=f"/topicSpaces/{f['ts_name']}",
                ),
                json={"name": f["ts_name"]} if not eg_not_found else {"error": {"code": "ResourceNotFound"}},
                status=eg_probe_status,
            )
            mocked_responses.add(
                method=responses.GET,
                url=_build_eg_endpoint(
                    f["eg_ns_name"], f["eg_rg"],
                    subscription_id=f["eg_sub"],
                    sub_resource=f"/permissionBindings/{f['pub_name']}",
                ),
                json={"name": f["pub_name"]} if not eg_not_found else {"error": {"code": "ResourceNotFound"}},
                status=eg_probe_status,
            )
            mocked_responses.add(
                method=responses.GET,
                url=_build_eg_endpoint(
                    f["eg_ns_name"], f["eg_rg"],
                    subscription_id=f["eg_sub"],
                    sub_resource=f"/permissionBindings/{f['sub_name']}",
                ),
                json={"name": f["sub_name"]} if not eg_not_found else {"error": {"code": "ResourceNotFound"}},
                status=eg_probe_status,
            )

        # 4. AIO resource deletion (response dataflow, graph, endpoint)
        # IoT Ops begin_delete accepts only 202/204; use 204 with no body.
        resp_status = 404 if aio_resources_not_found else 204
        if not graph_not_found_anywhere:
            # Response dataflow DELETE
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{graph_profile}/dataflows/{f['resp_name']}",
                ),
                status=resp_status,
                content_type="application/json",
            )
            # Dataflow graph DELETE
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{graph_profile}/dataflowGraphs/{f['graph_name']}",
                ),
                status=resp_status,
                content_type="application/json",
            )
        elif resp_dataflow_orphaned:
            # Orphaned response dataflow DELETE (no graph delete)
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                    f"/dataflows/{f['resp_name']}",
                ),
                status=resp_status,
                content_type="application/json",
            )

        # Dataflow endpoint DELETE (only if endpoint exists)
        if not ep_not_found:
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_iotops_endpoint(
                    f["instance_name"], f["rg"],
                    sub_resource=f"/dataflowEndpoints/{f['ep_name']}",
                ),
                status=resp_status,
                content_type="application/json",
            )

        # 5. ADR namespace PUT (remove management endpoint entry)
        # PATCH deep-merges dicts (can't remove keys) and ADR API rejects null values,
        # so we use PUT (begin_create_or_replace) to replace the entire resource.
        if f["mgmt_endpoints"]:
            mocked_responses.add(
                method=responses.PUT,
                url=_build_adr_endpoint(f["adr_ns_name"], f["adr_rg"]),
                json=_build_adr_namespace_response(
                    f["adr_ns_name"], f["adr_rg"],
                    identity_type="SystemAssigned",
                    principal_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
                    management_endpoints=extra_adr_endpoints or {},
                ),
                status=200,
            )

        # 6. EG resource deletion (only if EG resources were found during discovery)
        # EG begin_delete accepts 200/202/204 and uses _stream=True; use 200 with json body.
        if f["mgmt_endpoints"] and not eg_not_found:
            # Permission binding pub DELETE
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_eg_endpoint(
                    f["eg_ns_name"], f["eg_rg"],
                    subscription_id=f["eg_sub"],
                    sub_resource=f"/permissionBindings/{f['pub_name']}",
                ),
                json={},
                status=200,
            )
            # Permission binding sub DELETE
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_eg_endpoint(
                    f["eg_ns_name"], f["eg_rg"],
                    subscription_id=f["eg_sub"],
                    sub_resource=f"/permissionBindings/{f['sub_name']}",
                ),
                json={},
                status=200,
            )
            # Topic space DELETE
            mocked_responses.add(
                method=responses.DELETE,
                url=_build_eg_endpoint(
                    f["eg_ns_name"], f["eg_rg"],
                    subscription_id=f["eg_sub"],
                    sub_resource=f"/topicSpaces/{f['ts_name']}",
                ),
                json={},
                status=200,
            )

    def _call_disable(self, mocked_cmd, f: dict, **kwargs) -> None:
        """Invoke provider.disable() with standard arguments."""
        provider = MgmtActions(cmd=mocked_cmd)
        provider.disable(
            name=f["instance_name"],
            resource_group_name=f["rg"],
            confirm_yes=kwargs.pop("confirm_yes", True),
            wait_sec=0,
            **kwargs,
        )

    def test_happy_path(self, mocked_cmd, mocked_responses: responses, mocker):
        """All resources deleted in correct order with confirm_yes=True."""
        f = self._make_disable_fixtures()
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f)

        self._call_disable(mocked_cmd, f)

        # instance GET + ADR GET + graph detect GET + ep detect GET +
        # EG ts GET + EG pub GET + EG sub GET +
        # resp DELETE + graph DELETE + ep DELETE + ADR PUT +
        # pub DELETE + sub DELETE + ts DELETE = 14
        assert len(mocked_responses.calls) == 14

        # Verify full call sequence: discovery GETs → AIO DELETEs → ADR PUT → EG DELETEs
        call_methods = [c.request.method for c in mocked_responses.calls]
        assert call_methods == [
            "GET", "GET", "GET", "GET",     # instance, ADR, graph detect, ep detect
            "GET", "GET", "GET",             # EG ts, pub, sub existence
            "DELETE", "DELETE", "DELETE",    # resp dataflow, graph, endpoint
            "PUT",                           # ADR namespace update (full replace)
            "DELETE", "DELETE", "DELETE",    # pub binding, sub binding, topic space
        ]

        # Verify mutation calls target expected resources
        mut_paths = [
            c.request.path_url.split("?")[0]
            for c in mocked_responses.calls
            if c.request.method in ("DELETE", "PUT")
        ]
        assert f"/dataflows/{f['resp_name']}" in mut_paths[0]
        assert f"/dataflowGraphs/{f['graph_name']}" in mut_paths[1]
        assert f"/dataflowEndpoints/{f['ep_name']}" in mut_paths[2]
        assert f"/providers/{DEVICEREGISTRY_RP}/namespaces/{f['adr_ns_name']}" in mut_paths[3]
        assert f"/permissionBindings/{f['pub_name']}" in mut_paths[4]
        assert f"/permissionBindings/{f['sub_name']}" in mut_paths[5]
        assert f"/topicSpaces/{f['ts_name']}" in mut_paths[6]

    def test_confirmation_cancel(self, mocked_cmd, mocked_responses: responses, mocker):
        """Cancellation via should_continue_prompt stops all deletions."""
        f = self._make_disable_fixtures()
        mock_prompt = mocker.patch(self.PROMPT_TARGET, return_value=False)
        # Register mocks for all calls before the prompt:
        # instance GET + ADR GET + graph discovery + endpoint existence check.
        # Any call past the prompt would hit an unregistered mock and fail the test.
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=f["instance_response"],
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["adr_ns_name"], f["adr_rg"]),
            json=_build_adr_namespace_response(
                f["adr_ns_name"], f["adr_rg"],
                identity_type="SystemAssigned",
                principal_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
                management_endpoints=f["mgmt_endpoints"],
            ),
            status=200,
        )
        # Graph found in default profile (discovery)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                f["instance_name"], f["rg"],
                sub_resource=f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                f"/dataflowGraphs/{f['graph_name']}",
            ),
            json={"name": f["graph_name"]},
            status=200,
        )
        # Endpoint existence check
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                f["instance_name"], f["rg"],
                sub_resource=f"/dataflowEndpoints/{f['ep_name']}",
            ),
            json={"name": f["ep_name"]},
            status=200,
        )
        # EG resource existence probes (topic space + pub + sub)
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(
                f["eg_ns_name"], f["eg_rg"],
                subscription_id=f["eg_sub"],
                sub_resource=f"/topicSpaces/{f['ts_name']}",
            ),
            json={"name": f["ts_name"]},
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(
                f["eg_ns_name"], f["eg_rg"],
                subscription_id=f["eg_sub"],
                sub_resource=f"/permissionBindings/{f['pub_name']}",
            ),
            json={"name": f["pub_name"]},
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_eg_endpoint(
                f["eg_ns_name"], f["eg_rg"],
                subscription_id=f["eg_sub"],
                sub_resource=f"/permissionBindings/{f['sub_name']}",
            ),
            json={"name": f["sub_name"]},
            status=200,
        )

        self._call_disable(mocked_cmd, f, confirm_yes=None)

        mock_prompt.assert_called_once_with(confirm_yes=None)
        # instance GET + ADR GET + graph discovery GET + ep existence GET +
        # EG ts GET + EG pub GET + EG sub GET = 7
        assert len(mocked_responses.calls) == 7

    def test_confirm_yes_flag(self, mocked_cmd, mocked_responses: responses, mocker):
        """confirm_yes=True is forwarded to should_continue_prompt."""
        f = self._make_disable_fixtures()
        mock_prompt = mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f)

        self._call_disable(mocked_cmd, f, confirm_yes=True)

        mock_prompt.assert_called_once_with(confirm_yes=True)
        assert len(mocked_responses.calls) == 14

    def test_aio_resources_not_found(self, mocked_cmd, mocked_responses: responses, mocker):
        """AIO resources already deleted (404) — continues to ADR and EG cleanup."""
        f = self._make_disable_fixtures()
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f, aio_resources_not_found=True)

        self._call_disable(mocked_cmd, f)

        assert len(mocked_responses.calls) == 14

    def test_eg_resources_not_found(self, mocked_cmd, mocked_responses: responses, mocker):
        """EG resources not found during discovery — EG teardown skipped."""
        f = self._make_disable_fixtures()
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f, eg_not_found=True)

        self._call_disable(mocked_cmd, f)

        # instance GET + ADR GET + graph detect + ep detect +
        # EG ts GET(404) + EG pub GET(404) + EG sub GET(404) +
        # resp DELETE + graph DELETE + ep DELETE + ADR PUT = 11
        # No EG DELETEs since resources weren't found
        assert len(mocked_responses.calls) == 11

    def test_no_adr_namespace_ref(self, mocked_cmd, mocked_responses: responses):
        """Instance missing adrNamespaceRef — returns early with no deletions."""
        f = self._make_disable_fixtures(include_adr_namespace_ref=False)
        # Only instance GET is needed — no ADR ref means immediate return.
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=f["instance_response"],
            status=200,
        )

        self._call_disable(mocked_cmd, f)

        assert len(mocked_responses.calls) == 1

    def test_adr_namespace_not_found(self, mocked_cmd, mocked_responses: responses):
        """ADR namespace 404 — returns early with no deletions."""
        f = self._make_disable_fixtures()
        self._register_disable_mocks(mocked_responses, f, adr_not_found=True)

        self._call_disable(mocked_cmd, f)

        assert len(mocked_responses.calls) == 2

    def test_management_endpoint_missing(self, mocked_cmd, mocked_responses: responses, mocker):
        """No management endpoint entry for custom location — AIO deleted, EG skipped."""
        f = self._make_disable_fixtures(include_mgmt_endpoint=False)
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f)

        self._call_disable(mocked_cmd, f)

        # instance GET + ADR GET + graph detect + ep detect + 3 AIO DELETEs = 7
        # No ADR PUT (nothing to remove), no EG DELETEs (no EG context)
        assert len(mocked_responses.calls) == 7
        methods_paths = [(c.request.method, c.request.path_url) for c in mocked_responses.calls]
        assert not any("PUT" in m for m, _ in methods_paths)
        assert not any(f"/providers/{EVENTGRID_RP}/" in p for _, p in methods_paths)

    def test_cross_subscription_eg(self, mocked_cmd, mocked_responses: responses, mocker):
        """Cross-subscription EG namespace creates correct client and deletes succeed."""
        cross_sub = "11111111-1111-1111-1111-111111111111"
        f = self._make_disable_fixtures(eg_subscription_id=cross_sub)
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f)

        self._call_disable(mocked_cmd, f)

        eg_calls = [
            c for c in mocked_responses.calls
            if f"/providers/{EVENTGRID_RP}/" in c.request.path_url
        ]
        assert len(eg_calls) == 6  # 3 discovery GETs + 3 DELETEs
        for call in eg_calls:
            assert f"/subscriptions/{cross_sub}/" in call.request.path_url

    def test_adr_preserves_other_entries(self, mocked_cmd, mocked_responses: responses, mocker):
        """ADR namespace with multiple management endpoints — only ours is removed."""
        f = self._make_disable_fixtures()
        other_cl_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ExtendedLocation/customLocations/other"
        extra_endpoints = {
            other_cl_id: {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": "other.eventgrid.azure.net",
                "scopeId": "other-instance",
                "resourceId": (
                    "/subscriptions/sub/resourceGroups/rg"
                    "/providers/Microsoft.EventGrid/namespaces/other-ns"
                ),
            },
        }

        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f, extra_adr_endpoints=extra_endpoints)

        self._call_disable(mocked_cmd, f)

        put_calls = [c for c in mocked_responses.calls if c.request.method == "PUT"]
        assert len(put_calls) == 1
        put_body = json.loads(put_calls[0].request.body)
        put_endpoints = put_body["properties"]["management"]["endpoints"]
        # PUT replaces the entire resource — our entry is absent, other entries preserved
        assert f["custom_location_id"] not in put_endpoints
        assert put_endpoints[other_cl_id] == extra_endpoints[other_cl_id]
        # Verify identity and location are preserved
        assert put_body.get("location") == "eastus"
        assert put_body.get("identity", {}).get("type") == "SystemAssigned"

    def test_custom_profile_auto_detected(self, mocked_cmd, mocked_responses: responses, mocker):
        """Graph under a non-default profile is auto-detected and deleted."""
        f = self._make_disable_fixtures()
        custom_profile = "custom-profile"
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(
            mocked_responses, f,
            graph_profile=custom_profile,
            graph_not_found_in_default=True,
        )

        self._call_disable(mocked_cmd, f)

        delete_calls = [c for c in mocked_responses.calls if c.request.method == "DELETE"]
        resp_delete = [c for c in delete_calls if f"/dataflows/{f['resp_name']}" in c.request.path_url]
        graph_delete = [c for c in delete_calls if f"/dataflowGraphs/{f['graph_name']}" in c.request.path_url]
        assert len(resp_delete) == 1
        assert f"/dataflowProfiles/{custom_profile}/" in resp_delete[0].request.path_url
        assert len(graph_delete) == 1
        assert f"/dataflowProfiles/{custom_profile}/" in graph_delete[0].request.path_url

    def test_graph_not_found_anywhere(self, mocked_cmd, mocked_responses: responses, mocker):
        """Graph not in any profile — graph and response dataflow deletion skipped."""
        f = self._make_disable_fixtures()
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(mocked_responses, f, graph_not_found_anywhere=True)

        self._call_disable(mocked_cmd, f)

        delete_paths = [
            c.request.path_url.split("?")[0]
            for c in mocked_responses.calls
            if c.request.method == "DELETE"
        ]
        assert not any(f"/dataflows/{f['resp_name']}" in p for p in delete_paths)
        assert not any(f"/dataflowGraphs/{f['graph_name']}" in p for p in delete_paths)
        # endpoint + pub + sub + ts = 4 DELETEs
        assert len(delete_paths) == 4
        assert any(f"/dataflowEndpoints/{f['ep_name']}" in p for p in delete_paths)

    def test_orphaned_response_dataflow(self, mocked_cmd, mocked_responses: responses, mocker):
        """Graph gone but response dataflow still exists — orphaned resp is cleaned up."""
        f = self._make_disable_fixtures()
        mocker.patch(self.PROMPT_TARGET, return_value=True)
        self._register_disable_mocks(
            mocked_responses, f,
            graph_not_found_anywhere=True,
            resp_dataflow_orphaned=True,
        )

        self._call_disable(mocked_cmd, f)

        delete_paths = [
            c.request.path_url.split("?")[0]
            for c in mocked_responses.calls
            if c.request.method == "DELETE"
        ]
        # Orphaned response dataflow is deleted
        resp_deletes = [p for p in delete_paths if f"/dataflows/{f['resp_name']}" in p]
        assert len(resp_deletes) == 1
        assert f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}/" in resp_deletes[0]
        # Graph deletion is NOT attempted (already gone)
        assert not any(f"/dataflowGraphs/{f['graph_name']}" in p for p in delete_paths)
        # resp + endpoint + pub + sub + ts = 5 DELETEs
        assert len(delete_paths) == 5


# ---------------------------------------------------------------------------
# show() tests
# ---------------------------------------------------------------------------


class TestShow:
    """Tests for MgmtActions.show()."""

    def _register_show_aio_mocks(
        self,
        mocked_responses: responses,
        f: dict,
        include_ep: bool = True,
        include_graph: bool = True,
        include_resp: bool = True,
        graph_profile: str = MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE,
        graph_not_in_default: bool = False,
    ) -> None:
        """Register AIO dataflow resource mocks for show() calls.

        Mock insertion order mirrors the AIO probing sequence in show():
        1. Dataflow endpoint GET
        2. Graph discovery (via _discover_dataflow_profile)
        3. Response dataflow discovery
        """
        instance_name = f["instance_name"]
        rg = f["rg"]
        ep_name = f["ep_name"]
        graph_name = f["graph_name"]
        resp_name = f["resp_name"]

        # 1. Dataflow endpoint GET
        ep_auth = {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {
                "audience": MGMT_ACTIONS_EG_AUDIENCE,
            },
        }
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(
                instance_name, rg, sub_resource=f"/dataflowEndpoints/{ep_name}",
            ),
            json={
                "name": ep_name,
                "properties": {
                    "endpointType": MQTT_ENDPOINT_TYPE,
                    "mqttSettings": {"authentication": ep_auth},
                },
            } if include_ep else {"error": {"code": "ResourceNotFound"}},
            status=200 if include_ep else 404,
        )

        # 2. Graph discovery via _discover_dataflow_profile
        default_graph_url = _build_iotops_endpoint(
            instance_name, rg,
            sub_resource=(
                f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                f"/dataflowGraphs/{graph_name}"
            ),
        )
        profiles_url = _build_iotops_endpoint(instance_name, rg, sub_resource="/dataflowProfiles")

        if include_graph and not graph_not_in_default:
            # Found in default profile (fast path)
            mocked_responses.add(
                method=responses.GET, url=default_graph_url,
                json={"name": graph_name}, status=200,
            )
        elif include_graph and graph_not_in_default:
            # Not in default, found in custom profile
            mocked_responses.add(
                method=responses.GET, url=default_graph_url,
                json={"error": {"code": "ResourceNotFound"}}, status=404,
            )
            mocked_responses.add(
                method=responses.GET, url=profiles_url,
                json={"value": [{"name": graph_profile}]}, status=200,
            )
            mocked_responses.add(
                method=responses.GET,
                url=_build_iotops_endpoint(
                    instance_name, rg,
                    sub_resource=f"/dataflowProfiles/{graph_profile}/dataflowGraphs/{graph_name}",
                ),
                json={"name": graph_name}, status=200,
            )
        else:
            # Not found anywhere
            mocked_responses.add(
                method=responses.GET, url=default_graph_url,
                json={"error": {"code": "ResourceNotFound"}}, status=404,
            )
            mocked_responses.add(
                method=responses.GET, url=profiles_url,
                json={"value": []}, status=200,
            )

        # 3. Response dataflow discovery
        resolved_profile = (
            graph_profile if (include_graph and graph_not_in_default)
            else MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE
        )
        resp_url = _build_iotops_endpoint(
            instance_name, rg,
            sub_resource=f"/dataflowProfiles/{resolved_profile}/dataflows/{resp_name}",
        )

        if include_graph:
            # Graph exists — show() tries resp under graph's profile first
            if include_resp:
                mocked_responses.add(
                    method=responses.GET, url=resp_url,
                    json={"name": resp_name}, status=200,
                )
            else:
                # Resp not found under graph's profile → falls through to independent discovery
                mocked_responses.add(
                    method=responses.GET, url=resp_url,
                    json={"error": {"code": "ResourceNotFound"}}, status=404,
                )
                # Independent _discover_dataflow_profile starts with default profile.
                # If graph was in a custom profile, the default resp URL is a different URL
                # that needs its own 404 mock.
                if graph_not_in_default:
                    default_resp_url = _build_iotops_endpoint(
                        instance_name, rg,
                        sub_resource=(
                            f"/dataflowProfiles/{MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE}"
                            f"/dataflows/{resp_name}"
                        ),
                    )
                    mocked_responses.add(
                        method=responses.GET, url=default_resp_url,
                        json={"error": {"code": "ResourceNotFound"}}, status=404,
                    )
                # Profile list mock: only needed if not already registered by graph discovery.
                # Graph fast path (default profile) doesn't list profiles.
                if not graph_not_in_default:
                    mocked_responses.add(
                        method=responses.GET, url=profiles_url,
                        json={"value": []}, status=200,
                    )
        else:
            # No graph — independent resp discovery via _discover_dataflow_profile
            if include_resp:
                mocked_responses.add(
                    method=responses.GET, url=resp_url,
                    json={"name": resp_name}, status=200,
                )
            else:
                # Resp not found in default — profile list already registered (from graph discovery)
                mocked_responses.add(
                    method=responses.GET, url=resp_url,
                    json={"error": {"code": "ResourceNotFound"}}, status=404,
                )

    def _register_show_mocks(
        self,
        mocked_responses: responses,
        f: dict,
        # ADR control
        no_adr_ref: bool = False,
        adr_not_found: bool = False,
        management_endpoints: Optional[dict] = None,
        # EG control
        eg_not_found: bool = False,
        include_topic_space: bool = True,
        include_pub_binding: bool = True,
        include_sub_binding: bool = True,
        client_group: str = MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP,
        eg_subscription_id: Optional[str] = None,
        # AIO control (forwarded to _register_show_aio_mocks)
        include_ep: bool = True,
        include_graph: bool = True,
        include_resp: bool = True,
        graph_profile: str = MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE,
        graph_not_in_default: bool = False,
    ) -> None:
        """Register all HTTP mocks needed for a show() call.

        Mock insertion order mirrors the exact HTTP call sequence of show().
        show() probes all three domains independently — no early returns.
        """
        eg_sub = eg_subscription_id or ZEROED_SUBSCRIPTION

        # --- 1. Instance GET ---
        instance_response = _build_instance_response(
            f["instance_name"], f["rg"],
            adr_namespace_name=f["adr_ns_name"],
            include_adr_ref=not no_adr_ref,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=instance_response,
            status=200,
        )

        # --- 2. ADR namespace GET ---
        has_mgmt_endpoint = False
        if not no_adr_ref:
            eg_rid = _build_eg_resource_id(f["eg_ns_name"], f["eg_rg"], subscription_id=eg_sub)
            if management_endpoints is None:
                management_endpoints = {
                    f["custom_location_id"]: {
                        "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                        "address": f["hostname"],
                        "scopeId": f["instance_name"],
                        "resourceId": eg_rid,
                    },
                }

            if adr_not_found:
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_adr_endpoint(f["adr_ns_name"], f["rg"]),
                    json={"error": {"code": "ResourceNotFound"}},
                    status=404,
                )
            else:
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_adr_endpoint(f["adr_ns_name"], f["rg"]),
                    json=_build_adr_namespace_response(
                        f["adr_ns_name"], f["rg"],
                        identity_type="SystemAssigned",
                        principal_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
                        management_endpoints=management_endpoints,
                    ),
                    status=200,
                )
                has_mgmt_endpoint = bool(management_endpoints)

        # --- 3–6. EG namespace + sub-resource GETs ---
        if has_mgmt_endpoint:
            if eg_not_found:
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_eg_endpoint(f["eg_ns_name"], f["eg_rg"], subscription_id=eg_sub),
                    json={"error": {"code": "ResourceNotFound"}},
                    status=404,
                )
            else:
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_eg_endpoint(f["eg_ns_name"], f["eg_rg"], subscription_id=eg_sub),
                    json=_build_namespace_response(
                        f["eg_ns_name"], f["eg_rg"],
                        mqtt_hostname=f["hostname"], subscription_id=eg_sub,
                    ),
                    status=200,
                )

                # Topic space GET
                ts_name = f["ts_name"]
                expected_templates = _get_expected_topic_templates(f["instance_name"])
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_eg_endpoint(
                        f["eg_ns_name"], f["eg_rg"], subscription_id=eg_sub,
                        sub_resource=f"/topicSpaces/{ts_name}",
                    ),
                    json={
                        "name": ts_name,
                        "properties": {"topicTemplates": expected_templates},
                    } if include_topic_space else {"error": {"code": "ResourceNotFound"}},
                    status=200 if include_topic_space else 404,
                )

                # Publisher binding GET
                pub_name = f["pub_name"]
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_eg_endpoint(
                        f["eg_ns_name"], f["eg_rg"], subscription_id=eg_sub,
                        sub_resource=f"/permissionBindings/{pub_name}",
                    ),
                    json={
                        "name": pub_name,
                        "properties": {
                            "clientGroupName": client_group,
                            "permission": "Publisher",
                            "topicSpaceName": ts_name,
                        },
                    } if include_pub_binding else {"error": {"code": "ResourceNotFound"}},
                    status=200 if include_pub_binding else 404,
                )

                # Subscriber binding GET
                sub_name = f["sub_name"]
                mocked_responses.add(
                    method=responses.GET,
                    url=_build_eg_endpoint(
                        f["eg_ns_name"], f["eg_rg"], subscription_id=eg_sub,
                        sub_resource=f"/permissionBindings/{sub_name}",
                    ),
                    json={
                        "name": sub_name,
                        "properties": {
                            "clientGroupName": client_group,
                            "permission": "Subscriber",
                            "topicSpaceName": ts_name,
                        },
                    } if include_sub_binding else {"error": {"code": "ResourceNotFound"}},
                    status=200 if include_sub_binding else 404,
                )

        # --- 7–9. AIO resource mocks (always registered) ---
        self._register_show_aio_mocks(
            mocked_responses, f,
            include_ep=include_ep,
            include_graph=include_graph,
            include_resp=include_resp,
            graph_profile=graph_profile,
            graph_not_in_default=graph_not_in_default,
        )

    def _make_show_fixtures(self) -> dict:
        """Build common test fixtures for show tests."""
        base = _make_base_fixtures()
        eg_ns_name = generate_random_string()
        eg_rg = generate_random_string()
        return {
            **base,
            "eg_ns_name": eg_ns_name,
            "eg_rg": eg_rg,
            "hostname": f"{eg_ns_name}.eastus-1.ts.eventgrid.azure.net",
            "custom_location_id": MOCK_EXTENDED_LOCATION["name"],
        }

    def _assert_4_key_shape(self, result: dict) -> None:
        """Assert the result has the consistent 4-key shape."""
        assert set(result.keys()) == {"enabled", "instance", "eventGrid", "deviceRegistryNamespace"}

    def _assert_instance_all_exist(self, result: dict, f: dict) -> None:
        """Assert `instance` section has all resources existing with correct names."""
        inst = result["instance"]
        assert inst["dataflowProfile"] == MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE
        assert inst["dataflowEndpoint"]["name"] == f["ep_name"]
        assert inst["dataflowEndpoint"]["exists"] is True
        assert inst["dataflowEndpoint"]["authentication"] is not None
        assert inst["requestDataflowGraph"]["name"] == f["graph_name"]
        assert inst["requestDataflowGraph"]["exists"] is True
        assert inst["responseDataflow"]["name"] == f["resp_name"]
        assert inst["responseDataflow"]["exists"] is True

    def _assert_instance_all_missing(self, result: dict, f: dict) -> None:
        """Assert `instance` section has all resources missing."""
        inst = result["instance"]
        assert inst["dataflowProfile"] is None
        assert inst["dataflowEndpoint"]["name"] == f["ep_name"]
        assert inst["dataflowEndpoint"]["exists"] is False
        assert inst["dataflowEndpoint"]["authentication"] is None
        assert inst["requestDataflowGraph"]["name"] == f["graph_name"]
        assert inst["requestDataflowGraph"]["exists"] is False
        assert inst["responseDataflow"]["name"] == f["resp_name"]
        assert inst["responseDataflow"]["exists"] is False

    def test_fully_enabled(self, mocked_cmd, mocked_responses: responses):
        """Fully configured instance returns enabled=True with complete topology."""
        f = self._make_show_fixtures()
        self._register_show_mocks(mocked_responses, f)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is True

        # -- instance section --
        self._assert_instance_all_exist(result, f)

        # -- eventGrid section --
        eg = result["eventGrid"]
        assert eg["namespace"]["name"] == f["eg_ns_name"]
        assert eg["namespace"]["resourceGroup"] == f["eg_rg"]
        assert eg["namespace"]["subscriptionId"] == ZEROED_SUBSCRIPTION
        assert eg["namespace"]["mqttHostname"] == f["hostname"]
        assert eg["topicSpace"]["name"] == f["ts_name"]
        assert eg["topicSpace"]["scopeId"] == f["instance_name"]
        assert eg["topicSpace"]["exists"] is True
        assert len(eg["topicSpace"]["topicTemplates"]) == 2
        assert eg["permissionBindings"]["publisher"]["name"] == f["pub_name"]
        assert eg["permissionBindings"]["publisher"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert eg["permissionBindings"]["subscriber"]["name"] == f["sub_name"]
        assert eg["permissionBindings"]["subscriber"]["clientGroup"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        assert eg["permissionBindings"]["exists"] is True

        # -- deviceRegistryNamespace section --
        adr = result["deviceRegistryNamespace"]
        assert adr["name"] == f["adr_ns_name"]
        assert adr["resourceGroup"] == f["rg"]
        assert adr["subscriptionId"] == ZEROED_SUBSCRIPTION
        assert adr["managementEndpoint"]["endpointType"] == MGMT_ACTIONS_ADR_ENDPOINT_TYPE
        assert adr["managementEndpoint"]["address"] == f["hostname"]
        assert adr["managementEndpoint"]["scopeId"] == f["instance_name"]

        # instance GET + ADR GET + EG NS GET + TS GET + Pub GET + Sub GET + EP GET + Graph GET + Resp GET
        assert len(mocked_responses.calls) == 9

    def test_no_management_endpoint(self, mocked_cmd, mocked_responses: responses):
        """ADR namespace exists but no management endpoint entry → enabled=False, ADR populated, no EG."""
        f = self._make_show_fixtures()
        self._register_show_mocks(mocked_responses, f, management_endpoints={})

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        self._assert_instance_all_exist(result, f)
        assert result["eventGrid"] is None
        # ADR section populated with managementEndpoint: None
        adr = result["deviceRegistryNamespace"]
        assert adr["name"] == f["adr_ns_name"]
        assert adr["managementEndpoint"] is None
        # instance GET + ADR GET + 3 AIO GETs
        assert len(mocked_responses.calls) == 5

    def test_adr_namespace_not_found(self, mocked_cmd, mocked_responses: responses):
        """ADR namespace 404 → enabled=False, ADR null, EG null, instance probed."""
        f = self._make_show_fixtures()
        self._register_show_mocks(mocked_responses, f, adr_not_found=True)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        self._assert_instance_all_exist(result, f)
        assert result["eventGrid"] is None
        assert result["deviceRegistryNamespace"] is None
        # instance GET + ADR GET (404) + 3 AIO GETs
        assert len(mocked_responses.calls) == 5

    def test_eg_namespace_not_found(self, mocked_cmd, mocked_responses: responses):
        """EG namespace 404 → enabled=False, EG null, instance and ADR probed."""
        f = self._make_show_fixtures()
        self._register_show_mocks(mocked_responses, f, eg_not_found=True)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        # AIO probed independently — all exist
        self._assert_instance_all_exist(result, f)
        assert result["eventGrid"] is None
        assert result["deviceRegistryNamespace"] is not None
        assert result["deviceRegistryNamespace"]["managementEndpoint"] is not None
        # instance GET + ADR GET + EG NS GET (404) + 3 AIO GETs
        assert len(mocked_responses.calls) == 6

    @pytest.mark.parametrize(
        "missing_resource",
        ["topic_space", "pub_binding", "sub_binding"],
    )
    def test_partial_eg_resources(
        self,
        mocked_cmd,
        mocked_responses: responses,
        missing_resource: str,
    ):
        """Missing EG sub-resource → enabled=False with exists flags showing which is missing."""
        f = self._make_show_fixtures()
        kwargs = {
            "include_topic_space": missing_resource != "topic_space",
            "include_pub_binding": missing_resource != "pub_binding",
            "include_sub_binding": missing_resource != "sub_binding",
        }
        self._register_show_mocks(mocked_responses, f, **kwargs)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        self._assert_instance_all_exist(result, f)
        # EG section populated with exists flags
        eg = result["eventGrid"]
        assert eg is not None
        assert eg["namespace"]["name"] == f["eg_ns_name"]
        ts_exists = missing_resource != "topic_space"
        assert eg["topicSpace"]["exists"] is ts_exists
        assert eg["topicSpace"]["name"] == f["ts_name"]
        if ts_exists:
            assert "topicTemplates" in eg["topicSpace"]
            assert "scopeId" in eg["topicSpace"]
        else:
            assert "topicTemplates" not in eg["topicSpace"]
            assert "scopeId" not in eg["topicSpace"]
        # Bindings exist only when both pub and sub exist
        pub_missing = missing_resource == "pub_binding"
        sub_missing = missing_resource == "sub_binding"
        bindings_exist = not pub_missing and not sub_missing
        assert eg["permissionBindings"]["exists"] is bindings_exist
        if not pub_missing:
            assert "clientGroup" in eg["permissionBindings"]["publisher"]
        else:
            assert "clientGroup" not in eg["permissionBindings"]["publisher"]
        if not sub_missing:
            assert "clientGroup" in eg["permissionBindings"]["subscriber"]
        else:
            assert "clientGroup" not in eg["permissionBindings"]["subscriber"]

    def test_cross_subscription_eg(self, mocked_cmd, mocked_responses: responses):
        """EG namespace in a different subscription is handled correctly."""
        f = self._make_show_fixtures()
        cross_sub = "11111111-1111-1111-1111-111111111111"
        self._register_show_mocks(mocked_responses, f, eg_subscription_id=cross_sub)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is True
        assert result["eventGrid"]["namespace"]["subscriptionId"] == cross_sub

    def test_no_adr_namespace_ref(self, mocked_cmd, mocked_responses: responses):
        """Instance without adrNamespaceRef → enabled=False, ADR null, EG null, AIO probed."""
        f = self._make_show_fixtures()
        self._register_show_mocks(
            mocked_responses, f,
            no_adr_ref=True, include_ep=False, include_graph=False, include_resp=False,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        self._assert_instance_all_missing(result, f)
        assert result["eventGrid"] is None
        assert result["deviceRegistryNamespace"] is None

    def test_aio_all_missing(self, mocked_cmd, mocked_responses: responses):
        """All AIO resources 404 → enabled=False, instance section all exists=False."""
        f = self._make_show_fixtures()
        self._register_show_mocks(
            mocked_responses, f,
            include_ep=False, include_graph=False, include_resp=False,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        self._assert_instance_all_missing(result, f)
        # EG and ADR still fully populated
        assert result["eventGrid"] is not None
        assert result["eventGrid"]["topicSpace"]["exists"] is True
        assert result["eventGrid"]["permissionBindings"]["exists"] is True
        assert result["deviceRegistryNamespace"] is not None

    @pytest.mark.parametrize(
        "missing",
        ["endpoint", "graph", "response"],
    )
    def test_aio_partially_missing(
        self,
        mocked_cmd,
        mocked_responses: responses,
        missing: str,
    ):
        """Single AIO resource missing → enabled=False, correct exists flags."""
        f = self._make_show_fixtures()
        self._register_show_mocks(
            mocked_responses, f,
            include_ep=missing != "endpoint",
            include_graph=missing != "graph",
            include_resp=missing != "response",
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is False
        inst = result["instance"]
        assert inst["dataflowEndpoint"]["exists"] is (missing != "endpoint")
        assert inst["requestDataflowGraph"]["exists"] is (missing != "graph")
        assert inst["responseDataflow"]["exists"] is (missing != "response")

    def test_aio_custom_profile(self, mocked_cmd, mocked_responses: responses):
        """Graph and response under non-default profile → correct profile name reported."""
        f = self._make_show_fixtures()
        custom_profile = "custom-perf-profile"
        self._register_show_mocks(
            mocked_responses, f,
            graph_profile=custom_profile,
            graph_not_in_default=True,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.show(name=f["instance_name"], resource_group_name=f["rg"])

        self._assert_4_key_shape(result)
        assert result["enabled"] is True
        assert result["instance"]["dataflowProfile"] == custom_profile
        assert result["instance"]["requestDataflowGraph"]["exists"] is True
        assert result["instance"]["responseDataflow"]["exists"] is True


class TestExecute:
    """Tests for MgmtActions.execute()."""

    def _build_execute_action_endpoint(
        self,
        namespace_name: str,
        resource_group_name: str,
        asset_name: str,
        subscription_id: Optional[str] = None,
    ) -> str:
        """Build the executeAction POST URL."""
        sub_id = subscription_id or ZEROED_SUBSCRIPTION
        return (
            f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
            f"/providers/{DEVICEREGISTRY_RP}/namespaces/{namespace_name}"
            f"/assets/{asset_name}/executeAction"
            f"?api-version={DEVICEREGISTRY_API_VERSION}"
        )

    def _make_execute_fixtures(self) -> dict:
        """Build common test fixtures for execute tests."""
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = f"{instance_name}-adr-ns"
        asset_name = generate_random_string()
        group_name = generate_random_string()
        action_name = generate_random_string()
        return {
            "instance_name": instance_name,
            "rg": rg,
            "adr_ns_name": adr_ns_name,
            "asset_name": asset_name,
            "group_name": group_name,
            "action_name": action_name,
        }

    def _register_execute_mocks(
        self,
        mocked_responses: responses,
        instance_name: str,
        rg: str,
        adr_ns_name: str,
        asset_name: str,
        execute_response: dict,
        execute_status: int = 200,
        instance_response: Optional[dict] = None,
    ) -> None:
        """Register HTTP mocks for instance GET and executeAction POST."""
        if instance_response is None:
            instance_response = _build_instance_response(instance_name, rg, adr_namespace_name=adr_ns_name)

        # Instance GET
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg),
            json=instance_response,
            status=200,
        )

        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(adr_ns_name, rg, asset_name),
            json=execute_response,
            status=execute_status,
        )

    def test_happy_path_with_payload(self, mocked_cmd, mocked_responses: responses):
        """Execute with payload — verify request body and return value."""
        f = self._make_execute_fixtures()
        payload_str = '{"On": true}'
        expected_response = {
            "assetResourceId": f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{f['rg']}"
            f"/providers/{DEVICEREGISTRY_RP}/namespaces/{f['adr_ns_name']}/assets/{f['asset_name']}",
            "managementGroupName": f["group_name"],
            "managementActionName": f["action_name"],
            "status": "Succeeded",
            "response": '{"result": "ok"}',
        }
        self._register_execute_mocks(
            mocked_responses,
            instance_name=f["instance_name"],
            rg=f["rg"],
            adr_ns_name=f["adr_ns_name"],
            asset_name=f["asset_name"],
            execute_response=expected_response,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload=payload_str,
            wait_sec=0,
        )

        assert result == expected_response
        assert len(mocked_responses.calls) == 2

        # Verify the request body sent to executeAction
        execute_request = mocked_responses.calls[1]
        body = json.loads(execute_request.request.body)
        assert body["managementActionName"] == f["action_name"]
        assert body["managementGroupName"] == f["group_name"]
        assert body["payload"] == {"On": True}

    def test_without_payload(self, mocked_cmd, mocked_responses: responses):
        """Execute without payload — verify payload key absent from request body."""
        f = self._make_execute_fixtures()
        expected_response = {
            "assetResourceId": "some-id",
            "managementGroupName": f["group_name"],
            "managementActionName": f["action_name"],
            "status": "Succeeded",
        }
        self._register_execute_mocks(
            mocked_responses,
            instance_name=f["instance_name"],
            rg=f["rg"],
            adr_ns_name=f["adr_ns_name"],
            asset_name=f["asset_name"],
            execute_response=expected_response,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            wait_sec=0,
        )

        assert result == expected_response

        # Verify no payload in request body
        execute_request = mocked_responses.calls[1]
        body = json.loads(execute_request.request.body)
        assert "payload" not in body

    def test_no_adr_namespace_ref(self, mocked_cmd, mocked_responses: responses):
        """Instance without adrNamespaceRef raises ValidationError."""
        instance_name = generate_random_string()
        rg = generate_random_string()

        instance_response = {
            "id": (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
                f"/providers/{IOTOPS_RP}/instances/{instance_name}"
            ),
            "name": instance_name,
            "location": "eastus",
            "extendedLocation": MOCK_EXTENDED_LOCATION,
            "properties": {
                "provisioningState": "Succeeded",
            },
        }
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(instance_name, rg),
            json=instance_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ValidationError, match="Instance does not have an ADR namespace reference"):
            provider.execute(
                instance_name=instance_name,
                resource_group_name=rg,
                asset_name="some-asset",
                group_name="some-group",
                action_name="some-action",
                wait_sec=0,
            )

        # Only instance GET — no executeAction call
        assert len(mocked_responses.calls) == 1

    def test_action_failed_on_device(self, mocked_cmd, mocked_responses: responses):
        """LRO completes with status Failed — error details returned, not raised."""
        f = self._make_execute_fixtures()
        expected_response = {
            "assetResourceId": "some-id",
            "managementGroupName": f["group_name"],
            "managementActionName": f["action_name"],
            "status": "Failed",
            "error": {
                "code": "DeviceError",
                "message": "The device rejected the action.",
            },
        }
        self._register_execute_mocks(
            mocked_responses,
            instance_name=f["instance_name"],
            rg=f["rg"],
            adr_ns_name=f["adr_ns_name"],
            asset_name=f["asset_name"],
            execute_response=expected_response,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            wait_sec=0,
        )

        # Failed status is returned as-is — not raised as an exception
        assert result["status"] == "Failed"
        assert result["error"]["code"] == "DeviceError"

    def test_invalid_payload(self, mocked_cmd, mocked_responses: responses):
        """Invalid JSON payload raises InvalidArgumentValueError before any API call."""
        f = self._make_execute_fixtures()

        # Only register instance GET — executeAction POST should never fire
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=_build_instance_response(f["instance_name"], f["rg"], adr_namespace_name=f["adr_ns_name"]),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(InvalidArgumentValueError, match="Failed to parse JSON input"):
            provider.execute(
                instance_name=f["instance_name"],
                resource_group_name=f["rg"],
                asset_name=f["asset_name"],
                group_name=f["group_name"],
                action_name=f["action_name"],
                payload="not valid json",
                wait_sec=0,
            )

        # Instance GET fires, but executeAction should not
        assert len(mocked_responses.calls) == 1

    def test_payload_from_file(self, mocker, mocked_cmd, mocked_responses: responses):
        """Payload resolved from file path via deserialize_json_input."""
        f = self._make_execute_fixtures()
        file_content = '{"temperature": {"setpoint": 72}}'
        mocker.patch(
            "azext_edge.edge.util.file_operations.read_file_content",
            return_value=file_content,
        )
        expected_response = {
            "assetResourceId": "some-id",
            "managementGroupName": f["group_name"],
            "managementActionName": f["action_name"],
            "status": "Succeeded",
        }
        self._register_execute_mocks(
            mocked_responses,
            instance_name=f["instance_name"],
            rg=f["rg"],
            adr_ns_name=f["adr_ns_name"],
            asset_name=f["asset_name"],
            execute_response=expected_response,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload="somefile.json",
            wait_sec=0,
        )

        assert result == expected_response

        # Verify payload was deserialized from file content
        execute_request = mocked_responses.calls[1]
        body = json.loads(execute_request.request.body)
        assert body["payload"] == {"temperature": {"setpoint": 72}}


# ---------------------------------------------------------------------------
# Schema validation tests for execute()
# ---------------------------------------------------------------------------


def _build_namespace_asset_endpoint(
    namespace_name: str,
    resource_group_name: str,
    asset_name: str,
    subscription_id: Optional[str] = None,
) -> str:
    """Build a full management endpoint URL for a namespace asset GET."""
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    return (
        f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
        f"/providers/{DEVICEREGISTRY_RP}/namespaces/{namespace_name}/assets/{asset_name}"
        f"?api-version={DEVICEREGISTRY_API_VERSION}"
    )


def _build_schema_version_endpoint(
    registry_rg: str,
    registry_name: str,
    schema_name: str,
    schema_version: str,
    subscription_id: Optional[str] = None,
) -> str:
    """Build a full management endpoint URL for a schema version GET."""
    sub_id = subscription_id or ZEROED_SUBSCRIPTION
    return (
        f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{registry_rg}"
        f"/providers/{DEVICEREGISTRY_RP}/schemaRegistries/{registry_name}"
        f"/schemas/{schema_name}/schemaVersions/{schema_version}"
        f"?api-version={DEVICEREGISTRY_API_VERSION}"
    )


def _build_asset_response_with_schema(
    asset_name: str,
    group_name: str,
    action_name: str,
    schema_name: str,
    schema_version: str,
) -> dict:
    """Build a namespace asset GET response with requestMessageSchemaReference in status."""
    return {
        "name": asset_name,
        "properties": {
            "provisioningState": "Succeeded",
            "status": {
                "managementGroups": [
                    {
                        "name": group_name,
                        "actions": [
                            {
                                "name": action_name,
                                "requestMessageSchemaReference": {
                                    "schemaName": schema_name,
                                    "schemaVersion": schema_version,
                                },
                            }
                        ],
                    }
                ]
            },
        },
    }


def _build_schema_version_response(schema_content: str) -> dict:
    """Build a schema version GET response with stringified JSON Schema."""
    return {
        "properties": {
            "schemaContent": schema_content,
        },
    }


class _SchemaTestBase:
    """Shared fixtures and helpers for schema-related execute() tests."""

    SCHEMA_NAME = "temperatureSchema"
    SCHEMA_VERSION = "1"
    REGISTRY_NAME = "mySchemaRegistry"

    def _make_fixtures(self) -> dict:
        instance_name = generate_random_string()
        rg = generate_random_string()
        adr_ns_name = f"{instance_name}-adr-ns"
        asset_name = generate_random_string()
        group_name = generate_random_string()
        action_name = generate_random_string()
        return {
            "instance_name": instance_name,
            "rg": rg,
            "adr_ns_name": adr_ns_name,
            "asset_name": asset_name,
            "group_name": group_name,
            "action_name": action_name,
        }

    def _build_instance_with_registry(self, f: dict) -> dict:
        """Build instance response with schemaRegistryRef."""
        resp = _build_instance_response(f["instance_name"], f["rg"], adr_namespace_name=f["adr_ns_name"])
        registry_id = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{f['rg']}"
            f"/providers/{DEVICEREGISTRY_RP}/schemaRegistries/{self.REGISTRY_NAME}"
        )
        resp["properties"]["schemaRegistryRef"] = {"resourceId": registry_id}
        return resp

    def _build_execute_action_endpoint(
        self,
        namespace_name: str,
        resource_group_name: str,
        asset_name: str,
    ) -> str:
        sub_id = ZEROED_SUBSCRIPTION
        return (
            f"{BASE_URL}/subscriptions/{sub_id}/resourceGroups/{resource_group_name}"
            f"/providers/{DEVICEREGISTRY_RP}/namespaces/{namespace_name}"
            f"/assets/{asset_name}/executeAction"
            f"?api-version={DEVICEREGISTRY_API_VERSION}"
        )

    def _register_schema_resolution_mocks(
        self,
        mocked_responses: responses,
        f: dict,
        schema_content: str,
    ) -> None:
        """Register mocks for schema resolution: Instance GET → Asset GET → Schema Version GET."""
        # Instance GET
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        # Asset GET
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=_build_asset_response_with_schema(
                f["asset_name"], f["group_name"], f["action_name"],
                self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            status=200,
        )
        # Schema Version GET
        mocked_responses.add(
            method=responses.GET,
            url=_build_schema_version_endpoint(
                f["rg"], self.REGISTRY_NAME, self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            json=_build_schema_version_response(schema_content),
            status=200,
        )


class TestExecutePayloadValidation(_SchemaTestBase):
    """Tests for payload-against-schema validation in execute().

    Schema resolution is soft-fail during normal execution — if any step
    in the chain fails, validation is skipped and executeAction proceeds.
    """

    def _register_full_validation_mocks(
        self,
        mocked_responses: responses,
        f: dict,
        schema_content: str,
        execute_response: dict,
    ) -> None:
        """Register all mocks for a full validation+execution flow.

        Order: Instance GET → Asset GET → Schema Version GET → executeAction POST
        """
        self._register_schema_resolution_mocks(mocked_responses, f, schema_content)
        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

    def test_validation_passes(self, mocked_cmd, mocked_responses: responses):
        """Schema resolved and payload conforms → executeAction called normally."""
        f = self._make_fixtures()
        schema = json.dumps({
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        })
        execute_response = {"status": "Succeeded"}
        self._register_full_validation_mocks(mocked_responses, f, schema, execute_response)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 4 calls: Instance GET, Asset GET, Schema Version GET, executeAction POST
        assert len(mocked_responses.calls) == 4

    def test_validation_fails(self, mocked_cmd, mocked_responses: responses):
        """Schema resolved, payload violates schema → InvalidArgumentValueError before POST."""
        f = self._make_fixtures()
        schema = json.dumps({
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
            "required": ["temperature"],
            "additionalProperties": False,
        })
        # Register all mocks except POST (validation should fail before it)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=_build_asset_response_with_schema(
                f["asset_name"], f["group_name"], f["action_name"],
                self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_schema_version_endpoint(
                f["rg"], self.REGISTRY_NAME, self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            json=_build_schema_version_response(schema),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(InvalidArgumentValueError, match="payload"):
            provider.execute(
                instance_name=f["instance_name"],
                resource_group_name=f["rg"],
                asset_name=f["asset_name"],
                group_name=f["group_name"],
                action_name=f["action_name"],
                payload='{"badField": "wrong"}',
                wait_sec=0,
            )

        # 3 calls: Instance GET, Asset GET, Schema Version GET — no POST
        assert len(mocked_responses.calls) == 3

    def test_no_payload_validates_empty_object(self, mocked_cmd, mocked_responses: responses):
        """No payload → schema resolved, {} validated against it, executeAction proceeds."""
        f = self._make_fixtures()
        schema = json.dumps({
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        })
        execute_response = {"status": "Succeeded"}
        self._register_full_validation_mocks(mocked_responses, f, schema, execute_response)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            wait_sec=0,
        )

        assert result == execute_response
        # 4 calls: Instance GET, Asset GET, Schema Version GET, executeAction POST
        assert len(mocked_responses.calls) == 4

    def test_no_payload_required_fields_fails(self, mocked_cmd, mocked_responses: responses):
        """No payload + schema has required fields → InvalidArgumentValueError before POST."""
        f = self._make_fixtures()
        schema = json.dumps({
            "type": "object",
            "properties": {"mode": {"type": "string"}},
            "required": ["mode"],
        })
        # Register all mocks except POST (validation should fail before it)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=_build_asset_response_with_schema(
                f["asset_name"], f["group_name"], f["action_name"],
                self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_schema_version_endpoint(
                f["rg"], self.REGISTRY_NAME, self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            json=_build_schema_version_response(schema),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(InvalidArgumentValueError, match="payload"):
            provider.execute(
                instance_name=f["instance_name"],
                resource_group_name=f["rg"],
                asset_name=f["asset_name"],
                group_name=f["group_name"],
                action_name=f["action_name"],
                wait_sec=0,
            )

        # 3 calls: Instance GET, Asset GET, Schema Version GET — no POST
        assert len(mocked_responses.calls) == 3

    def test_no_validate_skips_resolution(self, mocked_cmd, mocked_responses: responses):
        """no_validate=True → _resolve_request_schema not called, executeAction proceeds."""
        f = self._make_fixtures()
        execute_response = {"status": "Succeeded"}
        # Only register instance GET and executeAction POST — no schema mocks
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            no_validate=True,
            wait_sec=0,
        )

        assert result == execute_response
        # 2 calls only: Instance GET, executeAction POST
        assert len(mocked_responses.calls) == 2

    def test_schema_resolution_fails_soft(self, mocked_cmd, mocked_responses: responses):
        """Asset GET fails → validation skipped, executeAction proceeds."""
        f = self._make_fixtures()
        execute_response = {"status": "Succeeded"}
        # Instance GET (with registry)
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        # Asset GET returns 404
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        # executeAction POST (should proceed despite schema failure)
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 3 calls: Instance GET, Asset GET (404), executeAction POST
        assert len(mocked_responses.calls) == 3

    def test_no_schema_registry_ref(self, mocked_cmd, mocked_responses: responses):
        """Instance has no schemaRegistryRef → validation skipped, executeAction proceeds."""
        f = self._make_fixtures()
        execute_response = {"status": "Succeeded"}
        # Instance without schemaRegistryRef
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=_build_instance_response(f["instance_name"], f["rg"], adr_namespace_name=f["adr_ns_name"]),
            status=200,
        )
        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 2 calls: Instance GET, executeAction POST — no schema resolution attempted
        assert len(mocked_responses.calls) == 2

    def test_cross_subscription_registry(self, mocked_cmd, mocked_responses: responses):
        """Schema registry in different subscription → cross-sub client created, validation works."""
        f = self._make_fixtures()
        cross_sub = "11111111-1111-1111-1111-111111111111"
        schema = json.dumps({
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        })
        execute_response = {"status": "Succeeded"}

        # Build instance with cross-subscription registry
        instance_resp = _build_instance_response(
            f["instance_name"], f["rg"], adr_namespace_name=f["adr_ns_name"],
        )
        registry_id = (
            f"/subscriptions/{cross_sub}/resourceGroups/{f['rg']}"
            f"/providers/{DEVICEREGISTRY_RP}/schemaRegistries/{self.REGISTRY_NAME}"
        )
        instance_resp["properties"]["schemaRegistryRef"] = {"resourceId": registry_id}

        # Instance GET
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=instance_resp,
            status=200,
        )
        # Asset GET (same subscription as instance — uses self.registry_mgmt_client)
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=_build_asset_response_with_schema(
                f["asset_name"], f["group_name"], f["action_name"],
                self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            status=200,
        )
        # Schema Version GET — note cross_sub in the URL (uses cross-sub client)
        mocked_responses.add(
            method=responses.GET,
            url=_build_schema_version_endpoint(
                f["rg"], self.REGISTRY_NAME, self.SCHEMA_NAME, self.SCHEMA_VERSION,
                subscription_id=cross_sub,
            ),
            json=_build_schema_version_response(schema),
            status=200,
        )
        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 4 calls: Instance GET, Asset GET, Schema Version GET (cross-sub), executeAction POST
        assert len(mocked_responses.calls) == 4

    def test_no_matching_action_in_status(self, mocked_cmd, mocked_responses: responses):
        """Asset status has no matching group/action → validation skipped."""
        f = self._make_fixtures()
        execute_response = {"status": "Succeeded"}
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        # Asset with different group/action in status
        asset_response = _build_asset_response_with_schema(
            f["asset_name"], "otherGroup", "otherAction",
            self.SCHEMA_NAME, self.SCHEMA_VERSION,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=asset_response,
            status=200,
        )
        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 3 calls: Instance GET, Asset GET, executeAction POST
        assert len(mocked_responses.calls) == 3

    def test_schema_content_not_json(self, mocked_cmd, mocked_responses: responses):
        """schemaContent is malformed → validation skipped, executeAction proceeds."""
        f = self._make_fixtures()
        execute_response = {"status": "Succeeded"}
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=_build_asset_response_with_schema(
                f["asset_name"], f["group_name"], f["action_name"],
                self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            status=200,
        )
        # Schema version with non-JSON content
        mocked_responses.add(
            method=responses.GET,
            url=_build_schema_version_endpoint(
                f["rg"], self.REGISTRY_NAME, self.SCHEMA_NAME, self.SCHEMA_VERSION,
            ),
            json=_build_schema_version_response("not valid json {{{"),
            status=200,
        )
        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 4 calls: Instance GET, Asset GET, Schema Version GET, executeAction POST
        assert len(mocked_responses.calls) == 4

    def test_incomplete_schema_reference(self, mocked_cmd, mocked_responses: responses):
        """requestMessageSchemaReference missing schemaVersion → validation skipped."""
        f = self._make_fixtures()
        execute_response = {"status": "Succeeded"}
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=self._build_instance_with_registry(f),
            status=200,
        )
        # Asset with incomplete schema reference (missing schemaVersion)
        asset_response = {
            "name": f["asset_name"],
            "properties": {
                "provisioningState": "Succeeded",
                "status": {
                    "managementGroups": [
                        {
                            "name": f["group_name"],
                            "actions": [
                                {
                                    "name": f["action_name"],
                                    "requestMessageSchemaReference": {
                                        "schemaName": self.SCHEMA_NAME,
                                        # schemaVersion intentionally missing
                                    },
                                }
                            ],
                        }
                    ]
                },
            },
        }
        mocked_responses.add(
            method=responses.GET,
            url=_build_namespace_asset_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=asset_response,
            status=200,
        )
        # executeAction POST
        mocked_responses.add(
            method=responses.POST,
            url=self._build_execute_action_endpoint(f["adr_ns_name"], f["rg"], f["asset_name"]),
            json=execute_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 3 calls: Instance GET, Asset GET, executeAction POST
        assert len(mocked_responses.calls) == 3

    def test_non_jsonschema_format_skips_validation(self, mocked_cmd, mocked_responses: responses):
        """Schema with non-standard $schema dialect → validation skipped, executeAction proceeds."""
        f = self._make_fixtures()
        schema = json.dumps({
            "$schema": "iot-operations/1.0",
            "fields": [{"name": "temperature", "type": "float"}],
        })
        execute_response = {"status": "Succeeded"}
        self._register_full_validation_mocks(mocked_responses, f, schema, execute_response)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 4 calls: Instance GET, Asset GET, Schema Version GET, executeAction POST
        assert len(mocked_responses.calls) == 4

    def test_malformed_jsonschema_skips_validation(self, mocked_cmd, mocked_responses: responses):
        """Schema with recognized $schema but malformed body → SchemaError caught, executeAction proceeds."""
        f = self._make_fixtures()
        # Valid $schema URI but body uses invalid JSON Schema constructs
        schema = json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": "not-a-dict",
        })
        execute_response = {"status": "Succeeded"}
        self._register_full_validation_mocks(mocked_responses, f, schema, execute_response)

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            wait_sec=0,
        )

        assert result == execute_response
        # 4 calls: Instance GET, Asset GET, Schema Version GET, executeAction POST
        assert len(mocked_responses.calls) == 4


class TestExecuteShowSchema(_SchemaTestBase):
    """Tests for --show-schema mode.

    When show_schema=True, the command resolves the request schema and returns
    it without executing the action. Failures are hard (ResourceNotFoundError)
    because the user explicitly requested the schema.
    """

    def test_show_schema_returns_schema(self, mocked_cmd, mocked_responses: responses):
        """show_schema=True → resolves full chain → returns parsed JSON Schema dict."""
        f = self._make_fixtures()
        schema_dict = {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        }
        self._register_schema_resolution_mocks(mocked_responses, f, json.dumps(schema_dict))

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            show_schema=True,
            wait_sec=0,
        )

        assert result == schema_dict
        # 3 calls: Instance GET, Asset GET, Schema Version GET — no executeAction POST
        assert len(mocked_responses.calls) == 3

    def test_show_schema_resolution_fails(self, mocked_cmd, mocked_responses: responses):
        """show_schema=True, no schemaRegistryRef → ResourceNotFoundError."""
        f = self._make_fixtures()
        # Instance without schemaRegistryRef
        mocked_responses.add(
            method=responses.GET,
            url=_build_iotops_endpoint(f["instance_name"], f["rg"]),
            json=_build_instance_response(f["instance_name"], f["rg"], adr_namespace_name=f["adr_ns_name"]),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(ResourceNotFoundError, match="Could not resolve the request schema"):
            provider.execute(
                instance_name=f["instance_name"],
                resource_group_name=f["rg"],
                asset_name=f["asset_name"],
                group_name=f["group_name"],
                action_name=f["action_name"],
                show_schema=True,
                wait_sec=0,
            )

        # 1 call: Instance GET only
        assert len(mocked_responses.calls) == 1

    def test_show_schema_ignores_payload(self, mocked_cmd, mocked_responses: responses):
        """show_schema=True + payload → payload ignored, schema returned."""
        f = self._make_fixtures()
        schema_dict = {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        }
        self._register_schema_resolution_mocks(mocked_responses, f, json.dumps(schema_dict))

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            payload='{"temperature": 72}',
            show_schema=True,
            wait_sec=0,
        )

        assert result == schema_dict
        # 3 calls: Instance GET, Asset GET, Schema Version GET — no executeAction POST
        assert len(mocked_responses.calls) == 3

    def test_show_schema_ignores_no_validate(self, mocked_cmd, mocked_responses: responses):
        """show_schema=True + no_validate=True → schema returned normally."""
        f = self._make_fixtures()
        schema_dict = {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        }
        self._register_schema_resolution_mocks(mocked_responses, f, json.dumps(schema_dict))

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider.execute(
            instance_name=f["instance_name"],
            resource_group_name=f["rg"],
            asset_name=f["asset_name"],
            group_name=f["group_name"],
            action_name=f["action_name"],
            show_schema=True,
            no_validate=True,
            wait_sec=0,
        )

        assert result == schema_dict
        # 3 calls: Instance GET, Asset GET, Schema Version GET
        assert len(mocked_responses.calls) == 3


# ---------------------------------------------------------------------------
# remove_management_endpoint tests
# ---------------------------------------------------------------------------


class TestRemoveManagementEndpoint:
    """Tests for MgmtActions.remove_management_endpoint().

    Surgical removal of a single management endpoint entry from an ADR namespace
    via GET + PUT (not PATCH — ARM PATCH deep-merges dicts, can't remove keys).
    """

    PROMPT_TARGET = "azext_edge.edge.providers.orchestration.mgmt_actions.should_continue_prompt"

    def _make_fixtures(self, num_endpoints: int = 1) -> dict:
        """Build test fixtures for remove_management_endpoint tests."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        target_key = (
            f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
            f"/providers/Microsoft.ExtendedLocation/customLocations/my-cl"
        )
        endpoints = {}
        if num_endpoints >= 1:
            endpoints[target_key] = {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": "test-ns.eastus-1.ts.eventgrid.azure.net",
                "scopeId": "test-instance",
            }
        if num_endpoints >= 2:
            other_key = (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
                f"/providers/Microsoft.ExtendedLocation/customLocations/other-cl"
            )
            endpoints[other_key] = {
                "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
                "address": "other-ns.eastus-1.ts.eventgrid.azure.net",
                "scopeId": "other-instance",
            }
        else:
            other_key = None

        return {
            "ns_name": ns_name,
            "rg": rg,
            "target_key": target_key,
            "other_key": other_key,
            "endpoints": endpoints,
        }

    def _build_ns_response(self, f: dict, management_endpoints: dict = None) -> dict:
        """Build ADR namespace response with optional management endpoints and extra fields."""
        eps = management_endpoints if management_endpoints is not None else f["endpoints"]
        resp = _build_adr_namespace_response(
            f["ns_name"], f["rg"],
            identity_type="SystemAssigned",
            principal_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
            management_endpoints=eps,
        )
        # Add tags and messaging to verify preservation in PUT payload
        resp["tags"] = {"env": "test"}
        resp["properties"]["messaging"] = {
            "endpoints": {
                "myEgEndpoint": {
                    "address": "https://eg.westeurope-1.eventgrid.azure.net",
                    "endpointType": "Microsoft.EventGrid",
                }
            }
        }
        return resp

    def test_happy_path(self, mocked_cmd, mocked_responses: responses, mocker):
        """Single endpoint entry is removed via PUT."""
        f = self._make_fixtures(num_endpoints=1)
        mocker.patch(self.PROMPT_TARGET, return_value=True)

        ns_response = self._build_ns_response(f)
        # GET namespace
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )
        # PUT namespace (with endpoint removed)
        mocked_responses.add(
            method=responses.PUT,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=self._build_ns_response(f, management_endpoints={}),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key=f["target_key"],
            confirm_yes=True,
            wait_sec=0,
        )

        assert len(mocked_responses.calls) == 2
        assert mocked_responses.calls[0].request.method == "GET"
        assert mocked_responses.calls[1].request.method == "PUT"

        # Verify PUT payload has empty management.endpoints
        put_body = json.loads(mocked_responses.calls[1].request.body)
        assert put_body["properties"]["management"]["endpoints"] == {}
        # Verify identity, tags, messaging preserved
        assert put_body["identity"] == ns_response["identity"]
        assert put_body["tags"] == ns_response["tags"]
        assert put_body["properties"]["messaging"] == ns_response["properties"]["messaging"]
        assert put_body["location"] == ns_response["location"]

    def test_preserves_other_endpoints(self, mocked_cmd, mocked_responses: responses, mocker):
        """Only target key removed; sibling entries, identity, tags, messaging survive."""
        f = self._make_fixtures(num_endpoints=2)
        mocker.patch(self.PROMPT_TARGET, return_value=True)

        ns_response = self._build_ns_response(f)
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )
        expected_remaining = {f["other_key"]: f["endpoints"][f["other_key"]]}
        mocked_responses.add(
            method=responses.PUT,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=self._build_ns_response(f, management_endpoints=expected_remaining),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key=f["target_key"],
            confirm_yes=True,
            wait_sec=0,
        )

        assert len(mocked_responses.calls) == 2
        put_body = json.loads(mocked_responses.calls[1].request.body)
        remaining_endpoints = put_body["properties"]["management"]["endpoints"]
        assert f["target_key"] not in remaining_endpoints
        assert f["other_key"] in remaining_endpoints
        assert remaining_endpoints[f["other_key"]] == f["endpoints"][f["other_key"]]
        # Verify identity, tags, messaging preserved
        assert put_body["identity"] == ns_response["identity"]
        assert put_body["tags"] == ns_response["tags"]
        assert put_body["properties"]["messaging"] == ns_response["properties"]["messaging"]

    def test_endpoint_key_not_found(self, mocked_cmd, mocked_responses: responses):
        """Specified key not in management.endpoints — early return, no PUT."""
        f = self._make_fixtures(num_endpoints=1)
        ns_response = self._build_ns_response(f)
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key="/nonexistent/key",
            confirm_yes=True,
            wait_sec=0,
        )

        # Only the GET call, no PUT
        assert len(mocked_responses.calls) == 1

    def test_empty_management_endpoints(self, mocked_cmd, mocked_responses: responses):
        """Namespace has no management endpoints — early return, no PUT."""
        f = self._make_fixtures(num_endpoints=0)
        ns_response = self._build_ns_response(f, management_endpoints={})
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key=f["target_key"],
            confirm_yes=True,
            wait_sec=0,
        )

        assert len(mocked_responses.calls) == 1

    def test_no_management_property(self, mocked_cmd, mocked_responses: responses):
        """Namespace has no management property at all — early return, no PUT."""
        f = self._make_fixtures(num_endpoints=0)
        ns_response = _build_adr_namespace_response(
            f["ns_name"], f["rg"],
            identity_type="SystemAssigned",
            management_endpoints=None,  # No management property in response
        )
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key=f["target_key"],
            confirm_yes=True,
            wait_sec=0,
        )

        assert len(mocked_responses.calls) == 1

    def test_confirmation_cancel(self, mocked_cmd, mocked_responses: responses, mocker):
        """User cancels at prompt — no PUT executed."""
        f = self._make_fixtures(num_endpoints=1)
        mock_prompt = mocker.patch(self.PROMPT_TARGET, return_value=False)

        ns_response = self._build_ns_response(f)
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key=f["target_key"],
            confirm_yes=None,
            wait_sec=0,
        )

        mock_prompt.assert_called_once_with(None)
        # Only the GET call, no PUT
        assert len(mocked_responses.calls) == 1

    def test_yes_flag(self, mocked_cmd, mocked_responses: responses, mocker):
        """confirm_yes=True skips prompt, direct PUT."""
        f = self._make_fixtures(num_endpoints=1)
        mock_prompt = mocker.patch(self.PROMPT_TARGET, return_value=True)

        ns_response = self._build_ns_response(f)
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=ns_response,
            status=200,
        )
        mocked_responses.add(
            method=responses.PUT,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json=self._build_ns_response(f, management_endpoints={}),
            status=200,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        provider.remove_management_endpoint(
            namespace_name=f["ns_name"],
            resource_group_name=f["rg"],
            endpoint_key=f["target_key"],
            confirm_yes=True,
            wait_sec=0,
        )

        mock_prompt.assert_called_once_with(True)
        assert len(mocked_responses.calls) == 2

    def test_namespace_not_found(self, mocked_cmd, mocked_responses: responses, mocker):
        """ADR namespace returns 404 — HttpResponseError propagated."""
        f = self._make_fixtures(num_endpoints=1)
        mocked_responses.add(
            method=responses.GET,
            url=_build_adr_endpoint(f["ns_name"], f["rg"]),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )

        provider = MgmtActions(cmd=mocked_cmd)
        with pytest.raises(HttpResponseError):
            provider.remove_management_endpoint(
                namespace_name=f["ns_name"],
                resource_group_name=f["rg"],
                endpoint_key=f["target_key"],
                confirm_yes=True,
                wait_sec=0,
            )
