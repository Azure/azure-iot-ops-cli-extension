# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Union, Optional
from rich.console import Console
from rich.prompt import Confirm
from rich import print

from .resource_map import IoTOperationsResourceMap, IoTOperationsResource


console = Console()


def remove_ops_resources(cmd, cluster_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None):
    manager = RemovalManager(cmd=cmd, cluster_name=cluster_name, resource_group_name=resource_group_name)
    manager.do_work(confirm_yes=confirm_yes)


class RemovalManager:
    def __init__(self, cmd, cluster_name: str, resource_group_name: str):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.resource_map = IoTOperationsResourceMap(
            cmd=cmd, cluster_name=cluster_name, resource_group_name=resource_group_name
        )

        self.subscription_id = get_subscription_id(cli_ctx=cmd.cli_ctx)

    def do_work(self, confirm_yes: Optional[bool] = None):
        should_delete = True
        if not confirm_yes:
            self.display_work()
            should_delete = Confirm.ask("Remove resources?")

        import pdb

        pdb.set_trace()
        pass

    def display_work(self):
        print(self.resource_map.build_tree())
