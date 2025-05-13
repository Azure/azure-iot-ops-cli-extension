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
from ....util.common import parse_kvp_nargs
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
        endpoints: Optional[List[List[str]]] = None,
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
                    "endpoints": self._process_endpoints(endpoints)
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
        update_payload = {}
        if tags:
            update_payload["tags"] = tags

        if mi_system_identity is not None:
            update_payload["identity"] = _build_identity(system=mi_system_identity)

        with console.status(f"Updating {namespace_name}..."):
            poller = self.ops.begin_update(
                resource_group_name,
                namespace_name,
                update_payload
            )
            return wait_for_terminal_state(poller, **kwargs)

    def add_endpoint(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoints: List[List[str]],
        **kwargs
    ):
        # get the original namespace endpoints
        original_endpoints = self.show(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )["properties"]["messaging"]["endpoints"]

        # TODO: check with DOE if the messaging.endpoints exist in response calls with no initial endpoints
        # update the endpoints with the new ones
        endpoint_body = self._process_endpoints(endpoints=endpoints)
        original_endpoints.update(endpoint_body)

        # update payload
        update_payload = {
            "properties": {
                "messaging": {
                    "endpoints": original_endpoints
                }
            }
        }

        with console.status(f"Updating to {namespace_name}..."):
            poller = self.ops.begin_update(
                resource_group_name,
                namespace_name,
                update_payload
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
        endpoint_names: List[str],
        **kwargs
    ):
        # get the namespace endpoints
        original_endpoints = self.show(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )["properties"]["messaging"]["endpoints"]
        # remove the endpoints from the namespace body by key
        remaining_endpoints = {
            endpoint: endpoint_body
            for endpoint, endpoint_body in original_endpoints.items()
            if endpoint not in endpoint_names
        }

        # update payload
        update_payload = {
            "properties": {
                "messaging": {
                    "endpoints": remaining_endpoints
                }
            }
        }

        with console.status(f"Updating to {namespace_name}..."):
            poller = self.ops.begin_update(
                resource_group_name,
                namespace_name,
                update_payload
            )
            result = wait_for_terminal_state(poller, **kwargs)
            return result["properties"]["messaging"]["endpoints"]

    def _process_endpoints(self, endpoints: List[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Takes a list of endpoint ids and returns a dictionary of endpoints
        with the format:
        {
            "endpoint_name": {
                "endpointType": "<endpoint_type>",
                "address": "<endpoint_address>",
                "resourceId": "<endpoint_id>"
            }
        }

        if the endpoint name is not provided, it will be generated like so:
        "<resource_group_name>-<endpoint_name>"

        if the endpoint does not exist, it will be skipped and a warning will be logged.
        """
        result = {}
        if not endpoints:
            return result

        for endpoint in endpoints:
            parsed_endpoint = parse_kvp_nargs(endpoint)
            if "id" not in parsed_endpoint:
                logger.warning(f"Provided endpoint {endpoint} does not have an id. Skipping.")
                continue
            try:
                # get the endpoint body via the id
                endpoint_body = self.resource_ops.get_by_id(
                    resource_id=parsed_endpoint["id"],
                    api_version=EVENTGRIDTOPIC_API_VERSION,
                )
                # for some reason Event grid does not return resource group
                endpoint_resource_group = parsed_endpoint["id"].split("/")[4]
                # generate a key for the endpoint
                endpoint_name = parsed_endpoint.get("name", f"{endpoint_resource_group}-{endpoint_body['name']}")
                result[endpoint_name] = {
                    "endpointType": endpoint_body["type"].split("/")[0],
                    "address": endpoint_body["properties"]["endpoint"],
                    "resourceId": parsed_endpoint["id"]
                }
            except Exception as e:
                logger.warning(f"Failed to get endpoint {parsed_endpoint['id']}:\n{e}.")
        return result


def _build_identity(system: bool = False) -> dict:
    if system:
        identity_type = IdentityType.system_assigned.value
    else:
        identity_type = IdentityType.none.value
        logger.warning("An identity type was not specified. The namespace may not function as expected.")

    return {"type": identity_type}
