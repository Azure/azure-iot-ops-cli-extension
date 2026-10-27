# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from uuid import UUID

from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import AzureError, HttpResponseError, ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console

from ...util.az_client import (
    get_eventgrid_mgmt_client,
    get_iotops_mgmt_client,
    get_registry_mgmt_client,
    wait_for_terminal_state,
)
from ...util.cloud_config import CloudConfig
from ...util.common import should_continue_prompt, url_safe_hash_phrase
from ...util.id_tools import parse_resource_id as parse_resource_id_dict
from ...util.workflow_display import StepState, WorkflowDisplay, render_summary
from .common import (
    EG_TOPICSPACES_PUBLISHER_ROLE_ID,
    EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
    LIVE_DATA_ADR_API_VERSION,
    LIVE_DATA_ADR_ENDPOINT_TYPE,
    LIVE_DATA_ENDPOINT_NAME,
    LIVE_DATA_PROFILE_NAME,
    LIVE_DATA_TOPIC_TEMPLATE,
    LIVE_DATA_TOPICSPACE_PREFIX,
    LIVE_DATA_USER_ROLE_ID,
    LiveDataRoleScope,
)
from .eg_provider_base import EgNamespaceContext, EventGridProviderBase, graceful_delete
from .permissions import ROLE_DEF_FORMAT_STR, PermissionManager, PrincipalType
from .runtime import OperationRequirements
from .runtime_catalog import get_runtime_catalog
from .runtime_profiles import RuntimeChannel

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )
    from ...vendor.clients.eventgridmgmt import EventGridManagementClient

logger = get_logger(__name__)
console = Console()

LIVE_DATA_RUNTIME_REQUIREMENT = OperationRequirements(
    "Live Data", channels={RuntimeChannel.PREVIEW},
)
LIVE_DATA_RECOVERY_REQUIREMENT = OperationRequirements(
    "Live Data", channels={RuntimeChannel.PREVIEW}, requires_ready=False,
)


def get_live_data_topic_space_name(instance_resource_id: str) -> str:
    """Build the deterministic topic space name: live-data-ts-{hash8}.

    hash8 = first 8 chars of a URL-safe hash of the instance ARM resource ID, so the
    shared Event Grid namespace can host topic spaces for multiple instances.
    """
    hash8 = url_safe_hash_phrase(instance_resource_id)[:8]
    return f"{LIVE_DATA_TOPICSPACE_PREFIX}-{hash8}"


def _resolve_observability_endpoint_key(endpoints: Dict, custom_location_id: str) -> Optional[str]:
    return next((key for key in endpoints if key.lower() == custom_location_id.lower()), None)


def _build_adr_observability_put_payload(adr_namespace: Dict, custom_location_id: str) -> Dict:
    """Build an ADR namespace PUT payload with one observability endpoint entry removed.

    ARM PATCH deep-merges dicts (omitting a key preserves it) and the ADR API rejects
    null endpoint values, so a full PUT replaces the resource. Preserves identity, tags,
    outboundIdentity, management, and messaging from the original namespace.
    """
    properties = adr_namespace.get("properties", {})
    observability = properties.get("observability", {})
    existing_endpoints = observability.get("endpoints", {})
    endpoint_key = _resolve_observability_endpoint_key(existing_endpoints, custom_location_id)
    updated_endpoints = {k: v for k, v in existing_endpoints.items() if k != endpoint_key}

    # Preserve any sibling keys under observability since this is a full PUT.
    updated_observability = dict(observability)
    updated_observability["enabled"] = bool(updated_endpoints)
    updated_observability["endpoints"] = updated_endpoints

    payload: Dict = {
        "location": adr_namespace.get("location", ""),
        "properties": {
            "observability": updated_observability,
        },
    }
    if adr_namespace.get("identity"):
        payload["identity"] = adr_namespace["identity"]
    if adr_namespace.get("tags"):
        payload["tags"] = adr_namespace["tags"]
    outbound_identity = properties.get("outboundIdentity")
    if outbound_identity:
        payload["properties"]["outboundIdentity"] = outbound_identity
    management = properties.get("management")
    if management:
        payload["properties"]["management"] = management
    messaging = properties.get("messaging")
    if messaging:
        payload["properties"]["messaging"] = messaging
    return payload


class LiveData(EventGridProviderBase):
    """Provider for Live Data enable/show/disable operations."""

    def __init__(self, cmd, subscription_id: Optional[str] = None):
        super().__init__(cmd=cmd, subscription_id=subscription_id)
        self.runtime_profile = get_runtime_catalog().get(RuntimeChannel.PREVIEW)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            api_version=self.runtime_profile.iotops_api_version,
            **self._get_client_kwargs(),
        )
        # Live Data requires ADR observability fields from the preview API version.
        self.registry_mgmt_client: "MicrosoftDeviceRegistryManagementService" = get_registry_mgmt_client(
            api_version=LIVE_DATA_ADR_API_VERSION,
            **self._get_client_kwargs(),
        )
        self._registry_clients = {self.default_subscription_id.lower(): self.registry_mgmt_client}
        # May be replaced with a cross-subscription client by _validate_eg_namespace.
        self.eventgrid_mgmt_client: "EventGridManagementClient" = get_eventgrid_mgmt_client(
            **self._get_client_kwargs()
        )
        self.permission_manager = PermissionManager(
            **self._get_client_kwargs(),
            credential_scopes=[CloudConfig(self.cmd).arm_endpoint_scope],
        )

    def _resolve_adr_namespace(self, instance: Dict) -> Tuple[Dict, Dict]:
        resource_id = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
        if not resource_id:
            raise ValidationError(
                "Instance does not have an ADR namespace reference (adrNamespaceRef.resourceId). "
                "This is required for Live Data. Ensure the instance was deployed with an ADR namespace."
            )
        parsed = parse_resource_id_dict(resource_id)
        if (
            not all(parsed.get(key) for key in ("subscription", "resource_group", "name"))
            or parsed.get("namespace", "").lower() != "microsoft.deviceregistry"
            or parsed.get("type", "").lower() != "namespaces"
            or parsed.get("last_child_num")
        ):
            raise ValidationError(f"Malformed ADR namespace resource Id '{resource_id}'.")
        subscription_id = parsed["subscription"]
        key = subscription_id.lower()
        if key not in self._registry_clients:
            self._registry_clients[key] = get_registry_mgmt_client(
                api_version=LIVE_DATA_ADR_API_VERSION,
                **self._get_client_kwargs(subscription_id=subscription_id),
            )
        self.registry_mgmt_client = self._registry_clients[key]
        namespace = self.registry_mgmt_client.namespaces.get(
            resource_group_name=parsed["resource_group"],
            namespace_name=parsed["name"],
        )
        return parsed, namespace

    def enable(
        self,
        name: str,
        resource_group_name: str,
        eg_resource_id: str,
        mi_user_assigned: Optional[str] = None,
        ra_scope: Optional[str] = None,
        adr_role_ids: Optional[List[str]] = None,
        ops_role_ids: Optional[List[str]] = None,
        user_object_ids: Optional[List[str]] = None,
        subscriber_object_ids: Optional[List[str]] = None,
        skip_role_assignments: Optional[bool] = None,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> Dict:
        """Enable Live Data infrastructure for an IoT Operations instance.

        Converges Event Grid, AIO, and ADR namespace resources plus role assignments.
        All steps are idempotent — re-running adds to shared resources without
        overwriting unrelated entries.
        """
        if not CloudConfig(self.cmd).supports_eventgrid_mqtt:
            raise ValidationError(
                "Live Data is not available in this cloud environment. This feature relies on "
                "Event Grid Namespaces with MQTT, which is not supported in the active cloud."
            )

        resolved_user_object_ids = self._resolve_object_ids(user_object_ids, "user", skip_role_assignments)
        resolved_subscriber_object_ids = self._resolve_object_ids(
            subscriber_object_ids, "subscriber", skip_role_assignments,
        )
        resolved_scope = LiveDataRoleScope(ra_scope) if ra_scope else LiveDataRoleScope.NAMESPACE

        analyzing_cats = {"Analyzing": ["Instance resolution", "EG namespace validation", "UAMI resolution"]}
        with WorkflowDisplay(
            "Live Data Enablement", analyzing_cats, no_progress=no_progress,
        ) as display:
            with display.step_scope("Analyzing", "Instance resolution"):
                instance = self.iotops_mgmt_client.instance.get(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                )
                name = instance["name"]
                instance_resource_id: str = instance["id"]
                extended_location: Dict = instance["extendedLocation"]
                custom_location_id: str = extended_location["name"]
                _, adr_namespace = self._resolve_adr_namespace(instance)
                display.update_step("Analyzing", "Instance resolution", StepState.COMPLETE, "done")

            with display.step_scope("Analyzing", "EG namespace validation"):
                eg_ctx = self._validate_eg_namespace(eg_resource_id)
                display.update_step("Analyzing", "EG namespace validation", StepState.COMPLETE, "done")

            with display.step_scope("Analyzing", "UAMI resolution"):
                mi_resource = self._resolve_user_assigned_mi(mi_user_assigned) if mi_user_assigned else None
                self._validate_shared_adr_identity(adr_namespace, custom_location_id, mi_resource)
                if mi_resource:
                    display.update_step("Analyzing", "UAMI resolution", StepState.COMPLETE, "done")
                else:
                    display.update_step("Analyzing", "UAMI resolution", StepState.SKIPPED, "not needed")

        adr_ns_ref = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId", "")
        adr_ns_display = parse_resource_id_dict(adr_ns_ref).get("name", "") if adr_ns_ref else ""

        cat_eg = f"Event Grid Namespace ({eg_ctx.namespace_name})"
        cat_aio = f"IoT Operations Instance ({name})"
        cat_adr = f"Device Registry Namespace ({adr_ns_display})" if adr_ns_display else "Device Registry Namespace"
        cat_roles = "Role Assignments"

        config_cats: Dict[str, List[str]] = {
            cat_eg: ["Topic space"],
            cat_aio: ["Dataflow profile", "EG dataflow endpoint"],
            cat_adr: ["Outbound identity", "Observability endpoint"],
        }
        if not skip_role_assignments:
            role_steps = ["Publisher (instance)", "Subscriber (namespace)"]
            if resolved_user_object_ids:
                role_steps.append("Reader (users)")
            if resolved_subscriber_object_ids:
                role_steps.append("Subscriber (additional principals)")
            config_cats[cat_roles] = role_steps

        with WorkflowDisplay(
            "Live Data Enablement", config_cats, transient=False, no_progress=no_progress,
        ) as display:
            with display.step_scope(cat_eg, "Topic space"):
                topic_space_result = self._setup_topic_space(
                    eg_ctx=eg_ctx,
                    instance_name=name,
                    instance_resource_id=instance_resource_id,
                    **kwargs,
                )
                detail = "updated" if topic_space_result.get("updated") else (
                    "exists" if topic_space_result.get("exists") else "created"
                )
                state = StepState.SKIPPED if detail == "exists" else StepState.COMPLETE
                display.update_step(cat_eg, "Topic space", state, detail)

            with display.step_scope(cat_aio, "Dataflow profile"):
                profile_result = self._setup_dataflow_profile(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                    extended_location=extended_location,
                    **kwargs,
                )
                detail = "updated" if profile_result.get("updated") else (
                    "exists" if profile_result.get("exists") else "created"
                )
                state = StepState.SKIPPED if detail == "exists" else StepState.COMPLETE
                display.update_step(cat_aio, "Dataflow profile", state, detail)

            with display.step_scope(cat_aio, "EG dataflow endpoint"):
                endpoint_result = self._setup_eg_dataflow_endpoint(
                    eg_ctx=eg_ctx,
                    instance_name=name,
                    resource_group_name=resource_group_name,
                    extended_location=extended_location,
                    endpoint_name=LIVE_DATA_ENDPOINT_NAME,
                    mi_resource=mi_resource,
                    **kwargs,
                )
                if endpoint_result.get("updated"):
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.COMPLETE, "updated")
                elif endpoint_result.get("exists"):
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.SKIPPED, "exists")
                else:
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.COMPLETE, "created")

            # ADR namespace + role assignments are interdependent (staged identity flow).
            display.update_step(cat_adr, "Outbound identity", StepState.ACTIVE)
            display.update_step(cat_adr, "Observability endpoint", StepState.ACTIVE)
            try:
                adr_result = self._setup_adr_observability(
                    instance=instance,
                    eg_ctx=eg_ctx,
                    custom_location_id=custom_location_id,
                    mi_resource=mi_resource,
                    ra_scope=resolved_scope,
                    topic_space_name=topic_space_result["name"],
                    adr_role_ids=adr_role_ids,
                    skip_role_assignments=bool(skip_role_assignments),
                    **kwargs,
                )
                identity_detail = "exists" if adr_result.get("identity_exists") else "enabled"
                identity_state = StepState.SKIPPED if adr_result.get("identity_exists") else StepState.COMPLETE
                display.update_step(cat_adr, "Outbound identity", identity_state, identity_detail)
                endpoint_detail = "exists" if adr_result.get("endpoint_exists") else "created"
                endpoint_state = StepState.SKIPPED if adr_result.get("endpoint_exists") else StepState.COMPLETE
                display.update_step(cat_adr, "Observability endpoint", endpoint_state, endpoint_detail)
            except Exception as exc:
                display.update_step(cat_adr, "Outbound identity", StepState.FAILED, str(exc)[:40])
                display.update_step(cat_adr, "Observability endpoint", StepState.FAILED, str(exc)[:40])
                raise

            role_assignments_result = None
            if not skip_role_assignments:
                display.update_step(cat_roles, "Publisher (instance)", StepState.ACTIVE)
                display.update_step(cat_roles, "Subscriber (namespace)", StepState.ACTIVE)
                try:
                    publisher_principal_id = self._resolve_ops_extension_identity(
                        instance=instance,
                        mi_resource=mi_resource,
                    )
                    role_assignments_result = self._setup_role_assignments(
                        eg_ctx=eg_ctx,
                        ra_scope=resolved_scope,
                        topic_space_name=topic_space_result["name"],
                        publisher_principal_id=publisher_principal_id,
                        subscriber_principal_id=adr_result["identity"]["principalId"],
                        adr_role_ids=adr_role_ids,
                        ops_role_ids=ops_role_ids,
                    )
                    display.update_step(cat_roles, "Publisher (instance)", StepState.COMPLETE, "done")
                    display.update_step(cat_roles, "Subscriber (namespace)", StepState.COMPLETE, "done")
                except Exception as exc:
                    display.update_step(cat_roles, "Publisher (instance)", StepState.FAILED, str(exc)[:40])
                    display.update_step(cat_roles, "Subscriber (namespace)", StepState.FAILED, str(exc)[:40])
                    raise

                if resolved_subscriber_object_ids:
                    with display.step_scope(cat_roles, "Subscriber (additional principals)"):
                        role_assignments_result["subscribers"] = self._setup_subscriber_role_assignments(
                            eg_ctx=eg_ctx,
                            ra_scope=resolved_scope,
                            topic_space_name=topic_space_result["name"],
                            subscriber_object_ids=resolved_subscriber_object_ids,
                        )
                        display.update_step(
                            cat_roles, "Subscriber (additional principals)", StepState.COMPLETE, "done",
                        )

                if resolved_user_object_ids:
                    with display.step_scope(cat_roles, "Reader (users)"):
                        try:
                            role_assignments_result["users"] = self._setup_user_role_assignments(
                                adr_namespace_id=adr_ns_ref,
                                user_object_ids=resolved_user_object_ids,
                            )
                        except ValidationError as exc:
                            if resolved_subscriber_object_ids:
                                subscribers = role_assignments_result["subscribers"]
                                raise ValidationError(
                                    f"{exc}\n"
                                    f"{self._format_retained_subscriber_detail(subscribers)}"
                                ) from exc
                            raise
                        display.update_step(cat_roles, "Reader (users)", StepState.COMPLETE, "done")

        for sub_result in [topic_space_result, profile_result, endpoint_result]:
            sub_result.pop("exists", None)
            sub_result.pop("updated", None)

        result: Dict = {
            "instance": {
                "dataflowProfile": profile_result,
                "dataflowEndpoint": endpoint_result,
            },
            "eventGrid": {
                "namespace": {
                    "name": eg_ctx.namespace_name,
                    "resourceGroup": eg_ctx.resource_group_name,
                    "subscriptionId": eg_ctx.subscription_id,
                    "mqttHostname": eg_ctx.mqtt_hostname,
                },
                "topicSpace": topic_space_result,
            },
            "deviceRegistryNamespace": {
                "name": adr_result["name"],
                "resourceGroup": adr_result["resourceGroup"],
                "subscriptionId": adr_result["subscriptionId"],
                "outboundIdentity": adr_result.get("outboundIdentity"),
                "observabilityEndpoint": adr_result.get("observabilityEndpoint"),
            },
            "roleAssignmentScope": resolved_scope.value,
        }
        if role_assignments_result is not None:
            result["roleAssignments"] = role_assignments_result

        return result

    @staticmethod
    def _format_retained_subscriber_detail(subscribers: Dict) -> str:
        new_ids = " ".join(
            assignment["assignmentId"] for assignment in subscribers["assignments"] if assignment["created"]
        )
        existing_ids = " ".join(
            assignment["assignmentId"] for assignment in subscribers["assignments"] if not assignment["created"]
        )
        return (
            "Event Grid Subscriber assignments from the completed subscriber phase "
            f"remain in place at scope '{subscribers['scope']}'.\n"
            f"Newly created Subscriber assignment IDs: {new_ids or '(none)'}\n"
            f"Pre-existing Subscriber assignment IDs: {existing_ids or '(none)'}\n"
            "No Subscriber assignments were rolled back. To undo access added by this invocation, "
            "use 'az role assignment delete --ids' with only the newly created assignment IDs; "
            "leave pre-existing assignments unchanged."
        )

    @classmethod
    def _resolve_object_ids(
        cls, object_ids: Optional[List[str]], principal_kind: str, skip_role_assignments: Optional[bool],
    ) -> List[str]:
        if skip_role_assignments and object_ids:
            logger.warning(
                "Both --skip-ra and --%s-object-ids were provided. "
                "Skipping all role assignments because --skip-ra takes precedence.",
                principal_kind,
            )
            return []
        return cls._normalize_object_ids(object_ids, principal_kind)

    @staticmethod
    def _normalize_object_ids(object_ids: Optional[List[str]], principal_kind: str) -> List[str]:
        """Validate and de-duplicate Microsoft Entra object IDs."""
        normalized: List[str] = []
        seen = set()
        for object_id in object_ids or []:
            try:
                value = str(UUID(object_id))
            except (AttributeError, TypeError, ValueError):
                raise ValidationError(
                    f"Invalid Microsoft Entra {principal_kind} object ID '{object_id}'. Provide GUID object IDs."
                )
            if value not in seen:
                seen.add(value)
                normalized.append(value)
        return normalized

    def _setup_user_role_assignments(
        self,
        adr_namespace_id: str,
        user_object_ids: List[str],
    ) -> Dict:
        """Grant Reader to explicit users at the Device Registry namespace scope."""
        parsed_adr = parse_resource_id_dict(adr_namespace_id)
        subscription_id = parsed_adr.get("subscription", "")
        if not subscription_id:
            raise ValidationError(
                f"Malformed ADR namespace resource Id '{adr_namespace_id}'. Could not extract subscription Id."
            )

        manager = PermissionManager(
            **self._get_client_kwargs(subscription_id=subscription_id),
            credential_scopes=[CloudConfig(self.cmd).arm_endpoint_scope],
        )
        return self._setup_explicit_role_assignments(
            manager=manager,
            scope=adr_namespace_id,
            subscription_id=subscription_id,
            object_ids=user_object_ids,
            role_id=LIVE_DATA_USER_ROLE_ID,
            preserved_on_disable=True,
            principal_type=PrincipalType.USER.value,
        )

    def _setup_subscriber_role_assignments(
        self,
        eg_ctx: EgNamespaceContext,
        ra_scope: LiveDataRoleScope,
        topic_space_name: str,
        subscriber_object_ids: List[str],
    ) -> Dict:
        return self._setup_explicit_role_assignments(
            manager=self._permission_manager(eg_ctx),
            scope=self._role_scope(eg_ctx, ra_scope, topic_space_name),
            subscription_id=eg_ctx.subscription_id,
            object_ids=subscriber_object_ids,
            role_id=EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
            preserved_on_disable=ra_scope == LiveDataRoleScope.NAMESPACE,
        )

    def _setup_explicit_role_assignments(
        self,
        manager: PermissionManager,
        scope: str,
        subscription_id: str,
        object_ids: List[str],
        role_id: str,
        preserved_on_disable: bool,
        principal_type: Optional[str] = None,
    ) -> Dict:
        role_def_id = ROLE_DEF_FORMAT_STR.format(subscription_id=subscription_id, role_id=role_id)
        role_name = {
            LIVE_DATA_USER_ROLE_ID: "Reader",
            EG_TOPICSPACES_SUBSCRIBER_ROLE_ID: "Event Grid TopicSpaces Subscriber",
        }[role_id]
        assignments: List[Dict] = []
        for object_id in object_ids:
            try:
                # Omit the type for mixed subscribers so ARM resolves it without a CLI Graph lookup.
                role_assignment, created = manager.ensure_role_assignment(
                    scope=scope,
                    principal_id=object_id,
                    role_def_id=role_def_id,
                    principal_type=principal_type,
                )
            except AzureError as e:
                rolled_back, rollback_failures = self._rollback_role_assignments(manager, assignments)
                rollback_detail = self._format_assignment_rollback_detail(rolled_back, rollback_failures)
                raise ValidationError(
                    f"Failed to assign role '{role_name}' ({role_id}) to principal '{object_id}' "
                    f"at scope '{scope}'.\n"
                    f"Error: {e}\n"
                    f"  Scope: {scope}\n  Principal ID: {object_id}\n"
                    f"  Role ID: {role_id}\n{rollback_detail}"
                ) from e

            assignment_id = role_assignment.get("id", "") if role_assignment else ""
            if not assignment_id:
                rolled_back, rollback_failures = self._rollback_role_assignments(manager, assignments)
                rollback_detail = self._format_assignment_rollback_detail(rolled_back, rollback_failures)
                raise ValidationError(
                    f"Role assignment for '{role_name}' ({role_id}) to principal '{object_id}' "
                    "succeeded but no assignment Id was returned. "
                    "The current assignment could not be targeted for cleanup.\n"
                    f"{rollback_detail}"
                )
            assignments.append(
                {
                    "principalId": object_id,
                    "assignmentId": assignment_id,
                    "created": created,
                }
            )

        return {
            "roleId": role_id,
            "scope": scope,
            "preservedOnDisable": preserved_on_disable,
            "assignments": assignments,
        }

    @staticmethod
    def _rollback_role_assignments(
        manager: PermissionManager,
        assignments: List[Dict],
    ) -> Tuple[List[str], List[str]]:
        """Remove assignments created earlier in the current operation."""
        rolled_back: List[str] = []
        rollback_failures: List[str] = []
        for assignment in reversed(assignments):
            if not assignment["created"]:
                continue
            assignment_id = assignment["assignmentId"]
            try:
                manager.delete_role_assignment(assignment_id)
            except AzureError:
                rollback_failures.append(assignment_id)
            else:
                rolled_back.append(assignment_id)
        return rolled_back, rollback_failures

    @staticmethod
    def _format_assignment_rollback_detail(
        rolled_back: List[str],
        rollback_failures: List[str],
    ) -> str:
        if rollback_failures:
            detail = (
                "Cleanup failed for newly created role assignment IDs: "
                f"{', '.join(rollback_failures)}"
            )
            if rolled_back:
                detail += f"\nRolled back role assignment IDs: {', '.join(rolled_back)}"
            return detail
        if rolled_back:
            return f"Rolled back role assignment IDs: {', '.join(rolled_back)}"
        return "No new role assignments were created earlier in this assignment batch."

    def show(
        self,
        name: str,
        resource_group_name: str,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> Dict:
        """Show Live Data configuration for an IoT Operations instance.

        Live Data state requires this instance's observability.endpoints[<customLocationId>]
        entry and configured supporting resources. The namespace-wide flag is informational.
        """
        analyzing_cats = {
            "Analyzing": ["Instance & ADR namespace", "Event Grid resources", "Instance dataflow resources"],
        }

        adr_section: Optional[Dict] = None
        eg_section: Optional[Dict] = None
        obs_endpoint: Optional[Dict] = None
        observability_enabled = False
        obs_endpoint_exists = False
        eg_all_exist = False
        outbound_identity: Dict = {}

        with WorkflowDisplay(
            title="Live Data Status",
            categories=analyzing_cats,
            transient=True,
            no_progress=no_progress,
        ) as display:
            with display.step_scope("Analyzing", "Instance & ADR namespace"):
                instance = self.iotops_mgmt_client.instance.get(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                )
                name = instance["name"]
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
                            _, adr_namespace = self._resolve_adr_namespace(instance)
                            observability = (
                                adr_namespace.get("properties", {}).get("observability", {})
                            )
                            observability_enabled = observability.get("enabled") is True
                            existing_endpoints = observability.get("endpoints", {})
                            endpoint_key = _resolve_observability_endpoint_key(existing_endpoints, custom_location_id)
                            obs_endpoint = existing_endpoints.get(endpoint_key) if endpoint_key is not None else None
                            obs_endpoint_exists = bool(obs_endpoint)
                            outbound_identity = adr_namespace.get("properties", {}).get("outboundIdentity") or {}

                            adr_section = {
                                "name": adr_namespace_name,
                                "resourceGroup": adr_resource_group,
                                "subscriptionId": adr_subscription_id,
                                "outboundIdentity": adr_namespace.get("properties", {}).get("outboundIdentity"),
                                "observabilityEnabled": observability_enabled,
                                "observabilityEndpoint": {
                                    "endpointType": obs_endpoint.get("endpointType", ""),
                                    "address": obs_endpoint.get("address", ""),
                                    "scopeId": obs_endpoint.get("scopeId", ""),
                                } if obs_endpoint else None,
                            }
                        except ResourceNotFoundError:
                            logger.warning("ADR namespace '%s' not found.", adr_namespace_name)

                if adr_section:
                    adr_section["userReaderAssignments"] = self._get_user_reader_assignments(
                        adr_namespace_resource_id, adr_section["subscriptionId"],
                    )

                display.update_step("Analyzing", "Instance & ADR namespace", StepState.COMPLETE, "done")

            with display.step_scope("Analyzing", "Event Grid resources"):
                eg_ctx = self._discover_eg_context(obs_endpoint)
                if eg_ctx:
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
                        ts_name = get_live_data_topic_space_name(instance_resource_id)
                        ts_exists = False
                        ts_configured = False
                        topic_space_section: Dict = {"name": ts_name, "exists": False}
                        try:
                            ts_resource = self.eventgrid_mgmt_client.topic_spaces.get(
                                resource_group_name=eg_ctx.resource_group_name,
                                namespace_name=eg_ctx.namespace_name,
                                topic_space_name=ts_name,
                            )
                            ts_exists = True
                            ts_configured = ts_resource.get("properties", {}).get("topicTemplates") == [
                                LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=name)
                            ]
                            topic_space_section = {
                                "name": ts_name,
                                "topicTemplates": ts_resource.get("properties", {}).get("topicTemplates", []),
                                "exists": True,
                                "configured": ts_configured,
                            }
                        except ResourceNotFoundError:
                            pass

                        eg_all_exist = ts_exists and ts_configured
                        eg_section = {
                            "namespace": {
                                "name": eg_ctx.namespace_name,
                                "resourceGroup": eg_ctx.resource_group_name,
                                "subscriptionId": eg_ctx.subscription_id,
                                "mqttHostname": mqtt_hostname,
                            },
                            "topicSpace": topic_space_section,
                        }
                    except ResourceNotFoundError:
                        logger.warning("Event Grid namespace '%s' not found.", eg_ctx.namespace_name)
                    else:
                        eg_section["namespace"]["subscriberAssignments"] = self._get_subscriber_assignments(
                            eg_ctx, eg_ctx.resource_id,
                        )
                        topic_space_section["subscriberAssignments"] = (
                            self._get_subscriber_assignments(
                                eg_ctx, self._role_scope(eg_ctx, LiveDataRoleScope.TOPIC_SPACE, ts_name),
                            ) if ts_exists else []
                        )

                eg_detail = "done" if eg_section else ("not reachable" if eg_ctx else "skipped")
                display.update_step("Analyzing", "Event Grid resources", StepState.COMPLETE, eg_detail)

            with display.step_scope("Analyzing", "Instance dataflow resources"):
                profile_exists = False
                profile_configured = False
                try:
                    profile = self.iotops_mgmt_client.dataflow_profile.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
                    )
                    profile_exists = True
                    profile_configured = self._dataflow_profile_configured(profile)
                except ResourceNotFoundError:
                    pass

                ep_exists = False
                ep_configured = False
                try:
                    endpoint = self.iotops_mgmt_client.dataflow_endpoint.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_endpoint_name=LIVE_DATA_ENDPOINT_NAME,
                    )
                    ep_exists = True
                    if eg_section and eg_ctx:
                        authentication = self._get_live_data_endpoint_auth(outbound_identity)
                        if authentication is not None:
                            current_eg_ctx = eg_ctx._replace(
                                mqtt_hostname=eg_section["namespace"]["mqttHostname"],
                            )
                            ep_configured = self._eg_dataflow_endpoint_configured(
                                endpoint, current_eg_ctx, name, authentication,
                            )
                except ResourceNotFoundError:
                    pass

                aio_all_exist = profile_exists and profile_configured and ep_exists and ep_configured
                display.update_step("Analyzing", "Instance dataflow resources", StepState.COMPLETE, "done")

        instance_section = {
            "dataflowProfile": {
                "name": LIVE_DATA_PROFILE_NAME, "exists": profile_exists, "configured": profile_configured,
            },
            "dataflowEndpoint": {
                "name": LIVE_DATA_ENDPOINT_NAME, "exists": ep_exists, "configured": ep_configured,
            },
        }

        enabled = obs_endpoint_exists and eg_all_exist and aio_all_exist

        return {
            "enabled": enabled,
            "instance": instance_section,
            "eventGrid": eg_section,
            "deviceRegistryNamespace": adr_section,
        }

    def _get_user_reader_assignments(self, namespace_id: str, subscription_id: str) -> List[Dict]:
        manager = PermissionManager(
            **self._get_client_kwargs(subscription_id=subscription_id),
            credential_scopes=[CloudConfig(self.cmd).arm_endpoint_scope],
        )
        role_id = ROLE_DEF_FORMAT_STR.format(
            subscription_id=subscription_id, role_id=LIVE_DATA_USER_ROLE_ID,
        )
        return [
            {"principalId": assignment["principalId"], "assignmentId": assignment["assignmentId"]}
            for assignment in self._get_scoped_role_assignments(manager, namespace_id, role_id)
            if (assignment["principalType"] or "").lower() == PrincipalType.USER.value.lower()
        ]

    def _get_subscriber_assignments(self, eg_ctx: EgNamespaceContext, scope: str) -> List[Dict]:
        role_id = ROLE_DEF_FORMAT_STR.format(
            subscription_id=eg_ctx.subscription_id, role_id=EG_TOPICSPACES_SUBSCRIBER_ROLE_ID,
        )
        return self._get_scoped_role_assignments(self._permission_manager(eg_ctx), scope, role_id)

    @staticmethod
    def _get_scoped_role_assignments(manager: PermissionManager, scope: str, role_id: str) -> List[Dict]:
        assignments = []
        for assignment in manager.authz_client.role_assignments.list_for_scope(scope=scope, filter="atScope()"):
            properties = assignment.get("properties") or {}
            if (
                (properties.get("scope") or "").lower() == scope.lower()
                and (properties.get("roleDefinitionId") or "").lower() == role_id.lower()
            ):
                assignments.append({
                    "principalId": properties["principalId"],
                    "assignmentId": assignment["id"],
                    "principalType": properties.get("principalType"),
                })
        return assignments

    def _get_live_data_endpoint_auth(self, outbound_identity: Dict) -> Optional[Dict]:
        identity_type = (outbound_identity.get("type") or "").lower()
        if identity_type == "systemassigned":
            return self._build_eg_endpoint_auth()
        if identity_type == "userassigned" and outbound_identity.get("userAssignedIdentity"):
            resource_id = outbound_identity["userAssignedIdentity"]
            try:
                mi_resource = self._get_user_assigned_mi(resource_id)
            except ResourceNotFoundError:
                logger.warning(
                    "Live Data outbound identity '%s' not found; endpoint configuration cannot be verified.",
                    resource_id,
                )
                return None
            return self._build_eg_endpoint_auth(mi_resource)
        logger.warning(
            "Live Data outbound identity is missing or unsupported; endpoint configuration cannot be verified."
        )
        return None

    def disable(
        self,
        name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Disable Live Data for an IoT Operations instance.

        Tears down the dedicated dataflow profile, EG dataflow endpoint, and topic space,
        then removes this instance's observability endpoint entry from the Device Registry
        namespace last so an interrupted disable can be safely re-run. Namespace-scoped
        role assignments are preserved; topic-space-scoped roles are removed together with
        the topic space.
        """
        analyzing_cats = {"Analyzing": ["Instance & ADR namespace", "Resource probing"]}
        with WorkflowDisplay(
            "Live Data Disablement", analyzing_cats, no_progress=no_progress,
        ) as display:
            with display.step_scope("Analyzing", "Instance & ADR namespace"):
                instance = self.iotops_mgmt_client.instance.get(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                )
                instance_resource_id: str = instance["id"]
                custom_location_id: str = instance.get("extendedLocation", {}).get("name", "")
                ts_name = get_live_data_topic_space_name(instance_resource_id)

                adr_namespace_resource_id = (
                    instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
                )
                adr_namespace = {}
                adr_resource_group = ""
                adr_namespace_name = ""
                existing_endpoints = {}
                if not adr_namespace_resource_id:
                    logger.warning(
                        "Instance '%s' has no ADR namespace reference. Live Data may not have been enabled.",
                        name,
                    )
                else:
                    parsed_adr = parse_resource_id_dict(adr_namespace_resource_id)
                    adr_resource_group = parsed_adr.get("resource_group", "")
                    adr_namespace_name = parsed_adr.get("name", "")
                    try:
                        _, adr_namespace = self._resolve_adr_namespace(instance)
                    except ResourceNotFoundError:
                        logger.warning("ADR namespace '%s' not found. Continuing instance cleanup.", adr_namespace_name)
                    else:
                        existing_endpoints = (
                            adr_namespace.get("properties", {}).get("observability", {}).get("endpoints", {})
                        )
                endpoint_key = _resolve_observability_endpoint_key(existing_endpoints, custom_location_id)
                obs_endpoint = existing_endpoints.get(endpoint_key) if endpoint_key is not None else None
                eg_ctx = self._discover_eg_context(obs_endpoint)
                if not eg_ctx:
                    logger.warning(
                        "Cannot locate Event Grid topic space '%s' without an observability endpoint resourceId. "
                        "Continuing instance cleanup; remove the topic space manually if it exists.",
                        ts_name,
                    )
                display.update_step(
                    "Analyzing", "Instance & ADR namespace",
                    StepState.COMPLETE if adr_namespace else StepState.SKIPPED,
                    "found" if adr_namespace else "unavailable; continuing cleanup",
                )

            with display.step_scope("Analyzing", "Resource probing"):
                profile_exists = True
                try:
                    self.iotops_mgmt_client.dataflow_profile.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
                    )
                except ResourceNotFoundError:
                    profile_exists = False

                ep_exists = True
                try:
                    self.iotops_mgmt_client.dataflow_endpoint.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_endpoint_name=LIVE_DATA_ENDPOINT_NAME,
                    )
                except ResourceNotFoundError:
                    ep_exists = False

                ts_exists = False
                if eg_ctx:
                    try:
                        self.eventgrid_mgmt_client.topic_spaces.get(
                            resource_group_name=eg_ctx.resource_group_name,
                            namespace_name=eg_ctx.namespace_name,
                            topic_space_name=ts_name,
                        )
                        ts_exists = True
                    except ResourceNotFoundError:
                        pass
                display.update_step("Analyzing", "Resource probing", StepState.COMPLETE, "done")

        has_endpoint_entry = endpoint_key is not None
        if not confirm_yes:
            self._log_disable_summary(
                instance_name=name,
                adr_namespace_name=adr_namespace_name,
                has_endpoint_entry=has_endpoint_entry,
                profile_exists=profile_exists,
                ep_exists=ep_exists,
                ts_exists=ts_exists,
                eg_ctx=eg_ctx,
            )

        if not should_continue_prompt(confirm_yes=confirm_yes):
            return

        self._execute_disable_teardown(
            name=name,
            resource_group_name=resource_group_name,
            adr_namespace=adr_namespace,
            adr_resource_group=adr_resource_group,
            adr_namespace_name=adr_namespace_name,
            custom_location_id=custom_location_id,
            existing_endpoints=existing_endpoints,
            profile_exists=profile_exists,
            ep_exists=ep_exists,
            eg_ctx=eg_ctx,
            ts_name=ts_name,
            ts_exists=ts_exists,
            no_progress=no_progress,
            **kwargs,
        )

    def _execute_disable_teardown(
        self,
        name: str,
        resource_group_name: str,
        adr_namespace: Dict,
        adr_resource_group: str,
        adr_namespace_name: str,
        custom_location_id: str,
        existing_endpoints: Dict,
        profile_exists: bool,
        ep_exists: bool,
        eg_ctx: Optional["EgNamespaceContext"],
        ts_name: str,
        ts_exists: bool,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Execute the teardown of disable(): delete resources first, then remove the endpoint entry last."""
        eg_ns_label = f"Event Grid Namespace ({eg_ctx.namespace_name})" if eg_ctx else "Event Grid Namespace"
        cat_adr = f"Device Registry Namespace ({adr_namespace_name})"
        cat_aio = f"IoT Operations Instance ({name})"

        teardown_cats: Dict[str, List[str]] = {
            cat_adr: ["Observability endpoint"],
            cat_aio: ["Dataflow profile", "EG dataflow endpoint"],
            eg_ns_label: ["Topic space"],
        }
        with WorkflowDisplay(
            "Live Data Disablement", teardown_cats, transient=False, no_progress=no_progress,
        ) as display:
            if profile_exists:
                with display.step_scope(cat_aio, "Dataflow profile"):
                    graceful_delete(
                        lambda: self.iotops_mgmt_client.dataflow_profile.begin_delete(
                            resource_group_name=resource_group_name,
                            instance_name=name,
                            dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
                        ),
                        resource_desc=f"dataflow profile '{LIVE_DATA_PROFILE_NAME}'",
                        **kwargs,
                    )
                    display.update_step(cat_aio, "Dataflow profile", StepState.COMPLETE, "removed")
            else:
                display.update_step(cat_aio, "Dataflow profile", StepState.SKIPPED, "not found")

            if ep_exists:
                with display.step_scope(cat_aio, "EG dataflow endpoint"):
                    graceful_delete(
                        lambda: self.iotops_mgmt_client.dataflow_endpoint.begin_delete(
                            resource_group_name=resource_group_name,
                            instance_name=name,
                            dataflow_endpoint_name=LIVE_DATA_ENDPOINT_NAME,
                        ),
                        resource_desc=f"dataflow endpoint '{LIVE_DATA_ENDPOINT_NAME}'",
                        **kwargs,
                    )
                    display.update_step(cat_aio, "EG dataflow endpoint", StepState.COMPLETE, "removed")
            else:
                display.update_step(cat_aio, "EG dataflow endpoint", StepState.SKIPPED, "not found")

            if eg_ctx and ts_exists:
                with display.step_scope(eg_ns_label, "Topic space"):
                    graceful_delete(
                        lambda: self.eventgrid_mgmt_client.topic_spaces.begin_delete(
                            resource_group_name=eg_ctx.resource_group_name,
                            namespace_name=eg_ctx.namespace_name,
                            topic_space_name=ts_name,
                        ),
                        resource_desc=f"topic space '{ts_name}'",
                        **kwargs,
                    )
                    display.update_step(eg_ns_label, "Topic space", StepState.COMPLETE, "removed")
            else:
                display.update_step(eg_ns_label, "Topic space", StepState.SKIPPED, "not found")

            # Remove the ADR endpoint entry last: it holds the EG resourceId used to discover
            # the EG namespace, so keeping it until the end keeps an interrupted disable re-run-safe.
            if _resolve_observability_endpoint_key(existing_endpoints, custom_location_id) is not None:
                with display.step_scope(cat_adr, "Observability endpoint"):
                    put_payload = _build_adr_observability_put_payload(adr_namespace, custom_location_id)
                    poller = self.registry_mgmt_client.namespaces.begin_create_or_replace(
                        resource_group_name=adr_resource_group,
                        namespace_name=adr_namespace_name,
                        resource=put_payload,
                    )
                    wait_for_terminal_state(poller, **kwargs)
                    logger.info(
                        "Removed observability endpoint entry for custom location from ADR namespace '%s'.",
                        adr_namespace_name,
                    )
                    display.update_step(cat_adr, "Observability endpoint", StepState.COMPLETE, "removed")
            else:
                display.update_step(cat_adr, "Observability endpoint", StepState.SKIPPED, "not found")

    def _log_disable_summary(
        self,
        instance_name: str,
        adr_namespace_name: str,
        has_endpoint_entry: bool,
        profile_exists: bool,
        ep_exists: bool,
        ts_exists: bool,
        eg_ctx: Optional["EgNamespaceContext"],
    ) -> None:
        """Render a Rich summary of resources that will be removed by disable()."""
        aio_items: List[str] = []
        if profile_exists:
            aio_items.append("Dataflow profile")
        if ep_exists:
            aio_items.append("EG dataflow endpoint")

        adr_items: List[str] = []
        if has_endpoint_entry:
            adr_items.append("Observability endpoint")

        eg_items: List[str] = []
        if ts_exists:
            eg_items.append("Topic space")

        eg_ns_label = f"Event Grid Namespace ({eg_ctx.namespace_name})" if eg_ctx else "Event Grid Namespace"
        sections: Dict[str, List[str]] = {
            f"IoT Operations Instance ({instance_name})": aio_items,
            f"Device Registry Namespace ({adr_namespace_name})": adr_items,
            eg_ns_label: eg_items,
        }
        total = sum(len(items) for items in sections.values())
        render_summary(
            title=f"Resources to remove ({total})",
            sections=sections,
            footer="Note: Namespace-scoped role assignments are NOT removed.",
        )

    def _setup_topic_space(
        self,
        eg_ctx: EgNamespaceContext,
        instance_name: str,
        instance_resource_id: str,
        **kwargs,
    ) -> Dict:
        """Reconcile the Live Data-owned topic templates, preserving other fields."""
        topic_space_name = get_live_data_topic_space_name(instance_resource_id)
        topic_templates = [LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=instance_name)]

        existing = None
        try:
            existing = self.eventgrid_mgmt_client.topic_spaces.get(
                resource_group_name=eg_ctx.resource_group_name,
                namespace_name=eg_ctx.namespace_name,
                topic_space_name=topic_space_name,
            )
            if existing.get("properties", {}).get("topicTemplates") == topic_templates:
                return {"name": topic_space_name, "topicTemplates": topic_templates, "exists": True}
        except ResourceNotFoundError:
            pass

        topic_space_payload = {
            "properties": {
                "description": f"Live Data topic space for IoT Operations instance '{instance_name}'.",
                "topicTemplates": topic_templates,
            }
        }
        if existing is not None:
            topic_space_payload["properties"] = dict(existing.get("properties", {}))
            topic_space_payload["properties"].pop("provisioningState", None)
            topic_space_payload["properties"]["topicTemplates"] = topic_templates
        poller = self.eventgrid_mgmt_client.topic_spaces.begin_create_or_update(
            resource_group_name=eg_ctx.resource_group_name,
            namespace_name=eg_ctx.namespace_name,
            topic_space_name=topic_space_name,
            topic_space_info=topic_space_payload,
        )
        wait_for_terminal_state(poller, **kwargs)
        logger.info("Reconciled topic space '%s' on namespace '%s'.", topic_space_name, eg_ctx.namespace_name)
        return {
            "name": topic_space_name, "topicTemplates": topic_templates,
            "exists": existing is not None, "updated": existing is not None,
        }

    @staticmethod
    def _dataflow_profile_configured(profile: Dict) -> bool:
        properties = profile.get("properties", {})
        diagnostics = properties.get("diagnostics") or {}
        logs = diagnostics.get("logs") or {}
        return (
            properties.get("instanceCount") == 1
            and logs.get("level") == "info"
        )

    def _setup_dataflow_profile(
        self,
        instance_name: str,
        resource_group_name: str,
        extended_location: Dict,
        **kwargs,
    ) -> Dict:
        """Reconcile owned profile settings without replacing unrelated configuration."""
        existing = None
        try:
            existing = self.iotops_mgmt_client.dataflow_profile.get(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
            )
            if self._dataflow_profile_configured(existing):
                return {"name": LIVE_DATA_PROFILE_NAME, "exists": True}
        except ResourceNotFoundError:
            pass

        resource = {
            "extendedLocation": extended_location,
            "properties": {
                "diagnostics": {"logs": {"level": "info"}},
                "instanceCount": 1,
            },
        }
        if existing is not None:
            properties = dict(existing.get("properties", {}))
            properties.pop("provisioningState", None)
            diagnostics = dict(properties.get("diagnostics") or {})
            logs = dict(diagnostics.get("logs") or {})
            logs["level"] = "info"
            diagnostics["logs"] = logs
            properties.update(instanceCount=1, diagnostics=diagnostics)
            resource["properties"] = properties
            if "tags" in existing:
                resource["tags"] = existing["tags"]
        poller = self.iotops_mgmt_client.dataflow_profile.begin_create_or_update(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
            resource=resource,
        )
        wait_for_terminal_state(poller, **kwargs)
        logger.info("Reconciled dataflow profile '%s' on instance '%s'.", LIVE_DATA_PROFILE_NAME, instance_name)
        return {"name": LIVE_DATA_PROFILE_NAME, "exists": existing is not None, "updated": existing is not None}

    def _setup_adr_observability(
        self,
        instance: Dict,
        eg_ctx: EgNamespaceContext,
        custom_location_id: str,
        mi_resource: Optional[Dict],
        ra_scope: LiveDataRoleScope,
        topic_space_name: str,
        adr_role_ids: Optional[List[str]],
        skip_role_assignments: bool,
        **kwargs,
    ) -> Dict:
        """Configure outboundIdentity and the observability endpoint on the ADR namespace.

        When the outbound identity is a new system-assigned identity, staged enablement is
        used: the identity is enabled first (no endpoint entry), the Subscriber role is
        granted to its principal, then the endpoint entry is written. When the identity
        already exists (or a UAMI is supplied and pre-authorized), a single write is used.
        """
        parsed_adr, adr_namespace = self._resolve_adr_namespace(instance)
        adr_resource_group = parsed_adr.get("resource_group", "")
        adr_namespace_name = parsed_adr.get("name", "")
        adr_subscription_id = parsed_adr.get("subscription", "")
        properties = adr_namespace.get("properties", {})
        self._validate_shared_adr_identity(adr_namespace, custom_location_id, mi_resource)

        desired_endpoint = {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE,
            "address": eg_ctx.mqtt_hostname,
            "scopeId": instance.get("name", ""),
            "resourceId": eg_ctx.resource_id,
        }
        outbound_identity = self._build_outbound_identity(mi_resource)

        observability = properties.get("observability", {})
        observability_already_enabled = observability.get("enabled") is True
        existing_endpoints = observability.get("endpoints", {})
        endpoint_key = _resolve_observability_endpoint_key(existing_endpoints, custom_location_id)
        current_endpoint = existing_endpoints.get(endpoint_key) if endpoint_key is not None else None
        endpoint_already_configured = current_endpoint == desired_endpoint

        outbound_identity_already_configured = properties.get("outboundIdentity") == outbound_identity

        current_identity = adr_namespace.get("identity", {})
        current_identity_types = {
            identity_type.strip().lower()
            for identity_type in (current_identity.get("type") or "").split(",")
        }
        sami_already_enabled = "systemassigned" in current_identity_types

        use_sami = mi_resource is None
        if use_sami:
            identity_already_configured = sami_already_enabled
        else:
            current_uamis = current_identity.get("userAssignedIdentities") or {}
            identity_already_configured = (
                "userassigned" in current_identity_types
                and any(resource_id.lower() == mi_resource["id"].lower() for resource_id in current_uamis)
            )
        needs_identity_enable = not identity_already_configured

        base_payload: Dict = {"properties": {"outboundIdentity": outbound_identity}}
        if needs_identity_enable:
            if use_sami:
                base_payload["identity"] = {"type": "SystemAssigned"}
            else:
                updated_uamis = dict(current_identity.get("userAssignedIdentities") or {})
                updated_uamis[mi_resource["id"]] = {}
                identity_type = (
                    "SystemAssigned, UserAssigned"
                    if sami_already_enabled
                    else "UserAssigned"
                )
                base_payload["identity"] = {
                    "type": identity_type,
                    "userAssignedIdentities": updated_uamis,
                }

        if (
            observability_already_enabled
            and endpoint_already_configured
            and outbound_identity_already_configured
            and identity_already_configured
        ):
            principal_id = self._resolve_outbound_principal(mi_resource, current_identity)
            logger.info(
                "ADR namespace '%s' already has outbound identity and observability endpoint configured.",
                adr_namespace_name,
            )
            return {
                "name": adr_namespace_name,
                "resourceGroup": adr_resource_group,
                "subscriptionId": adr_subscription_id,
                "outboundIdentity": outbound_identity,
                "identity": {"principalId": principal_id},
                "observabilityEndpoint": desired_endpoint,
                "identity_exists": True,
                "endpoint_exists": True,
            }

        # Staged write for a new system-assigned identity: enable identity + outboundIdentity
        # first (no endpoint), grant Subscriber, then add the endpoint entry.
        staged = use_sami and needs_identity_enable and not skip_role_assignments
        if staged:
            identity_payload = dict(base_payload)
            updated_namespace = self._patch_namespace(
                adr_resource_group, adr_namespace_name, identity_payload, **kwargs
            )
            principal_id = updated_namespace.get("identity", {}).get("principalId", "")
            if not principal_id:
                raise ValidationError(
                    f"ADR namespace '{adr_namespace_name}' was updated with a SystemAssigned identity "
                    f"but no principalId was returned. The operation may still be propagating."
                )
            self._assign_subscriber_role(
                eg_ctx=eg_ctx,
                ra_scope=ra_scope,
                topic_space_name=topic_space_name,
                principal_id=principal_id,
                adr_role_ids=adr_role_ids,
            )
            merged_endpoints = dict(existing_endpoints)
            merged_endpoints[endpoint_key if endpoint_key is not None else custom_location_id] = desired_endpoint
            endpoint_payload = {
                "properties": {
                    "observability": {
                        "enabled": True,
                        "endpoints": merged_endpoints,
                    }
                }
            }
            self._patch_namespace(adr_resource_group, adr_namespace_name, endpoint_payload, **kwargs)
        else:
            merged_endpoints = dict(existing_endpoints)
            merged_endpoints[endpoint_key if endpoint_key is not None else custom_location_id] = desired_endpoint
            payload = dict(base_payload)
            payload["properties"]["observability"] = {
                "enabled": True,
                "endpoints": merged_endpoints,
            }
            updated_namespace = self._patch_namespace(
                adr_resource_group, adr_namespace_name, payload, **kwargs
            )
            principal_id = self._resolve_outbound_principal(
                mi_resource, updated_namespace.get("identity", {})
            )

        return {
            "name": adr_namespace_name,
            "resourceGroup": adr_resource_group,
            "subscriptionId": adr_subscription_id,
            "outboundIdentity": outbound_identity,
            "identity": {"principalId": principal_id},
            "observabilityEndpoint": desired_endpoint,
            "identity_exists": identity_already_configured,
            "endpoint_exists": endpoint_already_configured,
        }

    def _patch_namespace(self, resource_group_name: str, namespace_name: str, payload: Dict, **kwargs) -> Dict:
        poller = self.registry_mgmt_client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=payload,
        )
        return wait_for_terminal_state(poller, **kwargs)

    def _build_outbound_identity(self, mi_resource: Optional[Dict]) -> Dict:
        """Build the ADR namespace outboundIdentity block."""
        if mi_resource:
            return {"type": "UserAssigned", "userAssignedIdentity": mi_resource["id"]}
        return {"type": "SystemAssigned"}

    def _validate_shared_adr_identity(
        self, namespace: Dict, custom_location_id: str, mi_resource: Optional[Dict],
    ) -> None:
        properties = namespace.get("properties") or {}
        observability = properties.get("observability") or {}
        endpoints = observability.get("endpoints") or {}
        endpoint_key = _resolve_observability_endpoint_key(endpoints, custom_location_id)
        sibling_endpoints = any(key != endpoint_key for key in endpoints)
        management_endpoints = (properties.get("management") or {}).get("endpoints")
        if not sibling_endpoints and not management_endpoints:
            return
        current = properties.get("outboundIdentity") or {}
        desired = self._build_outbound_identity(mi_resource)
        if (
            (current.get("type") or "").lower() == desired["type"].lower()
            and (current.get("userAssignedIdentity") or "").lower()
            == desired.get("userAssignedIdentity", "").lower()
        ):
            return
        raise ValidationError(
            "Cannot change the ADR namespace outbound identity while endpoints for other instances or features exist. "
            "Reuse the existing outbound identity; changing this shared identity requires a coordinated migration."
        )

    def _resolve_outbound_principal(self, mi_resource: Optional[Dict], identity: Dict) -> str:
        """Resolve the principal ID of the ADR namespace outbound identity."""
        if mi_resource:
            principal_id = mi_resource.get("properties", {}).get("principalId", "")
        else:
            principal_id = identity.get("principalId", "")
        if not principal_id:
            raise ValidationError(
                "Could not resolve the outbound identity principal ID for the ADR namespace. "
                "The identity may still be provisioning."
            )
        return principal_id

    def _role_scope(self, eg_ctx: EgNamespaceContext, ra_scope: LiveDataRoleScope, topic_space_name: str) -> str:
        """Resolve the role-assignment scope resource ID for the selected --ra-scope."""
        if ra_scope == LiveDataRoleScope.TOPIC_SPACE:
            return f"{eg_ctx.resource_id}/topicSpaces/{topic_space_name}"
        return eg_ctx.resource_id

    def _assign_subscriber_role(
        self,
        eg_ctx: EgNamespaceContext,
        ra_scope: LiveDataRoleScope,
        topic_space_name: str,
        principal_id: str,
        adr_role_ids: Optional[List[str]],
    ) -> None:
        """Grant the ADR namespace identity the Subscriber role at the selected scope."""
        role_ids = adr_role_ids or [EG_TOPICSPACES_SUBSCRIBER_ROLE_ID]
        scope = self._role_scope(eg_ctx, ra_scope, topic_space_name)
        manager = self._permission_manager(eg_ctx)
        try:
            for role_id in role_ids:
                role_def_id = ROLE_DEF_FORMAT_STR.format(
                    subscription_id=eg_ctx.subscription_id, role_id=role_id
                )
                manager.apply_role_assignment(
                    scope=scope,
                    principal_id=principal_id,
                    role_def_id=role_def_id,
                    principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
                )
        except HttpResponseError as e:
            raise ValidationError(
                f"Failed to assign Subscriber role for principal '{principal_id}' "
                f"on Event Grid namespace '{eg_ctx.namespace_name}'.\n"
                f"Error: {e.message}\n"
                f"  Scope: {scope}\n  Principal ID: {principal_id}\n  Role IDs: {', '.join(role_ids)}"
            )

    def _setup_role_assignments(
        self,
        eg_ctx: EgNamespaceContext,
        ra_scope: LiveDataRoleScope,
        topic_space_name: str,
        publisher_principal_id: str,
        subscriber_principal_id: str,
        adr_role_ids: Optional[List[str]] = None,
        ops_role_ids: Optional[List[str]] = None,
    ) -> Dict:
        """Assign Publisher (instance identity) and Subscriber (ADR namespace identity) roles.

        Idempotent — existing assignments are skipped. Scope is the EG namespace
        (--ra-scope namespace, default) or the topic-space resource (--ra-scope topic-space).
        """
        resolved_ops_roles = ops_role_ids or [EG_TOPICSPACES_PUBLISHER_ROLE_ID]
        resolved_adr_roles = adr_role_ids or [EG_TOPICSPACES_SUBSCRIBER_ROLE_ID]
        scope = self._role_scope(eg_ctx, ra_scope, topic_space_name)
        manager = self._permission_manager(eg_ctx)

        assignments = [
            ("instance", publisher_principal_id, resolved_ops_roles),
            ("adrNamespace", subscriber_principal_id, resolved_adr_roles),
        ]
        result: Dict = {}
        for result_key, principal_id, role_ids in assignments:
            try:
                for role_id in role_ids:
                    role_def_id = ROLE_DEF_FORMAT_STR.format(
                        subscription_id=eg_ctx.subscription_id, role_id=role_id
                    )
                    manager.apply_role_assignment(
                        scope=scope,
                        principal_id=principal_id,
                        role_def_id=role_def_id,
                        principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
                    )
            except HttpResponseError as e:
                raise ValidationError(
                    f"Failed to assign role(s) for principal '{principal_id}' "
                    f"on Event Grid namespace '{eg_ctx.namespace_name}'.\n"
                    f"Error: {e.message}\n"
                    f"  Scope: {scope}\n  Principal ID: {principal_id}\n  Role IDs: {', '.join(role_ids)}"
                )
            result[result_key] = {"principalId": principal_id, "roles": list(role_ids)}
        return result
