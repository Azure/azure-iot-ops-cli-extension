# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional
from knack.log import get_logger

logger = get_logger(__name__)


class BaseProvider:
    def __init__(
        self,
        cmd,
        api_version: str,
        resource_type: str,
        **kwargs
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id
        from ..util.az_client import get_resource_client

        self.cmd = cmd
        self.subscription = get_subscription_id(cmd.cli_ctx)
        self.resource_client = get_resource_client(subscription_id=self.subscription)
        self.api_version = api_version
        self.resource_type = resource_type
        self.required_extension = kwargs.get("required_extension")

    def delete(
        self,
        resource_name: str,
        resource_group_name: str
    ):
        return self.resource_client.resources.begin_delete(
            resource_group_name=resource_group_name,
            resource_provider_namespace=self.resource_type,
            parent_resource_path="",
            resource_type="",
            resource_name=resource_name,
            api_version=self.api_version
        )

    def get_location(
        self,
        resource_group_name: str
    ) -> str:
        resource_group = self.resource_client.resource_groups.get(resource_group_name=resource_group_name)
        return resource_group.as_dict()["location"]

    def list(
        self,
        resource_group_name: Optional[str] = None,
    ) -> List[Any]:
        # Note the usage of az rest/send_raw_request over resource
        # az resource list/resource_client.resources.list will omit properties
        from ..util.common import _process_raw_request
        uri = f"/subscriptions/{self.subscription}"
        if resource_group_name:
            uri += f"/resourceGroups/{resource_group_name}"
        uri += f"/providers/{self.resource_type}?api-version={self.api_version}"
        return _process_raw_request(
            cmd=self.cmd, method="GET", url=uri, keyword="value"
        )

    def show(
        self,
        resource_name: str,
        resource_group_name: str
    ) -> Dict[str, Any]:
        result = self.resource_client.resources.get(
            resource_group_name=resource_group_name,
            resource_provider_namespace=self.resource_type,
            parent_resource_path="",
            resource_type="",
            resource_name=resource_name,
            api_version=self.api_version
        )
        # serialize takes out id
        # as_dict turns extendedLocation into extended_location
        # fix as_dict here
        result = result.as_dict()
        extended_location = result.pop("extended_location", None)
        if extended_location:
            result["extendedLocation"] = extended_location
        return result
