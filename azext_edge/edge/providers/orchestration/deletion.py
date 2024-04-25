# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, Union
from time import sleep

from knack.log import get_logger
from rich import print
from rich.console import Console
from rich.prompt import Confirm

from .resource_map import IoTOperationsResource, IoTOperationsResourceMap
from ...util.az_client import get_resource_client, wait_for_terminal_state

logger = get_logger(__name__)

console = Console()


MAX_WAITS = 60


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
        extension_work = []

        import pdb; pdb.set_trace()
        for extension in todo_extensions:
            extension_work.append(
                self.resource_client.resources.begin_delete_by_id(
                    resource_id=extension.resource_id, api_version=extension.api_version
                )
            )

        if extension_work:
            for _ in range(MAX_WAITS):
                for i in range(len(extension_work)):
                    if extension_work[i].done():
                        extension_work.pop(i)
                sleep(15)

        import pdb; pdb.set_trace()
        pass
