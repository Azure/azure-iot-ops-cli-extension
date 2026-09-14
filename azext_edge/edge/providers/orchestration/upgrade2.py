# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from time import sleep
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table, box

from .common import DEFAULT_REGISTRY_HOST
from ...util import parse_kvp_nargs, should_continue_prompt
from ...util.machinery import scoped_semver_import
from .common import (
    EXTENSION_MONIKER_CM,
    EXTENSION_MONIKER_OPS,
    EXTENSION_MONIKER_TO_ALIAS_MAP,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_TO_MONIKER_MAP,
    MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
    MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE,
    MIN_INSTANCE_VERSION_V1_FOR_V2_UPGRADE,
    MIN_INSTANCE_VERSION_V2,
    OPCUA_CONNECTOR_ENDPOINT_TYPE,
    OPCUA_CONNECTOR_TEMPLATE_NAME_PREFIX,
    OPCUA_CONNECTOR_VERSION,
    PROVISIONING_STATE_FAILED,
    PROVISIONING_STATE_SUCCESS,
    ConfigSyncModeType,
)
from .migration import SecretSyncMigrationManager
from .resources import RegistryEndpoints
from .resources.connector_templates import ConnectorTemplates
from .resources.instances import SECRET_SYNC_RESOURCE_TYPE, SPC_RESOURCE_TYPE, Instances
from .targets import InitTargets

logger = get_logger(__name__)

console = Console()


IOT_OPS_DELAY = 30  # seconds


class ExtensionOperation(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


def upgrade_ops_instance(
    cmd,
    resource_group_name: str,
    instance_name: str,
    adr_namespace_resource_id: Optional[str] = None,
    no_progress: Optional[bool] = None,
    confirm_yes: Optional[bool] = None,
    force: Optional[bool] = None,
    no_cm_install: Optional[bool] = None,
    **kwargs,
):
    upgrade_manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        adr_namespace_resource_id=adr_namespace_resource_id,
        no_progress=no_progress,
        force=force,
        no_cm_install=no_cm_install,
    )

    upgrade_state = upgrade_manager.analyze_cluster(**kwargs)

    stale_monikers = upgrade_state.get_stale_cli_extensions()
    if stale_monikers:
        logger.warning(
            "This azure-iot-ops CLI extension has no newer version to offer for: %s. "
            "The version deployed on the cluster is newer than the version built into this CLI. "
            "No deployed version of the listed extensions will be changed. "
            "Run 'az extension update --name azure-iot-ops' to pick up newer versions.",
            ", ".join(stale_monikers),
        )

    if not upgrade_state.has_upgrades():
        logger.warning("Nothing to upgrade :)")
        return

    if not no_progress:
        render_upgrade_table(upgrade_state)

    should_bail = not should_continue_prompt(confirm_yes=confirm_yes, context="Upgrade")
    if should_bail:
        return

    return upgrade_manager.apply_upgrades(upgrade_state)


class UpgradeManager:
    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: str,
        adr_namespace_resource_id: Optional[str] = None,
        no_progress: Optional[bool] = None,
        force: Optional[bool] = None,
        no_cm_install: Optional[bool] = None,
    ):
        self.cmd = cmd
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.no_progress = no_progress
        self.force = force
        self.no_cm_install = no_cm_install
        self.instances = Instances(self.cmd)
        self.registry_endpoints = RegistryEndpoints(self.cmd)
        self.connector_templates = ConnectorTemplates(self.cmd)
        # Name of an existing failed OPC UA template to repair in place (set during the check).
        self._opcua_template_name_to_repair = None
        self.instance_record = self.instances.show(
            name=self.instance_name, resource_group_name=self.resource_group_name
        )
        self.resource_map = self.instances.get_resource_map(self.instance_record)
        self.targets = InitTargets(
            cluster_name=self.resource_map.connected_cluster.cluster_name,
            resource_group_name=resource_group_name,
            adr_namespace_resource_id=adr_namespace_resource_id,
        )
        self.secretsync_migration = SecretSyncMigrationManager(
            cmd=self.cmd,
            instance_record=self.instance_record,
            resource_map=self.resource_map,
            secretsync_resources=self.resource_map.connected_cluster.get_cl_resources_by_type(
                custom_location_id=self.instance_record["extendedLocation"]["name"],
                resource_types={SPC_RESOURCE_TYPE, SECRET_SYNC_RESOURCE_TYPE},
                show_properties=True,
            ),
        )

    def get_desired_config(self) -> Dict[str, str]:
        return {}
        # TODO @digimaun - enable with template gen or alt desired state diff.
        # instance_template, _ = self.targets.get_ops_instance_template([])
        # return {
        #     EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS]: instance_template["variables"][
        #         "defaultAioConfigurationSettings"
        #     ]
        # }

    def analyze_cluster(self, **override_kwargs: dict) -> "ClusterUpgradeState":
        with Progress(
            SpinnerColumn("star"),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=True,
            disable=bool(self.no_progress),
        ) as progress:
            _ = progress.add_task("Analyzing cluster...", total=None)
            if not self.resource_map.connected_cluster.connected:
                raise ValidationError(f"Cluster {self.resource_map.connected_cluster.cluster_name} is not connected.")

            return ClusterUpgradeState(
                extensions_map=self.resource_map.connected_cluster.get_extensions_by_type(
                    *list(EXTENSION_TYPE_TO_MONIKER_MAP.keys())
                ),
                init_version_map={
                    **self.targets.get_extension_versions(),
                    **self.targets.get_extension_versions(False),
                },
                desired_config_map=self.get_desired_config(),
                override_map=build_override_map(**override_kwargs),
                instance=self.instance_record,
                adr_namespace_resource_id=self.targets.adr_namespace_resource_id,
                registry_endpoint_check=self._check_default_registry_needed,
                connector_template_check=self._check_opcua_connector_template_needed,
                secretsync_migration=self.secretsync_migration,
                force=self.force,
                no_cm_install=self.no_cm_install,
            )

    def _check_default_registry_needed(self) -> bool:
        try:
            existing_endpoints = self.registry_endpoints.list(
                instance_name=self.instance_name, resource_group_name=self.resource_group_name
            )
            for endpoint in existing_endpoints:
                if endpoint["name"].lower() == "default":
                    logger.debug("Default registry endpoint already exists.")
                    return False
            return True
        except HttpResponseError as e:
            logger.debug(f"Error checking registry endpoints: {e}")
            return False

    def _check_opcua_connector_template_needed(self) -> Tuple[bool, Optional[str]]:
        """Return (needed, repair_name) for the default OPC UA connector template.

        The OPC UA supervisor requires a default ``akriConnectorTemplates`` resource (2608+) that
        no CLI install path created historically. A prefix-matching template that exists but is in
        a terminal ``Failed`` state is repaired in place by reusing its name (``repair_name``);
        transient states (e.g. Accepted/Updating/Deleting) are left alone to avoid racing an
        in-flight provisioning.
        """
        self._opcua_template_name_to_repair = None
        try:
            existing_templates = self.connector_templates.list(
                instance_name=self.instance_name, resource_group_name=self.resource_group_name
            )
            for template in existing_templates:
                if not (template.get("name") or "").lower().startswith(OPCUA_CONNECTOR_TEMPLATE_NAME_PREFIX):
                    continue
                if (template.get("provisioningState") or "").lower() == PROVISIONING_STATE_FAILED.lower():
                    # Repair the existing resource in place by reusing its name.
                    self._opcua_template_name_to_repair = template.get("name")
                    logger.debug("Default OPC UA connector template exists but failed; will repair in place.")
                    return True, self._opcua_template_name_to_repair
                # Succeeded or a transient state: leave it alone.
                logger.debug("Default OPC UA connector template already exists.")
                return False, None
            return True, None
        except HttpResponseError as e:
            logger.debug(f"Error checking OPC UA connector template: {e}")
            return False, None

    def _create_default_opcua_connector_template(self, headers: dict) -> dict:
        return self.connector_templates.create_default_opcua_template(
            resource_group_name=self.resource_group_name,
            instance_name=self.instance_name,
            template_name=self._opcua_template_name_to_repair,
            connector_version=OPCUA_CONNECTOR_VERSION,
            headers=headers,
            no_status=True,
        )

    def apply_upgrades(
        self,
        upgrade_state: "ClusterUpgradeState",
    ) -> List[dict]:
        with Progress(
            SpinnerColumn("star"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
            disable=bool(self.no_progress),
        ) as progress:
            # Group by operation type
            operations = self._group_by_operation(upgrade_state.extension_upgrades)
            total = sum(len(ops) for ops in operations.values())

            for aux_upgrade in [
                upgrade_state.instance_upgrade,
                upgrade_state.registry_endpoint_needed,
                upgrade_state.connector_template_needed,
                upgrade_state.secretsync_migration_needed,
            ]:
                if aux_upgrade:
                    total += 1

            return_payload = []
            correlation_id = str(uuid4())
            headers = {"x-ms-correlation-request-id": correlation_id, "CommandName": "iot ops upgrade"}
            task = progress.add_task("Applying changes...", total=total)

            # Apply in order: DELETE -> CREATE -> UPDATE
            for op_type in [ExtensionOperation.DELETE, ExtensionOperation.CREATE, ExtensionOperation.UPDATE]:
                for ext in operations.get(op_type, []):
                    try:
                        result = self._apply_single_operation(ext=ext, op_type=op_type, headers=headers)
                        return_payload.append(result)
                        progress.advance(task)
                    except HttpResponseError:
                        progress.stop()
                        logger.error(f"Correlation Id for failed {op_type.value} operation: {correlation_id}")
                        raise

            if upgrade_state.instance_upgrade:
                try:
                    instance_result = self._apply_instance_update(
                        needs_adr_update=upgrade_state._check_adr_namespace_update(),
                        needs_spc_update=upgrade_state._check_spc_reference_update(),
                        headers=headers,
                    )
                    return_payload.append(instance_result)
                    progress.advance(task)
                except HttpResponseError:
                    progress.stop()
                    logger.error(f"Correlation Id for failed instance update: {correlation_id}")
                    raise

            if upgrade_state.registry_endpoint_needed:
                try:
                    registry_result = self._create_default_registry_endpoint(headers)
                    return_payload.append(registry_result)
                    progress.advance(task)
                except HttpResponseError:
                    progress.stop()
                    logger.error(f"Correlation Id for failed registry endpoint creation: {correlation_id}")
                    raise

            if upgrade_state.connector_template_needed:
                try:
                    connector_template_result = self._create_default_opcua_connector_template(headers)
                    return_payload.append(connector_template_result)
                    progress.advance(task)
                except HttpResponseError:
                    progress.stop()
                    logger.error(f"Correlation Id for failed OPC UA connector template creation: {correlation_id}")
                    raise

            if upgrade_state.secretsync_migration_needed:
                try:
                    default_spc = self.secretsync_migration.migrate_to_v2(headers)
                    return_payload.append(default_spc)
                    progress.advance(task)
                except HttpResponseError:
                    progress.stop()
                    logger.error(f"Correlation Id for failed secretsync migration: {correlation_id}")
                    raise

            return return_payload

    def _apply_instance_update(self, needs_adr_update: bool, needs_spc_update: bool, headers: dict) -> dict:
        """Apply instance updates based on what's needed.

        Args:
            needs_adr_update: Whether ADR namespace needs updating
            needs_spc_update: Whether SPC reference needs updating
            headers: Request headers

        Returns:
            Updated instance resource dictionary
        """
        adr_resource_id = None
        spc_resource_id = None

        if needs_adr_update:
            adr_resource_id = self.targets.adr_namespace_resource_id

        if needs_spc_update and self.secretsync_migration and self.secretsync_migration.spc_default:
            spc_resource_id = self.secretsync_migration.spc_default.get("id")

        return self.instances.update(
            name=self.instance_name,
            resource_group_name=self.resource_group_name,
            instance=self.instance_record,
            adr_namespace_resource_id=adr_resource_id,
            spc_resource_id=spc_resource_id,
            headers=headers,
            no_status=True,  # Disable status since we're already in a Progress context
        )

    def _create_default_registry_endpoint(self, headers: dict) -> dict:
        return self.registry_endpoints.create(
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
            registry_endpoint_name="default",
            host=DEFAULT_REGISTRY_HOST,
            no_auth=True,
            headers=headers,
            no_status=True,
        )

    def _group_by_operation(self, extensions: List["ExtensionUpgradeState"]) -> Dict[ExtensionOperation, List]:
        groups = {op: [] for op in ExtensionOperation}
        for ext in extensions:
            if ext.can_upgrade():
                groups[ext.operation_type].append(ext)
        return groups

    def _apply_single_operation(self, ext: "ExtensionUpgradeState", op_type: ExtensionOperation, headers: dict) -> dict:
        cluster_name = self.resource_map.connected_cluster.cluster_name

        if op_type == ExtensionOperation.DELETE:
            self.resource_map.connected_cluster.clusters.extensions.delete_cluster_extension(
                resource_group_name=self.resource_group_name,
                cluster_name=cluster_name,
                extension_name=ext.extension["name"],
                headers=headers,
            )
            # DELETE returns None/empty, so we create a meaningful response for the user
            return {
                "name": ext.extension["name"],
                "properties": {"extensionType": ext.extension_type, "provisioningState": "Deleted"},
            }
        elif op_type == ExtensionOperation.CREATE:
            return self.resource_map.connected_cluster.clusters.extensions.create_cluster_extension(
                resource_group_name=self.resource_group_name,
                cluster_name=cluster_name,
                extension_name="cert-manager",
                create_payload=self._build_creation_payload(ext),
                headers=headers,
            )
        else:  # UPDATE
            result = self.resource_map.connected_cluster.clusters.extensions.update_cluster_extension(
                resource_group_name=self.resource_group_name,
                cluster_name=cluster_name,
                extension_name=ext.extension["name"],
                update_payload=ext.get_patch(),
                headers=headers,
            )

            if ext.moniker == EXTENSION_MONIKER_OPS:
                logger.debug(f"Wait {IOT_OPS_DELAY} seconds for iot ops extension version update to propagate...")
                sleep(IOT_OPS_DELAY)

            return result

    def _build_creation_payload(self, ext: "ExtensionUpgradeState") -> dict:
        """Build creation payload for certmanager extension"""
        # Get version with fallback
        version = ext.desired_version[0]
        if not version:
            cm_versions = self.targets.get_extension_versions(True).get(EXTENSION_MONIKER_CM, {})
            version = cm_versions.get("version", "0.6.2")

        return {
            "properties": {
                "extensionType": ext.extension_type or EXTENSION_TYPE_CM,
                "version": version,
                "releaseTrain": ext.desired_version[1] or "stable",
                "autoUpgradeMinorVersion": False,
                "scope": {"cluster": {"releaseNamespace": "cert-manager"}},
                "configurationSettings": ext.desired_config or {"AgentOperationTimeoutInMinutes": "20"},
            },
            "identity": {"type": "SystemAssigned"},
        }


def format_version_with_train(version: Optional[str], train: Optional[str]) -> str:
    if not version:
        return "[dim]Not Available[/dim]"

    if not train:
        return version

    # Use brackets to show train info, escaped for Rich formatting
    return f"{version} \\[{train}]"


# Color Strategy:
# - [green] = Additions/installations/new resources
# - [red] = Deletions/removals
# - [cyan] = Updates/modifications/changes to existing resources
# - [yellow] = Warnings/non-ideal states
# - [dim] = Not available/no changes/secondary information
# - [bold] = Important values (hostnames, versions, etc.)


def format_extension_row(ext: "ExtensionUpgradeState") -> Tuple[str, str, str]:
    """Format an extension row for the upgrade table.
    Returns: (current_version, desired_version, action)
    """
    try:
        status_indicator = ""
        if ext.provisioning_state and ext.provisioning_state.lower() != PROVISIONING_STATE_SUCCESS.lower():
            status_indicator = f" [yellow]({ext.provisioning_state})[/yellow]"

        if ext.operation_type == ExtensionOperation.DELETE:
            current = format_version_with_train(ext.current_version[0], ext.current_version[1]) + status_indicator
            desired = "[red]Removed[/red]"
            action = f"[red]Delete {ext.moniker}[/red]"
            return current, desired, action

        if ext.operation_type == ExtensionOperation.CREATE:
            current = "[dim]Not Installed[/dim]"
            version = ext.desired_version[0] or "[dim]default[/dim]"
            train = ext.desired_version[1] or "stable"
            desired = f"[green]{format_version_with_train(version, train)}[/green]"
            action = f"[green]Install {ext.moniker}[/green]"
            return current, desired, action

        # UPDATE operation
        current = format_version_with_train(ext.current_version[0], ext.current_version[1]) + status_indicator

        patch = ext.get_patch()
        props = patch.get("properties", {})

        desired_state = format_version_with_train(
            props.get("version", ext.current_version[0]),
            props.get("releaseTrain", ext.current_version[1]),
        )
        desired_style = "cyan" if ("version" in props or "releaseTrain" in props) else "dim"
        desired = f"[{desired_style}]{desired_state}[/{desired_style}]"

        if not patch or "properties" not in patch:
            return current, desired, "[dim]No changes[/dim]"

        action_lines = []

        if "version" in props:
            if props["version"] == ext.current_version[0]:
                action_lines.append(f"[cyan]•[/cyan] Reconcile at version [bold]{props['version']}[/bold]")
            else:
                action_lines.append(f"[cyan]•[/cyan] Update version to [bold]{props['version']}[/bold]")

        if "releaseTrain" in props:
            action_lines.append(f"[cyan]•[/cyan] Change release train to [bold]{props['releaseTrain']}[/bold]")

        if "configurationSettings" in props:
            config_settings = props.get("configurationSettings", {})
            wasm_settings = [
                (k, v) for k, v in config_settings.items() if k and k.startswith("dataFlows.values.tinyKube.mqttBroker")
            ]
            other_settings = [
                (k, v)
                for k, v in config_settings.items()
                if k and not k.startswith("dataFlows.values.tinyKube.mqttBroker")
            ]

            if wasm_settings:
                action_lines.append("[cyan]•[/cyan] WASM Graph config:")
                for key, value in wasm_settings:
                    if "hostName" in key:
                        action_lines.append(f"  [dim]◦[/dim] Hostname: [bold]{value}[/bold]")
                    elif "port" in key:
                        action_lines.append(f"  [dim]◦[/dim] Port: [bold]{value}[/bold]")
                    elif "serviceAccountTokenAudience" in key:
                        action_lines.append(f"  [dim]◦[/dim] Token audience: [bold]{value}[/bold]")
                    else:
                        key_parts = key.split(".")
                        simple_key = key_parts[-1] if key_parts else key
                        display_value = f"[bold]{value}[/bold]" if value else "[dim]removed[/dim]"
                        action_lines.append(f"  [dim]◦[/dim] {simple_key}: {display_value}")

            for key, value in other_settings:
                if value is None:
                    action_lines.append(f"[red]•[/red] Remove config: [strike]{key}[/strike]")
                else:
                    display_value = str(value)
                    if len(display_value) > 50:
                        display_value = display_value[:47] + "..."
                    action_lines.append(f"[cyan]•[/cyan] Set {key}: [bold]{display_value}[/bold]")

        return current, desired, "\n".join(action_lines) if action_lines else "[dim]No changes[/dim]"

    except Exception as e:
        logger.debug(f"Error formatting extension row for {ext.moniker}: {e}")
        return "[dim]Unknown[/dim]", "[dim]Unknown[/dim]", "[yellow]Check configuration[/yellow]"


def get_default_table() -> Table:
    table = Table(
        box=box.ROUNDED,
        highlight=True,
        expand=False,
        title="The Upgrade Story",
        min_width=79,
    )
    table.add_column("Resource", style="cyan")
    table.add_column("Current State")
    table.add_column("Desired State")
    table.add_column("Action")

    return table


def render_upgrade_table(upgrade_state: "ClusterUpgradeState"):  # noqa: C901
    """Render the upgrade table with all planned changes."""
    try:
        table = get_default_table()

        # Check if cert-manager installation was skipped due to --no-cm-install
        if upgrade_state.no_cm_install and upgrade_state._is_target_version_above_migration_threshold():
            has_certmanager = bool(upgrade_state.extensions_map.get(EXTENSION_TYPE_CM))

            # Would have installed certManager if not for no_cm_install flag
            if not has_certmanager:
                table.add_row(
                    "certManager",
                    "[dim]Not Installed[/dim]",
                    "[yellow]Skipped[/yellow]",
                    "[yellow]Installation disabled by --no-cm-install[/yellow]",
                )
                table.add_section()

        # Add extension rows
        for ext in upgrade_state.extension_upgrades:
            if not ext.can_upgrade():
                continue
            try:
                current, desired, action = format_extension_row(ext)
                if action:
                    table.add_row(ext.moniker, current, desired, action)
                    table.add_section()
            except Exception as e:
                logger.debug(f"Error adding row for {ext.moniker}: {e}")

        # Add instance update row if needed
        if upgrade_state.instance_upgrade:
            try:
                action_lines = []
                needs_adr = upgrade_state._check_adr_namespace_update()
                needs_spc = upgrade_state._check_spc_reference_update()

                if needs_adr and upgrade_state.adr_namespace_resource_id:
                    adr_parts = upgrade_state.adr_namespace_resource_id.split("/")
                    adr_name = adr_parts[-1] if adr_parts else "ADR namespace"
                    action_lines.append(f"[cyan]•[/cyan] Link ADR namespace: [bold]{adr_name}[/bold]")

                if needs_spc and upgrade_state.secretsync_migration and upgrade_state.secretsync_migration.spc_default:
                    spc_resource_id = upgrade_state.secretsync_migration.spc_default.get("id", "")
                    spc_parts = spc_resource_id.split("/")
                    spc_name = spc_parts[-1] if spc_parts else "default SPC"
                    action_lines.append(f"[cyan]•[/cyan] Link default SPC: [bold]{spc_name}[/bold]")

                # Format current state
                instance_props = upgrade_state.instance.get("properties", {})
                current_namespace_ref = instance_props.get("adrNamespaceRef")
                current_spc_ref = instance_props.get("defaultSecretProviderClassRef")

                current_parts = []
                if current_namespace_ref and current_namespace_ref.get("resourceId"):
                    ns_parts = current_namespace_ref.get("resourceId", "").split("/")
                    current_parts.append(f"ADR: {ns_parts[-1] if ns_parts else 'configured'}")
                else:
                    current_parts.append("[dim]No ADR namespace[/dim]")

                if current_spc_ref and current_spc_ref.get("resourceId"):
                    spc_parts = current_spc_ref.get("resourceId", "").split("/")
                    current_parts.append(f"SPC: {spc_parts[-1] if spc_parts else 'configured'}")
                else:
                    current_parts.append("[dim]No SPC ref[/dim]")

                # Format desired state
                desired_parts = []
                if needs_adr and upgrade_state.adr_namespace_resource_id:
                    adr_parts = upgrade_state.adr_namespace_resource_id.split("/")
                    desired_parts.append(f"[cyan]Linked {adr_parts[-1] if adr_parts else 'namespace'}[/cyan]")
                elif current_namespace_ref:
                    desired_parts.append("[dim]Keep ADR ref[/dim]")

                if needs_spc:
                    desired_parts.append("[cyan]Linked default SPC[/cyan]")
                elif current_spc_ref:
                    desired_parts.append("[dim]Keep SPC ref[/dim]")

                table.add_row(
                    "instance",
                    "\n".join(current_parts),
                    "\n".join(desired_parts) if desired_parts else "[dim]No changes[/dim]",
                    "\n".join(action_lines) if action_lines else "[dim]No changes[/dim]",
                )
                table.add_section()
            except Exception as e:
                logger.debug(f"Error adding instance row: {e}")

        # Add registry endpoint row if needed
        if upgrade_state.registry_endpoint_needed:
            try:
                table.add_row(
                    "default registry",
                    "[dim]Not configured[/dim]",
                    "[green]Created 'default'[/green]",
                    f"[green]•[/green] Create registry endpoint\n"
                    f"[green]•[/green] Host: [bold]{DEFAULT_REGISTRY_HOST}[/bold]\n"
                    f"[green]•[/green] Auth: [bold]Anonymous[/bold]",
                )
                table.add_section()
            except Exception as e:
                logger.debug(f"Error adding registry row: {e}")

        # Add OPC UA connector template row if needed
        if upgrade_state.connector_template_needed:
            try:
                repair_name = getattr(upgrade_state, "connector_template_repair_name", None)
                if repair_name:
                    table.add_row(
                        "opc-ua connector template",
                        f"[bold]{repair_name}[/bold]\n[red]Failed[/red]",
                        "[yellow]Replaced[/yellow]",
                        f"[yellow]•[/yellow] Replace failed template [bold]{repair_name}[/bold]\n"
                        f"[yellow]•[/yellow] Existing template settings are reset to defaults\n"
                        f"[green]•[/green] Endpoint: [bold]{OPCUA_CONNECTOR_ENDPOINT_TYPE}[/bold]\n"
                        f"[green]•[/green] Version: [bold]{OPCUA_CONNECTOR_VERSION}[/bold]",
                    )
                else:
                    table.add_row(
                        "opc-ua connector template",
                        "[dim]Not configured[/dim]",
                        "[green]Created[/green]",
                        f"[green]•[/green] Create default OPC UA connector template\n"
                        f"[green]•[/green] Endpoint: [bold]{OPCUA_CONNECTOR_ENDPOINT_TYPE}[/bold]\n"
                        f"[green]•[/green] Version: [bold]{OPCUA_CONNECTOR_VERSION}[/bold]",
                    )
                table.add_section()
            except Exception as e:
                logger.debug(f"Error adding connector template row: {e}")

        # Add secretsync migration row if needed
        if upgrade_state.secretsync_migration_needed:
            try:
                table.add_row(
                    "opc-ua-connector SPC",
                    "Created",
                    "[red]Removed[/red]",
                    "[cyan]•[/cyan] Migrate secret refs to default SPC\n" "[red]•[/red] Delete opc-ua-connector SPC",
                )
                table.add_section()
            except Exception as e:
                logger.debug(f"Error adding secretsync migration row: {e}")

        console.print(table)

    except Exception as e:
        logger.error(f"Error rendering upgrade table: {e}")
        console.print("[yellow]Unable to render upgrade table. Please check the logs.[/yellow]")


def build_override_map(**override_kwargs: dict) -> Dict[str, "ConfigOverride"]:
    result_map = {}
    for moniker in EXTENSION_MONIKER_TO_ALIAS_MAP:
        alias = EXTENSION_MONIKER_TO_ALIAS_MAP[moniker]
        config_override = ConfigOverride(
            config=override_kwargs.get(f"{alias}_config"),
            config_sync_mode=override_kwargs.get(f"{alias}_config_sync_mode"),
            version=override_kwargs.get(f"{alias}_version"),
            train=override_kwargs.get(f"{alias}_train"),
        )
        if not config_override.is_empty():
            result_map[moniker] = config_override

    return result_map


class ConfigOverride:
    def __init__(
        self,
        config: Optional[List[str]] = None,
        config_sync_mode: Optional[str] = None,
        version: Optional[str] = None,
        train: Optional[str] = None,
    ):
        self.config = parse_kvp_nargs(config)
        self.config_sync_mode = config_sync_mode
        self.version = version
        self.train = train

    def is_empty(self) -> bool:
        return not any([self.config, self.config_sync_mode, self.version, self.train])


class ClusterUpgradeState:
    def __init__(
        self,
        extensions_map: Dict[str, dict],
        init_version_map: Dict[str, dict],
        desired_config_map: Dict[str, str],
        override_map: Dict[str, "ConfigOverride"],
        instance: Optional[dict] = None,
        adr_namespace_resource_id: Optional[str] = None,
        registry_endpoint_check: Optional[callable] = None,
        connector_template_check: Optional[callable] = None,
        secretsync_migration: Optional["SecretSyncMigrationManager"] = None,
        force: Optional[bool] = None,
        no_cm_install: Optional[bool] = None,
    ):
        self.extensions_map = extensions_map
        self.init_version_map = init_version_map
        self.desired_config_map = desired_config_map
        self.override_map = override_map
        self.instance = instance
        self.adr_namespace_resource_id = adr_namespace_resource_id
        self.registry_endpoint_check = registry_endpoint_check
        self.connector_template_check = connector_template_check
        self.secretsync_migration = secretsync_migration
        self.force = force
        self.no_cm_install = no_cm_install
        self.semver = scoped_semver_import()
        self.connector_template_repair_name = None
        self.extension_upgrades = self._refresh_upgrade_state()
        self.instance_upgrade = self._check_instance_upgrade()
        self.registry_endpoint_needed = self._check_registry_endpoint_needed()
        self.connector_template_needed = self._check_connector_template_needed()
        self.secretsync_migration_needed = self._check_secretsync_migration_needed()

    def has_upgrades(self) -> bool:
        return (
            any(ext_state.can_upgrade() for ext_state in self.extension_upgrades)
            or bool(self.instance_upgrade)
            or bool(self.registry_endpoint_needed)
            or bool(self.connector_template_needed)
            or bool(self.secretsync_migration_needed)
        )

    def get_stale_cli_extensions(self) -> List[str]:
        return [ext_state.moniker for ext_state in self.extension_upgrades if ext_state.is_cli_behind_cluster()]

    def _check_instance_upgrade(self) -> bool:
        """Check if instance needs updates.

        Instance updates include:
        1. ADR namespace reference update
        2. Default SPC reference update

        Returns:
            bool: True if any updates are needed
        """
        if not self.instance:
            return False

        if not self._is_target_version_above_migration_threshold():
            return False

        needs_adr_update = self._check_adr_namespace_update()
        needs_spc_update = self._check_spc_reference_update()

        return needs_adr_update or needs_spc_update

    def _check_adr_namespace_update(self) -> bool:
        """Check if ADR namespace reference needs updating.

        Note: This assumes v2 migration check has already been done by caller.

        Returns:
            bool: True if ADR namespace update is needed

        Raises:
            ValidationError: If ADR namespace is required for v2 migration but not provided
        """
        namespace_ref = self.instance.get("properties", {}).get("adrNamespaceRef")
        current_adr_id = namespace_ref.get("resourceId") if namespace_ref else None

        # User explicitly provided an ADR namespace to set/update
        if self.adr_namespace_resource_id:
            return current_adr_id != self.adr_namespace_resource_id

        # Check if ADR namespace is required but missing (v2 migration requirement)
        if not current_adr_id:
            raise ValidationError(
                "The instance requires an ADR namespace for migration to v2.\n"
                "Please provide a value for --ns-resource-id."
            )

        return False

    def _check_spc_reference_update(self) -> bool:
        """Check if default SPC reference needs to be added to instance.

        Note: This assumes v2 migration check has already been done by caller.

        Returns:
            bool: True if SPC reference should be added
        """
        # Check if instance already has a default SPC reference
        current_spc_ref = self.instance.get("properties", {}).get("defaultSecretProviderClassRef")
        if current_spc_ref and current_spc_ref.get("resourceId"):
            return False

        # Check if a default SPC exists that needs linking
        if self.secretsync_migration and self.secretsync_migration.spc_default:
            return True

        return False

    def _check_registry_endpoint_needed(self) -> bool:
        """Check if default registry endpoint needs to be created.

        Returns True if:
        - Target IoT Operations version >= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
        - Default registry endpoint check function is provided and returns True (doesn't exist)
        """

        if not self._is_target_version_above_migration_threshold():
            return False

        # Check if the registry endpoint check function was provided and what it returns
        if self.registry_endpoint_check:
            return self.registry_endpoint_check()

        return False

    def _check_connector_template_needed(self) -> bool:
        """Check if the default OPC UA connector template needs to be created or repaired.

        Returns True when the target IoT Operations version is at/above
        MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE and the template is missing or failed.
        When repairing a failed template, ``connector_template_repair_name`` holds its name.
        """
        self.connector_template_repair_name = None

        if not self._is_target_version_at_least(MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE):
            return False

        if self.connector_template_check:
            needed, repair_name = self.connector_template_check()
            self.connector_template_repair_name = repair_name
            return needed

        return False

    def _check_secretsync_migration_needed(self) -> bool:
        """Check if SecretSync migration is needed.

        Returns True if:
        - Target IoT Operations version >= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
        - SecretSync migration check function is provided and returns True (migration needed)
        """

        if not self._is_target_version_above_migration_threshold():
            return False

        if self.secretsync_migration:
            return self.secretsync_migration.has_v1_spc()

        return False

    def _refresh_upgrade_state(self) -> List["ExtensionUpgradeState"]:
        ext_queue: List["ExtensionUpgradeState"] = []

        ops_extension = self.extensions_map.get(EXTENSION_TYPE_OPS)
        if not ops_extension:
            raise ValidationError(
                "The cluster backing the instance has an invalid state. IoT Operations extension not detected."
            )

        # Build IoT Operations extension state first and validate upgrade compatibility.
        ops_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS]
        ops_upgrade_state = ExtensionUpgradeState(
            extension=ops_extension,
            desired_version_map=self.init_version_map.get(ops_moniker, {}),
            desired_config=self.desired_config_map.get(ops_moniker),
            override=self.override_map.get(ops_moniker),
            force=self.force,
        )
        ops_upgrade_state.validate_upgrade()

        should_delete_platform = self._should_delete_platform()
        should_create_certmanager = self._should_create_certmanager(deleting_platform=should_delete_platform)

        # Add deletion of platform if needed
        if should_delete_platform:
            platform_ext = self.extensions_map.get(EXTENSION_TYPE_PLATFORM)
            if platform_ext:
                ext_queue.append(
                    ExtensionUpgradeState(
                        extension=platform_ext,
                        desired_version_map={},
                        desired_config=None,
                        override=ConfigOverride(),
                        force=True,
                        operation_type=ExtensionOperation.DELETE,
                    )
                )

        # Add creation of certmanager if needed
        if should_create_certmanager:
            cm_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_CM]
            ext_queue.append(
                ExtensionUpgradeState(
                    extension=None,
                    desired_version_map=self.init_version_map.get(cm_moniker, {}),
                    desired_config=self.desired_config_map.get(cm_moniker),
                    override=self.override_map.get(cm_moniker),
                    force=self.force,
                    operation_type=ExtensionOperation.CREATE,
                    extension_type=EXTENSION_TYPE_CM,
                )
            )

        # Add regular extension updates
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            ext_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
            extension = self.extensions_map.get(ext_type)

            # Skip platform if we're deleting it
            if ext_type == EXTENSION_TYPE_PLATFORM and should_delete_platform:
                continue

            # Skip certmanager if we're creating it (already handled above)
            if ext_type == EXTENSION_TYPE_CM and should_create_certmanager:
                continue

            # Use pre-built ops_upgrade_state for IoT Operations extension
            if ext_type == EXTENSION_TYPE_OPS:
                ext_queue.append(ops_upgrade_state)
                continue

            if extension:
                ext_queue.append(
                    ExtensionUpgradeState(
                        extension=extension,
                        desired_version_map=self.init_version_map.get(ext_moniker, {}),
                        desired_config=self.desired_config_map.get(ext_moniker),
                        override=self.override_map.get(ext_moniker),
                        force=self.force,
                    )
                )

        return ext_queue

    def _should_delete_platform(self) -> bool:
        has_platform = bool(self.extensions_map.get(EXTENSION_TYPE_PLATFORM))
        if not has_platform:
            return False

        return self._is_target_version_above_migration_threshold()

    def _should_create_certmanager(self, deleting_platform: bool = False) -> bool:
        """
        Create certmanager extension when:
        1. CertManager extension doesn't exist
        2. Platform extension doesn't exist OR is being deleted
        3. Target IoT Operations version v2
        4. no_cm_install is not True (i.e., cert-manager installation is not disabled)
        """
        if self.no_cm_install:
            return False

        has_certmanager = bool(self.extensions_map.get(EXTENSION_TYPE_CM))
        if has_certmanager:
            return False

        has_platform = bool(self.extensions_map.get(EXTENSION_TYPE_PLATFORM))
        if has_platform and not deleting_platform:
            return False

        return self._is_target_version_above_migration_threshold()

    def _is_target_version_above_migration_threshold(self) -> bool:
        return self._is_target_version_at_least(MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)

    def _get_target_ops_version(self) -> Optional[str]:
        ops_extension = self.extensions_map.get(EXTENSION_TYPE_OPS)
        if not ops_extension:
            return None

        ops_override = self.override_map.get(EXTENSION_MONIKER_OPS) or ConfigOverride()

        # Priority: override > init_version_map > current version
        return (
            ops_override.version
            or self.init_version_map.get(EXTENSION_MONIKER_OPS, {}).get("version")
            or ops_extension.get("properties", {}).get("version")
        )

    def _is_target_version_at_least(self, min_version: str) -> bool:
        target_version = self._get_target_ops_version()
        if not target_version:
            return False

        target_semver = self.semver.parse(target_version)
        min_semver = self.semver.parse(min_version)
        return target_semver >= min_semver


class ExtensionUpgradeState:
    def __init__(
        self,
        extension: Optional[dict],
        desired_version_map: dict,
        desired_config: Optional[Dict[str, str]] = None,
        override: Optional[ConfigOverride] = None,
        force: Optional[bool] = None,
        operation_type: Optional[ExtensionOperation] = None,
        extension_type: Optional[str] = None,
    ):
        self.extension = extension
        self.extension_type = extension_type or (
            extension["properties"]["extensionType"].lower() if extension else None
        )
        self.desired_version_map = desired_version_map
        self.desired_config = desired_config or {}
        self.override = override or ConfigOverride()
        self.config_delta = {}
        self.force = force
        self.operation_type = operation_type or ExtensionOperation.UPDATE
        self._mqtt_migration_config = None
        self.semver = scoped_semver_import()

    @property
    def moniker(self) -> str:
        if self.extension_type:
            return EXTENSION_TYPE_TO_MONIKER_MAP.get(self.extension_type, "unknown")
        return "unknown"

    @property
    def current_version(self) -> Tuple[Optional[str], Optional[str]]:
        if not self.extension:
            return (None, None)
        props = self.extension.get("properties", {})
        return (props.get("version"), props.get("releaseTrain"))

    @property
    def desired_version(self) -> Tuple[Optional[str], Optional[str]]:
        return (
            self.override.version or self.desired_version_map.get("version"),
            self.override.train or self.desired_version_map.get("train"),
        )

    @property
    def provisioning_state(self) -> str:
        if not self.extension:
            return "N/A"
        return self.extension.get("properties", {}).get("provisioningState", "Unknown")

    def is_cli_behind_cluster(self) -> bool:
        if self.operation_type != ExtensionOperation.UPDATE:
            return False

        # An explicit --ops-version, not the built-in default, decides what gets sent.
        if self.override.version:
            return False

        built_in_version = self.desired_version_map.get("version")
        if not built_in_version or not self.current_version[0]:
            return False

        try:
            return self.semver.parse(built_in_version) < self.semver.parse(self.current_version[0])
        except (ValueError, TypeError):
            return False

    def can_upgrade(self) -> bool:
        if self.operation_type in [ExtensionOperation.CREATE, ExtensionOperation.DELETE]:
            return True

        if not self.extension:
            return False

        return any(
            [
                self._has_delta_in_version(),
                self._has_delta_in_train(),
                self._has_delta_in_config(),
                self._has_non_success_state(),
            ]
        )

    def get_patch(self) -> dict:
        """Get patch payload for UPDATE operations"""

        if self.operation_type != ExtensionOperation.UPDATE:
            return {}

        if not self.can_upgrade():
            return {}

        payload = {
            "properties": {},
        }

        target_version = self._validate_and_resolve_version()
        if target_version:
            payload["properties"]["version"] = target_version

        if self._has_delta_in_train():
            payload["properties"]["releaseTrain"] = self.desired_version[1]
        if self._has_delta_in_config():
            config_settings = {}

            # Apply config delta first (respects sync_mode)
            config_settings.update(self.config_delta)

            # Apply user overrides (always overwrites if provided)
            config_settings.update(self.override.config)

            # Add MQTT broker migration config using ADD mode (only new keys)
            if self.moniker == EXTENSION_MONIKER_OPS and self._should_migrate_mqtt_config():
                mqtt_migration_config = self._get_mqtt_migration_config()
                if mqtt_migration_config:
                    current_config = self.extension.get("properties", {}).get("configurationSettings", {})
                    mqtt_delta = calculate_config_delta(
                        current=current_config, target=mqtt_migration_config, sync_mode=ConfigSyncModeType.ADD.value
                    )
                    config_settings.update(mqtt_delta)

            payload["properties"]["configurationSettings"] = config_settings

        return payload

    def validate_upgrade(self) -> None:
        """Validate the upgrade path for this extension.

        Should be called early to ensure upgrade compatibility before
        computing dependent operations (e.g., platform deletion, certmanager creation).

        Raises:
            ValidationError: If the upgrade is not valid (e.g., downgrade, incompatible versions).
        """
        if self.operation_type != ExtensionOperation.UPDATE:
            return

        self._validate_and_resolve_version()

    def _validate_and_resolve_version(self) -> Optional[str]:
        if self._has_delta_in_version():
            self._validate_version_upgrade()
            return self.desired_version[0]

        if self._has_non_success_state():
            reconcile_version = self._get_reconcile_version()
            if not reconcile_version:
                raise ValidationError(
                    f"Unable to determine installed version for {self.moniker} extension. "
                    "Cannot validate upgrade path."
                )
            # A failed extension can have a version but no releaseTrain. Calling _validate_version_upgrade()
            # unconditionally then raises "Unable to determine release train" even though the patch only
            # reapplies the current version and sends no train.
            if self._has_delta_in_train():
                self._validate_version_upgrade(target_version=reconcile_version)
            return reconcile_version

        return None

    def _get_reconcile_version(self) -> Optional[str]:
        if self.current_version[0]:
            return self.current_version[0]
        return self.desired_version[0] if self.force else None

    def _should_migrate_mqtt_config(self) -> bool:
        if not self.extension:
            return False

        # Only for IoT Operations extension
        if self.moniker != EXTENSION_MONIKER_OPS:
            return False

        # Check if target version is >= migration threshold
        if not self.desired_version[0]:
            return False

        target_semver = self.semver.parse(self.desired_version[0])
        min_migration_semver = self.semver.parse(MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)

        return target_semver >= min_migration_semver

    def _get_mqtt_migration_config(self) -> dict:
        """Extract and transform MQTT broker config for v2 migration."""
        # Use cached result if already calculated
        if self._mqtt_migration_config is not None:
            return self._mqtt_migration_config

        # Initialize to empty dict (meaning "checked but no migration needed")
        self._mqtt_migration_config = {}

        if not self.extension:
            return self._mqtt_migration_config

        current_config = self.extension.get("properties", {}).get("configurationSettings", {})

        # Extract existing MQTT broker settings
        mqtt_address = current_config.get("connectors.values.mqttBroker.address")
        token_audience = current_config.get("connectors.values.mqttBroker.serviceAccountTokenAudience")

        if not mqtt_address:
            logger.debug(f"No MQTT address found in {self.moniker} config, skipping migration")
            return self._mqtt_migration_config

        # Parse MQTT address (e.g., "mqtts://aio-broker.azure-iot-operations:18883")
        mqtt_config = {}
        try:
            from urllib.parse import urlparse

            parsed = urlparse(mqtt_address)
            if parsed.hostname:
                mqtt_config["dataFlows.values.tinyKube.mqttBroker.hostName"] = parsed.hostname
                if parsed.port:
                    mqtt_config["dataFlows.values.tinyKube.mqttBroker.port"] = str(parsed.port)
            else:
                logger.debug(f"Could not parse hostname from MQTT address '{mqtt_address}'")

        except Exception as e:
            logger.debug(f"Failed to parse MQTT address '{mqtt_address}': {e}")

        if token_audience:
            mqtt_config["dataFlows.values.tinyKube.mqttBroker.authentication.serviceAccountTokenAudience"] = (
                token_audience
            )

        logger.debug(f"MQTT migration config for {self.moniker}: {mqtt_config}")
        if mqtt_config:
            self._mqtt_migration_config = mqtt_config
        return self._mqtt_migration_config

    def _has_delta_in_version(self) -> bool:
        # Can't have delta if no current version
        if not self.extension:
            return False

        # User explicitly provided a version override - always consider this a delta
        if self.override.version:
            return True

        # Can't compare versions if current version is unknown
        if not self.current_version[0]:
            return False

        # Check if desired version is greater than current
        return self.desired_version[0] and self.semver.parse(self.desired_version[0]) > self.semver.parse(
            self.current_version[0]
        )

    def _has_delta_in_train(self) -> bool:
        # Can't have delta if no extension
        if not self.extension:
            return False

        # User explicitly provided a train override - always consider this a delta
        if self.override.train:
            return True

        # Can't compare trains if current version/train is unknown
        if not self.current_version[0] or not self.current_version[1]:
            return False

        # Check if train differs (only when versions are compatible and no version override)
        return (
            self.desired_version[0]
            and self.desired_version[1]
            and self.semver.parse(self.desired_version[0]) >= self.semver.parse(self.current_version[0])
            and not self.override.version
            and self.desired_version[1].lower() != self.current_version[1].lower()
        )

    def _has_delta_in_config(self) -> bool:
        # Can't have delta if no extension
        if not self.extension:
            return False

        if self.desired_config:
            # Handle None sync_mode by defaulting to FULL
            sync_mode = self.override.config_sync_mode or ConfigSyncModeType.FULL.value

            self.config_delta = calculate_config_delta(
                current=self.extension["properties"].get("configurationSettings", {}),
                target=self.desired_config,
                sync_mode=sync_mode,
            )

        # Check for MQTT migration config changes
        has_mqtt_migration = False
        if self.moniker == EXTENSION_MONIKER_OPS and self._should_migrate_mqtt_config():
            mqtt_migration_config = self._get_mqtt_migration_config()
            if mqtt_migration_config:
                # Just check if any keys would be added (simpler than calculating full delta)
                current_config = self.extension["properties"].get("configurationSettings", {})
                for key in mqtt_migration_config:
                    if key not in current_config:
                        has_mqtt_migration = True
                        break

        return self.override.config or self.config_delta or has_mqtt_migration

    def _has_non_success_state(self) -> bool:
        """
        Determines if the extension has a non-success provisioning state.
        """
        return self.provisioning_state.lower() != PROVISIONING_STATE_SUCCESS.lower()

    def _validate_version_upgrade(self, target_version: Optional[str] = None):
        # Skip validation for CREATE/DELETE operations
        if self.operation_type in [ExtensionOperation.CREATE, ExtensionOperation.DELETE]:
            return

        if self.force:
            return

        target_version = target_version or self.desired_version[0]

        # Validate required fields are present
        if not self.current_version[0]:
            raise ValidationError(
                f"Unable to determine installed version for {self.moniker} extension. Cannot validate upgrade path."
            )
        if not target_version:
            raise ValidationError(
                f"Unable to determine target version for {self.moniker} extension. Cannot validate upgrade path."
            )
        if not self.current_version[1]:
            raise ValidationError(
                f"Unable to determine release train for installed {self.moniker} extension. "
                "Cannot validate upgrade path."
            )
        if not self.desired_version[1]:
            raise ValidationError(
                f"Unable to determine target release train for {self.moniker} extension. "
                "Cannot validate upgrade path."
            )

        parsed_current = self.semver.parse(self.current_version[0])
        parsed_desired = self.semver.parse(target_version)

        current_is_preview = self.current_version[1].lower() != "stable"
        desired_is_preview = self.desired_version[1].lower() != "stable"

        # Check for downgrade
        if parsed_desired < parsed_current:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {target_version} version is a downgrade which is not supported."
            )

        if self.moniker != EXTENSION_MONIKER_OPS:
            return

        # Check version compatibility (within 2 minor versions)
        if parsed_desired.major != parsed_current.major:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {target_version} version is incompatible (different major version)."
            )

        minor_diff = parsed_desired.minor - parsed_current.minor
        if minor_diff > 2:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {target_version} version is incompatible (more than 2 minor versions ahead)."
            )

        min_v2_semver_broker_upgrade = self.semver.parse(MIN_INSTANCE_VERSION_V1_FOR_V2_UPGRADE)
        min_v2_semver = self.semver.parse(MIN_INSTANCE_VERSION_V2)
        if parsed_current < min_v2_semver_broker_upgrade and parsed_desired >= min_v2_semver:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {target_version} version is incompatible "
                f"(min compatible upgrade version {min_v2_semver_broker_upgrade}).\n"
                f"Please first upgrade to at least {min_v2_semver_broker_upgrade}/AIO2506. "
                "See https://aka.ms/aio-versions for version details."
            )

        if current_is_preview or desired_is_preview:
            if parsed_current != parsed_desired or self.current_version[1].lower() != self.desired_version[1].lower():
                raise ValidationError(
                    f"Installed {self.moniker} extension is on train {self.current_version[1]}.\n"
                    f"Desired version would be on train {self.desired_version[1]}.\n"
                    f"Upgrades to or from non-stable release trains are not supported."
                )


def calculate_config_delta(current: Dict[str, str], target: Dict[str, str], sync_mode: Optional[str] = None) -> dict:
    """Calculate configuration delta between current and target state.

    Args:
        current: Current configuration settings
        target: Target configuration settings
        sync_mode: How to sync config (FULL, ADD, NONE). Defaults to FULL if None.

    Returns:
        Dictionary of configuration changes to apply
    """
    if sync_mode is None:
        sync_mode = ConfigSyncModeType.FULL.value

    delta = {}

    if sync_mode == ConfigSyncModeType.NONE.value:
        return delta

    if sync_mode == ConfigSyncModeType.FULL.value:
        # In FULL mode, update/delete existing keys to match target
        for key in current:
            if key in target and current[key] != target[key]:
                delta[key] = target[key]
            elif key not in target:
                delta[key] = None  # Mark for deletion

    # In both FULL and ADD modes, add new keys from target
    if sync_mode in [ConfigSyncModeType.FULL.value, ConfigSyncModeType.ADD.value]:
        for key in target:
            if key not in current:
                delta[key] = target[key]

    return delta
