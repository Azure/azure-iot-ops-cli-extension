# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Dict, List, Optional

from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
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
    LiveDataRoleScope,
)
from .eg_provider_base import EgNamespaceContext, EventGridProviderBase, graceful_delete
from .permissions import ROLE_DEF_FORMAT_STR, PermissionManager, PrincipalType

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )
    from ...vendor.clients.eventgridmgmt import EventGridManagementClient

logger = get_logger(__name__)
console = Console()


def get_live_data_topic_space_name(instance_resource_id: str) -> str:
    """Build the deterministic topic space name: live-data-ts-{hash8}.

    hash8 = first 8 chars of a URL-safe hash of the instance ARM resource ID, so the
    shared Event Grid namespace can host topic spaces for multiple instances.
    """
    hash8 = url_safe_hash_phrase(instance_resource_id)[:8]
    return f"{LIVE_DATA_TOPICSPACE_PREFIX}-{hash8}"


def _build_adr_observability_put_payload(adr_namespace: Dict, custom_location_id: str) -> Dict:
    """Build an ADR namespace PUT payload with one observability endpoint entry removed.

    ARM PATCH deep-merges dicts (omitting a key preserves it) and the ADR API rejects
    null endpoint values, so a full PUT replaces the resource. Preserves identity, tags,
    outboundIdentity, management, and messaging from the original namespace.
    """
    properties = adr_namespace.get("properties", {})
    observability = properties.get("observability", {})
    existing_endpoints = observability.get("endpoints", {})
    updated_endpoints = {k: v for k, v in existing_endpoints.items() if k != custom_location_id}

    # Preserve any sibling keys under observability since this is a full PUT.
    updated_observability = dict(observability)
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
        self.iotops_mgmt_client = get_iotops_mgmt_client(**self._get_client_kwargs())
        # Live Data requires ADR observability fields from the preview API version.
        self.registry_mgmt_client: "MicrosoftDeviceRegistryManagementService" = get_registry_mgmt_client(
            api_version=LIVE_DATA_ADR_API_VERSION,
            **self._get_client_kwargs(),
        )
        # May be replaced with a cross-subscription client by _validate_eg_namespace.
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
        ra_scope: Optional[str] = None,
        adr_role_ids: Optional[List[str]] = None,
        ops_role_ids: Optional[List[str]] = None,
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
                instance_resource_id: str = instance["id"]
                extended_location: Dict = instance["extendedLocation"]
                custom_location_id: str = extended_location["name"]
                display.update_step("Analyzing", "Instance resolution", StepState.COMPLETE, "done")

            with display.step_scope("Analyzing", "EG namespace validation"):
                eg_ctx = self._validate_eg_namespace(eg_resource_id)
                display.update_step("Analyzing", "EG namespace validation", StepState.COMPLETE, "done")

            with display.step_scope("Analyzing", "UAMI resolution"):
                mi_resource = self._resolve_user_assigned_mi(mi_user_assigned) if mi_user_assigned else None
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
            config_cats[cat_roles] = ["Publisher (instance)", "Subscriber (namespace)"]

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
                detail = "exists" if topic_space_result.get("exists") else "created"
                state = StepState.SKIPPED if topic_space_result.get("exists") else StepState.COMPLETE
                display.update_step(cat_eg, "Topic space", state, detail)

            with display.step_scope(cat_aio, "Dataflow profile"):
                profile_result = self._setup_dataflow_profile(
                    instance_name=name,
                    resource_group_name=resource_group_name,
                    extended_location=extended_location,
                    **kwargs,
                )
                detail = "exists" if profile_result.get("exists") else "created"
                state = StepState.SKIPPED if profile_result.get("exists") else StepState.COMPLETE
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

    def show(
        self,
        name: str,
        resource_group_name: str,
        no_progress: Optional[bool] = None,
        **kwargs,
    ) -> Dict:
        """Show Live Data configuration for an IoT Operations instance.

        Live Data state for this instance is derived from the presence of this instance's
        observability.endpoints[<customLocationId>] entry on the ADR namespace. The
        namespace-level observability.enabled flag is not managed or interpreted here.
        """
        analyzing_cats = {
            "Analyzing": ["Instance & ADR namespace", "Event Grid resources", "Instance dataflow resources"],
        }

        adr_section: Optional[Dict] = None
        eg_section: Optional[Dict] = None
        obs_endpoint: Optional[Dict] = None
        obs_endpoint_exists = False
        eg_all_exist = False

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
                                .get("observability", {})
                                .get("endpoints", {})
                            )
                            obs_endpoint = existing_endpoints.get(custom_location_id) if custom_location_id else None
                            obs_endpoint_exists = bool(obs_endpoint)

                            adr_section = {
                                "name": adr_namespace_name,
                                "resourceGroup": adr_resource_group,
                                "subscriptionId": adr_subscription_id,
                                "outboundIdentity": adr_namespace.get("properties", {}).get("outboundIdentity"),
                                "observabilityEndpoint": {
                                    "endpointType": obs_endpoint.get("endpointType", ""),
                                    "address": obs_endpoint.get("address", ""),
                                    "scopeId": obs_endpoint.get("scopeId", ""),
                                } if obs_endpoint else None,
                            }
                        except ResourceNotFoundError:
                            logger.warning("ADR namespace '%s' not found.", adr_namespace_name)

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
                        topic_space_section: Dict = {"name": ts_name, "exists": False}
                        try:
                            ts_resource = self.eventgrid_mgmt_client.topic_spaces.get(
                                resource_group_name=eg_ctx.resource_group_name,
                                namespace_name=eg_ctx.namespace_name,
                                topic_space_name=ts_name,
                            )
                            ts_exists = True
                            topic_space_section = {
                                "name": ts_name,
                                "topicTemplates": ts_resource.get("properties", {}).get("topicTemplates", []),
                                "exists": True,
                            }
                        except ResourceNotFoundError:
                            pass

                        eg_all_exist = ts_exists
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

                eg_detail = "done" if eg_section else ("not reachable" if eg_ctx else "skipped")
                display.update_step("Analyzing", "Event Grid resources", StepState.COMPLETE, eg_detail)

            with display.step_scope("Analyzing", "Instance dataflow resources"):
                profile_exists = False
                try:
                    self.iotops_mgmt_client.dataflow_profile.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
                    )
                    profile_exists = True
                except ResourceNotFoundError:
                    pass

                ep_exists = False
                try:
                    self.iotops_mgmt_client.dataflow_endpoint.get(
                        resource_group_name=resource_group_name,
                        instance_name=name,
                        dataflow_endpoint_name=LIVE_DATA_ENDPOINT_NAME,
                    )
                    ep_exists = True
                except ResourceNotFoundError:
                    pass

                aio_all_exist = profile_exists and ep_exists
                display.update_step("Analyzing", "Instance dataflow resources", StepState.COMPLETE, "done")

        instance_section = {
            "dataflowProfile": {"name": LIVE_DATA_PROFILE_NAME, "exists": profile_exists},
            "dataflowEndpoint": {"name": LIVE_DATA_ENDPOINT_NAME, "exists": ep_exists},
        }

        enabled = obs_endpoint_exists and eg_all_exist and aio_all_exist

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
                if not adr_namespace_resource_id:
                    logger.warning(
                        "Instance '%s' has no ADR namespace reference. Live Data may not have been enabled.",
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
                        "ADR namespace '%s' not found. Live Data may not have been enabled.",
                        adr_namespace_name,
                    )
                    display.update_step("Analyzing", "Instance & ADR namespace", StepState.SKIPPED, "not found")
                    return

                existing_endpoints = (
                    adr_namespace.get("properties", {}).get("observability", {}).get("endpoints", {})
                )
                obs_endpoint = existing_endpoints.get(custom_location_id)
                eg_ctx = self._discover_eg_context(obs_endpoint)
                display.update_step("Analyzing", "Instance & ADR namespace", StepState.COMPLETE, "found")

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

        has_endpoint_entry = custom_location_id in existing_endpoints
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
            if custom_location_id in existing_endpoints:
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
        """Create or confirm the Live Data topic space on the EG namespace."""
        topic_space_name = get_live_data_topic_space_name(instance_resource_id)
        topic_templates = [LIVE_DATA_TOPIC_TEMPLATE.format(scope_id=instance_name)]

        try:
            self.eventgrid_mgmt_client.topic_spaces.get(
                resource_group_name=eg_ctx.resource_group_name,
                namespace_name=eg_ctx.namespace_name,
                topic_space_name=topic_space_name,
            )
            logger.info(
                "Topic space '%s' already exists on namespace '%s'.", topic_space_name, eg_ctx.namespace_name
            )
            return {"name": topic_space_name, "topicTemplates": topic_templates, "exists": True}
        except ResourceNotFoundError:
            pass

        topic_space_payload = {
            "properties": {
                "description": f"Live Data topic space for IoT Operations instance '{instance_name}'.",
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
        return {"name": topic_space_name, "topicTemplates": topic_templates, "exists": False}

    def _setup_dataflow_profile(
        self,
        instance_name: str,
        resource_group_name: str,
        extended_location: Dict,
        **kwargs,
    ) -> Dict:
        """Create or confirm the dedicated Live Data dataflow profile (instanceCount=1)."""
        try:
            self.iotops_mgmt_client.dataflow_profile.get(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
            )
            logger.info(
                "Dataflow profile '%s' already exists on instance '%s'.", LIVE_DATA_PROFILE_NAME, instance_name
            )
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
        poller = self.iotops_mgmt_client.dataflow_profile.begin_create_or_update(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=LIVE_DATA_PROFILE_NAME,
            resource=resource,
        )
        wait_for_terminal_state(poller, **kwargs)
        logger.info("Created dataflow profile '%s' on instance '%s'.", LIVE_DATA_PROFILE_NAME, instance_name)
        return {"name": LIVE_DATA_PROFILE_NAME, "exists": False}

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
        adr_namespace_resource_id = instance.get("properties", {}).get("adrNamespaceRef", {}).get("resourceId")
        if not adr_namespace_resource_id:
            raise ValidationError(
                "Instance does not have an ADR namespace reference (adrNamespaceRef.resourceId). "
                "This is required for Live Data. Ensure the instance was deployed with an ADR namespace."
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

        adr_namespace = self.registry_mgmt_client.namespaces.get(
            resource_group_name=adr_resource_group,
            namespace_name=adr_namespace_name,
        )
        properties = adr_namespace.get("properties", {})

        desired_endpoint = {
            "endpointType": LIVE_DATA_ADR_ENDPOINT_TYPE,
            "address": eg_ctx.mqtt_hostname,
            "scopeId": instance.get("name", ""),
            "resourceId": eg_ctx.resource_id,
        }
        outbound_identity = self._build_outbound_identity(mi_resource)

        existing_endpoints = properties.get("observability", {}).get("endpoints", {})
        current_endpoint = existing_endpoints.get(custom_location_id)
        endpoint_already_configured = current_endpoint == desired_endpoint

        outbound_identity_already_configured = properties.get("outboundIdentity") == outbound_identity

        current_identity = adr_namespace.get("identity", {})
        current_identity_type = (current_identity.get("type") or "").lower()
        sami_already_enabled = current_identity_type == "systemassigned"

        use_sami = mi_resource is None
        needs_identity_enable = use_sami and not sami_already_enabled

        base_payload: Dict = {"properties": {"outboundIdentity": outbound_identity}}
        if needs_identity_enable:
            base_payload["identity"] = {"type": "SystemAssigned"}

        if endpoint_already_configured and outbound_identity_already_configured and (not needs_identity_enable):
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
        staged = needs_identity_enable and not skip_role_assignments
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
            merged_endpoints[custom_location_id] = desired_endpoint
            endpoint_payload = {"properties": {"observability": {"endpoints": merged_endpoints}}}
            self._patch_namespace(adr_resource_group, adr_namespace_name, endpoint_payload, **kwargs)
        else:
            merged_endpoints = dict(existing_endpoints)
            merged_endpoints[custom_location_id] = desired_endpoint
            payload = dict(base_payload)
            payload["properties"]["observability"] = {"endpoints": merged_endpoints}
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
            "identity_exists": sami_already_enabled if use_sami else True,
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
