# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    ValidationError,
)
from knack.log import get_logger
from rich.console import Console

from ...util.az_client import (
    get_registry_mgmt_client,
    get_resource_client,
    wait_for_terminal_state
)
from ...util import dump_content_to_file
from ...util.common import parse_kvp_nargs, should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.queryable import Queryable
from .common import FileType
from .helpers import (
    check_cluster_connectivity,
    ensure_schema_structure,
    get_instance_query,
    get_namespace_for_instance,
    get_query,
    process_additional_configuration,
)
from .namespace_devices import DeviceEndpointType
from .validator import ConnectorMetadataValidator

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt.operations import (
        NamespaceAssetsOperations,
        NamespaceDevicesOperations,
    )
    from ...vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)
NAMESPACE_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/assets"


def _convert_sub_points_to_csv_namespace(
    sub_points: List[Dict[str, str]],
    sub_point_type: str,
    default_configuration: str,
    portal_friendly: bool = False
) -> List[str]:
    """Convert datapoints or events to CSV format. Modifies sub_points in-place."""
    from collections import OrderedDict

    csv_conversion_map = [
        ("queueSize", "QueueSize" if portal_friendly else "Queue Size"),
        ("observabilityMode", "ObservabilityMode" if portal_friendly else "Observability Mode"),
    ]

    if not portal_friendly or sub_point_type == "dataPoints":
        csv_conversion_map.append(("samplingInterval", "Sampling Interval Milliseconds"))
    if not portal_friendly:
        csv_conversion_map.append(("capabilityId", "Capability Id"))

    if sub_point_type == "dataPoints":
        csv_conversion_map.insert(0, ("dataSource", "NodeID" if portal_friendly else "Data Source"))
        csv_conversion_map.insert(1, ("name", "TagName" if portal_friendly else "Name"))
    else:
        csv_conversion_map.insert(0, ("dataSource", "Data Source"))
        csv_conversion_map.insert(1, ("name", "EventName" if portal_friendly else "Name"))

    csv_conversion_map = OrderedDict(csv_conversion_map)
    default_config = json.loads(default_configuration) if portal_friendly else {}

    for point in sub_points:
        config_key = f"{sub_point_type[:-1]}Configuration"
        configuration = point.pop(config_key, "{}")
        point.update(json.loads(configuration))

        if portal_friendly:
            point.pop("capabilityId", None)
            if sub_point_type == "events":
                point.pop("samplingInterval", None)

        for asset_key, csv_key in csv_conversion_map.items():
            point[csv_key] = point.pop(asset_key, default_config.get(asset_key))

    return list(csv_conversion_map.values())


def _convert_sub_points_from_csv_namespace(sub_points: List[Dict[str, str]]):
    """Convert CSV format back to JSON. Modifies sub_points in-place."""
    csv_conversion_map = {
        "CapabilityId": "capabilityId",
        "Capability Id": "capabilityId",
        "Data Source": "dataSource",
        "EventName": "name",
        "EventNotifier": "eventNotifier",
        "Event Notifier": "eventNotifier",
        "Name": "name",
        "NodeID": "dataSource",
        "ObservabilityMode": "observabilityMode",
        "Observability Mode": "observabilityMode",
        "QueueSize": "queueSize",
        "Queue Size": "queueSize",
        "Sampling Interval Milliseconds": "samplingInterval",
        "TagName": "name",
    }

    for point in sub_points:
        point.pop("", None)

        for csv_key, json_key in csv_conversion_map.items():
            if csv_key in point:
                point[json_key] = point.pop(csv_key)

        configuration = {}
        # Move observabilityMode to configuration if it exists and is not empty
        observability_value = point.pop("observabilityMode", None)
        if observability_value and observability_value.strip():
            configuration["observabilityMode"] = observability_value.strip().capitalize()

        # Move samplingInterval to configuration if it exists and is not empty
        sampling_value = point.pop("samplingInterval", None)
        if sampling_value and str(sampling_value).strip():
            configuration["samplingInterval"] = int(sampling_value)

        # Move queueSize to configuration if it exists and is not empty
        queue_value = point.pop("queueSize", None)
        if queue_value and str(queue_value).strip():
            configuration["queueSize"] = int(queue_value)

        if configuration:
            config_key = "dataPointConfiguration" if "dataSource" in point else "eventConfiguration"
            point[config_key] = json.dumps(configuration)


def _convert_actions_to_csv(actions: List[Dict[str, str]]) -> List[str]:
    """Convert actions to CSV format. Modifies actions in-place and returns fieldnames."""
    # CSV column order per DOE design
    fieldnames = ["name", "targetUri", "actionType", "topic", "timeoutInSeconds"]

    for action in actions:
        # Ensure all standard fields are present (empty string if missing)
        for field in fieldnames:
            if field not in action:
                action[field] = ""
            elif action[field] is None:
                action[field] = ""

    return fieldnames


def _convert_actions_from_csv(actions: List[Dict[str, str]]):
    """Convert CSV format back to action objects. Modifies actions in-place."""
    # Only map CSV column names that differ from JSON property names
    csv_to_json_map = {
        "Name": "name",
        "Target URI": "targetUri",
        "Action Type": "actionType",
        "Topic": "topic",
        "Timeout Seconds": "timeoutInSeconds",
    }

    for action in actions:
        action.pop("", None)

        # Map alternate CSV column names to JSON property names
        for csv_key, json_key in csv_to_json_map.items():
            if csv_key in action:
                action[json_key] = action.pop(csv_key)

        # Convert timeoutInSeconds to integer if present and non-empty
        timeout_value = action.get("timeoutInSeconds")
        if timeout_value and str(timeout_value).strip():
            try:
                action["timeoutInSeconds"] = int(timeout_value)
            except ValueError:
                pass  # Let validation catch invalid values
        elif "timeoutInSeconds" in action:
            del action["timeoutInSeconds"]

        # Remove empty optional fields
        for field in ["topic", "actionType", "typeRef"]:
            if field in action and (action[field] is None or action[field] == ""):
                del action[field]


class NamespaceAssets(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
            **self._get_client_kwargs()
        )
        self.resource_mgmt_client = get_resource_client(
            **self._get_client_kwargs()
        )
        self.ops: "NamespaceAssetsOperations" = self.deviceregistry_mgmt_client.namespace_assets
        self.device_ops: "NamespaceDevicesOperations" = self.deviceregistry_mgmt_client.namespace_devices
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def create(  # noqa: C901
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
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
        device, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
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
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                resource=asset_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        namespace = get_namespace_for_instance(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )

        with console.status(f"Deleting asset {asset_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(
        self,
        asset_name: str,
        resource_group: str,
        namespace_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        check_cluster: bool = False
    ) -> dict:
        if not namespace_name:
            # assume resource group is instance resource group
            namespace = get_namespace_for_instance(
                cmd=self.cmd,
                instance_name=instance_name,
                instance_resource_group=resource_group
            )
            namespace_name = namespace["name"]
            resource_group = namespace["resource_group"]

        asset = self.ops.get(
            resource_group_name=resource_group, namespace_name=namespace_name, asset_name=asset_name
        )
        if check_cluster:
            check_cluster_connectivity(self.cmd, asset)

        return asset

    # note the usage of Azure Resource Graph over the list api
    def query_assets(
        self,
        asset_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        custom_query: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None,
        disabled: Optional[bool] = None,
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
    ) -> dict:
        """
        Queries the asset using Azure Resource Graph.
        """
        query = "Resources | where type =~ '{}'".format(NAMESPACE_ASSET_RESOURCE_TYPE)

        # for now, keep it simple
        # ideas for later on, add namespace (needs id parsing), device endpoint type (will need to add joins)
        def _build_query_body(
            **params: dict
        ) -> str:
            param_mapping = {
                "asset_name": "name",
                "device_name": "properties.deviceRef.deviceName",
                "device_endpoint_name": "properties.deviceRef.endpointName",
                "display_name": "properties.displayName",
                "documentation_uri": "properties.documentationUri",
                "external_asset_id": "properties.externalAssetId",
                "hardware_revision": "properties.hardwareRevision",
                "manufacturer": "properties.manufacturer",
                "manufacturer_uri": "properties.manufacturerUri",
                "model": "properties.model",
                "product_code": "properties.productCode",
                "serial_number": "properties.serialNumber",
                "software_revision": "properties.softwareRevision",
            }
            query_body = get_query(
                param_mapping=param_mapping,
                params=params
            )
            return (
                query_body + " | extend customLocation = tostring(extendedLocation.name) "
                "| extend provisioningState = properties.provisioningState "
                "| project id, customLocation, location, name, resourceGroup, provisioningState, "
                "tags, type, subscriptionId"
            )

        query += custom_query or _build_query_body(
            asset_name=asset_name,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name,
            disabled=disabled,
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

        query = get_instance_query(
            query=query,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            project_away_custom_location=False
        )
        logger.info(f"Querying assets with query: {query}")

        return self.query(query=query)

    def update(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
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
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        asset_properties = asset["properties"]

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
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )

    # DATASETS - only allowed for opcua and custom assets
    def add_dataset(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        dataset_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        # TODO: future pr, import datapoints from file
        **kwargs
    ):
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # get the datasets from the asset
        datasets = asset["properties"].get("datasets", [])
        # remove dataset if it exists
        unmatched_datasets = [ds for ds in datasets if ds["name"] != dataset_name]
        if len(unmatched_datasets) < len(datasets) and not replace:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing dataset."
            )

        # create the dataset
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        new_dataset = {
            "name": dataset_name,
            "datasetConfiguration": processed_configs.get("datasetsConfiguration"),
            "destinations": processed_configs.get("datasetsDestinations", []),
            "dataPoints": [],  # TODO: future pr, add datapoints
            "typeRef": type_ref
        }
        if data_source:
            new_dataset["dataSource"] = data_source

        # Validate the dataset configuration against connector metadata
        try:
            validator = ConnectorMetadataValidator.from_asset(
                self.cmd, asset, instance_name, instance_resource_group
            )
            validator.validate_dataset(new_dataset)
            logger.info(f"Dataset '{dataset_name}' configuration validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Dataset validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The dataset will be created but may fail at runtime if the configuration is invalid."
            )

        unmatched_datasets.append(new_dataset)

        update_payload = {
            "properties": {
                "datasets": unmatched_datasets
            }
        }
        with console.status(f"Adding dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            datasets = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]
            return next(dset for dset in datasets if dset["name"] == dataset_name)

    def list_datasets(self, asset_name: str, instance_name: str, instance_resource_group: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("datasets", [])

    def show_dataset(
        self, asset_name: str, instance_name: str, instance_resource_group: str, dataset_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, dataset_name, property_key="datasets")

    def update_dataset(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        dataset_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ):
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
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
            **kwargs
        )

        # update the dataset properties
        if "datasetsConfiguration" in processed_configs:
            dataset["datasetConfiguration"] = processed_configs["datasetsConfiguration"]
        if data_source:
            dataset["dataSource"] = data_source
        if type_ref:
            dataset["typeRef"] = type_ref
        if "datasetsDestinations" in processed_configs:
            dataset["destinations"] = processed_configs["datasetsDestinations"]

        # Validate the updated dataset configuration against connector metadata
        try:
            validator = ConnectorMetadataValidator.from_asset(
                self.cmd, asset, instance_name, instance_resource_group
            )
            validator.validate_dataset(dataset)
            logger.info(f"Updated dataset '{dataset_name}' configuration validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Dataset validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The dataset will be updated but may fail at runtime if the configuration is invalid."
            )

        update_payload = {
            "properties": {
                "datasets": datasets
            }
        }
        with console.status(f"Updating dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            datasets = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]
            return next(dset for dset in datasets if dset["name"] == dataset_name)

    def remove_dataset(
        self, asset_name: str, instance_name: str, instance_resource_group: str, dataset_name: str, **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

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
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]

    def export_datasets(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export all datasets from an asset to a file (JSON or YAML)."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        datasets = asset["properties"].get("datasets", [])

        file_path = dump_content_to_file(
            content=datasets,
            file_name=f"{asset_name}_datasets",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "dataset_count": len(datasets)}

    def import_datasets(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import datasets from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_datasets = asset["properties"].get("datasets", [])

        imported_datasets = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_datasets,
            point_key="name",
            replace=replace
        )

        # Validate imported datasets
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for dataset in imported_datasets:
                validator.validate_dataset(dataset)
            logger.info("Datasets validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Dataset validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The datasets will be imported but may fail at runtime if the configuration is invalid."
            )

        update_payload = {
            "properties": {
                "datasets": imported_datasets
            }
        }

        with console.status(f"Importing datasets for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]

    def add_dataset_datapoint(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        dataset_name: str,
        datapoint_name: str,
        data_source: str,
        # Custom
        custom_configuration: Optional[str] = None,
        # OPCUA specific
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        # note that for now, we will not expose typeref for dataset datapoints
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")

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
            custom_configuration=custom_configuration,
            type_ref=type_ref
        )

        # Validate the datapoint configuration against connector metadata
        try:
            validator = ConnectorMetadataValidator.from_asset(
                self.cmd, asset, instance_name, instance_resource_group
            )
            validator.validate_datapoint(datapoint)
            logger.info(f"Datapoint '{datapoint_name}' configuration validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Datapoint validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The datapoint will be created but may fail at runtime if the configuration is invalid."
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
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def list_dataset_datapoints(
        self, asset_name: str, instance_name: str, instance_resource_group: str, dataset_name: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def remove_dataset_datapoint(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        dataset_name: str,
        datapoint_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")
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
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def export_dataset_datapoints(
        self,
        asset_name: str,
        dataset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export datapoints from a dataset to a file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")
        datapoints = dataset.get("dataPoints", [])

        # Convert to CSV format if requested
        fieldnames = None
        if extension == FileType.csv.value:
            default_configuration = dataset.get("datasetConfiguration", "{}")
            if default_configuration == "{}":
                default_configuration = asset["properties"].get("defaultDatasetsConfiguration", "{}")
            fieldnames = _convert_sub_points_to_csv_namespace(
                sub_points=datapoints,
                sub_point_type="dataPoints",
                default_configuration=default_configuration,
                portal_friendly=True
            )

        file_path = dump_content_to_file(
            content=datapoints,
            file_name=f"{asset_name}_{dataset_name}_datapoints",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "datapoint_count": len(datapoints)}

    def import_dataset_datapoints(
        self,
        asset_name: str,
        dataset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import datapoints from file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        # Find the target dataset
        datasets = asset["properties"].get("datasets", [])
        dataset = None
        for dset in datasets:
            if dset["name"] == dataset_name:
                dataset = dset
                break

        if dataset is None:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' not found in asset '{asset_name}'. "
                f"Create the dataset first before importing datapoints."
            )

        # Merge or replace datapoints based on flag
        original_datapoints = dataset.get("dataPoints", [])
        imported_datapoints = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_datapoints,
            point_key="name",
            replace=replace,
            csv_converter=_convert_sub_points_from_csv_namespace
        )

        # Validate imported datapoints
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for datapoint in imported_datapoints:
                validator.validate_datapoint(datapoint)
            logger.info("Datapoints validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Datapoint validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The datapoints will be imported but may fail at runtime if the configuration is invalid."
            )

        dataset["dataPoints"] = imported_datapoints

        update_payload = {
            "properties": {
                "datasets": datasets
            }
        }

        with console.status(f"Importing datapoints for dataset {dataset_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def export_event_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export event-groups from an asset to a file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        event_groups = asset["properties"].get("eventGroups", [])

        file_path = dump_content_to_file(
            content=event_groups,
            file_name=f"{asset_name}_event_groups",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "event_group_count": len(event_groups)}

    def import_event_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import event-groups from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_event_groups = asset["properties"].get("eventGroups", [])
        imported_event_groups = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_event_groups,
            point_key="name",
            replace=replace
        )

        # Validate imported event-groups
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for event_group in imported_event_groups:
                validator.validate_event_group(event_group)
            logger.info("Event-groups validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Event-group validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The event-groups will be imported but may fail at runtime if the configuration is invalid."
            )

        update_payload = {
            "properties": {
                "eventGroups": imported_event_groups
            }
        }

        with console.status(f"Importing event-groups for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return asset["properties"].get("eventGroups", [])

    def export_event_group_events(
        self,
        asset_name: str,
        event_group_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export events from an event-group to a file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        event_group = _get_sub_property(asset, event_group_name, property_key="eventGroups")
        events = event_group.get("events", [])

        # Convert to CSV format if requested
        fieldnames = None
        if extension == FileType.csv.value:
            default_configuration = event_group.get("eventGroupConfiguration", "{}")
            if default_configuration == "{}":
                default_configuration = asset["properties"].get("defaultEventsConfiguration", "{}")
            fieldnames = _convert_sub_points_to_csv_namespace(
                sub_points=events,
                sub_point_type="events",
                default_configuration=default_configuration,
                portal_friendly=True
            )

        file_path = dump_content_to_file(
            content=events,
            file_name=f"{asset_name}_{event_group_name}_events",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "event_count": len(events)}

    def import_event_group_events(
        self,
        asset_name: str,
        event_group_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import events from file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        event_groups = asset["properties"].get("eventGroups", [])
        event_group = None
        for eg in event_groups:
            if eg["name"] == event_group_name:
                event_group = eg
                break

        if event_group is None:
            raise InvalidArgumentValueError(
                f"Event-group '{event_group_name}' not found in asset '{asset_name}'. "
                f"Create the event-group first before importing events."
            )

        original_events = event_group.get("events", [])

        # Get default destinations from event-group or asset configuration
        default_destinations = event_group.get("defaultDestinations")
        if not default_destinations:
            default_destinations = asset["properties"].get("defaultEventsDestinations", [])

        imported_events = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_events,
            point_key="name",
            replace=replace,
            csv_converter=_convert_sub_points_from_csv_namespace
        )

        # Validate imported events
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for event in imported_events:
                validator.validate_event(event)
            logger.info("Events validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Event validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The events will be imported but may fail at runtime if the configuration is invalid."
            )

        # Always auto-assign destinations if not present (required by API)
        for event in imported_events:
            if "destinations" not in event or not event["destinations"]:
                event["destinations"] = deepcopy(default_destinations)

        event_group["events"] = imported_events

        update_payload = {
            "properties": {
                "eventGroups": event_groups
            }
        }

        with console.status(f"Importing events for event-group {event_group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, event_group_name, property_key="eventGroups")["events"]

    # EVENT GROUPS - allowed for opcua, onvif, and custom assets
    def add_event_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        # TODO: future pr, add events
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        original_egs = asset["properties"].get("eventGroups", [])
        # remove event group if it exists
        new_egs = [event for event in original_egs if event["name"] != group_name]
        if len(new_egs) < len(original_egs) and not replace:
            raise InvalidArgumentValueError(
                f"Event group '{group_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing event group."
            )

        # create the event group
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        new_eg = {
            "name": group_name,
            "eventGroupConfiguration": processed_configs.get("eventsConfiguration"),
            "defaultDestinations": processed_configs.get("eventsDestinations", []),
            "events": [],
            "typeRef": type_ref
        }
        if data_source:
            new_eg["dataSource"] = data_source
        new_egs.append(new_eg)

        update_payload = {
            "properties": {
                "eventGroups": new_egs
            }
        }
        with console.status(f"Adding event group {group_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")

    def list_event_groups(self, asset_name: str, instance_name: str, instance_resource_group: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("eventGroups", [])

    def show_event_group(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, group_name, property_key="eventGroups")

    def remove_event_group(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str, **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        current_egs = asset["properties"].get("eventGroups", [])
        # note that delete should be ok with event not there
        remaining_egs = [event for event in current_egs if event["name"] != group_name]

        # if the event is not found, we should not update
        if len(remaining_egs) == len(current_egs):
            logger.info(f"Event group '{group_name}' not found in asset '{asset_name}'.")
            return current_egs

        update_payload = {
            "properties": {
                "eventGroups": remaining_egs
            }
        }
        with console.status(f"Removing event group {group_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            # TODO: should remove event return the list of events or just nothing?
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["eventGroups"]

    def update_event_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ):
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if event exists
        group = _get_sub_property(asset, group_name, property_key="eventGroups")

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_event_configuration=group.get("eventConfiguration"),
            **kwargs
        )

        # update the event properties
        if "eventsConfiguration" in processed_configs:
            group["eventGroupConfiguration"] = processed_configs["eventsConfiguration"]
        if "eventsDestinations" in processed_configs:
            group["defaultDestinations"] = processed_configs["eventsDestinations"]
        if data_source:
            group["dataSource"] = data_source
        if type_ref:
            group["typeRef"] = type_ref

        # get the events from the asset (note the event should be updated here already)
        groups = asset["properties"].get("eventGroups", [])
        update_payload = {
            "properties": {
                "eventGroups": groups
            }
        }
        with console.status(f"Updating event {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")

    # EVENT GROUP EVENTS - allowed for opcua, onvif, and custom assets
    def add_event_group_event(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        event_name: str,
        data_source: Optional[str] = None,
        # Custom
        custom_configuration: Optional[str] = None,
        # OPCUA specific
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        event_destinations: Optional[List[dict]] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )

        # check if event exists
        event_group = _get_sub_property(asset, group_name, property_key="eventGroups")

        # get the events
        og_events = event_group.get("events", [])
        remaining_events = [ev for ev in og_events if ev["name"] != event_name]
        if len(remaining_events) < len(og_events) and not replace:
            raise InvalidArgumentValueError(
                f"event '{event_name}' already exists in event group '{group_name}' of asset '{asset_name}'. "
                "Use --replace to overwrite the existing event."
            )

        # create the event
        event = _create_event(
            event_name=event_name,
            data_source=data_source,
            type_ref=type_ref,
            custom_configuration=custom_configuration,
            event_destinations=event_destinations,
            queue_size=queue_size,
            sampling_interval=sampling_interval
        )
        remaining_events.append(event)
        event_group["events"] = remaining_events

        # get the events from the asset
        event_groups = asset["properties"].get("eventGroups", [])
        update_payload = {
            "properties": {
                "eventGroups": event_groups
            }
        }
        with console.status(f"Adding event {event_name} to event group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            # note that we return a list of events
            return _get_sub_property(asset, group_name, property_key="eventGroups")["events"]

    def list_event_group_events(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str
    ):
        event = self.show_event_group(
            asset_name=asset_name,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            group_name=group_name
        )
        return event.get("events", [])

    def remove_event_group_event(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        event_name: str,
        **kwargs
    ):
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        # since we do not check device props (not adding events), we parse namespace this way
        namespace = parse_resource_id(asset["id"])
        event_group = _get_sub_property(asset, group_name, property_key="eventGroups")
        og_events = event_group.get("events", [])
        # note that delete should be ok with event not there
        event_group["events"] = [ev for ev in og_events if ev["name"] != event_name]

        # no need for update if the event is not found
        if len(event_group["events"]) == len(og_events):
            logger.info(
                f"Event '{event_name}' not found in event group '{group_name}' of asset '{asset_name}'."
            )
            return event_group["events"]

        event_groups = asset["properties"].get("eventGroups", [])
        update_payload = {
            "properties": {
                "eventGroups": event_groups
            }
        }
        with console.status(
            f"Removing event {event_name} from event group {group_name} in asset {asset_name}..."
        ):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            # note that we return a list of events
            return _get_sub_property(asset, group_name, property_key="eventGroups")["events"]

    # STREAMS - allowed for media and custom assets
    def add_stream(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        stream_name: str,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        # ignoring typeref
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        streams = asset["properties"].get("streams", [])
        # remove stream if it exists
        unmatched_streams = [stream for stream in streams if stream["name"] != stream_name]
        if len(unmatched_streams) < len(streams) and not replace:
            raise InvalidArgumentValueError(
                f"Stream '{stream_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing stream."
            )

        # create the stream
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        unmatched_streams.append(
            {
                "name": stream_name,
                "streamConfiguration": processed_configs.get("streamsConfiguration"),
                "destinations": processed_configs.get("streamsDestinations", []),
                "typeRef": type_ref
            }
        )

        update_payload = {
            "properties": {
                "streams": unmatched_streams
            }
        }
        with console.status(f"Adding stream {stream_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            streams = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["streams"]
            return next(stream for stream in streams if stream["name"] == stream_name)

    def list_streams(self, asset_name: str, instance_name: str, instance_resource_group: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("streams", [])

    def show_stream(
        self, asset_name: str, instance_name: str, instance_resource_group: str, stream_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        streams = asset["properties"].get("streams", [])
        stream = next((s for s in streams if s["name"] == stream_name), None)
        if not stream:
            raise InvalidArgumentValueError(f"Stream '{stream_name}' not found in asset '{asset_name}'.")
        return stream

    def remove_stream(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        stream_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        streams = asset["properties"].get("streams", [])
        # note that delete should be ok with stream not there
        remaining_streams = [stream for stream in streams if stream["name"] != stream_name]

        if len(remaining_streams) == len(streams):
            logger.info(f"Stream '{stream_name}' not found in asset '{asset_name}'.")
            return streams

        update_payload = {
            "properties": {
                "streams": remaining_streams
            }
        }
        with console.status(f"Removing stream {stream_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["streams"]

    def update_stream(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        stream_name: str,
        type_ref: Optional[str] = None,
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if stream exists
        streams = asset["properties"].get("streams", [])
        stream = next((s for s in streams if s["name"] == stream_name), None)
        if not stream:
            raise InvalidArgumentValueError(f"Stream '{stream_name}' not found in asset '{asset_name}'.")

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_stream_configuration=stream.get("streamConfiguration"),
            **kwargs
        )

        # update the stream properties
        if "streamsConfiguration" in processed_configs:
            stream["streamConfiguration"] = processed_configs["streamsConfiguration"]
        if "streamsDestinations" in processed_configs:
            stream["destinations"] = processed_configs["streamsDestinations"]
        if type_ref:
            stream["typeRef"] = type_ref

        update_payload = {
            "properties": {
                "streams": streams
            }
        }
        with console.status(f"Updating stream {stream_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            streams = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["streams"]
            return next(stream for stream in streams if stream["name"] == stream_name)

    def export_streams(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export streams from an asset to a file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        streams = asset["properties"].get("streams", [])

        # Strip properties that should not be exported (per DOE design)
        export_streams = []
        for stream in streams:
            export_stream = {"name": stream.get("name")}
            # Include streamConfiguration if present (but not destinations - auto-assigned on import)
            if stream.get("streamConfiguration"):
                export_stream["streamConfiguration"] = stream["streamConfiguration"]
            if stream.get("typeRef"):
                export_stream["typeRef"] = stream["typeRef"]
            export_streams.append(export_stream)

        file_path = dump_content_to_file(
            content=export_streams,
            file_name=f"{asset_name}_streams",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "stream_count": len(export_streams)}

    def import_streams(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import streams from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_streams = asset["properties"].get("streams", [])

        # Get default destinations from asset configuration (if configured)
        default_destinations = asset["properties"].get("defaultStreamsDestinations") or []

        imported_streams = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_streams,
            point_key="name",
            replace=replace
        )

        # Validate imported streams
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for stream in imported_streams:
                validator.validate_stream(stream)
            logger.info("Streams validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Stream validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The streams will be imported but may fail at runtime if the configuration is invalid."
            )

        # Always auto-assign destinations if not present (required by API)
        for stream in imported_streams:
            if default_destinations and ("destinations" not in stream or not stream["destinations"]):
                stream["destinations"] = deepcopy(default_destinations)

        update_payload = {
            "properties": {
                "streams": imported_streams
            }
        }

        with console.status(f"Importing streams for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return asset["properties"].get("streams", [])

    # Management Groups - allowed for opcua, onvif, and custom assets
    def add_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        default_topic: Optional[str] = None,
        default_timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
        # TODO: add in mgmt configurations
    ) -> dict:
        # ignoring typeref
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        og_mgmt_groups = asset["properties"].get("managementGroups", [])
        # remove management group if it exists
        remaining_mgmt_groups = [mgmt for mgmt in og_mgmt_groups if mgmt["name"] != group_name]
        if len(remaining_mgmt_groups) < len(og_mgmt_groups) and not replace:
            raise InvalidArgumentValueError(
                f"Management group '{group_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing management group."
            )

        # create the management group
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        new_mgmt_group = {
            "name": group_name,
            "defaultTopic": default_topic,
            "defaultTimeoutInSeconds": default_timeout,
            "managementGroupConfiguration": processed_configs.get("managementGroupsConfiguration"),
            "typeRef": type_ref,
            "actions": []  # TODO: future, add actions in add_management_group
        }
        if data_source:
            new_mgmt_group["dataSource"] = data_source
        remaining_mgmt_groups.append(new_mgmt_group)
        update_payload = {
            "properties": {
                "managementGroups": remaining_mgmt_groups
            }
        }
        with console.status(f"Adding management group {group_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            return next(mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name)

    def list_management_groups(
        self, asset_name: str, instance_name: str, instance_resource_group: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("managementGroups", [])

    def show_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, group_name, property_key="managementGroups")

    def remove_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        mgmt_groups = asset["properties"].get("managementGroups", [])
        # note that delete should be ok with management group not there
        remaining_mgmt_groups = [mgmt for mgmt in mgmt_groups if mgmt["name"] != group_name]

        if len(remaining_mgmt_groups) == len(mgmt_groups):
            logger.info(f"Management group '{group_name}' not found in asset '{asset_name}'.")
            return mgmt_groups

        update_payload = {
            "properties": {
                "managementGroups": remaining_mgmt_groups
            }
        }
        with console.status(f"Removing management group {group_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]

    def update_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        default_topic: Optional[str] = None,
        default_timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if management group exists
        mgmt_groups = asset["properties"].get("managementGroups", [])
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_management_group_configuration=mgmt_group.get("managementGroupConfiguration"),
            **kwargs
        )

        # update the management group properties
        if "managementGroupsConfiguration" in processed_configs:
            mgmt_group["managementGroupConfiguration"] = processed_configs["managementGroupsConfiguration"]
        if default_topic == "":
            mgmt_group.pop("defaultTopic", None)
        elif default_topic:
            mgmt_group["defaultTopic"] = default_topic
        if default_timeout is not None:
            mgmt_group["defaultTimeoutInSeconds"] = default_timeout
        if data_source:
            mgmt_group["dataSource"] = data_source
        if type_ref:
            mgmt_group["typeRef"] = type_ref

        update_payload = {
            "properties": {
                "managementGroups": mgmt_groups
            }
        }
        with console.status(f"Updating management group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            return next(mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name)

    # MANAGEMENT GROUP ACTIONS
    def add_management_group_action(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        action_name: str,
        target_uri: str,
        topic: Optional[str] = None,
        action_type: Optional[str] = None,
        timeout: Optional[int] = None,
        custom_configuration: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        # also ignore typeref here
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")

        actions = mgmt_group.get("actions", [])
        unmatched_actions = [action for action in actions if action["name"] != action_name]
        if len(unmatched_actions) < len(actions) and not replace:
            raise InvalidArgumentValueError(
                f"Action '{action_name}' already exists in management group '{group_name}' "
                f"of asset '{asset_name}'. Use --replace to overwrite the existing action."
            )

        # create the action
        action = {
            "name": action_name,
            "targetUri": target_uri,
            "topic": topic,
            "actionType": action_type,
            "timeoutInSeconds": timeout,
            "typeRef": type_ref
        }
        if custom_configuration:
            action["actionConfiguration"] = process_additional_configuration(
                custom_configuration, config_type="action"

            )
        unmatched_actions.append(action)
        mgmt_group["actions"] = unmatched_actions

        update_payload = {
            "properties": {
                "managementGroups": asset["properties"]["managementGroups"]
            }
        }
        with console.status(f"Adding action {action_name} to management group {group_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            return next(mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name)["actions"]

    def list_management_group_actions(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")
        return mgmt_group.get("actions", [])

    def remove_management_group_action(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        action_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")

        actions = mgmt_group.get("actions", [])
        # note that delete should be ok with action not there
        remaining_actions = [action for action in actions if action["name"] != action_name]

        if len(remaining_actions) == len(actions):
            logger.info(
                f"Action '{action_name}' not found in management group '{group_name}' "
                f"of asset '{asset_name}'."
            )
            return actions

        mgmt_group["actions"] = remaining_actions

        update_payload = {
            "properties": {
                "managementGroups": asset["properties"]["managementGroups"]
            }
        }
        with console.status(f"Removing action {action_name} from management group {group_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            return next(mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name)["actions"]

    def export_management_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export management groups from an asset to a file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        mgmt_groups = asset["properties"].get("managementGroups", [])

        # Strip properties that should not be exported (per DOE design)
        export_mgmt_groups = []
        for mgmt_group in mgmt_groups:
            export_group = {
                "name": mgmt_group.get("name"),
            }
            # Include optional fields if present
            if mgmt_group.get("dataSource"):
                export_group["dataSource"] = mgmt_group["dataSource"]
            if mgmt_group.get("defaultTopic"):
                export_group["defaultTopic"] = mgmt_group["defaultTopic"]
            if mgmt_group.get("defaultTimeoutInSeconds") is not None:
                export_group["defaultTimeoutInSeconds"] = mgmt_group["defaultTimeoutInSeconds"]
            if mgmt_group.get("typeRef"):
                export_group["typeRef"] = mgmt_group["typeRef"]
            # Note: 'actions' array is NOT exported (exported separately)
            # Note: 'key' and 'managementGroupConfiguration' are stripped
            export_mgmt_groups.append(export_group)

        file_path = dump_content_to_file(
            content=export_mgmt_groups,
            file_name=f"{asset_name}_management_groups",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "management_group_count": len(export_mgmt_groups)}

    def import_management_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import management groups from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_mgmt_groups = asset["properties"].get("managementGroups", [])

        imported_mgmt_groups = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_mgmt_groups,
            point_key="name",
            replace=replace
        )

        # Validate imported management groups
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for mgmt_group in imported_mgmt_groups:
                validator.validate_management_group(mgmt_group)
            logger.info("Management groups validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Management group validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The management groups will be imported but may fail at runtime if the configuration is invalid."
            )

        # Always preserve existing actions if merging
        for mgmt_group in imported_mgmt_groups:
            if "actions" not in mgmt_group:
                name = mgmt_group.get("name", "")
                original = next((g for g in original_mgmt_groups if g["name"] == name), None)
                mgmt_group["actions"] = original.get("actions", []) if original else []

        update_payload = {
            "properties": {
                "managementGroups": imported_mgmt_groups
            }
        }

        with console.status(f"Importing management groups for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return asset["properties"].get("managementGroups", [])

    def export_management_group_actions(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export actions from a management group to a file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")
        actions = mgmt_group.get("actions", [])

        # Strip properties that should not be exported (per DOE design)
        export_actions = []
        for action in actions:
            export_action = {
                "name": action.get("name"),
                "targetUri": action.get("targetUri"),
            }
            # Include optional fields if present
            if action.get("actionType"):
                export_action["actionType"] = action["actionType"]
            if action.get("topic"):
                export_action["topic"] = action["topic"]
            if action.get("timeoutInSeconds") is not None:
                export_action["timeoutInSeconds"] = action["timeoutInSeconds"]
            if action.get("typeRef"):
                export_action["typeRef"] = action["typeRef"]
            # Note: 'key' and 'managementGroup' are stripped
            export_actions.append(export_action)

        # Convert to CSV format if requested
        fieldnames = None
        if extension == FileType.csv.value:
            fieldnames = _convert_actions_to_csv(export_actions)

        file_path = dump_content_to_file(
            content=export_actions,
            file_name=f"{asset_name}_{group_name}_actions",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "action_count": len(export_actions)}

    def import_management_group_actions(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import actions from file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        # Check that management group exists
        mgmt_groups = asset["properties"].get("managementGroups", [])
        if not mgmt_groups:
            raise InvalidArgumentValueError(
                f"No management groups found in asset '{asset_name}'. "
                "Create a management group first before importing actions."
            )

        mgmt_group = None
        for mg in mgmt_groups:
            if mg["name"] == group_name:
                mgmt_group = mg
                break

        if mgmt_group is None:
            raise InvalidArgumentValueError(
                f"Management group '{group_name}' not found in asset '{asset_name}'. "
                f"Create the management group first before importing actions."
            )

        original_actions = mgmt_group.get("actions", [])
        imported_actions = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_actions,
            point_key="name",
            replace=replace,
            csv_converter=_convert_actions_from_csv
        )

        # Validate imported actions
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

            for action in imported_actions:
                validator.validate_action(action)
            logger.info("Actions validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"Action validation skipped: {e}. "
                "This may occur if the connector is not deployed or the cluster is not connected. "
                "The actions will be imported but may fail at runtime if the configuration is invalid."
            )

        # Always default actionType to 'Call' if not specified
        for action in imported_actions:
            if not action.get("actionType"):
                action["actionType"] = "Call"

        mgmt_group["actions"] = imported_actions

        update_payload = {
            "properties": {
                "managementGroups": mgmt_groups
            }
        }

        with console.status(f"Importing actions for management group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="managementGroups")["actions"]

    def _check_device_props(
        self,
        instance_resource_group: str,
        instance_name: str,
        asset_type: Union[List[str], str],  # change to list
        asset_name: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None
    ) -> Tuple[dict, Dict[str, str]]:
        """
        Checks the device properties to ensure the endpoint type matches the asset operation's type.
        Returns the asset if the asset name is provided, otherwise the device
        (device name and device endpoint name must be provided).

        This also includes the cluster connectivity check.

        If asset_name is provided (in the case of the asset is already created), it will retrieve the
        asset to populate the device_name and device_endpoint_name.
        """
        asset = None
        namespace = None
        if asset_name:
            # get the asset to populate the device name and endpoint name
            asset = self.show(
                resource_group=instance_resource_group,
                instance_name=instance_name,
                asset_name=asset_name
            )
            device_name = asset["properties"]["deviceRef"]["deviceName"]
            device_endpoint_name = asset["properties"]["deviceRef"]["endpointName"]
            namespace = parse_resource_id(asset["id"])
        else:
            namespace = get_namespace_for_instance(
                cmd=self.cmd,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

        device = self.device_ops.get(
            resource_group_name=namespace["resource_group"],
            namespace_name=namespace["name"],
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

        return (asset if asset_name else device, namespace)


def _build_destination(
    destination_args: List[List[str]],
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
            "retain": "Never",
            "qos": "Qos0",
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
        from .common import DestinationQos, TopicRetain
        qos = destination_args.pop("qos")
        if qos not in DestinationQos.list():
            raise InvalidArgumentValueError(
                f"Invalid QoS value '{qos}'. Allowed values are: {', '.join(DestinationQos.list())}."
            )
        retain = destination_args.pop("retain")
        if retain not in TopicRetain.list():
            raise InvalidArgumentValueError(
                f"Invalid retain value '{retain}'. Allowed values are: {', '.join(TopicRetain.list())}."
            )

        destination = {
            "target": "Mqtt",
            "configuration": {
                "topic": destination_args.pop("topic"),
                "retain": retain,
                "qos": qos,
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


def _create_event(
    event_name: str,
    data_source: Optional[str] = None,
    type_ref: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    custom_configuration: Optional[str] = None,
    event_destinations: Optional[List[List[str]]] = None
) -> dict:
    """Helper function to create an event dictionary."""
    event = {
        "name": event_name,
    }
    if data_source:
        event["dataSource"] = data_source
    if type_ref:
        event["typeRef"] = type_ref
    if event_destinations:
        event["destinations"] = _build_destination(destination_args=event_destinations)

    # if custom configuration is provided, process it and return early
    if custom_configuration:
        event["eventConfiguration"] = process_additional_configuration(
            additional_configuration=custom_configuration,
            config_type="event"
        )
        return event
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

    event["eventConfiguration"] = json.dumps(additional_configuration)
    # TODO: other event specific configurations can be added here
    return event


def _get_sub_property(asset: dict, name: str, property_key: str) -> dict:
    """Helper function to get a dataset, event groups, or management groups from an asset.

    Raises InvalidArgumentValueError if the subproperty is not found.
    """
    # TODO: could have partial functions (_get_event_group) for ease
    props = asset["properties"].get(property_key, [])
    matched_props = [event for event in props if event["name"] == name]
    # TODO: would we want to prompt user to create if not found?
    if not matched_props:
        property_name = property_key.capitalize()[:-1]
        # deal with managment groups + event groups
        if property_name.endswith("group"):
            property_name = property_name[:-5] + " group"
        raise InvalidArgumentValueError(f"{property_name} '{name}' not found in asset '{asset['name']}'.")
    return matched_props[0]


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
        # allowed: datasets, events, mgmt groups (no schema?), destinations must be mqtt
        # not allowed: streams
        result = {
            "datasetsConfiguration": _process_opcua_dataset_configurations_v2(
                **kwargs
            ),
            "eventsConfiguration": _process_opcua_event_configurations_v2(
                **kwargs
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
        # allowed: events (no schema), mgmt groups (no schema), destinations must be mqtt
        # not allowed: datasets, streams
        result = {
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
    elif asset_type == DeviceEndpointType.REST.value.lower():
        # allowed only datasets
        result = {
            "datasetsConfiguration": _process_rest_dataset_configurations(
                **kwargs
            ),
            "datasetsDestinations": _build_destination(
                destination_args=kwargs.get("dataset_destinations", []),
                allowed_types=["BrokerStateStore", "Mqtt"]
            )
        }
    else:
        # Custom - treat everything as an overwrite
        result = {
            "datasetsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("dataset_custom_configuration"),
                config_type="dataset"
            ),
            "eventsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("event_custom_configuration"),
                config_type="event"
            ),
            "managementGroupsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("mgmt_custom_configuration"),
                config_type="management group"
            ),
            "streamsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("stream_custom_configuration"),
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


def _process_opcua_dataset_configurations_v1(
    original_dataset_configuration: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V1

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
        schema=NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V1,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_dataset_configurations_v2(
    original_dataset_configuration: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V2
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
        schema=NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V2,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_event_configurations_v1(
    original_event_configuration: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V1

    result = json.loads(original_event_configuration) if original_event_configuration else {}
    if opcua_event_publishing_interval is not None:
        result["publishingInterval"] = opcua_event_publishing_interval
    if opcua_event_queue_size is not None:
        result["queueSize"] = opcua_event_queue_size
    if opcua_event_start_instance is not None:
        result["startInstance"] = opcua_event_start_instance

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V1,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_event_configurations_v2(
    original_event_configuration: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_start_instance: Optional[str] = None,
    opcua_event_filter_type: Optional[str] = None,
    opcua_event_filter_clauses: Optional[List[List[str]]] = None,  # path (req), type, field
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V2

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
        schema=NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V2,
        input_data=result
    )
    return json.dumps(result)


def _process_media_stream_configurations(
    original_stream_configuration: Optional[str] = None,
    task_type: Optional[str] = None,
    disable_autostart: Optional[bool] = None,
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
    from .specs import (
        NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
        MediaFormat,
        MediaTaskType,
    )
    result = json.loads(original_stream_configuration) if original_stream_configuration else {}

    task_type = task_type or result.get("taskType")
    if not task_type:
        if not any([
            task_format, disable_autostart, snapshots_per_second, path, duration,
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
        "autostart": disable_autostart,
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
        if property_name == "autostart":
            param_value = not param_value  # Convert to 'enabled' property

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


def _process_rest_dataset_configurations(
    original_dataset_configuration: Optional[str] = None,
    rest_dataset_sampling_interval: Optional[int] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_REST_DATASET_CONFIGURATION_SCHEMA

    result = json.loads(original_dataset_configuration) if original_dataset_configuration else {}
    if rest_dataset_sampling_interval is not None:
        result["samplingIntervalInMilliseconds"] = rest_dataset_sampling_interval

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_REST_DATASET_CONFIGURATION_SCHEMA,
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


def _process_namespace_sub_points_file_path(
    file_path: str,
    original_items: Optional[List[dict]] = None,
    point_key: Optional[str] = None,
    replace: bool = False,
    csv_converter=None
) -> List[Dict[str, str]]:
    """Merge items from file with existing items."""
    from ...util import deserialize_file_content

    file_points = list(deserialize_file_content(file_path=file_path))

    if file_path.endswith('.csv'):
        if csv_converter:
            csv_converter(file_points)
        else:
            raise InvalidArgumentValueError("CSV conversion not supported for this operation.")

    if point_key is None:
        return file_points

    if not original_items:
        original_items = []

    original_points = {point[point_key]: point for point in original_items}
    file_points_dict = {point[point_key]: point for point in file_points}

    skipped_keys = []
    for key in file_points_dict:
        if key in original_points and not replace:
            skipped_keys.append(key)
        else:
            original_points[key] = file_points_dict[key]

    if skipped_keys:
        logger.warning(
            f"The following entries are already present in the asset and will be ignored: "
            f"{', '.join(str(k) for k in skipped_keys)}"
        )

    return list(original_points.values())
