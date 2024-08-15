# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional, Union

from rich.console import Console

from .az_client import get_resource_client
from .resource_graph import ResourceGraph


class Queryable:
    def __init__(self, cmd, subscriptions: Optional[List] = None):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.default_subscription_id: str = get_subscription_id(cli_ctx=cmd.cli_ctx)

        if not subscriptions:
            subscriptions = [self.default_subscription_id]

        self.subscriptions = subscriptions
        self.resource_graph = ResourceGraph(cmd=cmd, subscriptions=self.subscriptions)
        self.resource_client = get_resource_client(subscription_id=self.default_subscription_id)
        self.console = Console()

    def _process_query_result(self, result: dict, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        if "data" in result:
            if result["data"] and first:
                return result["data"][0]
            return result["data"]

    def query(self, query: str, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        return self._process_query_result(result=self.resource_graph.query_resources(query=query), first=first)

    def get_resource_group(self, name: str) -> dict:
        return self.resource_client.resource_groups.get(resource_group_name=name).as_dict()
