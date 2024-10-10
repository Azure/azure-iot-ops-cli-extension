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
        import pdb; pdb.set_trace()
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
        # try to get the instance first
        # done in _get_resource_map
        # figure out extensions and update them
        self.resource_map.connected_cluster.update_all_extensions()
        if self.require_instance_upgrade:
            # keep the schema reg id
            extension_type = "microsoft.iotoperations"
            aio_extension = self.resource_map.connected_cluster.get_extensions_by_type(extension_type)
            extension_props = aio_extension[extension_type]["properties"]
            sr_id = extension_props["configurationSettings"]["schemaRegistry.values.resourceId"]

            self.instance.pop("systemData", None)
            inst_props = self.instance["properties"]
            inst_props["schemaRegistryRef"] = sr_id
            inst_props["version"] = extension_props["currentVersion"]
            inst_props.pop("schemaRegistryNamespace", None)
            inst_props.pop("components", None)

            # update the instance
            result = self.instances.iotops_mgmt_client.instance.begin_create_or_update(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                resource=self.instance
            )
            return result


        # todo_extensions = []
        # todo_custom_locations = self.resource_map.custom_locations
        # todo_resource_sync_rules = []
        # todo_resources = []

        # for cl in todo_custom_locations:
        #     todo_resource_sync_rules.extend(self.resource_map.get_resource_sync_rules(cl.resource_id))
        #     todo_resources.extend(self.resource_map.get_resources(cl.resource_id))

        # batched_work = self._batch_resources(
        #     resources=todo_resources,
        #     resource_sync_rules=todo_resource_sync_rules,
        #     custom_locations=todo_custom_locations,
        #     extensions=todo_extensions,
        # )
        # if not batched_work:
        #     logger.warning("Nothing to update :)")
        #     return

        # if not force:
        #     if not self.resource_map.connected_cluster.connected:
        #         logger.warning(
        #             "Deletion cancelled. The cluster is not connected to Azure. "
        #             "Use --force to continue anyway, which may lead to errors."
        #         )
        #         return

        # try:
        #     for batches_key in batched_work:
        #         self._render_display(f"[red]Updating {batches_key}...")
        #         for batch in batched_work[batches_key]:
        #             # TODO: @digimaun - Show summary as result
        #             lros = self._delete_batch(batch)
        #             [lro.result() for lro in lros]
        # finally:
            # self._stop_display()

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
