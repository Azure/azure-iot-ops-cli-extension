# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from sys import maxsize
from time import sleep
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from knack.log import get_logger
from rich import print
from rich.console import Console
from rich.prompt import Confirm

from ...util.az_client import get_resource_client, wait_for_terminal_states
from .resource_map import IoTOperationsResource, IoTOperationsResourceMap

logger = get_logger(__name__)

console = Console()

if TYPE_CHECKING:
    from azure.core.polling import LROPoller


def delete_ops_resources(cmd, cluster_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None):
    manager = DeletionManager(cmd=cmd, cluster_name=cluster_name, resource_group_name=resource_group_name)
    manager.do_work(confirm_yes=confirm_yes)


class DeletionManager:
    def __init__(self, cmd, cluster_name: str, resource_group_name: str):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.resource_map = IoTOperationsResourceMap(
            cmd=cmd, cluster_name=cluster_name, resource_group_name=resource_group_name
        )
        self.subscription_id = get_subscription_id(cli_ctx=cmd.cli_ctx)
        self.resource_client = get_resource_client(self.subscription_id)

    def do_work(self, confirm_yes: Optional[bool] = None):
        self.display_resource_tree()

        should_delete = True
        if not confirm_yes:
            should_delete = Confirm.ask("Delete?")

        if not should_delete:
            logger.warning("Deletion cancelled.")
            return

        import pdb

        pdb.set_trace()
        self._process()

    def display_resource_tree(self):
        print(self.resource_map.build_tree())

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
        )

        if batched_work:
            for batch in batched_work:
                # import pdb; pdb.set_trace()
                delete_batch_result = self._delete_batch(batch)
                # import pdb; pdb.set_trace()
                pass

        import pdb

        pdb.set_trace()
        pass

    def _batch_resources(
        self,
        resources: List[IoTOperationsResource],
        resource_sync_rules: List[IoTOperationsResource],
        custom_locations: List[IoTOperationsResource],
    ) -> List[List[IoTOperationsResource]]:
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

        if resource_sync_rules:
            resource_batches.append(resource_sync_rules)
        if custom_locations:
            resource_batches.append(custom_locations)

        return resource_batches

    def _delete_batch(self, resource_batch: List[IoTOperationsResource]):
        return wait_for_terminal_states(
            *[
                self.resource_client.resources.begin_delete_by_id(
                    resource_id=resource.resource_id, api_version=resource.api_version
                )
                for resource in resource_batch
            ]
        )

    def _process_batch_result(self, pollers: List["LROPoller"]):
        pass
