# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import json
from rich.console import Console
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from knack.log import get_logger

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)

from ....util.common import parse_kvp_nargs, should_continue_prompt
from ....util.az_client import get_registry_refresh_mgmt_client, get_resource_client, wait_for_terminal_state
from ....util.queryable import Queryable
from .helpers import process_additional_configuration, ensure_schema_structure, get_default_dataset
from .namespace_devices import DeviceEndpointType

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt_v2.operations import (
        NamespaceAssetsOperations, NamespaceDevicesOperations
    )
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
        self.device_ops: "NamespaceDevicesOperations" = self.deviceregistry_mgmt_client.namespace_devices
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def create(  # noqa: C901
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        device_name: str,
        device_endpoint_name: str,
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
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
        """Creates a new asset in the specified namespace.

        kwargs will contain arguments used for default configurations and destinations.
        """
        # TODO: future, Add in options to import from files for datasets, events, streams, and mgmt groups

        # use the device to get the location, extended location, and check type and endpoint
        device = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name
        )

        # Initialize properties dictionary
        properties = {
            "deviceRef": {
                "deviceName": device_name,
                "endpointName": device_endpoint_name
            }
        }

        # handle the configs + destinations
        config_destinations = _process_configs(
            asset_type=asset_type,
            **kwargs
        )
        # might need to do some processing in the future
        properties.update(config_destinations)

        # other props
        _update_asset_props(
            properties=properties,
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
            "extendedLocation": device["extendedLocation"],
            "location": device["location"],
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
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return
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
        resource_group_name: str,
        check_cluster: bool = False
    ) -> dict:
        asset = self.ops.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        )
        if check_cluster:
            from .helpers import check_cluster_connectivity
            check_cluster_connectivity(self.cmd, asset)

        return asset

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
        # later on, add namespace (needs id parsing), location, device endpoint type (will need to add joins)
        def _build_query_body(
            asset_name: Optional[str] = None,
            resource_group_name: Optional[str] = None,
            device_name: Optional[str] = None,
            device_endpoint_name: Optional[str] = None
        ) -> str:
            query_body = ""
            # add in namespace name
            if resource_group_name:
                query_body += f' | where resourceGroup =~ "{resource_group_name}"'
            if asset_name:
                query_body += f' | where name =~ "{asset_name}"'
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
        asset_type: str,
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
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
        # need original asset default configurations to update
        asset_properties = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )["properties"]

        # update payload
        update_payload = {}
        if tags:
            update_payload["tags"] = tags

        properties = {}

        # handle the configs + destinations
        original_configs = {
            "original_dataset_configuration": asset_properties.get("defaultDatasetsConfiguration"),
            "original_event_configuration": asset_properties.get("defaultEventsConfiguration"),
            "original_mgmt_configuration": asset_properties.get("defaultManagementGroupsConfiguration"),
            "original_streams_configuration": asset_properties.get("defaultStreamsConfiguration"),
            "original_dataset_destinations": asset_properties.get("defaultDatasetsDestinations"),
            "original_event_destinations": asset_properties.get("defaultEventsDestinations"),
            "original_stream_destinations": asset_properties.get("defaultStreamsDestinations"),
        }
        config_destinations = _process_configs(
            asset_type=asset_type,
            **original_configs,
            **kwargs
        )
        # might need to do some processing in the future
        properties.update(config_destinations)

        _update_asset_props(
            properties=properties,
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

    # DATASETS - only allowed for opcua and custom assets
    def add_dataset(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        dataset_name: str,
        dataset_data_source: str,
        # TODO: singular dataset
        dataset_destinations: Optional[List[str]] = None,
        replace: bool = False,
        # TODO: future pr, import datapoints from file
        **kwargs
    ):
        # TODO: future, multi data support
        if dataset_name != "default":
            raise InvalidArgumentValueError(
                "Currently only one dataset with the name 'default' is supported. "
                "Please use 'default' as the dataset name."
            )
        asset = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # get the datasets from the asset
        datasets = asset["properties"].get("datasets", [])

        # current restriction to one dataset
        if datasets and not replace:
            raise InvalidArgumentValueError(
                "Currently only one dataset with the name 'default' is supported. "
                "Please use 'default' as the dataset name. If you want to update the dataset properties, "
                "please use the update command."
            )

        # create the dataset
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            dataset_destinations=dataset_destinations,
            **kwargs
        )
        datasets = [
            {
                "name": dataset_name,
                "dataSource": dataset_data_source,
                "datasetConfiguration": processed_configs.get("datasetsConfiguration"),
                "destinations": processed_configs.get("datasetsDestinations", []),
                "dataPoints": [],  # TODO: future pr, add datapoints
            }
        ]

        update_payload = {
            "properties": {
                "datasets": datasets
            }
        }
        with console.status(f"Adding dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            datasets = wait_for_terminal_state(poller, **kwargs)["properties"]["datasets"]
            return next(dset for dset in datasets if dset["name"] == dataset_name)

    def list_datasets(self, asset_name: str, namespace_name: str, resource_group_name: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        return asset["properties"].get("datasets", [])

    def show_dataset(
        self, asset_name: str, namespace_name: str, resource_group_name: str, dataset_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        return get_default_dataset(asset, dataset_name)

    def update_dataset(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        dataset_name: str,
        dataset_data_source: Optional[str] = None,
        dataset_type_ref: Optional[str] = None,
        dataset_destinations: Optional[List[str]] = None,
        **kwargs
    ):
        asset = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # get the datasets from the asset
        datasets = asset["properties"].get("datasets", [])
        # check if dataset exists
        dataset = [dset for dset in datasets if dset["name"] == dataset_name]
        if not dataset:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' not found in asset '{asset_name}'. "
            )
        dataset = dataset[0]

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_dataset_configuration=dataset.get("datasetConfiguration"),
            dataset_destinations=dataset_destinations,
            **kwargs
        )

        # update the dataset properties
        if "datasetsConfiguration" in processed_configs:
            dataset["datasetConfiguration"] = processed_configs["datasetsConfiguration"]
        if dataset_data_source:
            dataset["dataSource"] = dataset_data_source
        if dataset_type_ref:
            dataset["typeRef"] = dataset_type_ref
        if dataset_destinations:
            dataset["destinations"] = processed_configs.get("datasetsDestinations", [])

        update_payload = {
            "properties": {
                "datasets": datasets
            }
        }
        with console.status(f"Updating dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            datasets = wait_for_terminal_state(poller, **kwargs)["properties"]["datasets"]
            return next(dset for dset in datasets if dset["name"] == dataset_name)

    def remove_dataset(
        self, asset_name: str, namespace_name: str, resource_group_name: str, dataset_name: str, **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )

        datasets = asset["properties"].get("datasets", [])
        # note that delete should be ok with dataset not there
        remaining_datasets = [dset for dset in datasets if dset["name"] != dataset_name]

        if len(remaining_datasets) == len(datasets):
            logger.info(f"Dataset '{dataset_name}' not found in asset '{asset_name}'.")
            return datasets  # no change, return the original datasets

        update_payload = {
            "properties": {
                "datasets": remaining_datasets
            }
        }
        with console.status(f"Removing dataset {dataset_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            return wait_for_terminal_state(poller, **kwargs)["properties"]["datasets"]

    def add_dataset_datapoint(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        dataset_name: str,
        datapoint_name: str,
        data_source: str,
        # Custom
        custom_configuration: Optional[str] = None,
        # OPCUA specific
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        # note that for now, we will not expose typeref for dataset datapoints
        asset = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        dataset = get_default_dataset(asset, dataset_name, create_if_none=True)

        # get the datapoints
        datapoints = dataset["dataPoints"]
        non_matched_points = [point for point in datapoints if point["name"] != datapoint_name]
        if len(non_matched_points) < len(datapoints) and not replace:
            raise InvalidArgumentValueError(
                f"Datapoint '{datapoint_name}' already exists in dataset '{dataset_name}' of asset '{asset_name}'. "
                "Use --replace to overwrite the existing datapoint."
            )

        # create the datapoint
        datapoint = _create_datapoint(
            datapoint_name=datapoint_name,
            data_source=data_source,
            queue_size=queue_size,
            sampling_interval=sampling_interval,
            custom_configuration=custom_configuration
        )
        non_matched_points.append(datapoint)
        dataset["dataPoints"] = non_matched_points

        update_payload = {
            "properties": {
                "datasets": asset["properties"]["datasets"]
            }
        }

        with console.status(f"Updating asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name,
                namespace_name,
                asset_name,
                update_payload
            )
            asset = wait_for_terminal_state(poller, **kwargs)
            return get_default_dataset(asset, dataset_name)["dataPoints"]

    def list_dataset_datapoints(
        self, asset_name: str, namespace_name: str, resource_group_name: str, dataset_name: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        return get_default_dataset(asset, dataset_name)["dataPoints"]

    def remove_dataset_datapoint(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        dataset_name: str,
        datapoint_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )

        dataset = get_default_dataset(asset, dataset_name)
        datapoints = dataset.get("dataPoints", [])
        # note that delete should be ok with datapoint not there
        dataset["dataPoints"] = [dp for dp in datapoints if dp["name"] != datapoint_name]

        if len(dataset["dataPoints"]) == len(datapoints):
            logger.info(
                f"Datapoint '{datapoint_name}' not found in dataset '{dataset_name}' of asset '{asset_name}'."
            )
            return dataset["dataPoints"]

        update_payload = {
            "properties": {
                "datasets": asset["properties"]["datasets"]
            }
        }
        with console.status(
            f"Removing datapoint {datapoint_name} from dataset {dataset_name} in asset {asset_name}..."
        ):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            asset = wait_for_terminal_state(poller, **kwargs)
            return get_default_dataset(asset, dataset_name)["dataPoints"]

    # EVENTS - allowed for opcua, and custom assets
    def add_event(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        event_name: str,
        event_notifier: str,
        event_destinations: Optional[List[str]] = None,  # this can go into kwargs
        replace: bool = False,
        # TODO: future pr, add datapoints
        **kwargs
    ) -> dict:
        asset = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        events = asset["properties"].get("events", [])
        # remove event if it exists
        unmatched_events = [event for event in events if event["name"] != event_name]
        if len(unmatched_events) < len(events) and not replace:
            raise InvalidArgumentValueError(
                f"Event '{event_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing event."
            )

        # create the event
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            event_destinations=event_destinations,
            **kwargs
        )
        unmatched_events.append(
            {
                "name": event_name,
                "eventNotifier": event_notifier,
                "eventConfiguration": processed_configs.get("eventsConfiguration"),
                "destinations": processed_configs.get("eventsDestinations", []),
                "dataPoints": []  # TODO: future pr, add datapoints
            }
        )

        update_payload = {
            "properties": {
                "events": unmatched_events
            }
        }
        with console.status(f"Adding event {event_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            events = wait_for_terminal_state(poller, **kwargs)["properties"]["events"]
            return next(event for event in events if event["name"] == event_name)

    def list_events(self, asset_name: str, namespace_name: str, resource_group_name: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        return asset["properties"].get("events", [])

    def show_event(
        self, asset_name: str, namespace_name: str, resource_group_name: str, event_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        )
        return _get_event(asset, event_name)

    def remove_event(
        self, asset_name: str, namespace_name: str, resource_group_name: str, event_name: str, **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )

        events = asset["properties"].get("events", [])
        # note that delete should be ok with event not there
        remaining_events = [event for event in events if event["name"] != event_name]

        # if the event is not found, we should not update
        if len(remaining_events) == len(events):
            logger.info(f"Event '{event_name}' not found in asset '{asset_name}'.")
            return events

        update_payload = {
            "properties": {
                "events": remaining_events
            }
        }
        with console.status(f"Removing event {event_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            return wait_for_terminal_state(poller, **kwargs)["properties"]["events"]

    def update_event(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        event_name: str,
        event_notifier: Optional[str] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ):
        asset = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if event exists
        event = _get_event(asset, event_name)

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_event_configuration=event.get("eventConfiguration"),
            **kwargs
        )

        # update the event properties
        if "eventsConfiguration" in processed_configs:
            event["eventConfiguration"] = processed_configs["eventsConfiguration"]
        if event_notifier:
            event["eventNotifier"] = event_notifier
        if type_ref:
            event["typeRef"] = type_ref
        if "eventsDestinations" in processed_configs:
            event["destinations"] = processed_configs["eventsDestinations"]

        # get the events from the asset
        events = asset["properties"].get("events", [])
        update_payload = {
            "properties": {
                "events": events
            }
        }
        with console.status(f"Updating event {event_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            events = wait_for_terminal_state(poller, **kwargs)["properties"]["events"]
            return next(event for event in events if event["name"] == event_name)

    # EVENT DATAPOINTS - allowed for opcua, onvif, and custom assets
    def add_event_datapoint(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        asset_type: str,
        event_name: str,
        datapoint_name: str,
        data_source: str,
        # Custom
        custom_configuration: Optional[str] = None,
        # OPCUA specific
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        # note that event datapoints do not have type-refs
        asset = self._check_device_props(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_type=asset_type,
            asset_name=asset_name
        )

        # check if event exists
        event = _get_event(asset, event_name)

        # get the datapoints
        datapoints = event.get("dataPoints", [])
        non_matched_points = [point for point in datapoints if point["name"] != datapoint_name]
        if len(non_matched_points) < len(datapoints) and not replace:
            raise InvalidArgumentValueError(
                f"Datapoint '{datapoint_name}' already exists in event '{event_name}' of asset '{asset_name}'. "
                "Use --replace to overwrite the existing datapoint."
            )

        # create the datapoint
        datapoint = _create_datapoint(
            datapoint_name=datapoint_name,
            data_source=data_source,
            queue_size=queue_size,
            sampling_interval=sampling_interval,
            custom_configuration=custom_configuration,
        )
        non_matched_points.append(datapoint)
        event["dataPoints"] = non_matched_points

        # get the events from the asset
        events = asset["properties"].get("events", [])
        update_payload = {
            "properties": {
                "events": events
            }
        }
        with console.status(f"Adding datapoint {datapoint_name} to event {event_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            events = wait_for_terminal_state(poller, **kwargs)["properties"]["events"]
            # note that we return a list of datapoints
            return next(event for event in events if event["name"] == event_name)["dataPoints"]

    def list_event_datapoints(
        self, asset_name: str, namespace_name: str, resource_group_name: str, event_name: str
    ):
        event = self.show_event(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            event_name=event_name
        )
        return event.get("dataPoints", [])

    def remove_event_datapoint(
        self,
        asset_name: str,
        namespace_name: str,
        resource_group_name: str,
        event_name: str,
        datapoint_name: str,
        **kwargs
    ):
        asset = self.show(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )

        event = _get_event(asset, event_name)
        datapoints = event.get("dataPoints", [])
        # note that delete should be ok with datapoint not there
        event["dataPoints"] = [dp for dp in datapoints if dp["name"] != datapoint_name]

        # no need for update if the datapoint is not found
        if len(event["dataPoints"]) == len(datapoints):
            logger.info(
                f"Datapoint '{datapoint_name}' not found in event '{event_name}' of asset '{asset_name}'."
            )
            return event["dataPoints"]

        events = asset["properties"].get("events", [])
        update_payload = {
            "properties": {
                "events": events
            }
        }
        with console.status(
            f"Removing datapoint {datapoint_name} from event {event_name} in asset {asset_name}..."
        ):
            poller = self.ops.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                properties=update_payload
            )
            events = wait_for_terminal_state(poller, **kwargs)["properties"]["events"]
            # note that we return a list of datapoints
            return next(event for event in events if event["name"] == event_name)["dataPoints"]

    # TODO: future pr
    # STREAMS - allowed for media and custom assets
    # Management Groups - allowed for opcua, onvif, and custom assets

    # TODO: update unit tests to have asset types as list
    def _check_device_props(
        self,
        resource_group_name: str,
        namespace_name: str,
        asset_type: Union[List[str], str],  # change to list
        asset_name: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None
    ) -> dict:
        """
        Checks the device properties to ensure the endpoint type matches the asset operation's type.
        Returns the asset if the asset name is provided, otherwise the device
        (device name and device endpoint name must be provided).

        This also includes the cluster connectivity check.

        If asset_name is provided (in the case of the asset is already created), it will retrieve the
        asset to populate the device_name and device_endpoint_name.
        """
        from azext_edge.edge.providers.rpsaas.adr.helpers import check_cluster_connectivity

        asset = None
        if asset_name:
            # get the asset to populate the device name and endpoint name
            asset = self.show(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            )
            device_name = asset["properties"]["deviceRef"]["deviceName"]
            device_endpoint_name = asset["properties"]["deviceRef"]["endpointName"]

        device = self.device_ops.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name
        )

        # use the device to check cluster connectivity
        check_cluster_connectivity(self.cmd, device)

        # ensure device has the endpoint
        device_endpoint = device["properties"].get("endpoints", {}).get("inbound", {}).get(device_endpoint_name)
        if not device_endpoint:
            raise InvalidArgumentValueError(
                f"Device endpoint '{device_endpoint_name}' not found in device '{device_name}'."
            )

        if isinstance(asset_type, str):
            asset_type = [asset_type]
        # asset type must be the same as endpoint type unless either is custom
        device_type_list = [d.lower() for d in DeviceEndpointType.list()]
        allowed = True
        for at in asset_type:
            if (
                at.lower() in device_type_list
                and device_endpoint["endpointType"].lower() in device_type_list
                and at.lower() != device_endpoint["endpointType"].lower()
            ):
                allowed = False
                break

        # we could also change this to a y/n warning prompt
        if not allowed:
            raise InvalidArgumentValueError(
                f"Device endpoint '{device_endpoint_name}' is of type '{device_endpoint['endpointType']}', "
                f"but expected '{' or '.join(asset_type)}'."
            )

        return asset if asset_name else device


# Helpers
def _build_destination(
    destination_args: List[str],
    allowed_types: Optional[List[str]] = None
) -> List[dict]:
    """
    Builds a destination dictionary for use in assets. The result will be one of the following formats:

    [{
        "target": "BrokerStateStore",
        "configuration": {
            "key": "defaultValue"
        }
    }]

    or

    [{
        "target": "Storage",
        "configuration": {
            "path": "/tmp"
        }
    }]

    or

    [{
        "target": "Mqtt",
        "configuration": {
            "topic": "/contoso/test",
            "retain": "Never",  # TODO: enum for this, Keep
            "qos": "Qos0",  # TODO: enum for this, Qos1
            "ttl": 3600
        }
    }]

    or [] if no arguments are provided

    Note that this will replace rather than update current destinations. Right now there is support
    for only one destination at a time, but this may change in the future.
    """
    if not destination_args:
        return []
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
    elif any(
        key in destination_args for key in ["topic", "retain", "qos", "ttl"]
    ):
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


def _create_datapoint(
    datapoint_name: str,
    data_source: str,
    type_ref: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    custom_configuration: Optional[str] = None,
) -> dict:
    """Helper function to create a datapoint dictionary."""
    datapoint = {
        "name": datapoint_name,
        "dataSource": data_source,
    }
    if type_ref:
        datapoint["typeRef"] = type_ref

    # if custom configuration is provided, process it and return early
    if custom_configuration:
        datapoint["dataPointConfiguration"] = process_additional_configuration(
            additional_configuration=custom_configuration,
            config_type="datapoint"
        )
        return datapoint

    # otherwise process opcua specific configurations if provided
    additional_configuration = {}
    if queue_size is not None:
        additional_configuration["queueSize"] = queue_size
    if sampling_interval is not None:
        additional_configuration["samplingInterval"] = sampling_interval
    if additional_configuration:
        from .specs import NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA
        ensure_schema_structure(
            NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA, input_data=additional_configuration
        )
    datapoint["dataPointConfiguration"] = json.dumps(additional_configuration)
    # process configurations
    return datapoint


def _get_event(asset: dict, event_name: str) -> dict:
    """Helper function to get an event from an asset.

    Raises InvalidArgumentValueError if the event is not found.
    """
    events = asset["properties"].get("events", [])
    matched_events = [event for event in events if event["name"] == event_name]
    if not matched_events:
        raise InvalidArgumentValueError(f"Event '{event_name}' not found in asset '{asset['name']}'.")
    return matched_events[0]


# maybe move the config processing functions to specs?
def _process_configs(
    asset_type: str,
    default: bool = True,
    **kwargs
) -> dict:
    """Main function to process all of the config + destination args based on asset type.

    Destination and custom configuration arguments will be treated as an overwrite rather than update.
    For destinations, currently only one destination is supported but there may be more than one in the future.
    """
    result = {}
    asset_type = asset_type.lower()
    if asset_type == DeviceEndpointType.OPCUA.value.lower():
        # allowed: datasets, events, mgmt groups, destinations must be mqtt
        # not allowed: streams
        # still waiting on opcua mgmt group schemas
        result = {
            "datasetsConfiguration": _process_opcua_dataset_configurations(
                **kwargs
            ),
            "eventsConfiguration": _process_opcua_event_configurations(
                **kwargs
            ),
            "managementGroupsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("mgmt_custom_configuration"),
                config_type="management group"
            ),
            "datasetsDestinations": _build_destination(
                destination_args=kwargs.get("dataset_destinations", []),
                allowed_types=["Mqtt"]
            ),
            "eventsDestinations": _build_destination(
                destination_args=kwargs.get("event_destinations", []),
                allowed_types=["Mqtt"]
            ),
        }
    elif asset_type == DeviceEndpointType.ONVIF.value.lower():
        # allowed: events (no schema), mgmt groups, destinations must be mqtt
        # not allowed: datasets, streams
        # still waiting on onvif mgmt group schemas
        result = {
            "managementGroupsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("mgmt_custom_configuration"),
                config_type="management group"
            ),
            "eventsDestinations": _build_destination(
                destination_args=kwargs.get("event_destinations", []),
                allowed_types=["Mqtt"]
            )
        }
    elif asset_type == DeviceEndpointType.MEDIA.value.lower():
        # allowed: streams, destinations can be mqtt or storage
        # not allowed: datasets, events, mgmt groups
        result = {
            "streamsConfiguration": _process_media_stream_configurations(
                **kwargs
            ),
            "streamsDestinations": _build_destination(
                destination_args=kwargs.get("stream_destinations", []),
                allowed_types=["Storage", "Mqtt"]
            )
        }
    else:
        # Custom - treat everything as an overwrite
        result = {
            "datasetsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("datasets_custom_configuration"),
                config_type="dataset"
            ),
            "eventsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("events_custom_configuration"),
                config_type="event"
            ),
            "managementGroupsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("mgmt_custom_configuration"),
                config_type="management group"
            ),
            "streamsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("streams_custom_configuration"),
                config_type="stream"
            ),
            "datasetsDestinations": _build_destination(
                destination_args=kwargs.get("dataset_destinations", []),
            ),
            "eventsDestinations": _build_destination(
                destination_args=kwargs.get("event_destinations", []),
            ),
            "streamsDestinations": _build_destination(
                destination_args=kwargs.get("stream_destinations", []),
            )
        }

    # if default, captalize and add in "default" to key
    if default:
        for key in list(result.keys()):
            # Capitalize the first letter of OG key
            new_key = "default" + key[0].upper() + key[1:]
            result[new_key] = result.pop(key)

    # pop empty values:
    result = {k: v for k, v in result.items() if v}
    return result


def _process_opcua_dataset_configurations(
    original_dataset_configuration: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA
    result = json.loads(original_dataset_configuration) if original_dataset_configuration else {}
    if opcua_dataset_publishing_interval is not None:
        result["publishingInterval"] = opcua_dataset_publishing_interval
    if opcua_dataset_sampling_interval is not None:
        result["samplingInterval"] = opcua_dataset_sampling_interval
    if opcua_dataset_queue_size is not None:
        result["queueSize"] = opcua_dataset_queue_size
    if opcua_dataset_key_frame_count is not None:
        result["keyFrameCount"] = opcua_dataset_key_frame_count
    if opcua_dataset_start_instance is not None:
        result["startInstance"] = opcua_dataset_start_instance

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_event_configurations(
    original_event_configuration: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_start_instance: Optional[str] = None,
    opcua_event_filter_type: Optional[str] = None,
    opcua_event_filter_clauses: Optional[List[List[str]]] = None,  # path (req), type, field
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA

    result = json.loads(original_event_configuration) if original_event_configuration else {}
    if opcua_event_publishing_interval is not None:
        result["publishingInterval"] = opcua_event_publishing_interval
    if opcua_event_queue_size is not None:
        result["queueSize"] = opcua_event_queue_size
    if opcua_event_start_instance is not None:
        result["startInstance"] = opcua_event_start_instance

    if opcua_event_filter_type or opcua_event_filter_clauses:
        result["eventFilter"] = {}
    if opcua_event_filter_type is not None:
        result["eventFilter"]["typeDefinitionId"] = opcua_event_filter_type
    if opcua_event_filter_clauses:
        result["eventFilter"]["selectClauses"] = []
        for clause in opcua_event_filter_clauses or []:
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

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA,
        input_data=result
    )
    return json.dumps(result)


def _process_media_stream_configurations(
    original_stream_configuration: Optional[str] = None,
    task_type: Optional[str] = None,
    task_format: Optional[str] = None,
    snapshots_per_second: Optional[int] = None,
    path: Optional[str] = None,
    duration: Optional[int] = None,
    media_server_address: Optional[str] = None,
    media_server_path: Optional[str] = None,
    media_server_port: Optional[int] = None,
    media_server_username: Optional[str] = None,
    media_server_password: Optional[str] = None,
    media_server_certificate: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA, MediaFormat, MediaTaskType
    result = json.loads(original_stream_configuration) if original_stream_configuration else {}

    task_type = task_type or result.get("taskType")
    if not task_type:
        if not any([
            task_format, snapshots_per_second, path, duration,
            media_server_address, media_server_path, media_server_port,
            media_server_username, media_server_password, media_server_certificate
        ]):
            return original_stream_configuration
        else:
            raise RequiredArgumentMissingError(
                "Task type via --task-type must be provided when configuring media stream properties."
            )
    allowed_properties = MediaTaskType(task_type).allowed_properties

    # empty result if changing task type
    if result.get("taskType") and task_type != result.get("taskType"):
        logger.warning("Changing Media Stream Configuration task type, resetting configuration.")
        result = {}

    # Process provided parameters and update result
    for property_name, param_value in {
        "format": task_format,
        "snapshotsPerSecond": snapshots_per_second,
        "path": path,
        "duration": duration,
        "mediaServerAddress": media_server_address,
        "mediaServerPath": media_server_path,
        "mediaServerPort": media_server_port,
        "mediaServerUsernameRef": media_server_username,
        "mediaServerPasswordRef": media_server_password,
        "mediaServerCertificateRef": media_server_certificate
    }.items():
        # Skip None values
        if param_value is None:
            continue

        # Check if this property is allowed for the current task type
        if property_name not in allowed_properties:
            raise InvalidArgumentValueError(
                f"Property '{property_name}' is not allowed for task type '{task_type}'. "
                f"Allowed properties: {allowed_properties}"
            )

        # Validate format based on the task type
        if property_name == "format" and param_value:
            format_enum = MediaFormat(param_value)
            # Validate format for clip tasks
            if task_type == MediaTaskType.clip_to_fs.value:
                if not format_enum.allowed_for_clip:
                    clip_formats = [
                        f.value for f in MediaFormat
                        if MediaFormat(f.value).allowed_for_clip
                    ]
                    raise InvalidArgumentValueError(
                        f"Invalid format for clip task: '{param_value}'. "
                        f"Valid formats: {clip_formats}"
                    )
            # Validate format for snapshot tasks
            else:
                if not format_enum.allowed_for_snapshot:
                    snapshot_formats = [
                        f.value for f in MediaFormat
                        if MediaFormat(f.value).allowed_for_snapshot
                    ]
                    raise InvalidArgumentValueError(
                        f"Invalid format for snapshot task: '{param_value}'. "
                        f"Valid formats: {snapshot_formats}"
                    )

        # Apply the value to the result
        result[property_name] = param_value

    result["taskType"] = MediaTaskType(task_type).value
    # Final schema validation
    ensure_schema_structure(
        schema=NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
        input_data=result
    )
    return json.dumps(result)


def _update_asset_props(
    properties: dict,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
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
    # TODO: currently max num of asset type ref is 1
    if asset_type_refs:
        properties["assetTypeRefs"] = asset_type_refs
    if attributes:
        properties["attributes"] = parse_kvp_nargs(attributes)
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
