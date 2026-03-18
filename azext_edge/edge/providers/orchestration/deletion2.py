# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""ARM-primary deletion module for IoT Operations.

Replaces ARG-dependent resource discovery with cascading instance delete plus
targeted ARM GETs/lists. A single optional ARG sweep catches user-created
DeviceRegistry and SecretSync resources on the custom location.
"""

from collections import OrderedDict
from sys import maxsize
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from azure.cli.core.azclierror import ArgumentUsageError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import Console

from ...util.az_client import (
    DEFAULT_IOTOPS_MGMT_API_VERSION,
    get_resource_client,
    wait_for_terminal_state,
    wait_for_terminal_states,
)
from ...util.common import should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.machinery import scoped_semver_import
from ...util.resource_graph import ResourceGraph
from ...util.workflow_display import StepState, WorkflowDisplay, render_summary
from .common import (
    CLUSTER_EXTENSIONS_API_VERSION,
    CUSTOM_LOCATIONS_API_VERSION,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    MAX_INSTANCE_VERSION_ACS_DEPENDENCY,
    SECRET_SYNC_API_VERSION,
)
from .resource_map import IoTOperationsResource
from .resources import ConnectedClusters, Instances
from .resources.clusters import ClusterExtensions
from .resources.custom_locations import CustomLocations

logger = get_logger(__name__)


if TYPE_CHECKING:
    from azure.core.polling import LROPoller

# Step labels used as WorkflowDisplay categories and render_summary section headers.
_STEP_INSTANCE = "Instance"
_STEP_AIO_EXT = "Ops Extension"
_STEP_CL_RESOURCES = "CL Resources"
_STEP_SYNC_RULES = "Resource Sync Rules"
_STEP_CUSTOM_LOCATION = "Custom Location"
_STEP_DEP_EXTENSIONS = "Dependency Extensions"

# Extension types eligible for --include-deps deletion (excluding ACS, which is version-gated).
_DEP_EXTENSION_TYPES = frozenset([EXTENSION_TYPE_CM, EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_SSC])

# All AIO-related extension types — used for type-verified CL identification.
_AIO_EXTENSION_TYPES = frozenset([EXTENSION_TYPE_OPS, EXTENSION_TYPE_ACS]) | _DEP_EXTENSION_TYPES

# Default Kubernetes namespace for IoT Operations custom locations.
_AIO_DEFAULT_NAMESPACE = "azure-iot-operations"

# Friendly display labels for CL resource types (keyed by resource_type from parse_resource_id).
_FRIENDLY_TYPE_LABELS: Dict[str, str] = {
    "assets": "asset",
    "assetendpointprofiles": "asset endpoint profile",
    "devices": "device",
    "azurekeyvaultsecretproviderclasses": "secret provider class",
}

# ARG sweep KQL — finds all resources scoped to the custom location.
# Excludes IoT Operations resources (cascade-deleted with instance) and
# preserved external prerequisites (DR namespaces and schema registries).
_ARG_SWEEP_QUERY = """
resources
| where extendedLocation.name =~ '{cl_id}'
| where type !startswith 'microsoft.iotoperations'
    and type !~ 'microsoft.deviceregistry/namespaces'
    and type !~ 'microsoft.deviceregistry/schemaregistries'
| project id, name, apiVersion, type
"""


def delete_ops_resources(
    cmd,
    resource_group_name: str,
    instance_name: Optional[str] = None,
    cluster_name: Optional[str] = None,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    force: Optional[bool] = None,
    include_dependencies: Optional[bool] = None,
):
    manager = DeletionManager(
        cmd=cmd,
        instance_name=instance_name,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
        include_dependencies=include_dependencies,
    )
    manager.do_work(confirm_yes=confirm_yes, force=force)


class DeletionManager:
    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: Optional[str] = None,
        cluster_name: Optional[str] = None,
        include_dependencies: Optional[bool] = None,
        no_progress: Optional[bool] = None,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.instance_name = instance_name
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.include_dependencies = include_dependencies
        self.subscription_id = get_subscription_id(cli_ctx=cmd.cli_ctx)
        self.resource_client = get_resource_client(self.subscription_id)

        self._render_progress = not no_progress

        # Discovered state — populated during discovery phase.
        self._instance: Optional[dict] = None
        self._instance_resource: Optional[IoTOperationsResource] = None
        self._cl_id: Optional[str] = None
        self._cl_name: Optional[str] = None
        self._cluster_resource: Optional[dict] = None
        self._cluster_name: Optional[str] = None
        self._aio_extension: Optional[IoTOperationsResource] = None
        self._dep_extensions: List[IoTOperationsResource] = []
        self._cl_resources: List[IoTOperationsResource] = []
        self._sync_rules: List[IoTOperationsResource] = []
        self._cl_resource: Optional[IoTOperationsResource] = None
        self._cluster_extensions_client: Optional[ClusterExtensions] = None
        self._aio_typed_ext_ids: Set[str] = set()

    def do_work(self, confirm_yes: Optional[bool] = None, force: Optional[bool] = None) -> None:
        if not any([self.cluster_name, self.instance_name]):
            raise ArgumentUsageError("Please provide either an instance name or cluster name.")

        self.correlation_id = str(uuid4())
        self.headers = {"x-ms-correlation-request-id": self.correlation_id, "CommandName": "iot ops delete"}

        # Discovery phase — populate all deletion targets via ARM.
        if self._render_progress:
            console = Console(stderr=True)
            with console.status("Analyzing instance resources..."):
                if self.instance_name:
                    self._discover_instance_path()
                else:
                    self._discover_cluster_path()
        else:
            if self.instance_name:
                self._discover_instance_path()
            else:
                self._discover_cluster_path()

        # Connectivity gate — check before displaying summary or prompting.
        if self._cluster_resource and not force:
            connectivity_status = (
                self._cluster_resource.get("properties", {}).get("connectivityStatus", "Unknown")
            )
            if connectivity_status.lower() != "connected":
                raise ArgumentUsageError(
                    f"The cluster is not connected to Azure (status: {connectivity_status}). "
                    "Use --force to continue anyway, which may lead to errors."
                )

        if not self._has_work():
            logger.warning("Nothing to delete :)")
            return

        # Summary + prompt.
        if self._render_progress:
            logger.info(f"Deletion correlation Id: {self.correlation_id}")
            self._display_summary()

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        self._execute()

    # ------------------------------------------------------------------
    # Discovery — Instance-Name Path
    # ------------------------------------------------------------------

    def _discover_instance_path(self) -> None:
        """Instance-name path: all direct ARM GETs following known ID references."""
        instances = Instances(self.cmd)
        try:
            self._instance = instances.show(
                name=self.instance_name, resource_group_name=self.resource_group_name
            )
        except (HttpResponseError, ResourceNotFoundError):
            raise ResourceNotFoundError(
                f"Instance '{self.instance_name}' not found in resource group '{self.resource_group_name}'. "
                "If resources remain from a previous deletion, use --cluster to discover and clean them up."
            )

        instance_id: str = self._instance["id"]
        self._instance_resource = IoTOperationsResource(
            resource_id=instance_id,
            display_name=self._instance.get("name", self.instance_name),
            api_version=DEFAULT_IOTOPS_MGMT_API_VERSION.value,
        )

        # CL from instance extendedLocation.
        self._cl_id = self._instance.get("extendedLocation", {}).get("name", "")
        if self._cl_id:
            cl_parsed = parse_resource_id(self._cl_id)
            self._cl_name = cl_parsed.get("name", "")
            self._cl_resource = IoTOperationsResource(
                resource_id=self._cl_id,
                display_name=self._cl_name,
                api_version=CUSTOM_LOCATIONS_API_VERSION,
            )

        # Cluster from CL hostResourceId.
        if self._cl_id:
            try:
                cl_dict = self.resource_client.resources.get_by_id(
                    resource_id=self._cl_id, api_version=CUSTOM_LOCATIONS_API_VERSION
                )
                cluster_id = cl_dict.get("properties", {}).get("hostResourceId", "")
                if cluster_id:
                    cluster_parsed = parse_resource_id(cluster_id)
                    self._cluster_name = cluster_parsed.get("name", "")
                    cluster_rg = cluster_parsed.get("resource_group", self.resource_group_name)
                    clusters = ConnectedClusters(self.cmd)
                    self._cluster_resource = clusters.show(
                        resource_group_name=cluster_rg, cluster_name=self._cluster_name
                    )
            except HttpResponseError as e:
                logger.warning(f"Could not resolve cluster from custom location: {e}")

        # SPC from instance properties.
        self._collect_spc_from_instance()

        # Extensions, sync rules, ARG sweep — shared discovery.
        self._discover_extensions()
        self._discover_sync_rules()
        self._run_arg_sweep()

    # ------------------------------------------------------------------
    # Discovery — Cluster-Name Path
    # ------------------------------------------------------------------

    def _discover_cluster_path(self) -> None:
        """Cluster-name path: ARM lists + client-side filter."""
        clusters = ConnectedClusters(self.cmd)
        self._cluster_resource = clusters.show(
            resource_group_name=self.resource_group_name, cluster_name=self.cluster_name
        )
        self._cluster_name = self.cluster_name
        cluster_id: str = self._cluster_resource["id"]

        # Discover extensions first — populates type-verified IDs for CL identification.
        self._discover_extensions()

        # Find AIO custom location on this cluster using tiered identification.
        custom_locations = CustomLocations(self.cmd)
        all_cls = list(custom_locations.list(resource_group_name=self.resource_group_name))
        host_matched_cls = [
            cl for cl in all_cls
            if (cl.get("properties", {}).get("hostResourceId", "") or "").lower() == cluster_id.lower()
        ]
        matched_cl = self._identify_aio_cl(host_matched_cls)

        if matched_cl:
            self._cl_id = matched_cl["id"]
            cl_parsed = parse_resource_id(self._cl_id)
            self._cl_name = cl_parsed.get("name", "")
            self._cl_resource = IoTOperationsResource(
                resource_id=self._cl_id,
                display_name=self._cl_name,
                api_version=CUSTOM_LOCATIONS_API_VERSION,
            )

        # Find instance on this CL.
        if self._cl_id:
            instances = Instances(self.cmd)
            all_instances = list(instances.list(resource_group_name=self.resource_group_name))
            for inst in all_instances:
                inst_cl = inst.get("extendedLocation", {}).get("name", "")
                if inst_cl and inst_cl.lower() == self._cl_id.lower():
                    self._instance = inst
                    self._instance_resource = IoTOperationsResource(
                        resource_id=inst["id"],
                        display_name=inst.get("name", ""),
                        api_version=DEFAULT_IOTOPS_MGMT_API_VERSION.value,
                    )
                    break

        # SPC from instance properties (if instance found).
        if self._instance:
            self._collect_spc_from_instance()

        # Sync rules and ARG sweep — remaining shared discovery.
        self._discover_sync_rules()
        self._run_arg_sweep()

    def _identify_aio_cl(self, host_matched_cls: List[dict]) -> Optional[dict]:
        """Identify the AIO custom location from CLs on the same cluster.

        Tier 1: Cross-reference CL's clusterExtensionIds against type-verified
        AIO extensions discovered on the cluster.
        Tier 2: Match CL namespace against the default AIO namespace.
        Raises if CLs exist on the host but none can be identified as AIO.
        """
        if not host_matched_cls:
            return None

        # Tier 1: Extension type cross-reference.
        if self._aio_typed_ext_ids:
            for cl in host_matched_cls:
                cl_ext_ids = cl.get("properties", {}).get("clusterExtensionIds", []) or []
                if any(eid.lower() in self._aio_typed_ext_ids for eid in cl_ext_ids):
                    return cl

        # Tier 2: Namespace match.
        for cl in host_matched_cls:
            ns = cl.get("properties", {}).get("namespace", "")
            if ns and ns.lower() == _AIO_DEFAULT_NAMESPACE:
                return cl

        raise ResourceNotFoundError(
            f"Could not identify an IoT Operations custom location on cluster '{self.cluster_name}'. "
            "If resources remain, delete them manually."
        )

    # ------------------------------------------------------------------
    # Shared Discovery Helpers
    # ------------------------------------------------------------------

    def _collect_spc_from_instance(self) -> None:
        """Extract the default SPC resource ID from instance properties."""
        if not self._instance:
            return
        spc_ref = self._instance.get("properties", {}).get("defaultSecretProviderClassRef", {})
        spc_id = spc_ref.get("resourceId", "") if spc_ref else ""
        if spc_id:
            parsed = parse_resource_id(spc_id)
            self._cl_resources.append(IoTOperationsResource(
                resource_id=spc_id,
                display_name=parsed.get("resource_name", spc_id.rsplit("/", 1)[-1]),
                api_version=SECRET_SYNC_API_VERSION,
            ))

    def _discover_extensions(self) -> None:
        """Discover extensions on the cluster; separate AIO extension from deps."""
        if not self._cluster_name:
            return

        self._cluster_extensions_client = ClusterExtensions(self.cmd)
        all_exts = list(
            self._cluster_extensions_client.list(
                resource_group_name=self.resource_group_name, cluster_name=self._cluster_name
            )
        )

        aio_version: Optional[str] = None
        acs_extension: Optional[IoTOperationsResource] = None
        for ext in all_exts:
            ext_type = ext.get("properties", {}).get("extensionType", "").lower()
            ext_id = ext.get("id", "")
            ext_name = ext.get("name", "")

            if ext_type == EXTENSION_TYPE_OPS:
                self._aio_extension = IoTOperationsResource(
                    resource_id=ext_id,
                    display_name=ext_name,
                    api_version=CLUSTER_EXTENSIONS_API_VERSION,
                )
                aio_version = ext.get("properties", {}).get("version", "")
            elif ext_type == EXTENSION_TYPE_ACS:
                acs_extension = IoTOperationsResource(
                    resource_id=ext_id,
                    display_name=ext_name,
                    api_version=CLUSTER_EXTENSIONS_API_VERSION,
                )
            elif ext_type in _DEP_EXTENSION_TYPES:
                self._dep_extensions.append(IoTOperationsResource(
                    resource_id=ext_id,
                    display_name=ext_name,
                    api_version=CLUSTER_EXTENSIONS_API_VERSION,
                ))

            # Track type-verified extension IDs for CL identification.
            if ext_type in _AIO_EXTENSION_TYPES:
                self._aio_typed_ext_ids.add(ext_id.lower())

        # Version-gate ACS: only include if AIO version <= threshold.
        if acs_extension and self._should_include_acs(aio_version):
            self._dep_extensions.append(acs_extension)

    def _should_include_acs(self, aio_version: Optional[str]) -> bool:
        """Return True if ACS should be included in dependency deletion."""
        version_str = aio_version
        if not version_str and self._instance:
            version_str = self._instance.get("properties", {}).get("version", "")

        if not version_str:
            logger.debug("No AIO version available for ACS gating, preserving ACS.")
            return False

        try:
            semver = scoped_semver_import()
            parsed = semver.parse(version_str)
            threshold = semver.parse(MAX_INSTANCE_VERSION_ACS_DEPENDENCY)
            return parsed <= threshold
        except (ValueError, TypeError):
            logger.debug(f"Could not parse AIO version '{version_str}' for ACS gating, preserving ACS.")
            return False

    def _discover_sync_rules(self) -> None:
        """Discover resource sync rules for the custom location."""
        if not self._cl_id or not self._cl_name:
            return

        custom_locations = CustomLocations(self.cmd)
        cl_parsed = parse_resource_id(self._cl_id)
        cl_rg = cl_parsed.get("resource_group", self.resource_group_name)

        try:
            rules = list(
                custom_locations.list_resource_sync_rules(
                    resource_group_name=cl_rg, cl_name=self._cl_name
                )
            )
            for rule in rules:
                self._sync_rules.append(IoTOperationsResource(
                    resource_id=rule["id"],
                    display_name=rule.get("name", ""),
                    api_version=CUSTOM_LOCATIONS_API_VERSION,
                ))
        except HttpResponseError as e:
            logger.warning(f"Could not list resource sync rules: {e}")

    def _run_arg_sweep(self) -> None:
        """Optional ARG sweep for SecretSync + user-created DR resources on the CL."""
        if not self._cl_id:
            return

        try:
            rg = ResourceGraph(cmd=self.cmd, subscriptions=[self.subscription_id])
            query = _ARG_SWEEP_QUERY.format(cl_id=self._cl_id)
            result = rg.query_resources(query)
            data = result.get("data", []) if isinstance(result, dict) else result

            # Collect existing CL resource IDs for deduplication (case-insensitive).
            existing_ids = {r.resource_id.lower() for r in self._cl_resources}

            for row in data:
                rid = row.get("id", "")
                if rid.lower() in existing_ids:
                    continue
                parsed = parse_resource_id(rid)
                name = parsed.get("resource_name", rid.rsplit("/", 1)[-1])
                api_version = row.get("apiVersion", "")
                self._cl_resources.append(IoTOperationsResource(
                    resource_id=rid,
                    display_name=name,
                    api_version=api_version,
                ))
        except (HttpResponseError, ValueError, KeyError, TypeError) as e:
            logger.warning(
                f"Could not query for additional CL-scoped resources (e.g. user-created assets): {e}\n"
                "These resources may remain after deletion. "
                "Re-run with --cluster to discover and clean them up."
            )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _has_work(self) -> bool:
        return any([
            self._instance_resource,
            self._aio_extension,
            self._cl_resources,
            self._sync_rules,
            self._cl_resource,
            self.include_dependencies and self._dep_extensions,
        ])

    @staticmethod
    def _cl_resource_label(resource_id: str) -> str:
        """Derive a friendly type label from a CL resource ID."""
        parsed = parse_resource_id(resource_id)
        resource_type = parsed.get("resource_type", "").lower()
        label = _FRIENDLY_TYPE_LABELS.get(resource_type, resource_type or "resource")
        # Prefix with "ns" for namespace-scoped DR resources.
        if parsed.get("last_child_num") and parsed.get("namespace", "").lower() == "microsoft.deviceregistry":
            label = f"ns {label}"
        return label

    def _display_summary(self) -> None:
        """Render a pre-deletion confirmation summary to stderr."""
        sections: Dict[str, list] = OrderedDict()

        if self._instance_resource:
            sections[_STEP_INSTANCE] = [(self._instance_resource.display_name, "found")]

        if self._cl_resources:
            sections[_STEP_CL_RESOURCES] = [
                (r.display_name, self._cl_resource_label(r.resource_id))
                for r in self._cl_resources
            ]

        if self._sync_rules:
            sections[_STEP_SYNC_RULES] = [(r.display_name, "found") for r in self._sync_rules]

        if self._cl_resource:
            sections[_STEP_CUSTOM_LOCATION] = [(self._cl_resource.display_name, "found")]

        if self._aio_extension:
            sections[_STEP_AIO_EXT] = [(self._aio_extension.display_name, "found")]

        if self.include_dependencies and self._dep_extensions:
            sections[_STEP_DEP_EXTENSIONS] = [(e.display_name, "found") for e in self._dep_extensions]

        render_summary(
            title="IoT Operations Deletion",
            sections=sections,
            footer="Preserved (not deleted): DR namespace, schema registry",
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute(self) -> None:
        """Execute deletion in strict step order with WorkflowDisplay progress."""
        categories: Dict[str, List[str]] = OrderedDict()

        if self._instance_resource:
            categories[_STEP_INSTANCE] = [self._instance_resource.display_name]
        if self._cl_resources:
            count = len(self._cl_resources)
            categories[_STEP_CL_RESOURCES] = [f"{count} resource{'s' if count != 1 else ''}"]
        if self._sync_rules:
            categories[_STEP_SYNC_RULES] = [r.display_name for r in self._sync_rules]
        if self._cl_resource:
            categories[_STEP_CUSTOM_LOCATION] = [self._cl_resource.display_name]
        if self._aio_extension:
            categories[_STEP_AIO_EXT] = [self._aio_extension.display_name]
        if self.include_dependencies and self._dep_extensions:
            categories[_STEP_DEP_EXTENSIONS] = [e.display_name for e in self._dep_extensions]

        with WorkflowDisplay(
            title="Deleting IoT Operations",
            categories=categories,
            transient=False,
            no_progress=not self._render_progress,
        ) as display:
            try:
                # Instance (cascade).
                if self._instance_resource:
                    self._execute_step_single(
                        display, _STEP_INSTANCE, self._instance_resource
                    )

                # CL resources (SecretSync + DR assets) — collapsed summary step.
                if self._cl_resources:
                    self._execute_cl_resources(display)

                # Resource sync rules — single parallel batch.
                if self._sync_rules:
                    self._execute_step_parallel(display, _STEP_SYNC_RULES, self._sync_rules)

                # Custom location — soft-fail so extensions still run.
                if self._cl_resource:
                    try:
                        self._execute_step_single(
                            display, _STEP_CUSTOM_LOCATION, self._cl_resource
                        )
                    except HttpResponseError as e:
                        display.update_step(
                            _STEP_CUSTOM_LOCATION, self._cl_resource.display_name,
                            StepState.FAILED, "failed"
                        )
                        logger.warning(
                            f"Could not delete custom location '{self._cl_resource.display_name}': {e}\n"
                            "Resources scoped to it may still exist. "
                            "Re-run with --cluster to discover and clean them up."
                        )

                # AIO extension (uses dedicated extensions client for proper LRO).
                if self._aio_extension:
                    self._execute_extension_single(
                        display, _STEP_AIO_EXT, self._aio_extension
                    )

                # Dependency extensions (--include-deps only, dedicated client).
                if self.include_dependencies and self._dep_extensions:
                    self._execute_extension_parallel(display, _STEP_DEP_EXTENSIONS, self._dep_extensions)

            except HttpResponseError:
                logger.error(
                    f"Correlation Id for failed deletion: {self.headers['x-ms-correlation-request-id']}"
                )
                raise

    def _execute_step_single(
        self, display: WorkflowDisplay, category: str, resource: IoTOperationsResource
    ) -> None:
        """Delete a single resource and wait for completion."""
        with display.step_scope(category, resource.display_name):
            try:
                poller = self.resource_client.resources.begin_delete_by_id(
                    resource_id=resource.resource_id,
                    api_version=resource.api_version,
                    headers=self.headers,
                )
                wait_for_terminal_state(poller)
            except HttpResponseError as e:
                if e.status_code == 404:
                    logger.debug(f"Resource already deleted: {resource.resource_id}")
                else:
                    raise
            display.update_step(category, resource.display_name, StepState.COMPLETE, "removed")

    def _execute_step_parallel(
        self, display: WorkflowDisplay, category: str, resources: List[IoTOperationsResource]
    ) -> None:
        """Delete all resources in a single parallel batch."""
        for r in resources:
            display.update_step(category, r.display_name, StepState.ACTIVE)

        pollers: List[Tuple[IoTOperationsResource, "LROPoller"]] = []
        for r in resources:
            try:
                poller = self.resource_client.resources.begin_delete_by_id(
                    resource_id=r.resource_id,
                    api_version=r.api_version,
                    headers=self.headers,
                )
                pollers.append((r, poller))
            except HttpResponseError as e:
                if e.status_code == 404:
                    logger.debug(f"Resource already deleted: {r.resource_id}")
                    display.update_step(category, r.display_name, StepState.COMPLETE, "removed")
                else:
                    display.update_step(category, r.display_name, StepState.FAILED, str(e)[:40])
                    raise

        if pollers:
            wait_for_terminal_states(*[p for _, p in pollers])

        for r, _ in pollers:
            display.update_step(category, r.display_name, StepState.COMPLETE, "removed")

    @staticmethod
    def _batch_by_segment_depth(resources: List[IoTOperationsResource]) -> List[List[IoTOperationsResource]]:
        """Sort resources deepest-first and group into batches of equal segment depth."""
        sorted_resources = sorted(
            resources, key=lambda r: (r.segments, r.display_name.lower()), reverse=True
        )
        batches: List[List[IoTOperationsResource]] = []
        last_segments = maxsize
        current_batch: List[IoTOperationsResource] = []
        for resource in sorted_resources:
            current_segments = resource.segments
            if current_segments < last_segments and current_batch:
                batches.append(current_batch)
                current_batch = []
            current_batch.append(resource)
            last_segments = current_segments
        if current_batch:
            batches.append(current_batch)
        return batches

    def _execute_step_batched(
        self, display: WorkflowDisplay, category: str, resources: List[IoTOperationsResource]
    ) -> None:
        """Delete resources using segment-depth batching (deepest first)."""
        for batch in self._batch_by_segment_depth(resources):
            self._execute_step_parallel(display, category, batch)

    def _execute_cl_resources(self, display: WorkflowDisplay) -> None:
        """Delete CL resources with segment-depth batching, tracked as a single summary step."""
        count = len(self._cl_resources)
        label = f"{count} resource{'s' if count != 1 else ''}"

        with display.step_scope(_STEP_CL_RESOURCES, label):
            for batch in self._batch_by_segment_depth(self._cl_resources):
                pollers: List["LROPoller"] = []
                for r in batch:
                    try:
                        poller = self.resource_client.resources.begin_delete_by_id(
                            resource_id=r.resource_id,
                            api_version=r.api_version,
                            headers=self.headers,
                        )
                        pollers.append(poller)
                    except HttpResponseError as e:
                        if e.status_code == 404:
                            logger.debug(f"Resource already deleted: {r.resource_id}")
                        else:
                            raise

                if pollers:
                    wait_for_terminal_states(*pollers)

            display.update_step(_STEP_CL_RESOURCES, label, StepState.COMPLETE, "removed")

    # ------------------------------------------------------------------
    # Extension-specific execution (dedicated ClusterExtensions client)
    # ------------------------------------------------------------------

    def _begin_delete_extension(self, resource: IoTOperationsResource) -> "LROPoller":
        """Start extension deletion via the dedicated ClusterExtensions client."""
        if not self._cluster_extensions_client:
            self._cluster_extensions_client = ClusterExtensions(self.cmd)
        return self._cluster_extensions_client.ops.begin_delete(
            resource_group_name=self.resource_group_name,
            cluster_rp="Microsoft.Kubernetes",
            cluster_resource_name="connectedClusters",
            cluster_name=self._cluster_name,
            extension_name=resource.display_name,
            headers=self.headers,
        )

    def _execute_extension_single(
        self, display: WorkflowDisplay, category: str, resource: IoTOperationsResource
    ) -> None:
        """Delete a single extension and wait for completion using the dedicated client."""
        with display.step_scope(category, resource.display_name):
            try:
                poller = self._begin_delete_extension(resource)
                wait_for_terminal_state(poller)
            except HttpResponseError as e:
                if e.status_code == 404:
                    logger.debug(f"Extension already deleted: {resource.resource_id}")
                else:
                    raise
            display.update_step(category, resource.display_name, StepState.COMPLETE, "removed")

    def _execute_extension_parallel(
        self, display: WorkflowDisplay, category: str, resources: List[IoTOperationsResource]
    ) -> None:
        """Delete extensions in a parallel batch using the dedicated client."""
        for r in resources:
            display.update_step(category, r.display_name, StepState.ACTIVE)

        pollers: List[Tuple[IoTOperationsResource, "LROPoller"]] = []
        for r in resources:
            try:
                poller = self._begin_delete_extension(r)
                pollers.append((r, poller))
            except HttpResponseError as e:
                if e.status_code == 404:
                    logger.debug(f"Extension already deleted: {r.resource_id}")
                    display.update_step(category, r.display_name, StepState.COMPLETE, "removed")
                else:
                    display.update_step(category, r.display_name, StepState.FAILED, str(e)[:40])
                    raise

        if pollers:
            wait_for_terminal_states(*[p for _, p in pollers])

        for r, _ in pollers:
            display.update_step(category, r.display_name, StepState.COMPLETE, "removed")
