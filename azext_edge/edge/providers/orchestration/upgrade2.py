# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from json import dumps
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import Console
from rich.json import JSON
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table, box

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
    MIN_INSTANCE_VERSION_V1_FOR_V2_UPGRADE,
    MIN_INSTANCE_VERSION_V2,
    ConfigSyncModeType,
)
from .resources import Instances, RegistryEndpoints
from .targets import InitTargets

logger = get_logger(__name__)

console = Console()


DEFAULT_REGISTRY_HOST = "mcr.microsoft.com"


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
    **kwargs,
):
    upgrade_manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        adr_namespace_resource_id=adr_namespace_resource_id,
        no_progress=no_progress,
        force=force,
    )

    upgrade_state = upgrade_manager.analyze_cluster(**kwargs)

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
    ):
        self.cmd = cmd
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.no_progress = no_progress
        self.force = force
        self.instances = Instances(self.cmd)
        self.registry_endpoints = RegistryEndpoints(self.cmd)
        self.instance_record = self.instances.show(
            name=self.instance_name, resource_group_name=self.resource_group_name
        )
        self.resource_map = self.instances.get_resource_map(self.instance_record)
        self.targets = InitTargets(
            cluster_name=self.resource_map.connected_cluster.cluster_name,
            resource_group_name=resource_group_name,
            adr_namespace_resource_id=adr_namespace_resource_id,
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
                force=self.force,
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

            if upgrade_state.instance_upgrade:
                total += 1

            if upgrade_state.registry_endpoint_needed:
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
                    except HttpResponseError as e:
                        progress.stop()
                        logger.error(f"Correlation Id for failed {op_type.value} operation: {correlation_id}")
                        raise e

            if upgrade_state.instance_upgrade:
                try:
                    instance_result = self._apply_instance_update(headers)
                    return_payload.append(instance_result)
                    progress.advance(task)
                except HttpResponseError as e:
                    progress.stop()
                    logger.error(f"Correlation Id for failed instance update: {correlation_id}")
                    raise e

            if upgrade_state.registry_endpoint_needed:
                try:
                    registry_result = self._create_default_registry_endpoint(headers)
                    return_payload.append(registry_result)
                    progress.advance(task)
                except HttpResponseError as e:
                    progress.stop()
                    logger.error(f"Correlation Id for failed registry endpoint creation: {correlation_id}")
                    raise e

            return return_payload

    def _apply_instance_update(self, headers: dict) -> dict:
        return self.instances.update(
            name=self.instance_name,
            resource_group_name=self.resource_group_name,
            instance=self.instance_record,
            adr_namespace_resource_id=self.targets.adr_namespace_resource_id,
            headers=headers,
            no_status=True,  # Disable status since we're already in a Progress context
        )

    def _create_default_registry_endpoint(self, headers: dict) -> dict:
        return self.registry_endpoints.add(
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
            return self.resource_map.connected_cluster.clusters.extensions.update_cluster_extension(
                resource_group_name=self.resource_group_name,
                cluster_name=cluster_name,
                extension_name=ext.extension["name"],
                update_payload=ext.get_patch(),
                headers=headers,
            )

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
    return f"{version} \\[{train}]"


def format_extension_row(ext: "ExtensionUpgradeState") -> Tuple[str, str, str, any]:
    """Format an extension row for the upgrade table.
    Returns: (current_version, desired_version, action, patch_payload)
    """
    # Add status indicator for non-succeeded states
    status_indicator = ""
    if ext.provisioning_state.lower() != "succeeded":
        status_indicator = f" [yellow]({ext.provisioning_state})[/yellow]"

    if ext.operation_type == ExtensionOperation.DELETE:
        current = format_version_with_train(ext.current_version[0], ext.current_version[1]) + status_indicator
        desired = "[red]Remove[/red]"
        action = f"[red]Delete {ext.moniker}[/red]"
        return current, desired, action

    elif ext.operation_type == ExtensionOperation.CREATE:
        current = "[dim]Not Installed[/dim]"
        version = ext.desired_version[0] or "N/A"
        train = ext.desired_version[1] or "N/A"
        desired = f"[green]{format_version_with_train(version, train)}[/green]"
        action = f"[green]Install {ext.moniker}[/green]"
        return current, desired, action

    else:  # UPDATE
        current = format_version_with_train(ext.current_version[0], ext.current_version[1]) + status_indicator
        desired = format_version_with_train(ext.desired_version[0], ext.desired_version[1])
        patch = ext.get_patch()

        action = JSON(dumps(patch)) if patch else None
        return current, desired, action


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


def render_upgrade_table(upgrade_state: "ClusterUpgradeState"):
    table = get_default_table()

    for ext in upgrade_state.extension_upgrades:
        if not ext.can_upgrade():
            continue

        row_data = format_extension_row(ext)
        if row_data[2] is None:  # Skip if no action
            continue

        table.add_row(ext.moniker, *row_data)
        table.add_section()

    # Add instance update row if needed
    if upgrade_state.instance_upgrade:
        adr_id = upgrade_state.adr_namespace_resource_id
        adr_name = adr_id.split("/")[-1] if "/" in adr_id else adr_id

        # Show current state based on what's configured
        namespace_ref = upgrade_state.instance.get("properties", {}).get("adrNamespaceRef")
        if namespace_ref and namespace_ref.get("resourceId"):
            current_adr_id = namespace_ref.get("resourceId")
            current_adr_name = current_adr_id.split("/")[-1] if "/" in current_adr_id else current_adr_id
            current_state = f"[dim]Linked to {current_adr_name}[/dim]"
        else:
            current_state = "[dim]No ADR namespace[/dim]"

        table.add_row(
            "instance",
            current_state,
            f"[green]Link {adr_name}[/green]",
            JSON(dumps({"properties": {"adrNamespaceRef": {"resourceId": f"*/{adr_name}"}}})),
        )
        table.add_section()

    # Add registry endpoint row if needed
    if upgrade_state.registry_endpoint_needed:
        table.add_row(
            "default registry",
            "[dim]Not configured[/dim]",
            "[green]Create 'default'[/green]",
            JSON(
                dumps(
                    {
                        "name": "default",
                        "properties": {
                            "host": DEFAULT_REGISTRY_HOST,
                            "authentication": {"method": "Anonymous", "anonymousSettings": {}},
                        },
                    }
                )
            ),
        )
        table.add_section()

    console.print(table)


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

    def is_empty(self):
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
        force: Optional[bool] = None,
    ):
        self.extensions_map = extensions_map
        self.init_version_map = init_version_map
        self.desired_config_map = desired_config_map
        self.override_map = override_map
        self.instance = instance
        self.adr_namespace_resource_id = adr_namespace_resource_id
        self.registry_endpoint_check = registry_endpoint_check
        self.force = force
        self.semver = scoped_semver_import()
        self.extension_upgrades = self._refresh_upgrade_state()
        self.instance_upgrade = self._check_instance_upgrade()
        self.registry_endpoint_needed = self._check_registry_endpoint_needed()

    def has_upgrades(self) -> bool:
        return (
            any(ext_state.can_upgrade() for ext_state in self.extension_upgrades)
            or bool(self.instance_upgrade)
            or bool(self.registry_endpoint_needed)
        )

    def _check_instance_upgrade(self) -> bool:
        """Check if instance needs ADR namespace update.

        Returns True if:
        1. During v2 migration and instance needs ADR namespace (required)
        2. User provided --ns-resource-id to update/set ADR namespace (optional update)

        Raises ValidationError if ADR namespace is required but not provided.
        """
        if not self.instance:
            return False

        namespace_ref = self.instance.get("properties", {}).get("adrNamespaceRef")
        has_adr_namespace = namespace_ref and namespace_ref.get("resourceId")

        # If user provided an ADR namespace, check if update is needed
        if self.adr_namespace_resource_id:
            # Update needed if no current ADR or different from provided
            current_adr_id = namespace_ref.get("resourceId") if namespace_ref else None
            return not current_adr_id or current_adr_id != self.adr_namespace_resource_id

        # If no ADR namespace provided, check if it's required for v2 migration
        # Check if we're doing a v2 migration (platform -> certmanager)
        is_v2_migration = self._is_target_version_above_migration_threshold()

        if is_v2_migration and not has_adr_namespace:
            raise ValidationError(
                "The instance requires an ADR namespace for migration to v2.\n"
                "Please provide a value for --ns-resource-id."
            )

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

    def _refresh_upgrade_state(self) -> List["ExtensionUpgradeState"]:
        ext_queue: List["ExtensionUpgradeState"] = []

        if not self.extensions_map.get(EXTENSION_TYPE_OPS):
            raise ValidationError(
                "The cluster backing the instance has an invalid state. IoT Operations extension not detected."
            )

        # Check what operations we need
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
        """
        has_certmanager = bool(self.extensions_map.get(EXTENSION_TYPE_CM))
        if has_certmanager:
            return False

        has_platform = bool(self.extensions_map.get(EXTENSION_TYPE_PLATFORM))
        if has_platform and not deleting_platform:
            return False

        return self._is_target_version_above_migration_threshold()

    def _is_target_version_above_migration_threshold(self) -> bool:
        ops_extension = self.extensions_map.get(EXTENSION_TYPE_OPS)
        if not ops_extension:
            return False

        ops_override = self.override_map.get(EXTENSION_MONIKER_OPS, ConfigOverride())

        # Priority: override > init_version_map > current version
        target_version = (
            ops_override.version
            or self.init_version_map.get(EXTENSION_MONIKER_OPS, {}).get("version")
            or ops_extension.get("properties", {}).get("version")
        )

        if not target_version:
            return False

        target_semver = self.semver.parse(target_version)
        min_migration_semver = self.semver.parse(MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
        return target_semver >= min_migration_semver


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

        if self._has_delta_in_version() or self._has_non_success_state():
            self._validate_version_upgrade()
            payload["properties"]["version"] = self.desired_version[0]
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
        # Can't have delta if no current version (CREATE/DELETE operations)
        if not self.extension or not self.current_version[0]:
            return False

        return bool(self.override.version) or (
            self.desired_version[0]
            and self.semver.parse(self.desired_version[0]) > self.semver.parse(self.current_version[0])
        )

    def _has_delta_in_train(self) -> bool:
        # Can't have delta if no current version
        if not self.extension or not self.current_version[0]:
            return False

        return bool(self.override.train) or (
            self.desired_version[0]
            and self.current_version[0]
            and self.semver.parse(self.desired_version[0]) >= self.semver.parse(self.current_version[0])
            and not self.override.version
            and self.desired_version[1]
            and self.current_version[1]
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
        return self.provisioning_state.lower() not in {"succeeded"}

    def _validate_version_upgrade(self):
        # Skip validation for CREATE/DELETE operations
        if self.operation_type in [ExtensionOperation.CREATE, ExtensionOperation.DELETE]:
            return

        if self.force:
            return

        # Need both versions to validate
        if not self.current_version[0] or not self.desired_version[0]:
            return

        parsed_current = self.semver.parse(self.current_version[0])
        parsed_desired = self.semver.parse(self.desired_version[0])

        current_is_preview = self.current_version[1].lower() != "stable"
        desired_is_preview = self.desired_version[1].lower() != "stable"

        # Check for downgrade
        if parsed_desired < parsed_current:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {self.desired_version[0]} version is a downgrade which is not supported."
            )

        if self.moniker != EXTENSION_MONIKER_OPS:
            return

        # Check version compatibility (within 2 minor versions)
        if parsed_desired.major != parsed_current.major:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {self.desired_version[0]} version is incompatible (different major version)."
            )

        minor_diff = parsed_desired.minor - parsed_current.minor
        if minor_diff > 2:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {self.desired_version[0]} version is incompatible (more than 2 minor versions ahead)."
            )

        min_v2_semver_broker_upgrade = self.semver.parse(MIN_INSTANCE_VERSION_V1_FOR_V2_UPGRADE)
        min_v2_semver = self.semver.parse(MIN_INSTANCE_VERSION_V2)
        if parsed_current < min_v2_semver_broker_upgrade and parsed_desired >= min_v2_semver:
            raise ValidationError(
                f"Installed {self.moniker} extension version is {self.current_version[0]}.\n"
                f"The desired {self.desired_version[0]} version is incompatible "
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
