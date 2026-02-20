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

from azext_edge.edge.providers.orchestration.common import (
    MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP,
    MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE,
    MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE,
)
from azext_edge.edge.providers.orchestration.mgmt_actions import (
    EgNamespaceContext,
    MgmtActions,
    get_mgmt_actions_resource_name,
)

from ...generators import BASE_URL, generate_random_string, generate_resource_id, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
EVENTGRID_RP = "Microsoft.EventGrid"
EVENTGRID_API_VERSION = "2025-02-15"


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


def _build_namespace_response(
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
        self, mocked_cmd, mocked_responses: responses, state: str, expected_snippet: str,
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

    def _make_eg_ctx(
        self,
        namespace_name: Optional[str] = None,
        resource_group_name: Optional[str] = None,
    ) -> EgNamespaceContext:
        return EgNamespaceContext(
            resource_id=_build_eg_resource_id(
                namespace_name or "test-ns", resource_group_name or "test-rg"
            ),
            subscription_id=ZEROED_SUBSCRIPTION,
            resource_group_name=resource_group_name or "test-rg",
            namespace_name=namespace_name or "test-ns",
            mqtt_hostname="test-ns.eastus-1.ts.eventgrid.azure.net",
        )

    def test_create_new_topic_space(self, mocked_cmd, mocked_responses: responses):
        """When topic space does not exist, creates it and returns status 'Created'."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_name = generate_random_string()
        instance_rid = _build_eg_resource_id(instance_name, rg)
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)

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
        assert result["status"] == "Created"
        assert result["topicTemplates"] == expected_templates
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
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)

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
        assert result["status"] == "Exists"
        assert result["topicTemplates"] == expected_templates
        # Only the GET call, no PUT
        assert len(mocked_responses.calls) == 1

    def test_deterministic_naming(self, mocked_cmd, mocked_responses: responses):
        """Topic space name is deterministic based on instance resource ID."""
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("some-instance", rg)

        name_a = get_mgmt_actions_resource_name("ops", instance_rid)
        name_b = get_mgmt_actions_resource_name("ops", instance_rid)
        assert name_a == name_b
        assert name_a.startswith("mgmt-actions-ops-")
        assert len(name_a) == 25  # "mgmt-actions-ops-" (17) + hash8 (8) = 25

    def test_topic_templates_use_instance_name_as_scope(self, mocked_cmd, mocked_responses: responses):
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

    def _make_eg_ctx(
        self,
        namespace_name: Optional[str] = None,
        resource_group_name: Optional[str] = None,
    ) -> EgNamespaceContext:
        return EgNamespaceContext(
            resource_id=_build_eg_resource_id(
                namespace_name or "test-ns", resource_group_name or "test-rg"
            ),
            subscription_id=ZEROED_SUBSCRIPTION,
            resource_group_name=resource_group_name or "test-rg",
            namespace_name=namespace_name or "test-ns",
            mqtt_hostname="test-ns.eastus-1.ts.eventgrid.azure.net",
        )

    def test_create_both_bindings(self, mocked_cmd, mocked_responses: responses):
        """When neither binding exists, creates both and returns status 'Created'."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
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
        assert result["publisher"]["status"] == "Created"
        assert result["subscriber"]["name"] == sub_name
        assert result["subscriber"]["status"] == "Created"
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
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
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

        assert result["publisher"]["status"] == "Exists"
        assert result["subscriber"]["status"] == "Exists"
        # Only GET calls, no PUTs
        assert len(mocked_responses.calls) == 2

    def test_mixed_exists_and_create(self, mocked_cmd, mocked_responses: responses):
        """Publisher exists, subscriber does not — creates only subscriber."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
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

        assert result["publisher"]["status"] == "Exists"
        assert result["subscriber"]["status"] == "Created"
        # 1 GET (pub) + 1 GET (sub 404) + 1 PUT (sub create) = 3
        assert len(mocked_responses.calls) == 3

    def test_custom_client_group(self, mocked_cmd, mocked_responses: responses):
        """Custom eg_client_group is passed through in the binding payload."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
        ts_name = get_mgmt_actions_resource_name("ops", instance_rid)
        pub_name = get_mgmt_actions_resource_name("pub", instance_rid)
        sub_name = get_mgmt_actions_resource_name("sub", instance_rid)
        custom_group = "myCustomGroup"

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
                json=_build_permission_binding_response(name, perm, ts_name, client_group_name=custom_group),
                status=200,
            )

        provider = MgmtActions(cmd=mocked_cmd)
        result = provider._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_rid,
            topic_space_name=ts_name,
            eg_client_group=custom_group,
            wait_sec=0,
        )

        assert result["publisher"]["status"] == "Created"
        assert result["subscriber"]["status"] == "Created"

        # Verify custom client group in PUT payloads
        pub_body = json.loads(mocked_responses.calls[1].request.body)
        assert pub_body["properties"]["clientGroupName"] == custom_group
        sub_body = json.loads(mocked_responses.calls[3].request.body)
        assert sub_body["properties"]["clientGroupName"] == custom_group

    def test_default_client_group(self, mocked_cmd, mocked_responses: responses):
        """When eg_client_group is None, defaults to $all."""
        ns_name = generate_random_string()
        rg = generate_random_string()
        instance_rid = _build_eg_resource_id("inst", rg)
        eg_ctx = self._make_eg_ctx(namespace_name=ns_name, resource_group_name=rg)
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
                json=_build_permission_binding_response(name, perm, ts_name),
                status=200,
            )

        provider = MgmtActions(cmd=mocked_cmd)
        provider._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_rid,
            topic_space_name=ts_name,
            eg_client_group=None,
            wait_sec=0,
        )

        pub_body = json.loads(mocked_responses.calls[1].request.body)
        assert pub_body["properties"]["clientGroupName"] == MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
