# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import TYPE_CHECKING, Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console

from ...util.az_client import (
    get_eventgrid_mgmt_client,
    get_iotops_mgmt_client,
    get_registry_mgmt_client,
    wait_for_terminal_state,
)
from ...util.common import should_continue_prompt
from ...util.cloud_config import CloudConfig
from ...util.id_tools import parse_resource_id as parse_resource_id_dict
from ...util.queryable import Queryable
from ...util.workflow_display import StepState, WorkflowDisplay, render_summary
from .common import (
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
    MGMT_ACTIONS_GRAPH_ARTIFACT,
    MGMT_ACTIONS_GRAPH_RULES_VERSION,
    MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE,
    MGMT_ACTIONS_RESOURCE_PREFIX,
    MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE,
    MIN_EG_CLIENT_SESSIONS_PER_AUTH_NAME,
    MIN_INSTANCE_VERSION_MGMT_ACTIONS,
    MQTT_ENDPOINT_TYPE,
)
from .connected_cluster import ConnectedCluster
from .permissions import ROLE_DEF_FORMAT_STR, PermissionManager, PrincipalType

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )
    from ...vendor.clients.eventgridmgmt import EventGridManagementClient

logger = get_logger(__name__)
console = Console()


def get_mgmt_actions_resource_name(purpose: str, instance_resource_id: str) -> str:
    """Build a deterministic resource name for mgmt-actions resources.

    Format: mgmt-actions-{purpose}-{hash8}
    Where hash8 = first 8 chars of sha256(instance_resource_id).
    """
    from ...util.common import url_safe_hash_phrase

    hash8 = url_safe_hash_phrase(instance_resource_id)[:8]
    return f"{MGMT_ACTIONS_RESOURCE_PREFIX}-{purpose}-{hash8}"


def _build_graph_rules_config(topic_prefix_regex: str) -> List[Dict]:
    """Build the configuration array for the graph-dataflow-map rules engine.

    Returns a key-value configuration list where the 'rules' key contains a JSON
    string describing how to strip the topic prefix and copy the payload through.
    The topic_prefix_regex anchors the regex_replace to the instance-scoped request
    topic namespace.
    """
    rules_value = {
        "version": MGMT_ACTIONS_GRAPH_RULES_VERSION,
        "datasets": [],
        "map": [
            {
                "description": "Strip the topic prefix",
                "inputs": ["$metadata.topic"],
                "output": "$metadata.topic",
                "expression": f'str::regex_replace($1, "{topic_prefix_regex}", "")',
            },
            {
                "description": "Copy the payload",
                "inputs": ["*"],
                "output": "*",
            },
        ],
    }
    return [
        {
            "key": "rules",
            "value": json.dumps(rules_value),
        },
    ]


def _graceful_delete(begin_delete_fn: Callable, resource_desc: str, **kwargs) -> None:
    """Execute a begin_delete LRO, catching ResourceNotFoundError for idempotent teardown."""
    try:
        poller = begin_delete_fn()
        wait_for_terminal_state(poller, **kwargs)
        logger.info("Deleted %s.", resource_desc)
    except ResourceNotFoundError:
        logger.info("%s already deleted — skipping.", resource_desc.capitalize())


def _build_adr_put_payload(adr_namespace: Dict, endpoint_key_to_remove: str) -> Dict:
    """Build the ADR namespace PUT payload with one management endpoint entry removed.

    ARM PATCH deep-merges dicts (omitting a key preserves it) and the ADR API
    rejects null endpoint values, so we use PUT to replace the entire resource.
    Preserves identity, tags, and messaging configuration from the original namespace.
    """
    existing_endpoints = adr_namespace.get("properties", {}).get("management", {}).get("endpoints", {})
    updated_endpoints = {k: v for k, v in existing_endpoints.items() if k != endpoint_key_to_remove}

    payload: Dict = {
        "location": adr_namespace.get("location", ""),
        "properties": {
            "management": {"endpoints": updated_endpoints},
        },
    }
    # Preserve identity, tags, and messaging from the original namespace
    if adr_namespace.get("identity"):
        payload["identity"] = adr_namespace["identity"]
    if adr_namespace.get("tags"):
        payload["tags"] = adr_namespace["tags"]
    messaging = adr_namespace.get("properties", {}).get("messaging")
    if messaging:
        payload["properties"]["messaging"] = messaging
    return payload


def _log_disable_summary(
    instance_resource_id: str,
    dataflow_profile_name: Optional[str],
    resp_profile_name: Optional[str],
    ep_exists: bool,
    has_adr_entry: bool,
    adr_namespace_name: str,
    instance_name: str,
    ts_exists: bool,
    pub_exists: bool,
    sub_exists: bool,
    eg_ctx: Optional["EgNamespaceContext"],
) -> None:
    """Render a Rich summary of resources that will be removed by disable().

    Only lists resources confirmed to exist during the discovery phase.
    Printed to stderr via render_summary() alongside the confirmation prompt.
    Resource names are logged at info level for debugging — they are deterministic
    hashes that don't aid the confirmation decision.
    """
    aio_pairs: List[Tuple[str, str]] = []  # (display_label, purpose_code)
    if dataflow_profile_name:
        aio_pairs.append(("Response dataflow", "resp"))
        aio_pairs.append(("Dataflow graph", "req"))
    elif resp_profile_name:
        aio_pairs.append(("Response dataflow (orphaned)", "resp"))
    if ep_exists:
        aio_pairs.append(("EG dataflow endpoint", "eg"))

    adr_pairs: List[Tuple[str, str]] = []
    if has_adr_entry:
        adr_pairs.append(("Management endpoint", ""))

    eg_pairs: List[Tuple[str, str]] = []
    if pub_exists:
        eg_pairs.append(("Permission binding (publisher)", "pub"))
    if sub_exists:
        eg_pairs.append(("Permission binding (subscriber)", "sub"))
    if ts_exists:
        eg_pairs.append(("Topic space", "ops"))

    eg_ns_label = f"Event Grid Namespace ({eg_ctx.namespace_name})" if eg_ctx else "Event Grid Namespace"

    sections: Dict[str, List[str]] = {
        f"IoT Operations Instance ({instance_name})": [label for label, _ in aio_pairs],
        f"Device Registry Namespace ({adr_namespace_name})": [label for label, _ in adr_pairs],
        eg_ns_label: [label for label, _ in eg_pairs],
    }

    total = sum(len(items) for items in sections.values())

    render_summary(
        title=f"Resources to remove ({total})",
        sections=sections,
        footer="Note: Role assignments are NOT removed.",
    )

    # Log resource names at info level for debugging / portal cross-reference
    logger.info("Resource names targeted for removal:")
    for label, purpose in aio_pairs:
        if purpose:
            logger.info("  %s: %s", label, get_mgmt_actions_resource_name(purpose, instance_resource_id))
    if adr_pairs:
        logger.info("  Management endpoint: (ADR namespace '%s')", adr_namespace_name)
    for label, purpose in eg_pairs:
        if purpose:
            logger.info("  %s: %s", label, get_mgmt_actions_resource_name(purpose, instance_resource_id))


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


class MgmtActions(Queryable):
    """Provider for management actions enable/disable/show operations."""

    def __init__(self, cmd, subscription_id: Optional[str] = None):
        super().__init__(cmd=cmd, subscription_id=subscription_id)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            **self._get_client_kwargs()
        )
        self.registry_mgmt_client: "MicrosoftDeviceRegistryManagementService" = get_registry_mgmt_client(
            **self._get_client_kwargs()
        )
        # May be replaced with a cross-subscription client by _validate_eg_namespace
        self.eventgrid_mgmt_client: "EventGridManagementClient" = get_eventgrid_mgmt_client(
            **self._get_client_kwargs()
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
        registry_endpoint: Optional[str] = None,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> Dict:
        """Enable management actions for an IoT Operations instance.

        Bootstraps the management actions infrastructure across Event Grid, ADR, and AIO domains.
        """
        from ...util.machinery import scoped_semver_import

        if not CloudConfig(self.cmd).supports_eventgrid_mqtt:
            raise ValidationError(
                "Management actions are not available in this cloud environment. This feature relies on "
                "Event Grid Namespaces with MQTT, which is not supported in the active cloud."
            )

        semver = scoped_semver_import()

        # --- Phase 1: Analyzing (transient — vanishes before configuring phase) ---
        analyzing_cats = {"Analyzing": ["Instance & version check", "EG namespace validation", "UAMI resolution"]}
        with WorkflowDisplay(
            "Management Actions Enablement", analyzing_cats, no_progress=no_progress,
        ) as display:
            with display.step_scope("Analyzing", "Instance & version check"):
                # Resolve instance
                instance = self.iotops_mgmt_client.instance.get(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                )
                instance_resource_id: str = instance["id"]

                # Validate instance version
                instance_version = instance.get("properties", {}).get("version", "")
                parsed_version = semver.parse(instance_version) if instance_version else None
                if not parsed_version or (
                    not parsed_version.prerelease
                    and parsed_version < semver.parse(MIN_INSTANCE_VERSION_MGMT_ACTIONS)
                ):
                    raise ValidationError(
                        f"Instance '{name}' version '{instance_version}' does not meet the minimum "
                        f"required version '{MIN_INSTANCE_VERSION_MGMT_ACTIONS}' for management actions."
                    )
                display.update_step("Analyzing", "Instance & version check", StepState.COMPLETE, "done")

            # Validate EG namespace (format, existence, topic spaces, MQTT hostname)
            with display.step_scope("Analyzing", "EG namespace validation"):
                eg_ctx = self._validate_eg_namespace(eg_resource_id)
                display.update_step("Analyzing", "EG namespace validation", StepState.COMPLETE, "done")

            # Extract extendedLocation from instance (needed for AIO child resources)
            extended_location: Dict = instance["extendedLocation"]

            # Resolve UAMI once (used by EG dataflow endpoint + identity resolution)
            with display.step_scope("Analyzing", "UAMI resolution"):
                mi_resource = self._resolve_user_assigned_mi(mi_user_assigned) if mi_user_assigned else None
                if mi_resource:
                    display.update_step("Analyzing", "UAMI resolution", StepState.COMPLETE, "done")
                else:
                    display.update_step("Analyzing", "UAMI resolution", StepState.SKIPPED, "not needed")

        # --- Phase 2: Configuring (persistent — display remains with elapsed time) ---
        adr_ns_ref = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId", "")
        adr_ns_display = parse_resource_id_dict(adr_ns_ref).get("name", "") if adr_ns_ref else ""

        cat_eg = f"Event Grid Namespace ({eg_ctx.namespace_name})"
        cat_adr = f"Device Registry Namespace ({adr_ns_display})" if adr_ns_display else "Device Registry Namespace"
        cat_aio = f"IoT Operations Instance ({name})"
        cat_roles = "Role Assignments"

        config_cats: Dict[str, List[str]] = {
            cat_eg: ["Topic space", "Permission bindings"],
            cat_adr: ["Managed identity", "Management endpoint"],
            cat_aio: ["EG dataflow endpoint", "Dataflow graph", "Response dataflow"],
        }
        if not skip_role_assignments:
            config_cats[cat_roles] = ["ADR namespace roles", "Dataflow identity roles"]

        with WorkflowDisplay(
            "Management Actions Enablement", config_cats, transient=False, no_progress=no_progress,
        ) as display:
            with display.step_scope(cat_eg, "Topic space"):
                topic_space_result = self._setup_eg_topic_space(
                    eg_ctx=eg_ctx,
                    instance_name=name,
                    instance_resource_id=instance_resource_id,
                    **kwargs,
                )
                if topic_space_result.get("exists"):
                    display.update_step(cat_eg, "Topic space", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_eg, "Topic space", StepState.COMPLETE, "created")

            with display.step_scope(cat_eg, "Permission bindings"):
                permission_bindings_result = self._setup_eg_permission_bindings(
                    eg_ctx=eg_ctx,
                    instance_resource_id=instance_resource_id,
                    topic_space_name=topic_space_result["name"],
                    eg_client_group=eg_client_group,
                    **kwargs,
                )
                if permission_bindings_result.get("exists"):
                    display.update_step(cat_eg, "Permission bindings", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_eg, "Permission bindings", StepState.COMPLETE, "created")

            # ADR namespace — enable system MI + configure management endpoint
            display.update_step(cat_adr, "Managed identity", StepState.ACTIVE)
            display.update_step(cat_adr, "Management endpoint", StepState.ACTIVE)
            try:
                adr_result = self._setup_adr_management_endpoint(
                    instance=instance,
                    eg_ctx=eg_ctx,
                    **kwargs,
                )
                if adr_result.get("identity_exists"):
                    display.update_step(cat_adr, "Managed identity", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_adr, "Managed identity", StepState.COMPLETE, "enabled")
                if adr_result.get("endpoint_exists"):
                    display.update_step(cat_adr, "Management endpoint", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_adr, "Management endpoint", StepState.COMPLETE, "created")
            except Exception as exc:
                display.update_step(cat_adr, "Managed identity", StepState.FAILED, str(exc)[:40])
                display.update_step(cat_adr, "Management endpoint", StepState.FAILED, str(exc)[:40])
                raise

            with display.step_scope(cat_aio, "EG dataflow endpoint"):
                dataflow_endpoint_result = self._setup_eg_dataflow_endpoint(
                    eg_ctx=eg_ctx,
                    instance_name=name,
                    instance_resource_id=instance_resource_id,
                    resource_group_name=resource_group_name,
                    extended_location=extended_location,
                    mi_resource=mi_resource,
                    **kwargs,
                )
                if dataflow_endpoint_result.get("updated"):
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.COMPLETE, "updated")
                elif dataflow_endpoint_result.get("exists"):
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.COMPLETE, "created")

            # Dataflow graph (uses default registry endpoint provisioned with instance)
            resolved_profile = dataflow_profile or MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE
            resolved_registry_endpoint = registry_endpoint or MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT

            with display.step_scope(cat_aio, "Dataflow graph"):
                dataflow_graph_result = self._setup_dataflow_graph(
                    instance_name=name,
                    instance_resource_id=instance_resource_id,
                    resource_group_name=resource_group_name,
                    extended_location=extended_location,
                    eg_dataflow_endpoint_name=dataflow_endpoint_result["name"],
                    dataflow_profile_name=resolved_profile,
                    registry_endpoint_name=resolved_registry_endpoint,
                    **kwargs,
                )
                if dataflow_graph_result.get("exists"):
                    display.update_step(cat_aio, "Dataflow graph", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_aio, "Dataflow graph", StepState.COMPLETE, "created")

            # Response dataflow (edge→cloud: local MQTT → EG)
            with display.step_scope(cat_aio, "Response dataflow"):
                response_dataflow_result = self._setup_response_dataflow(
                    instance_name=name,
                    instance_resource_id=instance_resource_id,
                    resource_group_name=resource_group_name,
                    extended_location=extended_location,
                    eg_dataflow_endpoint_name=dataflow_endpoint_result["name"],
                    dataflow_profile_name=resolved_profile,
                    **kwargs,
                )
                if response_dataflow_result.get("exists"):
                    display.update_step(cat_aio, "Response dataflow", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_aio, "Response dataflow", StepState.COMPLETE, "created")

            # Role assignments — ADR namespace MI + dataflow auth identity → EG namespace
            role_assignments_result = None
            if not skip_role_assignments:
                display.update_step(cat_roles, "ADR namespace roles", StepState.ACTIVE)
                display.update_step(cat_roles, "Dataflow identity roles", StepState.ACTIVE)
                try:
                    dataflow_auth_principal_id = self._resolve_dataflow_auth_identity(
                        instance=instance,
                        mi_resource=mi_resource,
                    )
                    role_assignments_result = self._setup_role_assignments(
                        eg_ctx=eg_ctx,
                        adr_principal_id=adr_result["identity"]["principalId"],
                        dataflow_auth_principal_id=dataflow_auth_principal_id,
                        adr_role_ids=adr_role_ids,
                        ops_role_ids=ops_role_ids,
                    )
                    display.update_step(cat_roles, "ADR namespace roles", StepState.COMPLETE, "done")
                    display.update_step(cat_roles, "Dataflow identity roles", StepState.COMPLETE, "done")
                except Exception as exc:
                    display.update_step(cat_roles, "ADR namespace roles", StepState.FAILED, str(exc)[:40])
                    display.update_step(cat_roles, "Dataflow identity roles", StepState.FAILED, str(exc)[:40])
                    raise

        # Strip internal `exists` and `updated` flags before building consumer-facing return (desired-state semantics)
        for sub_result in [
            topic_space_result, dataflow_endpoint_result, dataflow_graph_result, response_dataflow_result,
        ]:
            sub_result.pop("exists", None)
            sub_result.pop("updated", None)

        # Extract our custom location's endpoint for the consumer-facing return
        our_endpoint = adr_result.get("managementEndpoints", {}).get(
            instance["extendedLocation"]["name"], {}
        )

        result: Dict = {
            "instance": {
                "dataflowProfile": resolved_profile,
                "dataflowEndpoint": dataflow_endpoint_result,
                "requestDataflowGraph": dataflow_graph_result,
                "responseDataflow": response_dataflow_result,
            },
            "eventGrid": {
                "namespace": {
                    "name": eg_ctx.namespace_name,
                    "resourceGroup": eg_ctx.resource_group_name,
                    "subscriptionId": eg_ctx.subscription_id,
                    "mqttHostname": eg_ctx.mqtt_hostname,
                },
                "topicSpace": topic_space_result,
                "permissionBindings": {
                    "publisher": permission_bindings_result["publisher"],
                    "subscriber": permission_bindings_result["subscriber"],
                },
            },
            "deviceRegistryNamespace": {
                "name": adr_result["name"],
                "resourceGroup": adr_result["resourceGroup"],
                "subscriptionId": adr_result["subscriptionId"],
                "identity": adr_result.get("identity"),
                "managementEndpoint": {
                    "endpointType": our_endpoint.get("endpointType", ""),
                    "address": our_endpoint.get("address", ""),
                    "scopeId": our_endpoint.get("scopeId", ""),
                },
            },
        }

        if role_assignments_result is not None:
            result["roleAssignments"] = role_assignments_result

        return result

    def show(
        self,
        name: str,
        resource_group_name: str,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> Dict:
        """Show management actions configuration for an IoT Operations instance.

        Checks ADR namespace, Event Grid, and AIO dataflow resources independently.
        Returns a consistent 4-key dict (`enabled`, `instance`, `eventGrid`,
        `deviceRegistryNamespace`) with per-sub-resource `exists` flags.

        `instance` is never null (names are deterministic from instance resource ID).
        `eventGrid` is null when the management endpoint address is not discoverable.
        `deviceRegistryNamespace` is null when the instance has no ADR namespace ref.
        `enabled` is True only when all sub-resources exist across all three areas.
        """

        analyzing_cats = {
            "Analyzing": [
                "Instance & ADR namespace",
                "Event Grid resources",
                "Instance dataflow resources",
            ],
        }

        adr_section: Optional[Dict] = None
        eg_section: Optional[Dict] = None
        mgmt_endpoint: Optional[Dict] = None
        mgmt_endpoint_exists = False
        eg_all_exist = False

        with WorkflowDisplay(
            title="Management Actions Status",
            categories=analyzing_cats,
            transient=True,
            no_progress=no_progress,
        ) as display:
            # --- ADR namespace ---
            with display.step_scope("Analyzing", "Instance & ADR namespace"):
                instance = self.iotops_mgmt_client.instance.get(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                )
                instance_resource_id: str = instance["id"]
                custom_location_id: str = instance.get("extendedLocation", {}).get("name", "")

                adr_namespace_resource_id = (
                    instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
                )

                if adr_namespace_resource_id:
                    parsed_adr = parse_resource_id_dict(adr_namespace_resource_id)
                    adr_subscription_id = parsed_adr.get("subscription", "")
                    adr_resource_group = parsed_adr.get("resource_group", "")
                    adr_namespace_name = parsed_adr.get("name", "")

                    if adr_subscription_id and adr_resource_group and adr_namespace_name:
                        try:
                            adr_namespace = self.registry_mgmt_client.namespaces.get(
                                resource_group_name=adr_resource_group,
                                namespace_name=adr_namespace_name,
                            )
                            existing_endpoints = (
                                adr_namespace.get("properties", {})
                                .get("management", {})
                                .get("endpoints", {})
                            )
                            mgmt_endpoint = existing_endpoints.get(custom_location_id) if custom_location_id else None
                            mgmt_endpoint_exists = bool(mgmt_endpoint)

                            adr_section = {
                                "name": adr_namespace_name,
                                "resourceGroup": adr_resource_group,
                                "subscriptionId": adr_subscription_id,
                                "managementEndpoint": {
                                    "endpointType": mgmt_endpoint.get("endpointType", ""),
                                    "address": mgmt_endpoint.get("address", ""),
                                    "scopeId": mgmt_endpoint.get("scopeId", ""),
                                } if mgmt_endpoint else None,
                            }
                        except ResourceNotFoundError:
                            logger.warning(
                                "ADR namespace '%s' not found.", adr_namespace_name,
                            )

                display.update_step("Analyzing", "Instance & ADR namespace", StepState.COMPLETE, "done")

            # --- Event Grid ---
            with display.step_scope("Analyzing", "Event Grid resources"):
                eg_ctx = self._discover_eg_context(mgmt_endpoint)

                if eg_ctx:
                    # Verify namespace is reachable
                    try:
                        eg_namespace = self.eventgrid_mgmt_client.namespaces.get(
                            resource_group_name=eg_ctx.resource_group_name,
                            namespace_name=eg_ctx.namespace_name,
                        )
                        mqtt_hostname = (
                            eg_namespace.get("properties", {})
                            .get("topicSpacesConfiguration", {})
                            .get("hostname", "")
                        )

                        # Reconstruct deterministic resource names
                        ts_name = get_mgmt_actions_resource_name("ops", instance_resource_id)
                        pub_name = get_mgmt_actions_resource_name("pub", instance_resource_id)
                        sub_name = get_mgmt_actions_resource_name("sub", instance_resource_id)

                        rg = eg_ctx.resource_group_name
                        ns = eg_ctx.namespace_name

                        # Probe topic space — single GET captures both existence and content
                        ts_exists = False
                        topic_space_section: Dict[str, Any] = {"name": ts_name, "exists": False}
                        try:
                            ts_resource = self.eventgrid_mgmt_client.topic_spaces.get(
                                resource_group_name=rg, namespace_name=ns, topic_space_name=ts_name,
                            )
                            ts_exists = True
                            topic_space_section = {
                                "name": ts_name,
                                "scopeId": name,
                                "topicTemplates": ts_resource.get("properties", {}).get("topicTemplates", []),
                                "exists": True,
                            }
                        except ResourceNotFoundError:
                            pass

                        # Probe permission bindings — single GET each
                        pub_exists = False
                        pub_section: Dict[str, Any] = {"name": pub_name}
                        try:
                            pub_resource = self.eventgrid_mgmt_client.permission_bindings.get(
                                resource_group_name=rg, namespace_name=ns, permission_binding_name=pub_name,
                            )
                            pub_exists = True
                            pub_section["clientGroup"] = (
                                pub_resource.get("properties", {}).get("clientGroupName", "")
                            )
                        except ResourceNotFoundError:
                            pass

                        sub_exists = False
                        sub_section: Dict[str, Any] = {"name": sub_name}
                        try:
                            sub_resource = self.eventgrid_mgmt_client.permission_bindings.get(
                                resource_group_name=rg, namespace_name=ns, permission_binding_name=sub_name,
                            )
                            sub_exists = True
                            sub_section["clientGroup"] = (
                                sub_resource.get("properties", {}).get("clientGroupName", "")
                            )
                        except ResourceNotFoundError:
                            pass

                        bindings_exist = pub_exists and sub_exists
                        eg_all_exist = ts_exists and bindings_exist
                        eg_section = {
                            "namespace": {
                                "name": eg_ctx.namespace_name,
                                "resourceGroup": eg_ctx.resource_group_name,
                                "subscriptionId": eg_ctx.subscription_id,
                                "mqttHostname": mqtt_hostname,
                            },
                            "topicSpace": topic_space_section,
                            "permissionBindings": {
                                "publisher": pub_section,
                                "subscriber": sub_section,
                                "exists": bindings_exist,
                            },
                        }
                    except ResourceNotFoundError:
                        logger.warning(
                            "Event Grid namespace '%s' not found.", eg_ctx.namespace_name,
                        )

                eg_detail = "done" if eg_section else ("not reachable" if eg_ctx else "skipped")
                display.update_step("Analyzing", "Event Grid resources", StepState.COMPLETE, eg_detail)

            # --- AIO dataflow resources ---
            with display.step_scope("Analyzing", "Instance dataflow resources"):
                ep_name = get_mgmt_actions_resource_name("eg", instance_resource_id)
                graph_name = get_mgmt_actions_resource_name("req", instance_resource_id)
                resp_name = get_mgmt_actions_resource_name("resp", instance_resource_id)

                # Probe dataflow endpoint
                ep_exists = False
                ep_authentication: Optional[Dict] = None
                try:
                    ep_resource = self.iotops_mgmt_client.dataflow_endpoint.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_endpoint_name=ep_name,
                    )
                    ep_exists = True
                    ep_authentication = (
                        ep_resource.get("properties", {})
                        .get("mqttSettings", {})
                        .get("authentication")
                    )
                except ResourceNotFoundError:
                    pass

                # Discover dataflow graph profile
                graph_profile = self._discover_dataflow_profile(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                    get_resource=lambda profile: self.iotops_mgmt_client.dataflow_graph.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=profile,
                        dataflow_graph_name=graph_name,
                    ),
                )
                graph_exists = bool(graph_profile)

                # Discover response dataflow profile.
                # If graph was found under a specific profile, check there first.
                resp_profile: Optional[str] = None
                if graph_profile:
                    try:
                        self.iotops_mgmt_client.dataflow.get(
                            resource_group_name=resource_group_name,
                            instance_name=name,
                            dataflow_profile_name=graph_profile,
                            dataflow_name=resp_name,
                        )
                        resp_profile = graph_profile
                    except ResourceNotFoundError:
                        pass  # Fall through to independent discovery

                if not resp_profile:
                    resp_profile = self._discover_dataflow_profile(
                        instance_name=name,
                        resource_group_name=resource_group_name,
                        get_resource=lambda profile: self.iotops_mgmt_client.dataflow.get(
                            resource_group_name=resource_group_name,
                            instance_name=name,
                            dataflow_profile_name=profile,
                            dataflow_name=resp_name,
                        ),
                    )
                resp_exists = bool(resp_profile)

                # Reported profile: graph's profile takes priority
                reported_profile = graph_profile or resp_profile

                aio_all_exist = ep_exists and graph_exists and resp_exists

                display.update_step("Analyzing", "Instance dataflow resources", StepState.COMPLETE, "done")

        # --- Build result ---
        instance_section = {
            "dataflowProfile": reported_profile,
            "dataflowEndpoint": {
                "name": ep_name,
                "authentication": ep_authentication,
                "exists": ep_exists,
            },
            "requestDataflowGraph": {"name": graph_name, "exists": graph_exists},
            "responseDataflow": {"name": resp_name, "exists": resp_exists},
        }

        enabled = mgmt_endpoint_exists and eg_all_exist and aio_all_exist

        return {
            "enabled": enabled,
            "instance": instance_section,
            "eventGrid": eg_section,
            "deviceRegistryNamespace": adr_section,
        }

    def disable(
        self,
        name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Disable management actions for an IoT Operations instance.

        Tears down management actions resources: dataflow graph, response dataflow, EG dataflow endpoint,
        EG topic space/permission bindings, and ADR namespace management endpoint entry.
        Role assignments are NOT removed — they may be shared with other resources.
        """

        # --- Phase 1: Discovery (transient — vanishes before prompt) ---
        analyzing_cats = {
            "Analyzing": ["Instance & ADR namespace", "Dataflow profile detection", "EG resource probing"],
        }
        with WorkflowDisplay(
            "Management Actions Disablement", analyzing_cats, no_progress=no_progress,
        ) as display:
            with display.step_scope("Analyzing", "Instance & ADR namespace"):
                # Resolve instance
                instance = self.iotops_mgmt_client.instance.get(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                )
                instance_resource_id: str = instance["id"]

                # Derive deterministic resource names
                resp_name = get_mgmt_actions_resource_name("resp", instance_resource_id)
                graph_name = get_mgmt_actions_resource_name("req", instance_resource_id)
                ep_name = get_mgmt_actions_resource_name("eg", instance_resource_id)
                ts_name = get_mgmt_actions_resource_name("ops", instance_resource_id)
                pub_name = get_mgmt_actions_resource_name("pub", instance_resource_id)
                sub_name = get_mgmt_actions_resource_name("sub", instance_resource_id)

                # Discover EG namespace from ADR namespace management endpoint
                adr_namespace_resource_id = instance.get("properties", {}).get(
                    "adrNamespaceRef", {},
                ).get("resourceId")
                if not adr_namespace_resource_id:
                    logger.warning(
                        "Instance '%s' does not have an ADR namespace reference. "
                        "Management actions may not have been enabled.",
                        name,
                    )
                    display.update_step("Analyzing", "Instance & ADR namespace", StepState.SKIPPED, "no ref")
                    return

                parsed_adr = parse_resource_id_dict(adr_namespace_resource_id)
                adr_resource_group = parsed_adr.get("resource_group", "")
                adr_namespace_name = parsed_adr.get("name", "")

                try:
                    adr_namespace = self.registry_mgmt_client.namespaces.get(
                        resource_group_name=adr_resource_group,
                        namespace_name=adr_namespace_name,
                    )
                except ResourceNotFoundError:
                    logger.warning(
                        "ADR namespace '%s' not found. Management actions may not have been enabled.",
                        adr_namespace_name,
                    )
                    display.update_step("Analyzing", "Instance & ADR namespace", StepState.SKIPPED, "not found")
                    return

                custom_location_id: str = instance.get("extendedLocation", {}).get("name", "")
                existing_endpoints = adr_namespace.get("properties", {}).get(
                    "management", {},
                ).get("endpoints", {})
                mgmt_endpoint = existing_endpoints.get(custom_location_id)

                eg_ctx = self._discover_eg_context(mgmt_endpoint)
                display.update_step("Analyzing", "Instance & ADR namespace", StepState.COMPLETE, "found")

            # --- Discovery phase: probe AIO resources before prompting ---
            with display.step_scope("Analyzing", "Dataflow profile detection"):
                # Auto-detect the dataflow profile containing our graph
                dataflow_profile_name = self._discover_dataflow_profile(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                    get_resource=lambda profile: self.iotops_mgmt_client.dataflow_graph.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=profile,
                        dataflow_graph_name=graph_name,
                    ),
                )

                # If graph gone, check for orphaned response dataflow
                resp_profile_name: Optional[str] = None
                if not dataflow_profile_name:
                    resp_profile_name = self._discover_dataflow_profile(
                        instance_name=name,
                        resource_group_name=resource_group_name,
                        get_resource=lambda profile: self.iotops_mgmt_client.dataflow.get(
                            resource_group_name=resource_group_name,
                            instance_name=name,
                            dataflow_profile_name=profile,
                            dataflow_name=resp_name,
                        ),
                    )

                # Check dataflow endpoint existence
                ep_exists = True
                try:
                    self.iotops_mgmt_client.dataflow_endpoint.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_endpoint_name=ep_name,
                    )
                except ResourceNotFoundError:
                    ep_exists = False

                if dataflow_profile_name:
                    profile_detail = "found"
                elif resp_profile_name:
                    profile_detail = "orphaned"
                else:
                    profile_detail = "not found"
                display.update_step("Analyzing", "Dataflow profile detection", StepState.COMPLETE, profile_detail)

            # Check EG resource existence (topic space + permission bindings)
            with display.step_scope("Analyzing", "EG resource probing"):
                ts_exists, pub_exists, sub_exists = self._probe_eg_resources(
                    eg_ctx=eg_ctx, ts_name=ts_name, pub_name=pub_name, sub_name=sub_name,
                )
                eg_found_count = sum([ts_exists, pub_exists, sub_exists])
                eg_probe_detail = f"{eg_found_count} found" if eg_found_count else "none found"
                display.update_step("Analyzing", "EG resource probing", StepState.COMPLETE, eg_probe_detail)

        # --- Phase 2: Summary + prompt (no display active) ---
        # Print summary of what will be removed (skip when --yes bypasses the prompt)
        if not confirm_yes:
            _log_disable_summary(
                instance_resource_id=instance_resource_id,
                dataflow_profile_name=dataflow_profile_name,
                resp_profile_name=resp_profile_name,
                ep_exists=ep_exists,
                has_adr_entry=custom_location_id in existing_endpoints,
                adr_namespace_name=adr_namespace_name,
                instance_name=name,
                ts_exists=ts_exists,
                pub_exists=pub_exists,
                sub_exists=sub_exists,
                eg_ctx=eg_ctx,
            )

        if not should_continue_prompt(confirm_yes=confirm_yes):
            return

        # --- Phase 3: Teardown (persistent — display remains as evidence) ---
        self._execute_disable_teardown(
            name=name,
            resource_group_name=resource_group_name,
            dataflow_profile_name=dataflow_profile_name,
            resp_profile_name=resp_profile_name,
            resp_name=resp_name,
            graph_name=graph_name,
            ep_name=ep_name,
            ep_exists=ep_exists,
            adr_namespace=adr_namespace,
            adr_resource_group=adr_resource_group,
            adr_namespace_name=adr_namespace_name,
            custom_location_id=custom_location_id,
            existing_endpoints=existing_endpoints,
            eg_ctx=eg_ctx,
            pub_name=pub_name,
            sub_name=sub_name,
            pub_exists=pub_exists,
            sub_exists=sub_exists,
            ts_name=ts_name,
            ts_exists=ts_exists,
            no_progress=no_progress,
            **kwargs,
        )

    def _execute_disable_teardown(
        self,
        name: str,
        resource_group_name: str,
        dataflow_profile_name: Optional[str],
        resp_profile_name: Optional[str],
        resp_name: str,
        graph_name: str,
        ep_name: str,
        ep_exists: bool,
        adr_namespace: Dict,
        adr_resource_group: str,
        adr_namespace_name: str,
        custom_location_id: str,
        existing_endpoints: Dict,
        eg_ctx: Optional["EgNamespaceContext"],
        pub_name: str,
        sub_name: str,
        pub_exists: bool,
        sub_exists: bool,
        ts_name: str,
        ts_exists: bool,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Execute the Phase 3 teardown of disable(), deleting discovered resources.

        Orchestrates three domain-specific teardown helpers (AIO, ADR, EG) under a
        single persistent WorkflowDisplay. All parameters are pre-resolved during
        discovery (Phase 1).
        """
        eg_ns_label = f"Event Grid Namespace ({eg_ctx.namespace_name})" if eg_ctx else "Event Grid Namespace"
        cat_aio = f"IoT Operations Instance ({name})"
        cat_adr = f"Device Registry Namespace ({adr_namespace_name})"

        teardown_cats: Dict[str, List[str]] = {
            cat_aio: ["Response dataflow", "Dataflow graph", "EG dataflow endpoint"],
            cat_adr: ["Management endpoint"],
            eg_ns_label: ["Permission bindings", "Topic space"],
        }
        with WorkflowDisplay(
            "Management Actions Disablement", teardown_cats, transient=False, no_progress=no_progress,
        ) as display:
            self._teardown_aio_resources(
                display=display,
                category=cat_aio,
                name=name,
                resource_group_name=resource_group_name,
                dataflow_profile_name=dataflow_profile_name,
                resp_profile_name=resp_profile_name,
                resp_name=resp_name,
                graph_name=graph_name,
                ep_name=ep_name,
                ep_exists=ep_exists,
                **kwargs,
            )
            self._teardown_adr_endpoint(
                display=display,
                category=cat_adr,
                adr_namespace=adr_namespace,
                adr_resource_group=adr_resource_group,
                adr_namespace_name=adr_namespace_name,
                custom_location_id=custom_location_id,
                existing_endpoints=existing_endpoints,
                **kwargs,
            )
            self._teardown_eg_resources(
                display=display,
                category=eg_ns_label,
                eg_ctx=eg_ctx,
                pub_name=pub_name,
                sub_name=sub_name,
                pub_exists=pub_exists,
                sub_exists=sub_exists,
                ts_name=ts_name,
                ts_exists=ts_exists,
                **kwargs,
            )

    def _teardown_aio_resources(
        self,
        display: WorkflowDisplay,
        category: str,
        name: str,
        resource_group_name: str,
        dataflow_profile_name: Optional[str],
        resp_profile_name: Optional[str],
        resp_name: str,
        graph_name: str,
        ep_name: str,
        ep_exists: bool,
        **kwargs,
    ) -> None:
        """Delete AIO dataflow resources (response dataflow, graph, EG endpoint).

        Handles three scenarios: both graph+response exist under one profile,
        only an orphaned response dataflow exists, or neither is found.
        """
        if dataflow_profile_name:
            with display.step_scope(category, "Response dataflow"):
                _graceful_delete(
                    lambda: self.iotops_mgmt_client.dataflow.begin_delete(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=dataflow_profile_name,
                        dataflow_name=resp_name,
                    ),
                    resource_desc=f"response dataflow '{resp_name}'",
                    **kwargs,
                )
                display.update_step(category, "Response dataflow", StepState.COMPLETE, "removed")

            with display.step_scope(category, "Dataflow graph"):
                _graceful_delete(
                    lambda: self.iotops_mgmt_client.dataflow_graph.begin_delete(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=dataflow_profile_name,
                        dataflow_graph_name=graph_name,
                    ),
                    resource_desc=f"dataflow graph '{graph_name}'",
                    **kwargs,
                )
                display.update_step(category, "Dataflow graph", StepState.COMPLETE, "removed")
        elif resp_profile_name:
            with display.step_scope(category, "Response dataflow"):
                _graceful_delete(
                    lambda: self.iotops_mgmt_client.dataflow.begin_delete(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=resp_profile_name,
                        dataflow_name=resp_name,
                    ),
                    resource_desc=f"orphaned response dataflow '{resp_name}'",
                    **kwargs,
                )
                display.update_step(category, "Response dataflow", StepState.COMPLETE, "removed")
            display.update_step(category, "Dataflow graph", StepState.SKIPPED, "not found")
        else:
            logger.info(
                "Dataflow graph '%s' and response dataflow '%s' not found in any profile — skipping.",
                graph_name,
                resp_name,
            )
            display.update_step(category, "Response dataflow", StepState.SKIPPED, "not found")
            display.update_step(category, "Dataflow graph", StepState.SKIPPED, "not found")

        if ep_exists:
            with display.step_scope(category, "EG dataflow endpoint"):
                _graceful_delete(
                    lambda: self.iotops_mgmt_client.dataflow_endpoint.begin_delete(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_endpoint_name=ep_name,
                    ),
                    resource_desc=f"dataflow endpoint '{ep_name}'",
                    **kwargs,
                )
                display.update_step(category, "EG dataflow endpoint", StepState.COMPLETE, "removed")
        else:
            logger.info("Dataflow endpoint '%s' not found — skipping.", ep_name)
            display.update_step(category, "EG dataflow endpoint", StepState.SKIPPED, "not found")

    def _teardown_adr_endpoint(
        self,
        display: WorkflowDisplay,
        category: str,
        adr_namespace: Dict,
        adr_resource_group: str,
        adr_namespace_name: str,
        custom_location_id: str,
        existing_endpoints: Dict,
        **kwargs,
    ) -> None:
        """Remove the management endpoint entry from the ADR namespace."""
        if custom_location_id in existing_endpoints:
            with display.step_scope(category, "Management endpoint"):
                put_payload = _build_adr_put_payload(adr_namespace, endpoint_key_to_remove=custom_location_id)
                poller = self.registry_mgmt_client.namespaces.begin_create_or_replace(
                    resource_group_name=adr_resource_group,
                    namespace_name=adr_namespace_name,
                    resource=put_payload,
                )
                wait_for_terminal_state(poller, **kwargs)
                logger.info(
                    "Removed management endpoint entry for custom location from ADR namespace '%s'.",
                    adr_namespace_name,
                )
                display.update_step(
                    category, "Management endpoint", StepState.COMPLETE, "removed",
                )
        else:
            logger.info(
                "No management endpoint entry found for custom location on ADR namespace '%s' — skipping.",
                adr_namespace_name,
            )
            display.update_step(
                category, "Management endpoint", StepState.SKIPPED, "not found",
            )

    def _teardown_eg_resources(
        self,
        display: WorkflowDisplay,
        category: str,
        eg_ctx: Optional["EgNamespaceContext"],
        pub_name: str,
        sub_name: str,
        pub_exists: bool,
        sub_exists: bool,
        ts_name: str,
        ts_exists: bool,
        **kwargs,
    ) -> None:
        """Delete EG permission bindings and topic space."""
        if not eg_ctx:
            logger.info("EG namespace not discovered from ADR — skipping EG resource cleanup.")
            display.update_step(category, "Permission bindings", StepState.SKIPPED, "not found")
            display.update_step(category, "Topic space", StepState.SKIPPED, "not found")
            return

        if pub_exists or sub_exists:
            with display.step_scope(category, "Permission bindings"):
                if pub_exists:
                    _graceful_delete(
                        lambda: self.eventgrid_mgmt_client.permission_bindings.begin_delete(
                            resource_group_name=eg_ctx.resource_group_name,
                            namespace_name=eg_ctx.namespace_name,
                            permission_binding_name=pub_name,
                        ),
                        resource_desc=f"permission binding '{pub_name}'",
                        **kwargs,
                    )
                if sub_exists:
                    _graceful_delete(
                        lambda: self.eventgrid_mgmt_client.permission_bindings.begin_delete(
                            resource_group_name=eg_ctx.resource_group_name,
                            namespace_name=eg_ctx.namespace_name,
                            permission_binding_name=sub_name,
                        ),
                        resource_desc=f"permission binding '{sub_name}'",
                        **kwargs,
                    )
                display.update_step(category, "Permission bindings", StepState.COMPLETE, "removed")
        else:
            display.update_step(category, "Permission bindings", StepState.SKIPPED, "not found")

        if ts_exists:
            with display.step_scope(category, "Topic space"):
                _graceful_delete(
                    lambda: self.eventgrid_mgmt_client.topic_spaces.begin_delete(
                        resource_group_name=eg_ctx.resource_group_name,
                        namespace_name=eg_ctx.namespace_name,
                        topic_space_name=ts_name,
                    ),
                    resource_desc=f"topic space '{ts_name}'",
                    **kwargs,
                )
                display.update_step(category, "Topic space", StepState.COMPLETE, "removed")
        else:
            display.update_step(category, "Topic space", StepState.SKIPPED, "not found")

        if not any([pub_exists, sub_exists, ts_exists]):
            logger.info("No EG resources found on namespace '%s' — skipping.", eg_ctx.namespace_name)

    def _probe_eg_resources(
        self,
        eg_ctx: Optional[EgNamespaceContext],
        ts_name: str,
        pub_name: str,
        sub_name: str,
    ) -> Tuple[bool, bool, bool]:
        """Check whether EG topic space and permission bindings exist.

        Issues individual GET requests for each resource, catching
        ResourceNotFoundError for resources that have already been removed.
        Skipped entirely when eg_ctx is None (no EG namespace discovered).

        Returns:
            (ts_exists, pub_exists, sub_exists) tuple of booleans.
        """
        if not eg_ctx:
            return False, False, False

        rg = eg_ctx.resource_group_name
        ns = eg_ctx.namespace_name

        ts_exists = True
        try:
            self.eventgrid_mgmt_client.topic_spaces.get(
                resource_group_name=rg, namespace_name=ns, topic_space_name=ts_name,
            )
        except ResourceNotFoundError:
            ts_exists = False

        pub_exists = True
        try:
            self.eventgrid_mgmt_client.permission_bindings.get(
                resource_group_name=rg, namespace_name=ns, permission_binding_name=pub_name,
            )
        except ResourceNotFoundError:
            pub_exists = False

        sub_exists = True
        try:
            self.eventgrid_mgmt_client.permission_bindings.get(
                resource_group_name=rg, namespace_name=ns, permission_binding_name=sub_name,
            )
        except ResourceNotFoundError:
            sub_exists = False

        return ts_exists, pub_exists, sub_exists

    def _discover_dataflow_profile(
        self,
        instance_name: str,
        resource_group_name: str,
        get_resource: Callable[[str], dict],
    ) -> Optional[str]:
        """Auto-detect which dataflow profile contains a mgmt-actions resource.

        Tries the default profile first (common case). If not found, lists all
        profiles and checks each one. Returns the profile name or None if the
        resource doesn't exist in any profile.

        Args:
            get_resource: Callable that takes a profile name and returns the resource
                dict on success, or raises ResourceNotFoundError if absent.
        """
        # Fast path: check the default profile
        try:
            get_resource(MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE)
            return MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE
        except ResourceNotFoundError:
            pass

        # Slow path: enumerate all profiles
        profiles = self.iotops_mgmt_client.dataflow_profile.list_by_resource_group(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        )
        for profile in profiles:
            profile_name = profile.get("name", "")
            if not profile_name or profile_name == MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE:
                continue
            try:
                get_resource(profile_name)
                return profile_name
            except ResourceNotFoundError:
                continue

        return None

    def _discover_eg_context(self, mgmt_endpoint: Optional[Dict]) -> Optional[EgNamespaceContext]:
        """Extract EG namespace context from an ADR management endpoint entry.

        Parses the resourceId from the endpoint, validates required fields, and creates
        a cross-subscription EG client when the namespace is in a different subscription.
        Returns None if the endpoint is missing or has incomplete EG reference data.
        """
        if not mgmt_endpoint:
            return None

        eg_resource_id = mgmt_endpoint.get("resourceId", "")
        if not eg_resource_id:
            return None

        parsed_eg = parse_resource_id_dict(eg_resource_id)
        eg_namespace_name = parsed_eg.get("name", "")
        eg_resource_group = parsed_eg.get("resource_group", "")
        eg_subscription_id = parsed_eg.get("subscription", "")
        mqtt_hostname = mgmt_endpoint.get("address", "")

        if not (eg_namespace_name and eg_resource_group and eg_subscription_id):
            return None

        eg_ctx = EgNamespaceContext(
            resource_id=eg_resource_id,
            subscription_id=eg_subscription_id,
            resource_group_name=eg_resource_group,
            namespace_name=eg_namespace_name,
            mqtt_hostname=mqtt_hostname,
        )

        # Handle cross-subscription EG namespace
        if eg_subscription_id.lower() != self.default_subscription_id.lower():
            self.eventgrid_mgmt_client = get_eventgrid_mgmt_client(
                **self._get_client_kwargs(subscription_id=eg_subscription_id)
            )

        return eg_ctx

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
            self.eventgrid_mgmt_client = get_eventgrid_mgmt_client(
                **self._get_client_kwargs(subscription_id=eg_subscription_id)
            )

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
                f"Current state: '{topic_spaces_state}'."
                if topic_spaces_state
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

        max_client_sessions = topic_spaces_config.get("maximumClientSessionsPerAuthenticationName", 0)
        if max_client_sessions < MIN_EG_CLIENT_SESSIONS_PER_AUTH_NAME:
            raise ValidationError(
                f"Event Grid namespace '{eg_name}' has maximumClientSessionsPerAuthenticationName "
                f"set to {max_client_sessions}. Management actions requires at least "
                f"{MIN_EG_CLIENT_SESSIONS_PER_AUTH_NAME} concurrent client sessions per authentication name "
                f"to support reliable dataflow connectivity."
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
                "topicTemplates": topic_templates,
                "scopeId": instance_name,
                "exists": True,
            }
        except ResourceNotFoundError:
            pass

        # Create the topic space
        topic_space_payload = {
            "properties": {
                "description": (f"Management actions topic space for IoT Operations instance '{instance_name}'."),
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
            "topicTemplates": topic_templates,
            "scopeId": instance_name,
            "exists": False,
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
        all_exists = True
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
                result[key] = {"name": binding_name, "clientGroup": client_group}
                continue
            except ResourceNotFoundError:
                all_exists = False

            # Create the permission binding
            binding_payload = {
                "properties": {
                    "clientGroupName": client_group,
                    "permission": permission,
                    "topicSpaceName": topic_space_name,
                    "description": (
                        f"Management actions {permission.lower()} binding " f"for topic space '{topic_space_name}'."
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
            result[key] = {"name": binding_name, "clientGroup": client_group}

        result["exists"] = all_exists
        return result

    def _setup_eg_dataflow_endpoint(
        self,
        eg_ctx: EgNamespaceContext,
        instance_name: str,
        instance_resource_id: str,
        resource_group_name: str,
        extended_location: Dict,
        mi_resource: Optional[Dict] = None,
        **kwargs,
    ) -> Dict:
        """Create or update the EG MQTT dataflow endpoint on the AIO instance.

        Uses GET-then-PUT to report accurate status. The endpoint connects to the EG
        namespace's MQTT broker using managed identity authentication. Defaults to
        SystemAssigned MI; when mi_resource is provided, a UserAssigned MI is
        configured instead using clientId and tenantId from the resolved UAMI resource.

        When the endpoint already exists, compares host, authentication, and
        clientIdPrefix against the desired state. If any differ (e.g., re-enabling with
        a different EG namespace, switching between SAMI/UAMI, or a stale/missing
        clientIdPrefix), the endpoint is updated via PUT.
        """
        endpoint_name = get_mgmt_actions_resource_name("eg", instance_resource_id)

        # Build desired authentication block
        desired_authentication = self._build_eg_endpoint_auth(mi_resource)

        # Check if endpoint already exists
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

            # Compare host, auth, and clientIdPrefix — update if any differ
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
            logger.info(
                "Updated dataflow endpoint '%s' on instance '%s'.",
                endpoint_name,
                instance_name,
            )
            return {"name": endpoint_name, "authentication": desired_authentication, "exists": True, "updated": True}

        logger.info(
            "Created dataflow endpoint '%s' on instance '%s'.",
            endpoint_name,
            instance_name,
        )
        return {"name": endpoint_name, "authentication": desired_authentication, "exists": False}

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

    def _setup_adr_management_endpoint(
        self,
        instance: Dict,
        eg_ctx: EgNamespaceContext,
        **kwargs,
    ) -> Dict:
        """Enable system-assigned MI and configure the management endpoint on the ADR namespace.

        Performs a GET-merge-PATCH to preserve existing management endpoints. The endpoint
        key is the instance's custom location resource ID, connecting the ADR namespace
        to the Event Grid MQTT broker for management actions routing.

        Returns a dict with the ADR namespace identity state and the full management
        endpoints map (all custom location entries, not just ours) for multi-instance
        awareness.
        """
        # Resolve ADR namespace from instance
        adr_namespace_resource_id = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
        if not adr_namespace_resource_id:
            raise ValidationError(
                "Instance does not have an ADR namespace reference (adrNamespaceRef.resourceId). "
                "This is required for management actions. Ensure the instance was deployed with an ADR namespace."
            )

        parsed_adr = parse_resource_id_dict(adr_namespace_resource_id)
        adr_resource_group = parsed_adr.get("resource_group", "")
        adr_namespace_name = parsed_adr.get("name", "")
        adr_subscription_id = parsed_adr.get("subscription", "")

        if not all([adr_resource_group, adr_namespace_name]):
            raise ValidationError(
                f"Malformed ADR namespace resource Id '{adr_namespace_resource_id}'. "
                f"Could not extract resource group or namespace name."
            )

        # GET the ADR namespace
        adr_namespace = self.registry_mgmt_client.namespaces.get(
            resource_group_name=adr_resource_group,
            namespace_name=adr_namespace_name,
        )

        # Determine identity state and whether an update is needed
        current_identity = adr_namespace.get("identity", {})
        current_identity_type = (current_identity.get("type") or "").lower()
        identity_already_enabled = current_identity_type == "systemassigned"

        # Build management endpoint entry — keyed by custom location resource ID
        custom_location_id: str = instance["extendedLocation"]["name"]
        desired_endpoint = {
            "endpointType": MGMT_ACTIONS_ADR_ENDPOINT_TYPE,
            "address": eg_ctx.mqtt_hostname,
            "scopeId": instance.get("name", ""),
            "resourceId": eg_ctx.resource_id,
        }

        # Read existing management endpoints (GET-merge-PUT to preserve other entries)
        existing_endpoints = adr_namespace.get("properties", {}).get("management", {}).get("endpoints", {})
        current_endpoint = existing_endpoints.get(custom_location_id)
        endpoint_already_configured = current_endpoint == desired_endpoint

        # Skip update entirely if both identity and endpoint are already correct
        if identity_already_enabled and endpoint_already_configured:
            principal_id = current_identity.get("principalId", "")
            logger.info(
                "ADR namespace '%s' already has SystemAssigned identity and management endpoint configured.",
                adr_namespace_name,
            )
            return {
                "name": adr_namespace_name,
                "resourceGroup": adr_resource_group,
                "subscriptionId": adr_subscription_id,
                "identity": {
                    "type": current_identity.get("type", ""),
                    "principalId": principal_id,
                },
                "managementEndpoints": existing_endpoints,
                "identity_exists": True,
                "endpoint_exists": True,
            }

        # Build the update payload
        merged_endpoints = dict(existing_endpoints)
        merged_endpoints[custom_location_id] = desired_endpoint

        update_payload: Dict = {
            "properties": {
                "management": {
                    "endpoints": merged_endpoints,
                },
            },
        }

        # Always include identity in the update to ensure SystemAssigned is set
        if not identity_already_enabled:
            update_payload["identity"] = {"type": "SystemAssigned"}

        poller = self.registry_mgmt_client.namespaces.begin_update(
            resource_group_name=adr_resource_group,
            namespace_name=adr_namespace_name,
            properties=update_payload,
        )
        updated_namespace = wait_for_terminal_state(poller, **kwargs)

        principal_id = updated_namespace.get("identity", {}).get("principalId", "")
        if not principal_id:
            raise ValidationError(
                f"ADR namespace '{adr_namespace_name}' was updated with SystemAssigned identity "
                f"but no principalId was returned. This may indicate the operation is still propagating."
            )

        updated_identity = updated_namespace.get("identity", {})
        updated_endpoints = updated_namespace.get("properties", {}).get("management", {}).get("endpoints", {})

        logger.info(
            "ADR namespace '%s' updated — identity type: %s, management endpoints: %d.",
            adr_namespace_name,
            updated_identity.get("type", ""),
            len(updated_endpoints),
        )

        return {
            "name": adr_namespace_name,
            "resourceGroup": adr_resource_group,
            "subscriptionId": adr_subscription_id,
            "identity": {
                "type": updated_identity.get("type", ""),
                "principalId": principal_id,
            },
            "managementEndpoints": updated_endpoints,
            "identity_exists": identity_already_enabled,
            "endpoint_exists": endpoint_already_configured,
        }

    def _setup_dataflow_graph(
        self,
        instance_name: str,
        instance_resource_id: str,
        resource_group_name: str,
        extended_location: Dict,
        eg_dataflow_endpoint_name: str,
        dataflow_profile_name: str,
        registry_endpoint_name: str,
        **kwargs,
    ) -> Dict:
        """Create or confirm the management actions dataflow graph on the AIO instance.

        The graph wires MQTT request messages through a graph-dataflow-map rules engine
        and back to a local MQTT destination. Three nodes (Source → Graph → Destination)
        with two connections form the pipeline.
        """
        graph_name = get_mgmt_actions_resource_name("req", instance_resource_id)

        # Check if dataflow graph already exists
        try:
            self.iotops_mgmt_client.dataflow_graph.get(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=dataflow_profile_name,
                dataflow_graph_name=graph_name,
            )
            logger.info(
                "Dataflow graph '%s' already exists on instance '%s'.",
                graph_name,
                instance_name,
            )
            return {"name": graph_name, "exists": True}
        except ResourceNotFoundError:
            pass

        request_topic_prefix = f"actions/requests/{instance_name}/"
        rules_config = _build_graph_rules_config(
            topic_prefix_regex=f"^{request_topic_prefix}",
        )

        resource = {
            "extendedLocation": extended_location,
            "properties": {
                "mode": "Enabled",
                "nodes": [
                    {
                        "name": "source",
                        "nodeType": "Source",
                        "sourceSettings": {
                            "endpointRef": eg_dataflow_endpoint_name,
                            "dataSources": [f"{request_topic_prefix}#"],
                        },
                    },
                    {
                        "name": "graph",
                        "nodeType": "Graph",
                        "graphSettings": {
                            "registryEndpointRef": registry_endpoint_name,
                            "artifact": MGMT_ACTIONS_GRAPH_ARTIFACT,
                            "configuration": rules_config,
                        },
                    },
                    {
                        "name": "destination",
                        "nodeType": "Destination",
                        "destinationSettings": {
                            "endpointRef": MGMT_ACTIONS_DEFAULT_MQTT_ENDPOINT,
                            "dataDestination": "${outputTopic}",
                        },
                    },
                ],
                "nodeConnections": [
                    {
                        "from": {"name": "source"},
                        "to": {"name": "graph"},
                    },
                    {
                        "from": {"name": "graph"},
                        "to": {"name": "destination"},
                    },
                ],
            },
        }

        poller = self.iotops_mgmt_client.dataflow_graph.begin_create_or_update(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
            dataflow_graph_name=graph_name,
            resource=resource,
        )
        wait_for_terminal_state(poller, **kwargs)
        logger.info(
            "Created dataflow graph '%s' on instance '%s' (profile: '%s').",
            graph_name,
            instance_name,
            dataflow_profile_name,
        )

        return {"name": graph_name, "exists": False}

    def _setup_response_dataflow(
        self,
        instance_name: str,
        instance_resource_id: str,
        resource_group_name: str,
        extended_location: Dict,
        eg_dataflow_endpoint_name: str,
        dataflow_profile_name: str,
        **kwargs,
    ) -> Dict:
        """Create or confirm the management actions response dataflow on the AIO instance.

        Routes response messages from the local MQTT broker back to Event Grid.
        This is a simple source→destination pipeline (not a graph) — responses don't
        require topic transformation because they already carry the full topic path.
        """
        dataflow_name = get_mgmt_actions_resource_name("resp", instance_resource_id)

        # Check if response dataflow already exists
        try:
            self.iotops_mgmt_client.dataflow.get(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=dataflow_profile_name,
                dataflow_name=dataflow_name,
            )
            logger.info(
                "Response dataflow '%s' already exists on instance '%s'.",
                dataflow_name,
                instance_name,
            )
            return {"name": dataflow_name, "exists": True}
        except ResourceNotFoundError:
            pass

        response_topic = MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE.format(scope_id=instance_name)

        resource = {
            "extendedLocation": extended_location,
            "properties": {
                "mode": "Enabled",
                "operations": [
                    {
                        "operationType": "Source",
                        "sourceSettings": {
                            "endpointRef": MGMT_ACTIONS_DEFAULT_MQTT_ENDPOINT,
                            "dataSources": [response_topic],
                        },
                    },
                    {
                        "operationType": "Destination",
                        "destinationSettings": {
                            "endpointRef": eg_dataflow_endpoint_name,
                            "dataDestination": "${inputTopic}",
                        },
                    },
                ],
            },
        }

        poller = self.iotops_mgmt_client.dataflow.begin_create_or_update(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
            dataflow_name=dataflow_name,
            resource=resource,
        )
        wait_for_terminal_state(poller, **kwargs)
        logger.info(
            "Created response dataflow '%s' on instance '%s' (profile: '%s').",
            dataflow_name,
            instance_name,
            dataflow_profile_name,
        )

        return {"name": dataflow_name, "exists": False}

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

    def _resolve_dataflow_auth_identity(
        self,
        instance: Dict,
        mi_resource: Optional[Dict] = None,
    ) -> str:
        """Resolve the principal ID of the identity that authenticates the dataflow endpoint.

        When a UAMI is provided, its principalId is used directly. Otherwise, resolves the
        AIO extension's system MI by traversing: instance → custom location → connected
        cluster → extensions. The resolved principal ID is used for EG role assignments.
        """
        if mi_resource:
            principal_id = mi_resource.get("properties", {}).get("principalId")
            if not principal_id:
                raise ValidationError(
                    "User-assigned managed identity is missing 'principalId'.\n"
                    "Verify the identity resource has been fully provisioned."
                )
            return principal_id

        # Resolve AIO extension system MI via custom location → connected cluster
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

    def _setup_role_assignments(
        self,
        eg_ctx: EgNamespaceContext,
        adr_principal_id: str,
        dataflow_auth_principal_id: str,
        adr_role_ids: Optional[List[str]] = None,
        ops_role_ids: Optional[List[str]] = None,
    ) -> Dict:
        """Assign EG Topic Spaces Publisher/Subscriber roles for both identity principals.

        Two principals need EG namespace access:
        - ADR namespace system MI (for device registry ↔ EG communication)
        - Dataflow auth identity (for dataflow endpoint ↔ EG communication)

        Uses a separate PermissionManager when the EG namespace is in a different
        subscription than the instance. Role assignments are idempotent — existing
        assignments are skipped.
        """
        default_role_ids = [EG_TOPICSPACES_PUBLISHER_ROLE_ID, EG_TOPICSPACES_SUBSCRIBER_ROLE_ID]
        resolved_adr_roles = adr_role_ids or default_role_ids
        resolved_ops_roles = ops_role_ids or default_role_ids

        # Use a cross-subscription PermissionManager when the EG namespace lives
        # in a different subscription than the instance.
        if eg_ctx.subscription_id.lower() != self.default_subscription_id.lower():
            eg_permission_manager = PermissionManager(subscription_id=eg_ctx.subscription_id)
        else:
            eg_permission_manager = self.permission_manager

        scope = eg_ctx.resource_id

        identity_assignments = [
            ("adrNamespace", adr_principal_id, resolved_adr_roles),
            ("dataflowIdentity", dataflow_auth_principal_id, resolved_ops_roles),
        ]

        result: Dict = {}
        for result_key, principal_id, role_ids in identity_assignments:
            try:
                for role_id in role_ids:
                    role_def_id = ROLE_DEF_FORMAT_STR.format(
                        subscription_id=eg_ctx.subscription_id,
                        role_id=role_id,
                    )
                    eg_permission_manager.apply_role_assignment(
                        scope=scope,
                        principal_id=principal_id,
                        role_def_id=role_def_id,
                        principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
                    )
            except HttpResponseError as e:
                raise ValidationError(
                    f"Failed to assign role(s) for principal '{principal_id}' "
                    f"on EG namespace '{eg_ctx.namespace_name}'.\n"
                    f"Error: {e.message}\n"
                    f"You can manually assign the required roles:\n"
                    f"  Scope: {scope}\n"
                    f"  Principal ID: {principal_id}\n"
                    f"  Role IDs: {', '.join(role_ids)}"
                )

            result[result_key] = {
                "principalId": principal_id,
                "roles": list(role_ids),
            }

        return result

    def _resolve_request_schema(
        self,
        instance: dict,
        namespace_rg: str,
        namespace_name: str,
        asset_name: str,
        group_name: str,
        action_name: str,
    ) -> Optional[dict]:
        """Resolve the request JSON schema for a management action.

        Walks the resolution chain: instance schemaRegistryRef → asset status →
        action's requestMessageSchemaReference → schema version content.
        Returns the parsed JSON Schema dict, or None if any step fails.
        """
        # Resolve schema registry from instance
        schema_registry_id = (
            instance.get("properties", {})
            .get("schemaRegistryRef", {})
            .get("resourceId")
        )
        if not schema_registry_id:
            logger.debug("No schemaRegistryRef on instance — skipping payload validation.")
            return None

        parsed_registry = parse_resource_id_dict(schema_registry_id)
        registry_rg = parsed_registry.get("resource_group")
        registry_name = parsed_registry.get("name")
        registry_sub = parsed_registry.get("subscription")
        if not registry_rg or not registry_name:
            logger.debug("Could not parse schema registry resource ID — skipping payload validation.")
            return None

        # Resolve client for schema registry operations (may be cross-subscription)
        if registry_sub and registry_sub.casefold() != self.default_subscription_id.casefold():
            logger.debug(
                "Schema registry is in subscription %s — using cross-subscription client.",
                registry_sub,
            )
            schema_client = get_registry_mgmt_client(**self._get_client_kwargs(subscription_id=registry_sub))
        else:
            schema_client = self.registry_mgmt_client

        # Fetch asset with status to get requestMessageSchemaReference
        try:
            asset = self.registry_mgmt_client.namespace_assets.get(
                resource_group_name=namespace_rg,
                namespace_name=namespace_name,
                asset_name=asset_name,
            )
        except HttpResponseError as e:
            logger.debug("Failed to fetch asset for schema resolution: %s", e)
            return None

        # Find matching group + action in status
        schema_ref = None
        for mg in asset.get("properties", {}).get("status", {}).get("managementGroups", []):
            if mg.get("name", "").casefold() != group_name.casefold():
                continue
            for action in mg.get("actions", []):
                if action.get("name", "").casefold() != action_name.casefold():
                    continue
                schema_ref = action.get("requestMessageSchemaReference")
                break
            if schema_ref:
                break

        if not schema_ref:
            logger.debug(
                "No requestMessageSchemaReference found for group=%s action=%s — skipping.",
                group_name,
                action_name,
            )
            return None

        schema_name = schema_ref.get("schemaName")
        schema_version = schema_ref.get("schemaVersion")
        if not schema_name or not schema_version:
            logger.debug(
                "Incomplete schemaReference (name=%s, version=%s) — skipping.",
                schema_name,
                schema_version,
            )
            return None

        # Fetch schema version content
        try:
            schema_version_resource = schema_client.schema_versions.get(
                resource_group_name=registry_rg,
                schema_registry_name=registry_name,
                schema_name=schema_name,
                schema_version_name=schema_version,
            )
        except HttpResponseError as e:
            logger.debug("Failed to fetch schema version %s/%s: %s", schema_name, schema_version, e)
            return None

        schema_content_str = schema_version_resource.get("properties", {}).get("schemaContent")
        if not schema_content_str:
            logger.debug("Schema version has no schemaContent — skipping payload validation.")
            return None

        # Parse schemaContent JSON
        try:
            return json.loads(schema_content_str)
        except json.JSONDecodeError as e:
            logger.debug("schemaContent is not valid JSON: %s — skipping payload validation.", e)
            return None

    def execute(
        self,
        instance_name: str,
        resource_group_name: str,
        asset_name: str,
        group_name: str,
        action_name: str,
        payload: Optional[str] = None,
        no_validate: bool = False,
        show_schema: bool = False,
        **kwargs,
    ) -> dict:
        """Execute a management action on a namespace asset.

        Resolves the ADR namespace from the instance, then optionally validates the
        payload against the action's request schema before invoking the executeAction
        ARM operation as an LRO. Returns the action result (status, response, errors).

        When show_schema is True, resolves and returns the request schema without
        executing the action.
        """
        from ...util.file_operations import deserialize_json_input

        # Resolve instance → ADR namespace
        instance = self.iotops_mgmt_client.instance.get(
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
        adr_namespace_ref = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
        if not adr_namespace_ref:
            raise ValidationError(
                "Instance does not have an ADR namespace reference. "
                "Ensure the instance is properly configured."
            )
        parsed_adr = parse_resource_id_dict(adr_namespace_ref)
        namespace_rg = parsed_adr.get("resource_group")
        namespace_name = parsed_adr.get("name")
        if not namespace_rg or not namespace_name:
            raise ValidationError(
                f"Could not parse ADR namespace resource ID: {adr_namespace_ref}"
            )

        # --show-schema: resolve and return the request schema, then exit
        if show_schema:
            with console.status("Resolving request schema..."):
                request_schema = self._resolve_request_schema(
                    instance=instance,
                    namespace_rg=namespace_rg,
                    namespace_name=namespace_name,
                    asset_name=asset_name,
                    group_name=group_name,
                    action_name=action_name,
                )
            if not request_schema:
                raise ResourceNotFoundError(
                    f"Could not resolve the request schema for action '{action_name}' "
                    f"in group '{group_name}' on asset '{asset_name}'. "
                    "The schema may not be published, the asset status may not be populated, "
                    "or the schema registry may be inaccessible."
                )
            return request_schema

        # Build request body
        body: Dict[str, Any] = {
            "managementActionName": action_name,
            "managementGroupName": group_name,
        }
        deserialized_payload = None
        if payload:
            deserialized_payload = deserialize_json_input(payload)
            body["payload"] = deserialized_payload

        # Validate payload against request schema (when validation is enabled)
        if not no_validate:
            with console.status("Validating payload..."):
                request_schema = self._resolve_request_schema(
                    instance=instance,
                    namespace_rg=namespace_rg,
                    namespace_name=namespace_name,
                    asset_name=asset_name,
                    group_name=group_name,
                    action_name=action_name,
                )
                if request_schema:
                    from ...util.schema_validation import check_json_schema, validate_data_against_schema

                    schema_issue = check_json_schema(request_schema)
                    if schema_issue:
                        logger.warning(
                            "%s — skipping validation. Use --show-schema to inspect the schema.",
                            schema_issue,
                        )
                    else:
                        validate_data_against_schema(
                            request_schema,
                            deserialized_payload if deserialized_payload is not None else {},
                            name="payload",
                        )

        logger.debug("Execute action request body: %s", body)

        # Execute action (LRO)
        with console.status("Sending request...") as status:
            poller = self.registry_mgmt_client.namespace_assets.begin_execute_action(
                resource_group_name=namespace_rg,
                namespace_name=namespace_name,
                asset_name=asset_name,
                body=body,
            )
            if not poller.done():
                status.update("Waiting for response...")
                return wait_for_terminal_state(poller, **kwargs)
            return poller.result()

    def remove_management_endpoint(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoint_key: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Remove a management endpoint entry from an ADR namespace.

        Uses PUT to replace the namespace resource with the target entry removed,
        because ARM PATCH deep-merges dicts (can't remove keys by omission) and
        the ADR API rejects null endpoint values.
        """
        adr_namespace = self.registry_mgmt_client.namespaces.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
        )

        existing_endpoints = adr_namespace.get("properties", {}).get("management", {}).get("endpoints", {})
        if endpoint_key not in existing_endpoints:
            logger.warning(
                "No management endpoint entry found for key '%s' on namespace '%s' — nothing to remove.",
                endpoint_key,
                namespace_name,
            )
            return

        endpoint_info = existing_endpoints[endpoint_key]
        endpoint_type = endpoint_info.get("endpointType", "unknown")
        logger.warning(
            "Management endpoint to remove from namespace '%s':\n  Key: %s\n  Type: %s",
            namespace_name,
            endpoint_key,
            endpoint_type,
        )

        if not should_continue_prompt(confirm_yes):
            return

        put_payload = _build_adr_put_payload(adr_namespace, endpoint_key_to_remove=endpoint_key)
        with console.status("Removing management endpoint..."):
            poller = self.registry_mgmt_client.namespaces.begin_create_or_replace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                resource=put_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
        logger.info(
            "Removed management endpoint entry '%s' from namespace '%s'.",
            endpoint_key,
            namespace_name,
        )
