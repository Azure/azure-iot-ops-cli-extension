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
from .resources import Instances
from .targets import InitTargets

logger = get_logger(__name__)

console = Console()


class ExtensionOperation(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


def upgrade_ops_instance(
    cmd,
    resource_group_name: str,
    instance_name: str,
    no_progress: Optional[bool] = None,
    confirm_yes: Optional[bool] = None,
    force: Optional[bool] = None,
    **kwargs,
):
    upgrade_manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
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
        no_progress: Optional[bool] = None,
        force: Optional[bool] = None,
    ):
        self.cmd = cmd
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.no_progress = no_progress
        self.force = force
        self.instances = Instances(self.cmd)
        self.resource_map = self.instances.get_resource_map(
            self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
        )
        self.targets = InitTargets(
            cluster_name=self.resource_map.connected_cluster.cluster_name, resource_group_name=resource_group_name
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
                force=self.force,
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

            return return_payload

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


def render_upgrade_table(upgrade_state: "ClusterUpgradeState"):
    table = get_default_table()

    for ext in upgrade_state.extension_upgrades:
        if not ext.can_upgrade():
            continue

        # Format versions based on operation
        if ext.operation_type == ExtensionOperation.DELETE:
            current_version = "-"
            if ext.current_version[0] and ext.current_version[1]:
                current_version = f"{ext.current_version[0]} [{ext.current_version[1]}]"
            desired_version = "[red]Remove[/red]"
            # More descriptive message
            patch_payload = f"[red]Delete {ext.moniker} extension[/red]"
        elif ext.operation_type == ExtensionOperation.CREATE:
            current_version = "[dim]Not Installed[/dim]"
            version = ext.desired_version[0] or "latest"
            train = ext.desired_version[1] or "stable"
            # Add green color for creation
            desired_version = f"[green]{version} [{train}][/green]"
            # More descriptive message
            patch_payload = f"[green]Create {ext.moniker} extension[/green]"
        else:  # UPDATE
            current_v = ext.current_version[0] or "unknown"
            current_t = ext.current_version[1] or "unknown"
            desired_v = ext.desired_version[0] or current_v
            desired_t = ext.desired_version[1] or current_t
            current_version = f"{current_v} [{current_t}]"
            desired_version = f"{desired_v} [{desired_t}]"
            patch_payload = ext.get_patch()
            if patch_payload:
                patch_payload = JSON(dumps(patch_payload))
            else:
                continue

        table.add_row(
            ext.moniker,
            current_version,
            desired_version,
            ext.provisioning_state,
            patch_payload,
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
        force: Optional[bool] = None,
    ):
        self.extensions_map = extensions_map
        self.init_version_map = init_version_map
        self.desired_config_map = desired_config_map
        self.override_map = override_map
        self.force = force
        self.semver = scoped_semver_import()
        self.extension_upgrades = self.refresh_upgrade_state()

    def has_upgrades(self) -> bool:
        return any(ext_state.can_upgrade() for ext_state in self.extension_upgrades)

    def refresh_upgrade_state(self) -> List["ExtensionUpgradeState"]:
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
            config_settings = self.config_delta
            config_settings.update(self.override.config)
            payload["properties"]["configurationSettings"] = config_settings

        return payload

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
            self.config_delta = calculate_config_delta(
                current=self.extension["properties"].get("configurationSettings", {}),
                target=self.desired_config,
                sync_mode=self.override.config_sync_mode,
            )
        return bool(self.override.config) or bool(self.config_delta)

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


def get_default_table() -> Table:
    table = Table(
        box=box.ROUNDED,
        highlight=True,
        expand=False,
        title="The Upgrade Story",
        min_width=79,
    )
    table.add_column("Extension")
    table.add_column("Current Version")
    table.add_column("Desired Version")
    table.add_column("Provisioning State")
    table.add_column("Action")

    return table


def calculate_config_delta(
    current: Dict[str, str], target: Dict[str, str], sync_mode: str = ConfigSyncModeType.FULL.value
) -> dict:
    delta = {}
    if sync_mode == ConfigSyncModeType.NONE.value:
        return delta

    if sync_mode == ConfigSyncModeType.FULL.value:
        for key in current:
            if key in target and current[key] != target[key]:
                delta[key] = target[key]
            elif key not in target:
                delta[key] = None

    for key in target:
        if key not in current:
            delta[key] = target[key]

    return delta
