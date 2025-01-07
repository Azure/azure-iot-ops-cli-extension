# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from json import dumps
from typing import Dict, List, Optional, Tuple

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger
from packaging import version
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

from ...util import parse_kvp_nargs
from ...util.common import should_continue_prompt
from .common import (
    EXTENSION_MONIKER_TO_ALIAS_MAP,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_TO_MONIKER_MAP,
)
from .resources import Instances
from .targets import InitTargets

logger = get_logger(__name__)

DEFAULT_CONSOLE = Console()


def upgrade_ops_instance(
    cmd,
    resource_group_name: str,
    instance_name: str,
    no_progress: Optional[bool] = None,
    confirm_yes: Optional[bool] = None,
    **kwargs,
):
    upgrade_manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
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
    ):
        self.cmd = cmd
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.no_progress = no_progress
        self.instances = Instances(self.cmd)
        self.resource_map = self.instances.get_resource_map(
            self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
        )
        self.targets = InitTargets(
            cluster_name=self.resource_map.connected_cluster.cluster_name, resource_group_name=resource_group_name
        )
        self.init_version_map: Dict[str, dict] = {
            **self.targets.get_extension_versions(),
            **self.targets.get_extension_versions(False),
        }

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
                init_version_map=self.init_version_map,
                override_map=build_override_map(**override_kwargs),
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
            upgradeable_extensions: List["ExtensionUpgradeState"] = [
                ext for ext in upgrade_state.extension_upgrades if ext.can_upgrade()
            ]
            return_payload = []
            upgrade_task = progress.add_task("Applying changes...", total=len(upgradeable_extensions))
            for ext in upgradeable_extensions:
                updated = self.resource_map.connected_cluster.clusters.extensions.update_cluster_extension(
                    resource_group_name=self.resource_group_name,
                    cluster_name=self.resource_map.connected_cluster.cluster_name,
                    extension_name=ext.extension["name"],
                    update_payload=ext.get_patch(),
                    retry_total=0,
                )
                return_payload.append(updated)
                progress.advance(upgrade_task)

            return return_payload


def render_upgrade_table(upgrade_state: "ClusterUpgradeState"):
    table = get_default_table()
    for ext in upgrade_state.extension_upgrades:
        patch_payload = ext.get_patch()
        if not patch_payload:
            continue

        patch_payload = JSON(dumps(patch_payload))

        table.add_row(
            f"{ext.moniker}",
            f"{ext.current_version[0]} \\[{ext.current_version[1]}]",
            f"{ext.desired_version[0]} \\[{ext.desired_version[1]}]",
            patch_payload,
        )
        table.add_section()

    DEFAULT_CONSOLE.print(table)


def build_override_map(**override_kwargs) -> Dict[str, "ConfigOverride"]:
    result_map = {}
    for moniker in EXTENSION_MONIKER_TO_ALIAS_MAP:
        alias = EXTENSION_MONIKER_TO_ALIAS_MAP[moniker]
        config_override = ConfigOverride(
            config=override_kwargs.get(f"{alias}_config"),
            version=override_kwargs.get(f"{alias}_version"),
            train=override_kwargs.get(f"{alias}_train"),
        )
        if not config_override.is_empty:
            result_map[moniker] = config_override

    return result_map


class ConfigOverride:
    def __init__(
        self,
        config: Optional[dict] = None,
        version: Optional[str] = None,
        train: Optional[str] = None,
    ):
        self.config = parse_kvp_nargs(config)
        self.version = version
        self.train = train

    @property
    def is_empty(self):
        return not any([self.config, self.version, self.train])


class ClusterUpgradeState:
    def __init__(
        self,
        extensions_map: Dict[str, dict],
        init_version_map: Dict[str, dict],
        override_map: Dict[str, "ConfigOverride"],
    ):
        self.extensions_map = extensions_map
        self.init_version_map = init_version_map
        self.override_map = override_map
        self.extension_upgrades = self.refresh_upgrade_state()

    def has_upgrades(self) -> bool:
        return any(ext_state.can_upgrade() for ext_state in self.extension_upgrades)

    def refresh_upgrade_state(self) -> List["ExtensionUpgradeState"]:
        ext_queue: List["ExtensionUpgradeState"] = []

        # TODO @digimaun - deterine further pre-checks.
        if not self.extensions_map.get(EXTENSION_TYPE_OPS):
            raise ValidationError(
                "The cluster backing the instance has an invalid state. IoT Operations extension not detected."
            )

        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            ext_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
            extension = self.extensions_map.get(ext_type)
            if extension:
                ext_queue.append(
                    ExtensionUpgradeState(
                        extension=extension,
                        desired_version_map=self.init_version_map.get(ext_moniker, {}),
                        override=self.override_map.get(ext_moniker),
                    )
                )
        return ext_queue


class ExtensionUpgradeState:
    def __init__(self, extension: dict, desired_version_map: dict, override: Optional[ConfigOverride] = None):
        self.extension = extension
        self.desired_version_map = desired_version_map
        self.override = override or ConfigOverride()

    @property
    def current_version(self) -> Tuple[str, str]:
        return (self.extension["properties"]["version"], self.extension["properties"]["releaseTrain"])

    @property
    def desired_version(self) -> Tuple[str, str]:
        return (
            self.override.version or self.desired_version_map.get("version"),
            self.override.train or self.desired_version_map.get("train"),
        )

    @property
    def moniker(self) -> str:
        return EXTENSION_TYPE_TO_MONIKER_MAP[self.extension["properties"]["extensionType"].lower()]

    def can_upgrade(self) -> bool:
        return any(
            [
                self._has_delta_in_version(),
                self._has_delta_in_train(),
                self._has_delta_in_config(),
            ]
        )

    def get_patch(self) -> dict:
        if not self.can_upgrade():
            return {}

        payload = {
            "properties": {},
        }

        if self._has_delta_in_version():
            payload["properties"]["version"] = self.desired_version[0]
        if self._has_delta_in_train():
            payload["properties"]["releaseTrain"] = self.desired_version[1]
        if self._has_delta_in_config():
            payload["properties"]["configurationSettings"] = self.override.config

        return payload

    def _has_delta_in_version(self) -> bool:
        return bool(self.override.version) or (
            self.desired_version[0] and version.parse(self.desired_version[0]) > version.parse(self.current_version[0])
        )

    def _has_delta_in_train(self) -> bool:
        return bool(self.override.train) or (
            self.desired_version[1] and self.desired_version[1].lower() != self.current_version[1].lower()
        )

    def _has_delta_in_config(self) -> bool:
        return bool(self.override.config)


def get_default_table() -> Table:
    table = Table(
        box=box.ROUNDED,
        highlight=True,
        expand=False,
        title="The Upgrade Story",
    )
    table.add_column(
        "Extension",
    )
    table.add_column("Current Version")
    table.add_column("Desired Version")
    table.add_column("Patch Payload")

    return table
