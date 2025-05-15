# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from rich.console import Console
from typing import TYPE_CHECKING, Dict, List, Iterable, Optional
from knack.log import get_logger

from azext_edge.edge.providers.rpsaas.adr.helpers import process_authentication

from ....util.az_client import get_registry_refresh_mgmt_client, get_resource_client, wait_for_terminal_state
from ....util.common import parse_kvp_nargs
from ....util.queryable import Queryable

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistryrefreshmgmt.operations import NamespacesOperations, NamespaceDevicesOperations
    from ....vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)


class NamespaceDevices(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_refresh_mgmt_client(
            subscription_id=self.default_subscription_id
        )
        self.resource_mgmt_client = get_resource_client(
            subscription_id=self.default_subscription_id
        )
        self.ops: "NamespaceDevicesOperations" = self.deviceregistry_mgmt_client.namespace_devices
        self.namespace_ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def create(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        instance_name: str,
        device_template_id: str,
        device_group_id: Optional[str] = None,
        custom_attributes: Optional[List[str]] = None,
        disabled: Optional[bool] = None,
        instance_resource_group: Optional[str] = None,
        instance_subscription: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        operating_system: Optional[str] = None,
        operating_system_version: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        # get the extended location from the instance
        from .helpers import get_extended_location
        extended_location = get_extended_location(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group or resource_group_name,
            instance_subscription=instance_subscription
        )
        # use the namespace location instead of the cluster location
        extended_location.pop("cluster_location")

        # get the location of the namespace
        location = self.namespace_ops.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name
        )["location"]

        # TODO: what format should custom attributes be?
        device_body = {
            "extendedLocation": extended_location,
            "location": location,
            "properties": {
                "deviceGroupId": device_group_id,
                "deviceTemplateId": device_template_id,
                "customAttributes": parse_kvp_nargs(custom_attributes),
                "enabled": not disabled,
                "manufacturer": manufacturer,
                "model": model,
                "operatingSystem": operating_system,
                "operatingSystemVersion": operating_system_version
            },
            "tags": tags
        }

        with console.status(f"Creating {namespace_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                device_name=device_name,
                resource=device_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(self, device_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        with console.status(f"Deleting {namespace_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                device_name=device_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, device_name: str, namespace_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name, namespace_name=namespace_name, device_name=device_name
        )

    def list(self, namespace_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(namespace_name=namespace_name, resource_group_name=resource_group_name)

    def update(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        custom_attributes: Optional[List[str]] = None,
        device_group_id: Optional[str] = None,
        disabled: Optional[bool] = None,
        operating_system_version: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        update_payload = {
            "properties": {}
        }
        if tags:
            update_payload["tags"] = tags
        if custom_attributes:
            update_payload["properties"]["customAttributes"] = parse_kvp_nargs(custom_attributes)
        if device_group_id:
            update_payload["properties"]["deviceGroupId"] = device_group_id
        if disabled is not None:
            update_payload["properties"]["enabled"] = not disabled
        if operating_system_version:
            update_payload["properties"]["operatingSystemVersion"] = operating_system_version

        # remove the properties key if there are no properties to update
        if not update_payload["properties"]:
            update_payload.pop("properties")

        with console.status(f"Updating {namespace_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                device_name=device_name,
                properties=update_payload
            )
            return wait_for_terminal_state(poller, **kwargs)

    # def add_inbound_endpoint(
    #     self,
    #     device_name: str,
    #     namespace_name: str,
    #     resource_group_name: str,
    #     **kwargs
    # ):
    #     # get the original inbound endpoints
    #     original_endpoints = self.show(
    #         device_name=device_name,
    #         namespace_name=namespace_name,
    #         resource_group_name=resource_group_name
    #     )["properties"].get("endpoints", {}).get("inbound", {})

    #     # update the endpoints with the new one
    #     endpoint_body = self._process_endpoint(endpoints=endpoints)
    #     original_endpoints.update(endpoint_body)

    #     # update payload
    #     update_payload = {
    #         "properties": {
    #             "endpoints": {
    #                 "inbound": original_endpoints
    #             }
    #         }
    #     }

    #     with console.status(f"Updating inbound endpoints for {device_name}..."):
    #         poller = self.ops.begin_update(
    #             resource_group_name=resource_group_name,
    #             namespace_name=namespace_name,
    #             device_name=device_name,
    #             properties=update_payload
    #         )
    #         result = wait_for_terminal_state(poller, **kwargs)
    #         return result["properties"]["messaging"]["endpoints"]

    def list_endpoints(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> dict:
        return self.show(
            device_name=device_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )["properties"].get("endpoints", {}).get("inbound", {})

    def remove_endpoint(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        endpoint_names: List[str],
        **kwargs
    ):
        # get the original inbound endpoints
        original_endpoints = self.show(
            device_name=device_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )["properties"].get("endpoints", {}).get("inbound", {})
        # remove the endpoints from the endpoint list by key
        remaining_endpoints = {
            endpoint: endpoint_body
            for endpoint, endpoint_body in original_endpoints.items()
            if endpoint not in endpoint_names
        }

        # update payload
        update_payload = {
            "properties": {
                "endpoints": {
                    "inbound": remaining_endpoints
                }
            }
        }

        with console.status(f"Updating inbound endpoints for {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                device_name=device_name,
                properties=update_payload
            )
            result = wait_for_terminal_state(poller, **kwargs)
            return result["properties"].get("endpoints", {}).get("inbound", {})

    def _process_endpoint(
        self,
        endpoint_name: str,
        endpoint_type: str,
        endpoint_address: str,
        publishing_interval: Optional[int] = 500,  # in milliseconds
        sampling_interval: Optional[int] = 500,  # in milliseconds
        queue_size: Optional[int] = 1,
        username_reference: Optional[str] = None,
        password_reference: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        enable_discovery: Optional[bool] = None,
        topic_path: Optional[str] = None,
        topic_retain_policy: Optional[str] = None,
    ) -> dict:
        result = {
            endpoint_name: {
                "endpointType": endpoint_type,
                "address": endpoint_address,
                "authentication": process_authentication(
                    certificate_reference=certificate_reference,
                    password_reference=password_reference,
                    username_reference=username_reference
                ),
            }
        }

        # TODO: check DOE how enable discovery works in AEPs (the functionality will be copied)
        additional_configuration = {
            "publishingInterval": publishing_interval,
            "samplingInterval": sampling_interval,
            "queueSize": queue_size,
            "enableDiscovery": enable_discovery
        }
        result[endpoint_name]["additionalConfiguration"] = json.dumps(
            additional_configuration
        )

        return result
