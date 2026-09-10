# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Callable, Dict, NamedTuple, Optional

from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from azure.core.exceptions import ResourceNotFoundError
from knack.log import get_logger

from ...util.az_client import get_eventgrid_mgmt_client, wait_for_terminal_state
from ...util.cloud_config import CloudConfig
from ...util.id_tools import parse_resource_id as parse_resource_id_dict
from ...util.queryable import Queryable
from .common import (
    CUSTOM_LOCATIONS_API_VERSION,
    EXTENSION_TYPE_OPS,
    MANAGED_IDENTITY_API_VERSION,
    MQTT_ENDPOINT_TYPE,
)
from .connected_cluster import ConnectedCluster
from .permissions import PermissionManager

logger = get_logger(__name__)


class EgNamespaceContext(NamedTuple):
    """Validated Event Grid namespace context, produced by _validate_eg_namespace().

    Set once during validation, then shared read-only across all subsequent setup
    methods. Immutable NamedTuple ensures thread safety if concurrency is added later.
    """

    resource_id: str
    subscription_id: str
    resource_group_name: str
    namespace_name: str
    mqtt_hostname: str


def graceful_delete(begin_delete_fn: Callable, resource_desc: str, **kwargs) -> None:
    """Execute a begin_delete LRO, catching ResourceNotFoundError for idempotent teardown."""
    try:
        poller = begin_delete_fn()
        wait_for_terminal_state(poller, **kwargs)
        logger.info("Deleted %s.", resource_desc)
    except ResourceNotFoundError:
        logger.info("%s already deleted — skipping.", resource_desc.capitalize())


class EventGridProviderBase(Queryable):
    """Shared base for providers that integrate an AIO instance with an Event Grid MQTT broker.

    Concentrates the Event Grid namespace validation, MQTT dataflow endpoint setup, and
    identity resolution reused by the management-actions and live-data providers. Subclasses
    are responsible for constructing the ``eventgrid_mgmt_client``, ``iotops_mgmt_client``,
    ``resource_client``, and ``permission_manager`` attributes these helpers rely on.
    """

    # Constructed by subclasses in __init__; declared here so shared helpers can reference them.
    iotops_mgmt_client: Any
    permission_manager: Any

    def _validate_eg_namespace(
        self,
        eg_resource_id: str,
        min_client_sessions: Optional[int] = None,
    ) -> EgNamespaceContext:
        """Parse, fetch, and validate an Event Grid namespace for MQTT integration.

        Validates that the resource ID is a well-formed Microsoft.EventGrid/namespaces ID,
        the namespace exists, and MQTT broker (topic spaces) is enabled. When the namespace
        resides in a different subscription, a cross-subscription EG client is created and
        stored as self.eventgrid_mgmt_client for use by subsequent EG setup methods. When
        ``min_client_sessions`` is provided, the namespace must allow at least that many
        concurrent client sessions per authentication name.
        """
        parsed = parse_resource_id_dict(eg_resource_id)

        eg_namespace = parsed.get("namespace", "")
        eg_type = parsed.get("type", "")
        if eg_namespace.lower() != "microsoft.eventgrid" or eg_type.lower() != "namespaces":
            raise InvalidArgumentValueError(
                f"--eg-resource-id must reference a Microsoft.EventGrid/namespaces resource.\n"
                f"Got: {eg_namespace}/{eg_type}\n"
                f"Expected format: /subscriptions/{{subscriptionId}}/resourceGroups/{{resourceGroup}}"
                f"/providers/Microsoft.EventGrid/namespaces/{{namespaceName}}"
            )

        eg_subscription_id = parsed.get("subscription", "")
        eg_resource_group = parsed.get("resource_group", "")
        eg_name = parsed.get("name", "")

        if not all([eg_subscription_id, eg_resource_group, eg_name]):
            raise InvalidArgumentValueError(
                f"Malformed resource Id '{eg_resource_id}'. Could not extract subscription, "
                f"resource group, or namespace name."
            )

        if eg_subscription_id.lower() != self.default_subscription_id.lower():
            logger.info(
                "Event Grid namespace is in subscription '%s' (instance subscription: '%s'). "
                "Creating cross-subscription client.",
                eg_subscription_id,
                self.default_subscription_id,
            )
            self.eventgrid_mgmt_client = get_eventgrid_mgmt_client(
                **self._get_client_kwargs(subscription_id=eg_subscription_id)
            )

        try:
            namespace_resource = self.eventgrid_mgmt_client.namespaces.get(
                resource_group_name=eg_resource_group,
                namespace_name=eg_name,
            )
        except ResourceNotFoundError:
            raise InvalidArgumentValueError(
                f"Event Grid namespace '{eg_name}' not found in resource group '{eg_resource_group}' "
                f"(subscription: {eg_subscription_id}).\n"
                f"Verify the --eg-resource-id value and ensure the namespace exists."
            )

        topic_spaces_config = namespace_resource.get("properties", {}).get("topicSpacesConfiguration", {})
        topic_spaces_state = topic_spaces_config.get("state", "")
        if topic_spaces_state != "Enabled":
            state_detail = (
                f"Current state: '{topic_spaces_state}'."
                if topic_spaces_state
                else "MQTT broker has not been configured."
            )
            raise ValidationError(
                f"Event Grid namespace '{eg_name}' does not have MQTT broker (topic spaces) enabled.\n"
                f"{state_detail} "
                f"Enable topic spaces on the namespace before enabling this feature."
            )

        mqtt_hostname = topic_spaces_config.get("hostname", "")
        if not mqtt_hostname:
            raise ValidationError(
                f"Event Grid namespace '{eg_name}' has topic spaces enabled but no MQTT hostname. "
                f"This may indicate the namespace is still provisioning."
            )

        if min_client_sessions is not None:
            max_client_sessions = topic_spaces_config.get("maximumClientSessionsPerAuthenticationName", 0)
            if max_client_sessions < min_client_sessions:
                raise ValidationError(
                    f"Event Grid namespace '{eg_name}' has maximumClientSessionsPerAuthenticationName "
                    f"set to {max_client_sessions}. This feature requires at least "
                    f"{min_client_sessions} concurrent client sessions per authentication name "
                    f"to support reliable dataflow connectivity."
                )

        return EgNamespaceContext(
            resource_id=eg_resource_id,
            subscription_id=eg_subscription_id,
            resource_group_name=eg_resource_group,
            namespace_name=eg_name,
            mqtt_hostname=mqtt_hostname,
        )

    def _discover_eg_context(self, endpoint_entry: Optional[Dict]) -> Optional[EgNamespaceContext]:
        """Extract EG namespace context from an ADR endpoint entry.

        Parses the resourceId from the endpoint, validates required fields, and creates a
        cross-subscription EG client when the namespace is in a different subscription.
        Returns None if the endpoint is missing or has incomplete EG reference data.
        """
        if not endpoint_entry:
            return None

        eg_resource_id = endpoint_entry.get("resourceId", "")
        if not eg_resource_id:
            return None

        parsed_eg = parse_resource_id_dict(eg_resource_id)
        eg_namespace_name = parsed_eg.get("name", "")
        eg_resource_group = parsed_eg.get("resource_group", "")
        eg_subscription_id = parsed_eg.get("subscription", "")
        mqtt_hostname = endpoint_entry.get("address", "")

        if not (eg_namespace_name and eg_resource_group and eg_subscription_id):
            return None

        eg_ctx = EgNamespaceContext(
            resource_id=eg_resource_id,
            subscription_id=eg_subscription_id,
            resource_group_name=eg_resource_group,
            namespace_name=eg_namespace_name,
            mqtt_hostname=mqtt_hostname,
        )

        if eg_subscription_id.lower() != self.default_subscription_id.lower():
            self.eventgrid_mgmt_client = get_eventgrid_mgmt_client(
                **self._get_client_kwargs(subscription_id=eg_subscription_id)
            )

        return eg_ctx

    def _build_eg_endpoint_auth(self, mi_resource: Optional[Dict] = None) -> Dict:
        """Build the authentication block for the EG MQTT dataflow endpoint."""
        eg_audience = CloudConfig(self.cmd).eventgrid_audience
        if mi_resource:
            return {
                "method": "UserAssignedManagedIdentity",
                "userAssignedManagedIdentitySettings": {
                    "clientId": mi_resource["properties"]["clientId"],
                    "tenantId": mi_resource["properties"]["tenantId"],
                    "scope": f"{eg_audience}/.default",
                },
            }
        return {
            "method": "SystemAssignedManagedIdentity",
            "systemAssignedManagedIdentitySettings": {
                "audience": eg_audience,
            },
        }

    def _setup_eg_dataflow_endpoint(
        self,
        eg_ctx: EgNamespaceContext,
        instance_name: str,
        resource_group_name: str,
        extended_location: Dict,
        endpoint_name: str,
        mi_resource: Optional[Dict] = None,
        **kwargs,
    ) -> Dict:
        """Create or update the EG MQTT dataflow endpoint on the AIO instance.

        Uses GET-then-PUT to report accurate status. The endpoint connects to the EG
        namespace's MQTT broker using managed identity authentication. Defaults to
        SystemAssigned MI; when mi_resource is provided, a UserAssigned MI is configured
        instead. When the endpoint already exists, compares host, authentication, and
        clientIdPrefix against the desired state and updates via PUT if any differ.
        """
        desired_authentication = self._build_eg_endpoint_auth(mi_resource)

        try:
            existing = self.iotops_mgmt_client.dataflow_endpoint.get(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=endpoint_name,
            )
            existing_mqtt = existing.get("properties", {}).get("mqttSettings", {})
            existing_host = existing_mqtt.get("host", "")
            existing_auth = existing_mqtt.get("authentication", {})
            existing_client_id_prefix = existing_mqtt.get("clientIdPrefix", "")

            host_matches = existing_host == eg_ctx.mqtt_hostname
            auth_matches = existing_auth == desired_authentication
            client_id_prefix_matches = existing_client_id_prefix == instance_name
            if host_matches and auth_matches and client_id_prefix_matches:
                logger.info(
                    "Dataflow endpoint '%s' already exists on instance '%s' with matching configuration.",
                    endpoint_name,
                    instance_name,
                )
                return {"name": endpoint_name, "authentication": existing_auth, "exists": True}

            logger.info(
                "Dataflow endpoint '%s' exists but configuration differs "
                "(host_match=%s, auth_match=%s, client_id_prefix_match=%s). Updating.",
                endpoint_name,
                host_matches,
                auth_matches,
                client_id_prefix_matches,
            )
        except ResourceNotFoundError:
            existing = None

        resource = {
            "extendedLocation": extended_location,
            "properties": {
                "endpointType": MQTT_ENDPOINT_TYPE,
                "mqttSettings": {
                    "host": eg_ctx.mqtt_hostname,
                    "clientIdPrefix": instance_name,
                    "authentication": desired_authentication,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        }

        poller = self.iotops_mgmt_client.dataflow_endpoint.begin_create_or_update(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=endpoint_name,
            resource=resource,
        )
        wait_for_terminal_state(poller, **kwargs)

        if existing:
            logger.info("Updated dataflow endpoint '%s' on instance '%s'.", endpoint_name, instance_name)
            return {
                "name": endpoint_name,
                "authentication": desired_authentication,
                "exists": True,
                "updated": True,
            }

        logger.info("Created dataflow endpoint '%s' on instance '%s'.", endpoint_name, instance_name)
        return {"name": endpoint_name, "authentication": desired_authentication, "exists": False}

    def _resolve_user_assigned_mi(self, mi_resource_id: str) -> Dict:
        """Fetch a user-assigned managed identity resource to extract clientId and tenantId.

        Uses the base Queryable resource_client for same-subscription lookups. When the
        UAMI is in a different subscription, creates a cross-subscription client.
        """
        parsed = parse_resource_id_dict(mi_resource_id)
        mi_subscription = parsed.get("subscription", self.default_subscription_id)

        if mi_subscription.lower() != self.default_subscription_id.lower():
            from ...util.az_client import get_resource_client

            client = get_resource_client(**self._get_client_kwargs(subscription_id=mi_subscription))
        else:
            client = self.resource_client

        try:
            return client.resources.get_by_id(
                resource_id=mi_resource_id,
                api_version=MANAGED_IDENTITY_API_VERSION,
            )
        except ResourceNotFoundError:
            raise InvalidArgumentValueError(
                f"User-assigned managed identity '{mi_resource_id}' not found.\n"
                f"Verify the --mi-user-assigned value and ensure the identity exists."
            )

    def _resolve_ops_extension_identity(self, instance: Dict, mi_resource: Optional[Dict] = None) -> str:
        """Resolve the principal ID of the identity used for Event Grid role assignments.

        When a UAMI is provided, its principalId is used directly. Otherwise, resolves the
        AIO extension's system MI by traversing: instance → custom location → connected
        cluster → extensions.
        """
        if mi_resource:
            principal_id = mi_resource.get("properties", {}).get("principalId")
            if not principal_id:
                raise ValidationError(
                    "User-assigned managed identity is missing 'principalId'.\n"
                    "Verify the identity resource has been fully provisioned."
                )
            return principal_id

        cl_id = instance.get("extendedLocation", {}).get("name")
        if not cl_id:
            raise ValidationError(
                "Instance is missing 'extendedLocation.name' (custom location ID).\n"
                "The instance may not be fully provisioned."
            )

        custom_location = self.resource_client.resources.get_by_id(
            resource_id=cl_id,
            api_version=CUSTOM_LOCATIONS_API_VERSION,
        )

        host_resource_id = custom_location.get("properties", {}).get("hostResourceId")
        if not host_resource_id:
            raise ValidationError(
                f"Custom location '{cl_id}' is missing 'hostResourceId'.\n"
                "Unable to resolve the connected cluster for extension identity."
            )

        cluster_parts = parse_resource_id_dict(host_resource_id)
        connected_cluster = ConnectedCluster(
            cmd=self.cmd,
            subscription_id=cluster_parts.get("subscription", self.default_subscription_id),
            cluster_name=cluster_parts["name"],
            resource_group_name=cluster_parts["resource_group"],
        )

        ext_map = connected_cluster.get_extensions_by_type(EXTENSION_TYPE_OPS)
        ops_ext = ext_map.get(EXTENSION_TYPE_OPS)
        if not ops_ext:
            raise ValidationError(
                "IoT Operations extension not found on the connected cluster.\n"
                "Cannot resolve the extension identity for EG role assignments.\n"
                "Ensure 'az iot ops create' has been run successfully."
            )

        principal_id = ops_ext.get("identity", {}).get("principalId")
        if not principal_id:
            raise ValidationError(
                "IoT Operations extension is missing 'identity.principalId'.\n"
                "Cannot assign EG roles without the extension identity.\n"
                "Please re-deploy via 'az iot ops create'."
            )

        return principal_id

    def _permission_manager(self, eg_ctx: EgNamespaceContext) -> PermissionManager:
        """Return a PermissionManager scoped to the EG namespace's subscription."""
        if eg_ctx.subscription_id.lower() != self.default_subscription_id.lower():
            return PermissionManager(subscription_id=eg_ctx.subscription_id)
        return self.permission_manager
