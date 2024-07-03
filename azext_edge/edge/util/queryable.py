# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional, Union
from azure.cli.core.azclierror import ResourceNotFoundError
from .resource_graph import ResourceGraph


def get_resource_group_query(name: str):
    return f"""
        ResourceContainers
        | where type =~ 'microsoft.resources/subscriptions/resourcegroups'
        | where name =~ '{name}'
        """


class Queryable:
    def __init__(self, cmd, subscriptions: Optional[List] = None):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.default_subscription_id: str = get_subscription_id(cli_ctx=cmd.cli_ctx)

        if not subscriptions:
            subscriptions = [self.default_subscription_id]

        self.subscriptions = subscriptions
        self.resource_graph = ResourceGraph(cmd=cmd, subscriptions=self.subscriptions)

    def _process_query_result(self, result: dict, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        if "data" in result:
            if result["data"] and first:
                return result["data"][0]
            return result["data"]

    @property
    def subscriptions_label(self) -> str:
        joined_subs = "', '".join(self.subscriptions)
        sub_label = "subscription"
        if len(self.subscriptions) > 1:
            sub_label += "s"

        return f"{sub_label} '{joined_subs}'"

    def _raise_on_resource_group_404(self, resource_group_name: str):
        query = get_resource_group_query(resource_group_name)
        result = self._process_query_result(result=self.resource_graph.query_resources(query=query))
        if not result:
            raise ResourceNotFoundError(
                f"Resource group '{resource_group_name}' does not exist in {self.subscriptions_label}."
            )

    def query(
        self, query: str, first: bool = False, resource_group_name: Optional[str] = None
    ) -> Optional[Union[dict, List[dict]]]:
        if resource_group_name:
            self._raise_on_resource_group_404(resource_group_name)

        return self._process_query_result(result=self.resource_graph.query_resources(query=query), first=first)
