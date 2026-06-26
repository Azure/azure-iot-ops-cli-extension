# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import cached_property
from typing import List, Optional, Union

from .az_client import get_resource_client
from .resource_graph import ResourceGraph
from knack.log import get_logger


logger = get_logger(__name__)


class Queryable:
    def __init__(
        self,
        cmd,
        subscription_id: Optional[str] = None,
        subscriptions: Optional[List[str]] = None,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self._arm_endpoint: str = cmd.cli_ctx.cloud.endpoints.resource_manager
        self.default_subscription_id: str = subscription_id or get_subscription_id(cli_ctx=cmd.cli_ctx)

        if not subscriptions:
            subscriptions = [self.default_subscription_id]

        self.subscriptions: List[str] = subscriptions
        self.resource_graph = ResourceGraph(cmd=cmd, subscriptions=self.subscriptions)

    def _get_client_kwargs(self, *, subscription_id: Optional[str] = None, **overrides) -> dict:
        """Build common kwargs for az_client factory functions.

        Bundles subscription_id and ARM endpoint so providers don't repeat them at every call site.
        Accepts overrides for cross-subscription or non-default api_version scenarios.
        """
        return {
            "subscription_id": subscription_id or self.default_subscription_id,
            "endpoint": self._arm_endpoint,
            **overrides,
        }

    @cached_property
    def resource_client(self):
        return get_resource_client(**self._get_client_kwargs())

    def _process_query_result(self, result: dict, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        if "data" in result:
            if result["data"] and first:
                return result["data"][0]
            return result["data"]

    def query(self, query: str, first: bool = False) -> Optional[Union[dict, List[dict]]]:
        return self._process_query_result(result=self.resource_graph.query_resources(query=query), first=first)

    def get_resource_group(self, name: str) -> dict:
        return self.resource_client.resource_groups.get(resource_group_name=name)

    def get_sp_id(self, app_id: str, token_resource: Optional[str] = None, **kwargs) -> Optional[str]:
        """
        Attempts to fetch the service principal Id by app Id from the Microsoft Graph API.
        """
        from azure.cli.core.util import send_raw_request
        from .cloud_config import CloudConfig

        cloud_config = CloudConfig(self.cmd)
        graph_sp_endpoint = f"{cloud_config.graph_endpoint}v1.0/servicePrincipals"
        token_resource = token_resource or cloud_config.graph_token_resource

        # See if we can fetch the RP OID.
        logger.debug(f"Using aud: {token_resource}")
        try:
            sp_response = send_raw_request(
                cli_ctx=self.cmd.cli_ctx,
                method="GET",
                url=f"{graph_sp_endpoint}(appId='{app_id}')",
                resource=token_resource,
                **kwargs,
            ).json()
            return sp_response.get("id", "").lower()
        except Exception as e:
            # If not, bail without throwing.
            logger.debug(f"Querying graph for app Id failed with:\n{e}")
