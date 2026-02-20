# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional

from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from azure.core.exceptions import ResourceNotFoundError
from knack.log import get_logger

from ...util.az_client import (
    get_eventgrid_mgmt_client,
    get_iotops_mgmt_client,
    get_registry_mgmt_client,
    wait_for_terminal_state,
)
from ...util.id_tools import parse_resource_id as parse_resource_id_dict
from ...util.queryable import Queryable
from .common import (
    MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP,
    MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE,
    MGMT_ACTIONS_RESOURCE_PREFIX,
    MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE,
    MIN_INSTANCE_VERSION_MGMT_ACTIONS,
)
from .permissions import PermissionManager

if TYPE_CHECKING:
    from ...vendor.clients.eventgridmgmt import EventGridManagementClient

logger = get_logger(__name__)


def get_mgmt_actions_resource_name(purpose: str, instance_resource_id: str) -> str:
    """Build a deterministic resource name for mgmt-actions resources.

    Format: mgmt-actions-{purpose}-{hash8}
    Where hash8 = first 8 chars of sha256(instance_resource_id).
    """
    from ...util.common import url_safe_hash_phrase

    hash8 = url_safe_hash_phrase(instance_resource_id)[:8]
    return f"{MGMT_ACTIONS_RESOURCE_PREFIX}-{purpose}-{hash8}"


class EgNamespaceContext(NamedTuple):
    """Validated Event Grid namespace context, produced by _validate_eg_namespace().

    Set once during Stage 1 (sequential validation), then read-only during
    Stage 2 concurrent lanes — inherently thread-safe as an immutable NamedTuple.
    """

    resource_id: str
    subscription_id: str
    resource_group_name: str
    namespace_name: str
    mqtt_hostname: str


class MgmtActions(Queryable):
    """Provider for management actions (outer loop) enable/disable operations."""

    def __init__(self, cmd, subscription_id: Optional[str] = None):
        super().__init__(cmd=cmd, subscription_id=subscription_id)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        # May be replaced with a cross-subscription client by _validate_eg_namespace
        self.eventgrid_mgmt_client: "EventGridManagementClient" = get_eventgrid_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.registry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.permission_manager = PermissionManager(self.default_subscription_id)

    def enable(
        self,
        name: str,
        resource_group_name: str,
        eg_resource_id: str,
        mi_user_assigned: Optional[str] = None,
        eg_client_group: Optional[str] = None,
        adr_role_ids: Optional[List[str]] = None,
        ops_role_ids: Optional[List[str]] = None,
        skip_role_assignments: Optional[bool] = None,
        dataflow_profile: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Enable management actions for an IoT Operations instance.

        Bootstraps the outer loop infrastructure across Event Grid, ADR, and AIO domains.
        """
        from ...util.machinery import scoped_semver_import

        semver = scoped_semver_import()

        # Stage 1: Validation (sequential)
        # Step 1 — Resolve instance
        instance = self.iotops_mgmt_client.instance.get(
            instance_name=name,
            resource_group_name=resource_group_name,
        )
        instance_resource_id: str = instance["id"]

        # Step 2 — Validate instance version
        instance_version = instance.get("properties", {}).get("version", "")
        if not instance_version or (
            semver.parse(instance_version) < semver.parse(MIN_INSTANCE_VERSION_MGMT_ACTIONS)
        ):
            raise ValidationError(
                f"Instance '{name}' version '{instance_version}' does not meet the minimum "
                f"required version '{MIN_INSTANCE_VERSION_MGMT_ACTIONS}' for management actions."
            )

        # Step 3-4 — Validate EG namespace (format, existence, topic spaces, MQTT hostname)
        eg_ctx = self._validate_eg_namespace(eg_resource_id)

        # Stage 2 Lane A: Event Grid infrastructure setup
        topic_space_result = self._setup_eg_topic_space(
            eg_ctx=eg_ctx,
            instance_name=name,
            instance_resource_id=instance_resource_id,
            **kwargs,
        )

        permission_bindings_result = self._setup_eg_permission_bindings(
            eg_ctx=eg_ctx,
            instance_resource_id=instance_resource_id,
            topic_space_name=topic_space_result["name"],
            eg_client_group=eg_client_group,
            **kwargs,
        )

        # TODO: Stage 2 Lane B — ADR namespace management endpoint setup
        # TODO: Stage 2 Lane C — AIO EG dataflow endpoint creation
        # TODO: Stage 3 Lane D — Dataflow graph creation
        # TODO: Stage 3 Lane E — Response dataflow creation
        # TODO: Stage 3 Lane F — ADR namespace MI → EG role assignments
        # TODO: Stage 3 Lane G — AIO extension MI → EG role assignments

        return {
            "instance": {
                "name": name,
                "resourceId": instance_resource_id,
                "version": instance_version,
            },
            "eventGrid": {
                "namespace": {
                    "resourceId": eg_ctx.resource_id,
                    "mqttHostname": eg_ctx.mqtt_hostname,
                },
                "topicSpace": topic_space_result,
                "permissionBindings": permission_bindings_result,
            },
        }

    def disable(
        self,
        name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Disable management actions for an IoT Operations instance.

        Tears down outer loop resources: dataflow graph, response dataflow, EG dataflow endpoint,
        EG topic space/permission bindings, and ADR namespace management endpoint entry.
        """
        raise NotImplementedError("mgmt-actions disable is not yet implemented")

    def _validate_eg_namespace(self, eg_resource_id: str) -> EgNamespaceContext:
        """Parse, fetch, and validate an Event Grid namespace for mgmt-actions use.

        Validates that the resource ID is a well-formed Microsoft.EventGrid/namespaces ID,
        the namespace exists, and MQTT broker (topic spaces) is enabled. When the namespace
        resides in a different subscription, a cross-subscription EG client is created and
        stored as self.eventgrid_mgmt_client for use by subsequent EG setup methods.
        """
        parsed = parse_resource_id_dict(eg_resource_id)

        # Validate resource type
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

        # Handle cross-subscription: create a new EG client if needed
        if eg_subscription_id.lower() != self.default_subscription_id.lower():
            logger.info(
                "Event Grid namespace is in subscription '%s' (instance subscription: '%s'). "
                "Creating cross-subscription client.",
                eg_subscription_id,
                self.default_subscription_id,
            )
            self.eventgrid_mgmt_client = get_eventgrid_mgmt_client(subscription_id=eg_subscription_id)

        # Fetch the namespace
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

        # Validate topic spaces enabled
        topic_spaces_config = namespace_resource.get("properties", {}).get("topicSpacesConfiguration", {})
        topic_spaces_state = topic_spaces_config.get("state", "")
        if topic_spaces_state != "Enabled":
            state_detail = (
                f"Current state: '{topic_spaces_state}'." if topic_spaces_state
                else "MQTT broker has not been configured."
            )
            raise ValidationError(
                f"Event Grid namespace '{eg_name}' does not have MQTT broker (topic spaces) enabled.\n"
                f"{state_detail} "
                f"Enable topic spaces on the namespace before running mgmt-actions enable."
            )

        mqtt_hostname = topic_spaces_config.get("hostname", "")
        if not mqtt_hostname:
            raise ValidationError(
                f"Event Grid namespace '{eg_name}' has topic spaces enabled but no MQTT hostname. "
                f"This may indicate the namespace is still provisioning."
            )

        return EgNamespaceContext(
            resource_id=eg_resource_id,
            subscription_id=eg_subscription_id,
            resource_group_name=eg_resource_group,
            namespace_name=eg_name,
            mqtt_hostname=mqtt_hostname,
        )

    def _setup_eg_topic_space(
        self,
        eg_ctx: EgNamespaceContext,
        instance_name: str,
        instance_resource_id: str,
        **kwargs,
    ) -> Dict:
        """Create or confirm the mgmt-actions topic space on the EG namespace.

        Uses GET-then-PUT to report accurate status. The topic space includes both
        request and response topic templates scoped to the instance name.
        """
        topic_space_name = get_mgmt_actions_resource_name("ops", instance_resource_id)
        request_template = MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE.format(scope_id=instance_name)
        response_template = MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE.format(scope_id=instance_name)
        topic_templates = [request_template, response_template]

        # Check if topic space already exists
        try:
            self.eventgrid_mgmt_client.topic_spaces.get(
                resource_group_name=eg_ctx.resource_group_name,
                namespace_name=eg_ctx.namespace_name,
                topic_space_name=topic_space_name,
            )
            logger.info("Topic space '%s' already exists on namespace '%s'.", topic_space_name, eg_ctx.namespace_name)
            return {
                "name": topic_space_name,
                "status": "Exists",
                "topicTemplates": topic_templates,
            }
        except ResourceNotFoundError:
            pass

        # Create the topic space
        topic_space_payload = {
            "properties": {
                "description": (
                    f"Management actions topic space for IoT Operations instance '{instance_name}'."
                ),
                "topicTemplates": topic_templates,
            }
        }

        poller = self.eventgrid_mgmt_client.topic_spaces.begin_create_or_update(
            resource_group_name=eg_ctx.resource_group_name,
            namespace_name=eg_ctx.namespace_name,
            topic_space_name=topic_space_name,
            topic_space_info=topic_space_payload,
        )
        wait_for_terminal_state(poller, **kwargs)
        logger.info("Created topic space '%s' on namespace '%s'.", topic_space_name, eg_ctx.namespace_name)

        return {
            "name": topic_space_name,
            "status": "Created",
            "topicTemplates": topic_templates,
        }

    def _setup_eg_permission_bindings(
        self,
        eg_ctx: EgNamespaceContext,
        instance_resource_id: str,
        topic_space_name: str,
        eg_client_group: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Create or confirm publisher and subscriber permission bindings for the topic space.

        Uses GET-then-PUT for each binding to report accurate status. The client group
        defaults to '$all' if not specified.
        """
        client_group = eg_client_group or MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP
        pub_name = get_mgmt_actions_resource_name("pub", instance_resource_id)
        sub_name = get_mgmt_actions_resource_name("sub", instance_resource_id)

        result: Dict = {}
        for binding_name, permission, key in [
            (pub_name, "Publisher", "publisher"),
            (sub_name, "Subscriber", "subscriber"),
        ]:
            # Check if binding already exists
            try:
                self.eventgrid_mgmt_client.permission_bindings.get(
                    resource_group_name=eg_ctx.resource_group_name,
                    namespace_name=eg_ctx.namespace_name,
                    permission_binding_name=binding_name,
                )
                logger.info(
                    "Permission binding '%s' already exists on namespace '%s'.",
                    binding_name,
                    eg_ctx.namespace_name,
                )
                result[key] = {"name": binding_name, "status": "Exists"}
                continue
            except ResourceNotFoundError:
                pass

            # Create the permission binding
            binding_payload = {
                "properties": {
                    "clientGroupName": client_group,
                    "permission": permission,
                    "topicSpaceName": topic_space_name,
                    "description": (
                        f"Management actions {permission.lower()} binding "
                        f"for topic space '{topic_space_name}'."
                    ),
                }
            }

            poller = self.eventgrid_mgmt_client.permission_bindings.begin_create_or_update(
                resource_group_name=eg_ctx.resource_group_name,
                namespace_name=eg_ctx.namespace_name,
                permission_binding_name=binding_name,
                permission_binding_info=binding_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            logger.info(
                "Created permission binding '%s' (%s) on namespace '%s'.",
                binding_name,
                permission,
                eg_ctx.namespace_name,
            )
            result[key] = {"name": binding_name, "status": "Created"}

        return result
