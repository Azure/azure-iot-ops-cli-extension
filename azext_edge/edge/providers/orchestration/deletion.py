# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from sys import maxsize
from typing import TYPE_CHECKING, Dict, List, Optional

from knack.log import get_logger
from rich import print
from rich.console import Console, NewLine
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.prompt import Confirm
from rich.table import Table

from ...util.az_client import get_resource_client, wait_for_terminal_states
from .resource_map import IoTOperationsResource, IoTOperationsResourceMap

logger = get_logger(__name__)

console = Console()

if TYPE_CHECKING:
    from azure.core.polling import LROPoller


def delete_ops_resources(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    force: Optional[bool] = None,
):
    manager = DeletionManager(
        cmd=cmd, cluster_name=cluster_name, resource_group_name=resource_group_name, no_progress=no_progress
    )
    manager.do_work(confirm_yes=confirm_yes, force=force)


class DeletionManager:
    def __init__(
        self,
        cmd,
        cluster_name: str,
        resource_group_name: str,
        no_progress: Optional[bool] = None,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.resource_map = IoTOperationsResourceMap(
            cmd=cmd, cluster_name=cluster_name, resource_group_name=resource_group_name
        )
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
        self._delete_task = self._progress_bar.add_task("Work.", total=None)

    def do_work(self, confirm_yes: Optional[bool] = None, force: Optional[bool] = None):
        if self._render_progress:
            self._display_resource_tree()

        should_delete = True
        if not confirm_yes:
            should_delete = Confirm.ask("Continue?")

        if not should_delete:
            logger.warning("Deletion cancelled.")
            return

        if not force:
            if not self.resource_map.connected_cluster.connected:
                logger.warning(
                    "The cluster is not connected to Azure. Deletion cancelled. "
                    "Use --force to continue anyway. Not recommended."
                )
                return

        self._process()

    def _display_resource_tree(self):
        print(self.resource_map.build_tree())

    def _render_progress_display(self, description: str):
        grid = Table.grid(expand=False)
        grid.add_column()
        grid.add_row(NewLine(1))
        grid.add_row(description)
        grid.add_row(NewLine(1))
        grid.add_row(self._progress_bar)
        self._live.update(grid, refresh=True)

        if self._render_progress and not self._live.is_started:
            self._live.start(True)

    def _process(self):
        todo_extensions = self.resource_map.extensions
        todo_custom_locations = self.resource_map.custom_locations
        todo_resource_sync_rules = []
        todo_resources = []

        for cl in todo_custom_locations:
            todo_resource_sync_rules.extend(self.resource_map.get_resource_sync_rules(cl.resource_id))
            todo_resources.extend(self.resource_map.get_resources(cl.resource_id))

        # delete_batch_result[0].status() == "Succeeded"
        batched_work = self._batch_resources(
            resources=todo_resources,
            resource_sync_rules=todo_resource_sync_rules,
            custom_locations=todo_custom_locations,
            extensions=todo_extensions,
        )
        if not batched_work:
            logger.warning("Nothing to delete :)")
            return

        try:
            for batches_key in batched_work:
                self._render_progress_display(f"[red]Deleting {batches_key}...")
                for batch in batched_work[batches_key]:
                    # TODO: @digimaun - Show summary as result
                    self._delete_batch(batch)
        finally:
            self._live.stop()

    def _batch_resources(
        self,
        resources: List[IoTOperationsResource] = None,
        resource_sync_rules: List[IoTOperationsResource] = None,
        custom_locations: List[IoTOperationsResource] = None,
        extensions: List[IoTOperationsResource] = None,
    ) -> Dict[str, List[List[IoTOperationsResource]]]:
        batched_work: Dict[str, List[List[IoTOperationsResource]]] = {}

        if resources:
            resource_batches: List[List[IoTOperationsResource]] = []
            last_segments = maxsize
            current_batch = []
            for resource in resources:
                current_segments = resource.segments
                if current_segments < last_segments and current_batch:
                    resource_batches.append(current_batch)
                    current_batch = []
                current_batch.append(resource)
                last_segments = current_segments
            if current_batch:
                resource_batches.append(current_batch)
            batched_work["resources"] = resource_batches

        if resource_sync_rules:
            batched_work["resource sync rules"] = [resource_sync_rules]
        if custom_locations:
            batched_work["custom locations"] = [custom_locations]
        if extensions:
            batched_work["extensions"] = [extensions]

        return batched_work

    def _delete_batch(self, resource_batch: List[IoTOperationsResource]) -> List["LROPoller"]:
        return wait_for_terminal_states(
            *[
                self.resource_client.resources.begin_delete_by_id(
                    resource_id=resource.resource_id, api_version=resource.api_version
                )
                for resource in resource_batch
            ]
        )
