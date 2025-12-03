# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from azure.cli.core.azclierror import InvalidArgumentValueError
from knack.log import get_logger
from rich.console import Console

from ...common import ListableEnum
from ...util.az_client import (
    get_registry_mgmt_client,
    get_resource_client,
    wait_for_terminal_state,
)
from ...util.common import parse_kvp_nargs, should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.queryable import Queryable

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt.operations import (
        NamespaceDevicesOperations,
        NamespacesOperations,
    )
    from ...vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)
NAMESPACE_DEVICE_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/devices"


class DeviceEndpointType(ListableEnum):
    """
    Enum for the device endpoint types.
    """

    OPCUA = "Microsoft.OpcUa"
    ONVIF = "Microsoft.Onvif"
    MEDIA = "Microsoft.Media"
    REST = "Microsoft.Http"
    SSE = "Microsoft.SSEHttp"
    MQTT = "Microsoft.Mqtt"

    @classmethod
    def get_type_from_keyword(cls, keyword: str, return_custom_keyword: bool = True) -> Optional[str]:
        """
        Returns the endpoint type based on the keyword.

        For listing endpoint purposes, if the keyword does not match any known type, it will return
        the keyword itself.
        For testing purposes, if the keyword does not match any known type, it will return "custom".
        """
        mapped_types = {
            "opcua": cls.OPCUA.value,
            "onvif": cls.ONVIF.value,
            "media": cls.MEDIA.value,
            "rest": cls.REST.value,
            "sse": cls.SSE.value,
            "mqtt": cls.MQTT.value
        }
        return mapped_types.get(keyword.lower(), "custom" if return_custom_keyword else keyword)


class NamespaceDevices(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
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
        instance_name: str,
        instance_resource_group: str,
        custom_attributes: Optional[List[str]] = None,
        disabled: Optional[bool] = None,
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
            instance_resource_group=instance_resource_group,
            instance_subscription=instance_subscription
        )
        # use the namespace location instead of the cluster location
        extended_location.pop("cluster_location")

        namespace = extended_location.pop("namespace", None)
        if not namespace:
            raise InvalidArgumentValueError(
                "The instance must have an ADR namespace reference to create a namespaced device."
            )
        # get the location of the namespace
        location = self.namespace_ops.get(
            resource_group_name=namespace["resource_group"],
            namespace_name=namespace["name"]
        )["location"]

        device_body = {
            "extendedLocation": extended_location,
            "location": location,
            "properties": {
                "attributes": parse_kvp_nargs(custom_attributes),
                "enabled": not disabled,
                "manufacturer": manufacturer,
                "model": model,
                "operatingSystem": operating_system,
                "operatingSystemVersion": operating_system_version
            },
            "tags": tags
        }

        with console.status(f"Creating {device_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                resource=device_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        from .helpers import get_namespace_for_instance
        namespace = get_namespace_for_instance(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )

        with console.status(f"Deleting {device_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(
        self,
        device_name: str,
        resource_group: str,
        namespace_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        check_cluster: bool = False
    ) -> dict:
        """
        Shows the details of a device in a namespace.
        One of the `namespace_name` or `instance_name` must be provided.

        Resource group can be either the namespace resource group or the instance resource group.
        The expected behavior is that if `namespace_name` is provided, the resource group
        is the namespace resource group, and if `instance_name` is provided, the resource group
        is the instance resource group."""
        if not namespace_name:
            # assume resource group is instance resource group
            from .helpers import get_namespace_for_instance
            namespace = get_namespace_for_instance(
                cmd=self.cmd,
                instance_name=instance_name,
                instance_resource_group=resource_group
            )
            namespace_name = namespace["name"]
            resource_group = namespace["resource_group"]

        device = self.ops.get(
            resource_group_name=resource_group, namespace_name=namespace_name, device_name=device_name
        )

        if check_cluster:
            from .helpers import check_cluster_connectivity
            check_cluster_connectivity(self.cmd, device)
        return device

    def query_devices(
        self,
        device_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        disabled: Optional[bool] = None,
        custom_query: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        operating_system: Optional[str] = None,
        operating_system_version: Optional[str] = None,
    ) -> dict:
        """
        Queries the devices using Azure Resource Graph.
        """
        from .helpers import get_instance_query, get_query
        query = "Resources | where type =~ '{}'".format(NAMESPACE_DEVICE_RESOURCE_TYPE)

        # for now, keep it simple
        # ideas for later on, add namespace (needs id parsing), endpoint types (will need to add joins)
        def _build_query_body(
            **params: dict
        ) -> str:
            param_mapping = {
                "device_name": "name",
                "manufacturer": "properties.manufacturer",
                "model": "properties.model",
                "operating_system": "properties.operatingSystem",
                "operating_system_version": "properties.operatingSystemVersion",
            }
            return get_query(
                param_mapping=param_mapping,
                params=params,
            )

        query += custom_query or _build_query_body(
            device_name=device_name,
            disabled=disabled,
            manufacturer=manufacturer,
            model=model,
            operating_system=operating_system,
            operating_system_version=operating_system_version
        )

        query = get_instance_query(
            query=query,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )
        logger.info(f"Querying devices with query: {query}")
        return self.query(query=query)

    def update(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        custom_attributes: Optional[List[str]] = None,
        disabled: Optional[bool] = None,
        operating_system_version: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        from .helpers import get_namespace_for_instance
        namespace = get_namespace_for_instance(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )
        update_payload = {
            "properties": {}
        }
        if tags:
            update_payload["tags"] = tags
        if custom_attributes:
            update_payload["properties"]["attributes"] = parse_kvp_nargs(custom_attributes)
        if disabled is not None:
            update_payload["properties"]["enabled"] = not disabled
        if operating_system_version:
            update_payload["properties"]["operatingSystemVersion"] = operating_system_version

        # remove the properties key if there are no properties to update
        if not update_payload["properties"]:
            update_payload.pop("properties")

        with console.status(f"Updating {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )

    def add_inbound_endpoint(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        endpoint_name: str,
        endpoint_address: str,
        endpoint_type: str,
        endpoint_version: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        key_reference: Optional[str] = None,
        intermediate_certificate_reference: Optional[str] = None,
        password_reference: Optional[str] = None,
        username_reference: Optional[str] = None,
        trust_list: Optional[str] = None,
        replace: Optional[bool] = False,
        **kwargs
    ):
        from .helpers import process_additional_configuration, process_authentication
        # get the original inbound endpoints
        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        namespace = parse_resource_id(device["id"])
        original_endpoints = _get_endpoints(device)
        if endpoint_name in original_endpoints and not replace:
            raise InvalidArgumentValueError(
                f"Inbound endpoint '{endpoint_name}' already exists. Use --replace to update it."
            )

        # create the new endpoint
        endpoint_body = {
            "address": endpoint_address,
            "endpointType": endpoint_type,
            "version": endpoint_version,
            "authentication": process_authentication(
                certificate_reference=certificate_reference,
                key_reference=key_reference,
                intermediate_certificate_reference=intermediate_certificate_reference,
                password_reference=password_reference,
                username_reference=username_reference
            )
        }

        # process the configuration for the endpoint
        config_func = ENDPOINT_TYPE_TO_FUNCTION_MAP.get(endpoint_type, process_additional_configuration)
        if config_func:
            endpoint_body["additionalConfiguration"] = config_func(**kwargs)

        # trust settings
        if trust_list:
            endpoint_body["trustSettings"] = {
                "trustList": trust_list
            }

        # update the endpoints with the new one
        original_endpoints[endpoint_name] = endpoint_body

        # update payload
        update_payload = {
            "properties": {
                "endpoints": {
                    "inbound": original_endpoints
                }
            }
        }

        with console.status(f"Updating inbound endpoints for {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            result = self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"]
            )
            return result["properties"].get("endpoints", {}).get("inbound", {})

    def list_endpoints(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        inbound: bool = False,
        inbound_endpoint_type: Optional[str] = None
    ) -> dict:
        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        endpoints = _get_endpoints(device, inbound=inbound)
        if inbound and inbound_endpoint_type:
            # support inputs of just "opcua", "onvif", etc.
            inbound_endpoint_type = DeviceEndpointType.get_type_from_keyword(
                inbound_endpoint_type, return_custom_keyword=False
            )
            endpoints = {
                name: body for name, body in endpoints.items()
                if body.get("endpointType", "").lower() == inbound_endpoint_type.lower()
            }
        return endpoints

    def inbound_remove_endpoint(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        endpoint_names: List[str],
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        # get the original inbound endpoints
        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        namespace = parse_resource_id(device["id"])
        original_endpoints = _get_endpoints(device)
        # remove the endpoints from the endpoint list by key
        # only send endpoints to be removed with null values
        # also include any existing endpoints that already have null bodies
        endpoints_to_remove = {}

        # Add endpoints explicitly requested for removal
        for endpoint_name in endpoint_names:
            if endpoint_name in original_endpoints:
                endpoints_to_remove[endpoint_name] = None

        # Add any existing endpoints that already have null/None bodies
        for endpoint_name, endpoint_body in original_endpoints.items():
            if endpoint_body is None:
                endpoints_to_remove[endpoint_name] = None

        # update payload
        update_payload = {
            "properties": {
                "endpoints": {
                    "inbound": endpoints_to_remove
                }
            }
        }

        with console.status(f"Updating inbound endpoints for {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            result = self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"]
            )
            return result["properties"].get("endpoints", {}).get("inbound", {})


# TODO: unit test
def _get_endpoints(device: dict, inbound: bool = True) -> dict:
    """
    Helper function to extract endpoints from a device.
    """
    device_props = device["properties"]

    # if device.properties.endpoints is not present or empty,
    # both inbound and outbound endpoints are {}
    if "endpoints" not in device_props or not device_props["endpoints"]:
        return {}

    device_endpoints = device_props.get("endpoints", {})
    return device_endpoints.get("inbound", {}) if inbound else device_endpoints


def _process_onvif_configuration(
    accept_invalid_hostnames: Optional[bool] = False,
    accept_invalid_certificates: Optional[bool] = False,
    **_
) -> str:
    """
    Creates a stringified JSON that follows the ONVIF endpoint schema specifications
    defined in NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA.
    """
    configuration = {
        "acceptInvalidHostnames": accept_invalid_hostnames,
        "acceptInvalidCertificates": accept_invalid_certificates
    }

    return json.dumps(configuration)


def _process_opcua_configuration(
    application_name: Optional[str] = "OPC UA Broker",
    keep_alive: Optional[int] = 10000,
    publishing_interval: Optional[int] = 1000,
    sampling_interval: Optional[int] = 1000,
    queue_size: Optional[int] = 1,
    key_frame_count: Optional[int] = 0,
    session_timeout: Optional[int] = 60000,
    session_keep_alive_interval: Optional[int] = 10000,
    session_reconnect_period: Optional[int] = 2000,
    session_reconnect_exponential_backoff: Optional[int] = 10000,
    session_enable_tracing_headers: Optional[bool] = False,
    subscription_max_items: Optional[int] = 1000,
    subscription_life_time: Optional[int] = 60000,
    security_auto_accept_certificates: Optional[bool] = False,
    security_policy: Optional[str] = None,
    security_mode: Optional[str] = None,
    run_asset_discovery: Optional[bool] = False,
    **_
) -> str:
    """
    Creates a stringified JSON that follows the OPC UA endpoint schema specifications
    defined in NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA.
    """
    from .helpers import ensure_schema_structure
    from .specs import NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA

    if security_policy:
        security_policy = "http://opcfoundation.org/UA/SecurityPolicy#" + security_policy

    configuration = {
        "applicationName": application_name,
        "keepAliveMilliseconds": keep_alive,
        "defaults": {
            "publishingIntervalMilliseconds": publishing_interval,
            "samplingIntervalMilliseconds": sampling_interval,
            "queueSize": queue_size,
            "keyFrameCount": key_frame_count
        },
        "session": {
            "timeoutMilliseconds": session_timeout,
            "keepAliveIntervalMilliseconds": session_keep_alive_interval,
            "reconnectPeriodMilliseconds": session_reconnect_period,
            "reconnectExponentialBackOffMilliseconds": session_reconnect_exponential_backoff,
            "enableTracingHeaders": session_enable_tracing_headers
        },
        "subscription": {
            "maxItems": subscription_max_items,
            "lifeTimeMilliseconds": subscription_life_time
        },
        "security": {
            "autoAcceptUntrustedServerCertificates": security_auto_accept_certificates,
            "securityPolicy": security_policy,
            "securityMode": security_mode
        },
        "runAssetDiscovery": run_asset_discovery
    }

    # Validate the configuration against the schema
    ensure_schema_structure(NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA, configuration)

    return json.dumps(configuration)


ENDPOINT_TYPE_TO_FUNCTION_MAP: Dict[str, Optional[Callable]] = {
    DeviceEndpointType.OPCUA.value: _process_opcua_configuration,
    DeviceEndpointType.ONVIF.value: _process_onvif_configuration,
    DeviceEndpointType.MEDIA.value: None,
}
