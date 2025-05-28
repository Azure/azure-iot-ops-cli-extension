# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import json
from rich.console import Console
from typing import TYPE_CHECKING, Dict, List, Optional
from knack.log import get_logger

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)

from ....util.common import parse_kvp_nargs
from ....util.az_client import get_registry_refresh_mgmt_client, get_resource_client, wait_for_terminal_state
from ....util.queryable import Queryable
from .asset_endpoint_profiles import _process_additional_configuration

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistryrefreshmgmt.operations import NamespaceAssetsOperations, NamespacesOperations
    from ....vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)
NAMESPACE_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/assets"


class NamespaceAssets(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_refresh_mgmt_client(
            subscription_id=self.default_subscription_id
        )
        self.resource_mgmt_client = get_resource_client(
            subscription_id=self.default_subscription_id
        )
        self.ops: "NamespaceAssetsOperations" = self.deviceregistry_mgmt_client.namespace_assets
        self.namespace_ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def create(  # noqa: C901
        self,
        asset_name: str,
        namespace_name: str,
        instance_name: str,
        resource_group_name: str,
        device_name: str,
        device_endpoint_name: str,
        instance_resource_group: Optional[str] = None,
        instance_subscription: Optional[str] = None,
        location: Optional[str] = None,
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
        # default dataset configurations
        default_dataset_publishing_interval: Optional[int] = None,
        default_dataset_sampling_interval: Optional[int] = None,
        default_dataset_queue_size: Optional[int] = None,
        default_dataset_key_frame_count: Optional[int] = None,
        default_dataset_start_instance: Optional[str] = None,
        default_datasets_custom_configuration: Optional[str] = None,
        default_datasets_destinations: Optional[str] = None,
        # default events configurations
        default_events_publishing_interval: Optional[int] = None,
        default_events_queue_size: Optional[int] = None,
        default_events_start_instance: Optional[str] = None,
        default_events_filter_type: Optional[str] = None,
        default_events_filter_clauses: Optional[List[str]] = None,  # path (req), type, field
        default_events_custom_configuration: Optional[str] = None,
        default_events_destinations: Optional[str] = None,
        # default management groups configurations
        default_mgmtg_custom_configuration: Optional[str] = None,
        # default streams configurations
        default_streams_custom_configuration: Optional[str] = None,
        default_streams_destinations: Optional[str] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        discovered_asset_refs: Optional[List[str]] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> dict:
        # TODO: future, Add in options to import from files for datasets, events, streams, and mgmt groups

        # get the extended location from the instance
        from .helpers import get_extended_location
        # TODO: add a check for instance being the right version
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

        # Initialize properties dictionary
        properties = {
            "deviceRef": {
                "deviceName": device_name,
                "endpointName": device_endpoint_name
            }
        }

        # TODO: future, add in checks mapping device type to allowed asset params:
        # opcua ->
        #   allowed: datasets, events, mgmt groups, destinations must be mqtt
        #   not allowed: streams
        # onvif ->
        #   allowed: events, mgmt groups, destinations must be mqtt
        #   not allowed: datasets, streams
        # media ->
        #   allowed: streams, destinations can be mqtt or storage
        #   not allowed: datasets, events, mgmt groups
        # custom -> allow all

        _update_asset_props(
            properties=properties,
            # dataset
            default_dataset_publishing_interval=default_dataset_publishing_interval,
            default_dataset_sampling_interval=default_dataset_sampling_interval,
            default_dataset_queue_size=default_dataset_queue_size,
            default_dataset_key_frame_count=default_dataset_key_frame_count,
            default_dataset_start_instance=default_dataset_start_instance,
            default_datasets_custom_configuration=default_datasets_custom_configuration,
            default_datasets_destinations=default_datasets_destinations,
            # event
            default_events_destinations=default_events_destinations,
            default_events_publishing_interval=default_events_publishing_interval,
            default_events_queue_size=default_events_queue_size,
            default_events_start_instance=default_events_start_instance,
            default_events_filter_type=default_events_filter_type,
            default_events_filter_clauses=default_events_filter_clauses,
            default_events_custom_configuration=default_events_custom_configuration,
            # mgmt
            default_mgmtg_custom_configuration=default_mgmtg_custom_configuration,
            # streams
            default_streams_custom_configuration=default_streams_custom_configuration,
            default_streams_destinations=default_streams_destinations,
            # other
            asset_type_refs=asset_type_refs,
            attributes=attributes,
            description=description,
            disabled=disabled,
            discovered_asset_refs=discovered_asset_refs,
            display_name=display_name,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        asset_body = {
            "extendedLocation": extended_location,
            "location": location,
            "properties": properties,
            "tags": tags,
        }

        with console.status(f"Creating asset {asset_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name,
                namespace_name,
                asset_name,
                resource=asset_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs
    ):
        with console.status(f"Deleting asset {asset_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str
    ) -> dict:
        self.ops.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        )

    # note the usage of Azure Resource Graph over the list api
    def query_assets(
        self,
        asset_name: Optional[str] = None,
        custom_query: Optional[str] = None,
        resource_group_name: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None,
    ) -> dict:
        """
        Queries the asset using Azure Resource Graph.
        """
        query = "Resources | where type =~ '{}'".format(NAMESPACE_ASSET_RESOURCE_TYPE)

        # for now, keep it simple
        def _build_query_body(
            asset_name: Optional[str] = None,
            resource_group_name: Optional[str] = None,
            device_name: Optional[str] = None,
            device_endpoint_name: Optional[str] = None
        ) -> str:
            query_body = ""
            if asset_name:
                query_body += f' | where name =~ "{asset_name}"'
            if resource_group_name:
                query_body += f' | where resourceGroup =~ "{resource_group_name}"'
            if device_name:
                query_body += f' | where properties.deviceRef.deviceName =~ "{device_name}"'
            if device_endpoint_name:
                query_body += f' | where properties.deviceRef.endpointName =~ "{device_endpoint_name}"'
            return (
                f"{query_body} | extend customLocation = tostring(extendedLocation.name) "
                "| extend provisioningState = properties.provisioningState "
                "| project id, customLocation, location, name, resourceGroup, provisioningState, "
                "tags, type, subscriptionId"
            )

        query += custom_query or _build_query_body(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name
        )

        return self.query(query=query)

    def update(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
        # default dataset configurations
        default_dataset_publishing_interval: Optional[int] = None,
        default_dataset_sampling_interval: Optional[int] = None,
        default_dataset_queue_size: Optional[int] = None,
        default_dataset_key_frame_count: Optional[int] = None,
        default_dataset_start_instance: Optional[str] = None,
        default_datasets_custom_configuration: Optional[str] = None,
        default_datasets_destinations: Optional[str] = None,
        # default events configurations
        default_events_publishing_interval: Optional[int] = None,
        default_events_queue_size: Optional[int] = None,
        default_events_start_instance: Optional[str] = None,
        default_events_filter_type: Optional[str] = None,
        default_events_filter_clauses: Optional[List[str]] = None,  # path (req), type, field
        default_events_custom_configuration: Optional[str] = None,
        default_events_destinations: Optional[str] = None,
        # default management groups configurations
        default_mgmtg_custom_configuration: Optional[str] = None,
        # default streams configurations
        default_streams_custom_configuration: Optional[str] = None,
        default_streams_destinations: Optional[str] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        discovered_asset_refs: Optional[List[str]] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> dict:
        update_payload = {}
        if tags:
            update_payload["tags"] = tags

        properties = {}
        _update_asset_props(
            properties=properties,
            # dataset
            default_dataset_publishing_interval=default_dataset_publishing_interval,
            default_dataset_sampling_interval=default_dataset_sampling_interval,
            default_dataset_queue_size=default_dataset_queue_size,
            default_dataset_key_frame_count=default_dataset_key_frame_count,
            default_dataset_start_instance=default_dataset_start_instance,
            default_datasets_custom_configuration=default_datasets_custom_configuration,
            default_datasets_destinations=default_datasets_destinations,
            # event
            default_events_destinations=default_events_destinations,
            default_events_publishing_interval=default_events_publishing_interval,
            default_events_queue_size=default_events_queue_size,
            default_events_start_instance=default_events_start_instance,
            default_events_filter_type=default_events_filter_type,
            default_events_filter_clauses=default_events_filter_clauses,
            default_events_custom_configuration=default_events_custom_configuration,
            # mgmt
            default_mgmtg_custom_configuration=default_mgmtg_custom_configuration,
            # streams
            default_streams_custom_configuration=default_streams_custom_configuration,
            default_streams_destinations=default_streams_destinations,
            # other
            asset_type_refs=asset_type_refs,
            attributes=attributes,
            description=description,
            disabled=disabled,
            discovered_asset_refs=discovered_asset_refs,
            display_name=display_name,
            documentation_uri=documentation_uri,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        if properties:
            update_payload["properties"] = properties

        with console.status(f"Updating asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name,
                namespace_name,
                asset_name,
                update_payload
            )
            return wait_for_terminal_state(poller, **kwargs)


def process_dataset_configurations(
    original_configuration: Optional[str] = None,
    publishing_interval: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    queue_size: Optional[int] = None,
    key_frame_count: Optional[int] = None,
    start_instance: Optional[str] = None,
    custom_configuration: Optional[str] = None,
) -> str:
    # custom configuration takes precidence over other parameters
    if custom_configuration:
        # TODO: change process add config to return more generic messages
        return _process_additional_configuration(custom_configuration)

    result = json.loads(original_configuration) if original_configuration else {}
    if publishing_interval is not None:
        result["publishingInterval"] = publishing_interval
    if sampling_interval is not None:
        result["samplingInterval"] = sampling_interval
    if queue_size is not None:
        result["queueSize"] = queue_size
    if key_frame_count is not None:
        result["keyFrameCount"] = key_frame_count
    if start_instance is not None:
        result["startInstance"] = start_instance

    # TODO: spec check (min/max)
    return json.dumps(result)


def process_event_configurations(
    original_configuration: Optional[str] = None,
    publishing_interval: Optional[int] = None,
    queue_size: Optional[int] = None,
    start_instance: Optional[str] = None,
    filter_type: Optional[str] = None,
    filter_clauses: Optional[List[str]] = None,  # path (req), type, field
    custom_configuration: Optional[str] = None,
) -> str:
    # custom configuration takes precidence over other parameters
    if custom_configuration:
        return _process_additional_configuration(custom_configuration)

    result = json.loads(original_configuration) if original_configuration else {}
    if publishing_interval is not None:
        result["publishingInterval"] = publishing_interval
    if queue_size is not None:
        result["queueSize"] = queue_size
    if start_instance is not None:
        result["startInstance"] = start_instance

    if filter_type or filter_clauses:
        result["eventFilter"] = {}
    if filter_type is not None:
        result["eventFilter"]["typeDefinitionId"] = filter_type
    if filter_clauses:
        result["eventFilter"]["selectClauses"] = []
        for clause in filter_clauses or []:
            clause = parse_kvp_nargs(clause)
            if "path" not in clause:
                logger.warning(
                    f"Skipping event filter clause '{clause}', it must contain a 'path' key."
                )
                continue
            formatted_clause = {"browsePath": clause["path"]}
            if "type" in clause:
                formatted_clause["typeDefinitionId"] = clause.get("type")
            if "field" in clause:
                formatted_clause["fieldId"] = clause.get("field")
            result["eventFilter"]["selectClauses"].append(formatted_clause)

    # TODO: spec check (min/max)
    return json.dumps(result)


def build_destination(
    destination_args: List[str],
    allowed_types: Optional[List[str]] = None
) -> List[dict]:
    """
    Builds a destination dictionary for use in assets. The result will be one of the following formats:

    {
        "target": "BrokerStateStore",
        "configuration": {
            "key": "defaultValue"
        }
    }

    or

    {
        "target": "Storage",
        "configuration": {
            "path": "/tmp"
        }
    }

    or

    {
        "target": "Mqtt",
        "configuration": {
            "topic": "/contoso/test",
            "retain": "Never",
            "qos": "Qos0",
            "ttl": 3600
        }
    }
    """
    destination = {}
    destination_args = parse_kvp_nargs(destination_args)
    destination_args_copy = deepcopy(destination_args)
    if "key" in destination_args:
        destination = {
            "target": "BrokerStateStore",
            "configuration": {
                "key": destination_args.pop("key")
            }
        }
    elif "path" in destination_args:
        destination = {
            "target": "Storage",
            "configuration": {
                "path": destination_args.pop("path")
            }
        }
    else:
        if not all(
            key in destination_args for key in ["topic", "retain", "qos", "ttl"]
        ):
            raise RequiredArgumentMissingError(
                "For MQTT destinations, 'topic', 'retain', 'qos', and 'ttl' must be provided."
            )
        destination = {
            "target": "Mqtt",
            "configuration": {
                "topic": destination_args.pop("topic"),
                "retain": destination_args.pop("retain"),
                "qos": destination_args.pop("qos"),
                "ttl": int(destination_args.pop("ttl"))
            }
        }
    if allowed_types and destination["target"] not in allowed_types:
        raise InvalidArgumentValueError(
            f"Destination type '{destination['target']}' is not allowed. "
            f"Allowed types are: {', '.join(allowed_types)}."
        )
    if destination_args:
        raise MutuallyExclusiveArgumentError(
            f"Conflicting arguments for destination: {', '.join(destination_args_copy.keys())}\n"
            "For BrokerStateStore, only 'key' is allowed.\n"
            "For Storage, only 'path' is allowed.\n"
            "For Mqtt, all of 'topic', 'retain', 'qos', and 'ttl' are allowed and required."
        )

    return [destination]


def _update_asset_props(  # noqa: C901
    properties: dict,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    # default dataset configurations
    default_dataset_publishing_interval: Optional[int] = None,
    default_dataset_sampling_interval: Optional[int] = None,
    default_dataset_queue_size: Optional[int] = None,
    default_dataset_key_frame_count: Optional[int] = None,
    default_dataset_start_instance: Optional[str] = None,
    default_datasets_custom_configuration: Optional[str] = None,
    default_datasets_destinations: Optional[str] = None,
    # default events configurations
    default_events_publishing_interval: Optional[int] = None,
    default_events_queue_size: Optional[int] = None,
    default_events_start_instance: Optional[str] = None,
    default_events_filter_type: Optional[str] = None,
    default_events_filter_clauses: Optional[List[str]] = None,  # path (req), type, field
    default_events_custom_configuration: Optional[str] = None,
    default_events_destinations: Optional[str] = None,
    # default management groups configurations
    default_mgmtg_custom_configuration: Optional[str] = None,
    # default streams configurations
    default_streams_custom_configuration: Optional[str] = None,
    default_streams_destinations: Optional[str] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
    discovered_asset_refs: Optional[List[str]] = None,
    display_name: Optional[str] = None,
    documentation_uri: Optional[str] = None,
    external_asset_id: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_uri: Optional[str] = None,
    model: Optional[str] = None,
    product_code: Optional[str] = None,
    serial_number: Optional[str] = None,
    software_revision: Optional[str] = None,
):
    if asset_type_refs:
        properties["assetTypeRefs"] = asset_type_refs
    if attributes:
        properties["attributes"] = parse_kvp_nargs(attributes)
    if default_datasets_destinations:
        properties["defaultDatasetsDestinations"] = build_destination(default_datasets_destinations)
    if default_events_destinations:
        properties["defaultEventsDestinations"] = build_destination(default_events_destinations)
    if default_mgmtg_custom_configuration:
        properties["defaultManagementGroupsConfiguration"] = _process_additional_configuration(
            default_mgmtg_custom_configuration
        )
    if default_streams_custom_configuration:
        properties["defaultStreamsConfiguration"] = _process_additional_configuration(
            default_streams_custom_configuration
        )
    if default_streams_destinations:
        properties["defaultStreamsDestinations"] = build_destination(default_streams_destinations)
    if description:
        properties["description"] = description
    if disabled is not None:
        properties["enabled"] = not disabled
    if discovered_asset_refs:
        properties["discoveredAssetRefs"] = discovered_asset_refs
    if display_name:
        properties["displayName"] = display_name
    if documentation_uri:
        properties["documentationUri"] = documentation_uri
    if external_asset_id:
        properties["externalAssetId"] = external_asset_id
    if hardware_revision:
        properties["hardwareRevision"] = hardware_revision
    if manufacturer:
        properties["manufacturer"] = manufacturer
    if manufacturer_uri:
        properties["manufacturerUri"] = manufacturer_uri
    if model:
        properties["model"] = model
    if product_code:
        properties["productCode"] = product_code
    if serial_number:
        properties["serialNumber"] = serial_number
    if software_revision:
        properties["softwareRevision"] = software_revision

    if any([
        default_dataset_publishing_interval,
        default_dataset_sampling_interval,
        default_dataset_queue_size,
        default_dataset_key_frame_count,
        default_dataset_start_instance,
        default_datasets_custom_configuration
    ]):
        properties["defaultDatasetsConfiguration"] = process_dataset_configurations(
            custom_configuration=default_datasets_custom_configuration,
            publishing_interval=default_dataset_publishing_interval,
            sampling_interval=default_dataset_sampling_interval,
            queue_size=default_dataset_queue_size,
            key_frame_count=default_dataset_key_frame_count,
            start_instance=default_dataset_start_instance
        )

    if any([
        default_events_publishing_interval,
        default_events_queue_size,
        default_events_start_instance,
        default_events_filter_type,
        default_events_filter_clauses,
        default_events_custom_configuration
    ]):
        properties["defaultEventsConfiguration"] = process_event_configurations(
            custom_configuration=default_events_custom_configuration,
            publishing_interval=default_events_publishing_interval,
            queue_size=default_events_queue_size,
            start_instance=default_events_start_instance,
            filter_type=default_events_filter_type,
            filter_clauses=default_events_filter_clauses
        )
