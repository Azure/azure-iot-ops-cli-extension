# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable

from knack.log import get_logger
from rich.console import Console

from ....util.az_client import wait_for_terminal_state
from ....util.queryable import Queryable
from .instances import Instances

logger = get_logger(__name__)

console = Console()


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        RegistryEndpointOperations,
    )


class RegistryEndpoints(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.registry_endpoints: "RegistryEndpointOperations" = self.iotops_mgmt_client.registry_endpoint

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        """
        List all registry endpoints for the IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :return: Iterable of registry endpoint dictionaries.
        :rtype: Iterable[dict]
        """
        return self.registry_endpoints.list_by_instance_resource(
            resource_group_name=resource_group_name, instance_name=instance_name
        )

    def show(self, instance_name: str, resource_group_name: str, registry_endpoint_name: str) -> dict:
        """
        Get a specific registry endpoint for the IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to retrieve.
        :return: The registry endpoint dictionary.
        :rtype: dict
        """
        return self.registry_endpoints.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        )

    # TODO - add support for update
    # TODO - break apart auth / creation params
    def add(
        self,
        instance_name: str,
        resource_group_name: str,
        registry_endpoint_name: str,
        registry_endpoint: dict,
        **kwargs,
    ) -> dict:
        """
        Add a registry endpoint to an IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to create or update.
        :param registry_endpoint: The registry endpoint properties to set.
        :param kwargs: Additional keyword arguments for the operation.
        """
        with console.status("Working..."):
            poller = self.registry_endpoints.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
                registry_endpoint=registry_endpoint,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def remove(self, instance_name: str, resource_group_name: str, registry_endpoint_name: str, **kwargs) -> None:
        """
        Remove a registry endpoint from an IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to delete.
        :param kwargs: Additional keyword arguments for the operation.
        """
        with console.status("Working..."):
            poller = self.registry_endpoints.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
            )
            wait_for_terminal_state(poller, **kwargs)
        logger.info(f"Registry endpoint '{registry_endpoint_name}' removed successfully.")
