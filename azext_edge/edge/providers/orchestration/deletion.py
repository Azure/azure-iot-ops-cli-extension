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

from azext_edge.edge.providers.orchestration.work import IOT_OPS_EXTENSION_TYPE

from ...util.az_client import get_resource_client, wait_for_terminal_states
from ...util.common import should_continue_prompt
from .resource_map import IoTOperationsResource, IoTOperationsResourceMap
from .resources import Instances

logger = get_logger(__name__)


if TYPE_CHECKING:
    from azure.core.polling import LROPoller


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
        self.instances = Instances(self.cmd)
        self.include_dependencies = include_dependencies
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

        if self.instance_name:
            self.instance = self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
            return self.instances.get_resource_map(self.instance)

        return IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=self.cluster_name,
            resource_group_name=self.resource_group_name,
            defer_refresh=True,
        )

    def _display_resource_tree(self):
        if self._render_progress:
            print(self.resource_map.build_tree(hide_extensions=not self.include_dependencies, category_color="red"))

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
        # instance delete should always delete the extension too
        aio_ext = self.resource_map.connected_cluster.get_extensions_by_type(IOT_OPS_EXTENSION_TYPE).get(
            IOT_OPS_EXTENSION_TYPE
        )
        aio_ext_id = aio_ext["id"] if aio_ext else None
        aio_ext_obj = next((_ for _ in self.resource_map.extensions if _.resource_id == aio_ext_id), None)
        todo_extensions = []
        # TODO - @c-ryan-k see if we can add extensions to delete tree output
        if aio_ext_obj:
            todo_extensions.append(aio_ext_obj)  # delete aio extension even if no dependencies
        if self.include_dependencies:
            todo_extensions.extend(self.resource_map.extensions)
        todo_custom_locations = self.resource_map.custom_locations
        todo_resource_sync_rules = []
        todo_resources = []

        for cl in todo_custom_locations:
            todo_resource_sync_rules.extend(self.resource_map.get_resource_sync_rules(cl.resource_id))
            todo_resources.extend(self.resource_map.get_resources(cl.resource_id))

        batched_work = self._batch_resources(
            resources=todo_resources,
            resource_sync_rules=todo_resource_sync_rules,
            custom_locations=todo_custom_locations,
            extensions=todo_extensions,
        )
        if not batched_work:
            logger.warning("Nothing to delete :)")
            return

        if not force:
            if not self.resource_map.connected_cluster.connected:
                logger.warning(
                    "Deletion cancelled. The cluster is not connected to Azure. "
                    "Use --force to continue anyway, which may lead to errors."
                )
                return

        try:
            for batches_key in batched_work:
                self._render_display(f"[red]Deleting {batches_key}...")
                for batch in batched_work[batches_key]:
                    # TODO: @digimaun - Show summary as result
                    lros = self._delete_batch(batch)
                    [lro.result() for lro in lros]
        finally:
            self._stop_display()

    def _batch_resources(
        self,
        resources: Optional[List[IoTOperationsResource]] = None,
        resource_sync_rules: Optional[List[IoTOperationsResource]] = None,
        custom_locations: Optional[List[IoTOperationsResource]] = None,
        extensions: Optional[List[IoTOperationsResource]] = None,
    ) -> Dict[str, List[List[IoTOperationsResource]]]:
        batched_work: Dict[str, List[List[IoTOperationsResource]]] = {}

        if resources:
            # resource_map.get_resources will sort resources in descending order by segment then display name
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

    def _delete_batch(self, resource_batch: List[IoTOperationsResource]) -> Tuple["LROPoller"]:
        return wait_for_terminal_states(
            *[
                self.resource_client.resources.begin_delete_by_id(
                    resource_id=resource.resource_id, api_version=resource.api_version
                )
                for resource in resource_batch
            ]
        )
