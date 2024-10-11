# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from sys import maxsize
from time import sleep
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from azure.cli.core.azclierror import ArgumentUsageError
from knack.log import get_logger
from rich import print
from rich.console import NewLine
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table

from ...util.az_client import get_resource_client, wait_for_terminal_states
from ...util.common import should_continue_prompt
from .resource_map import IoTOperationsResource, IoTOperationsResourceMap
from .resources import Instances

logger = get_logger(__name__)


if TYPE_CHECKING:
    from azure.core.polling import LROPoller


INSTANCE_7_API = "2024-08-15-preview"


def upgrade_ops_resources(
    cmd,
    resource_group_name: str,
    instance_name: Optional[str] = None,
    cluster_name: Optional[str] = None,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    force: Optional[bool] = None,
):
    manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
    )
    manager.do_work(confirm_yes=confirm_yes, force=force)


# TODO: see if dependencies need to be upgraded (broker, opcua etc)
# keeping this separate for easier removal once no longer needed
class UpgradeManager:
    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: Optional[str] = None,
        cluster_name: Optional[str] = None,
        no_progress: Optional[bool] = None,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.instance_name = instance_name
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.instances = Instances(self.cmd)
        self.subscription_id = get_subscription_id(cli_ctx=cmd.cli_ctx)
        self.resource_client = get_resource_client(self.subscription_id)

        self._render_progress = not no_progress
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=self._render_progress)
        self._progress_bar = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
        )
        self._progress_shown = False

    def do_work(self, confirm_yes: Optional[bool] = None, force: Optional[bool] = None):
        self.resource_map = self._get_resource_map()
        # Ensure cluster exists with existing resource_map pattern.
        self.resource_map.connected_cluster.resource
        self.resource_map.refresh_resource_state()
        self._display_resource_tree()

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        self._process(force=force)

    def _get_resource_map(self) -> IoTOperationsResourceMap:
        if not any([self.cluster_name, self.instance_name]):
            raise ArgumentUsageError("Please provide either an instance name or cluster name.")

        if not self.instance_name:
            resource_map = IoTOperationsResourceMap(
                cmd=self.cmd,
                cluster_name=self.cluster_name,
                resource_group_name=self.resource_group_name,
                defer_refresh=True,
            )
            self.instance_name = "WHEREDOESPAYMAUNGETTHENAME"

        self.require_instance_upgrade = True
        # try with 2024-08-15-preview -> it is m2
        try:
            self.instance = self.resource_client.resources.get(
                resource_group_name=self.resource_group_name,
                parent_resource_path="",
                resource_provider_namespace="Microsoft.IoTOperations",
                resource_type="instances",
                resource_name=self.instance_name,
                api_version=INSTANCE_7_API
            )
            return self.instances.get_resource_map(self.instance)
        except Exception as e:
            import pdb; pdb.set_trace()
            self.require_instance_upgrade = False
            # todo what type is e
            pass

        # try with 2024-09-15-preview -> it is m3 already
        try:
            self.instance = self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
            return self.instances.get_resource_map(self.instance)
        except Exception as e:
            # todo make sure e is something
            raise ArgumentUsageError(f"Cannot upgrade instance {self.instance_name}, please delete your instance, including dependencies, and reinstall.")

    def _display_resource_tree(self):
        if self._render_progress:
            print(self.resource_map.build_tree(hide_extensions=True, category_color="red"))

    def _render_display(self, description: str):
        if self._render_progress:
            grid = Table.grid(expand=False)
            grid.add_column()
            grid.add_row(NewLine(1))
            grid.add_row(description)
            grid.add_row(NewLine(1))
            grid.add_row(self._progress_bar)

            if not self._progress_shown:
                self._task_id = self._progress_bar.add_task(description="Work.", total=None)
                self._progress_shown = True
            self._live.update(grid, refresh=True)

            if not self._live.is_started:
                self._live.start(True)

    def _stop_display(self):
        if self._render_progress and self._live.is_started:
            if self._progress_shown:
                self._progress_bar.update(self._task_id, description="Done.")
                sleep(0.5)
            self._live.stop()

    def _process(self, force: bool = False):
        if self.require_instance_upgrade:
            # keep the schema reg id
            extension_type = "microsoft.iotoperations"
            aio_extension = self.resource_map.connected_cluster.get_extensions_by_type(extension_type)
            import pdb; pdb.set_trace()
            extension_props = aio_extension[extension_type]["properties"]
            sr_id = extension_props["configurationSettings"]["schemaRegistry.values.resourceId"]

            self.instance.pop("systemData", None)
            inst_props = self.instance["properties"]
            inst_props["schemaRegistryRef"] = sr_id
            inst_props["version"] = extension_props["currentVersion"]
            inst_props.pop("schemaRegistryNamespace", None)
            inst_props.pop("components", None)

        # Do the upgrade, the schema reg id may get lost
        self.resource_map.connected_cluster.update_all_extensions()

        if self.require_instance_upgrade:
            # update the instance
            result = self.instances.iotops_mgmt_client.instance.begin_create_or_update(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                resource=self.instance
            )
            return wait_for_terminal_states(result)
