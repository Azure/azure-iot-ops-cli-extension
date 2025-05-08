# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from rich.console import Console
from typing import TYPE_CHECKING, Dict, List, Iterable, Optional
from knack.log import get_logger

from ....common import IdentityType
from ....util.az_client import get_registry_refresh_mgmt_client, get_resource_client, wait_for_terminal_state
from ....util.queryable import Queryable

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistryrefreshmgmt.operations import NamespacesOperations
    from ....vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)
EVENTGRIDTOPIC_API_VERSION = "2025-02-15"
NAMESPACE_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces"


class Namespaces(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_refresh_mgmt_client(
            subscription_id=self.default_subscription_id
        )
        self.resource_mgmt_client = get_resource_client(
            subscription_id=self.default_subscription_id
        )
        self.ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def create(
        self,
        namespace_name: str,
        resource_group_name: str,
        initial_endpoint_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        mi_system_identity: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        if not location:
            location = self.get_resource_group(name=resource_group_name)["location"]
        namespace_body = {
            "identity": _build_identity(system=mi_system_identity),
            "location": location,
            "properties": {
                "messaging": {
                    "endpoints": self._process_endpoints(initial_endpoint_ids)
                }
            },
            "tags": tags,
        }
        with console.status(f"Creating {namespace_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name,
                namespace_name,
                resource=namespace_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(self, namespace_name: str, resource_group_name: str, **kwargs):
        with console.status(f"Deleting {namespace_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, namespace_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()

    def update(
        self,
        namespace_name: str,
        resource_group_name: str,
        # Note for now, keep this here but will be moved once user identities are supported
        mi_system_identity: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        # get the namespace
        original_namespace = self.show(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        if tags:
            original_namespace["tags"] = tags

        if mi_system_identity is not None:
            original_namespace["identity"] = _build_identity(system=mi_system_identity)

        with console.status(f"Updating {namespace_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name,
                namespace_name,
                original_namespace
            )
            return wait_for_terminal_state(poller, **kwargs)

    def add_endpoint(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoint_ids: List[str],
        **kwargs
    ):
        # get the namespace
        original_namespace = self.show(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        # TODO: check with DOE if the messaging.endpoints exist in response calls with no initial endpoints

        # add the endpoint to the namespace body
        endpoint_body = self._process_endpoints(endpoint_ids=endpoint_ids)
        original_namespace["properties"]["messaging"]["endpoints"].update(endpoint_body)

        with console.status(f"Updating to {namespace_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name,
                namespace_name,
                original_namespace
            )
            result = wait_for_terminal_state(poller, **kwargs)
            return result["properties"]["messaging"]["endpoints"]

    def list_endpoints(
        self,
        namespace_name: str,
        resource_group_name: str,
    ) -> dict:
        original_namespace = self.show(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        return original_namespace["properties"]["messaging"]["endpoints"]

    def remove_endpoint(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoint_ids: List[str],
        **kwargs
    ):
        # get the namespace
        original_namespace = self.show(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        # remove the endpoints from the namespace body
        # TODO: check with DOE if a namespace can have an endpoint with no resourceId
        # would removing by name/key be better?
        remaining_endpoints = {
            endpoint: endpoint_body
            for endpoint, endpoint_body in original_namespace["properties"]["messaging"]["endpoints"].items()
            if endpoint_body.get("resourceId") not in endpoint_ids
        }
        original_namespace["properties"]["messaging"]["endpoints"] = remaining_endpoints

        with console.status(f"Updating to {namespace_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name,
                namespace_name,
                original_namespace
            )
            result = wait_for_terminal_state(poller, **kwargs)
            return result["properties"]["messaging"]["endpoints"]

    def _process_endpoints(self, endpoint_ids: List[str] = None) -> dict:
        """
        Takes a list of endpoint ids and returns a dictionary of endpoints
        with the format:
        {
            "<resource_group>-<endpoint_name>": {
                "endpointType": "<endpoint_type>",
                "address": "<endpoint_address>",
                "resourceId": "<endpoint_id>"
            }
        }
        """
        result = {}
        if not endpoint_ids:
            return result

        for endpoint_id in endpoint_ids:
            try:
                # get the endpoint body via the id
                endpoint_body = self.resource_ops.get_by_id(
                    resource_id=endpoint_id,
                    api_version=EVENTGRIDTOPIC_API_VERSION,
                )

                # generate a key for the endpoint
                endpoint_name = f"{endpoint_body['resourceGroup']}-{endpoint_body['name']}"
                result[endpoint_name] = {
                    "endpointType": endpoint_body["type"].split("/")[0],
                    "address": endpoint_body["properties"]["endpoint"],
                    "resourceId": endpoint_id
                }
            except Exception as e:
                logger.warning(f"Failed to get endpoint {endpoint_id}: {e}.")
        return result


def _build_identity(system: bool = False) -> dict:
    if system:
        identity_type = IdentityType.system_assigned.value
    else:
        identity_type = IdentityType.none.value
        logger.warning("An identity type was not specified. The namespace may not function as expected.")

    return {"type": identity_type}
