# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import TYPE_CHECKING, Dict, List, Iterable, Optional, Union
from knack.log import get_logger
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)
# from azure.core.exceptions import ResourceNotFoundError

from .user_strings import INVALID_OBSERVABILITY_MODE_ERROR
from ....util import assemble_nargs_to_dict
from ....common import FileType
# TODO: push these into util init
from ....util.az_client import get_registry_mgmt_client
from ....util.queryable import Queryable

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt.operations import (
        AssetsOperations,
        DiscoveredAssetsOperations
    )


logger = get_logger(__name__)
ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/assets"
DISCOVERED_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/discoveredAssets"
VALID_DATA_OBSERVABILITY_MODES = ["None", "Gauge", "Counter", "Histogram", "Log"]
VALID_EVENT_OBSERVABILITY_MODES = ["None", "Log"]


class Assets(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id
        )
        self.ops: "AssetsOperations" = self.deviceregistry_mgmt_client.assets
        self.discovered_ops: "DiscoveredAssetsOperations" = self.deviceregistry_mgmt_client.discovered_assets
        self.update_ops: Optional[Union["AssetsOperations", "DiscoveredAssetsOperations"]] = None

    def create(
        self,
        asset_name: str,
        endpoint_profile: str,
        instance_name: str,
        resource_group_name: str,
        custom_location_id: Optional[str] = None,  # TODO: remove
        custom_attributes: Optional[List[str]] = None,
        # dataset_file_path: Optional[str] = None,
        default_topic_path: Optional[str] = None,
        default_topic_retain: Optional[str] = None,
        description: Optional[str] = None,
        disabled: bool = False,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        events: Optional[List[str]] = None,
        events_file_path: Optional[List[str]] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        instance_subscription: Optional[str] = None,
        location: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        ds_publishing_interval: int = 1000,
        ds_sampling_interval: int = 500,
        ds_queue_size: int = 1,
        ev_publishing_interval: int = 1000,
        ev_sampling_interval: int = 500,
        ev_queue_size: int = 1,
        tags: Optional[Dict[str, str]] = None,
        discovered: bool = False  # for quick discovered debugging
    ):
        from .helpers import get_extended_location
        extended_location = get_extended_location(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group or resource_group_name,
            instance_subscription=instance_subscription
        )
        cluster_location = extended_location.pop("cluster_location")

        # Properties
        properties = {
            "assetEndpointProfileRef": endpoint_profile,
            "events": _process_asset_sub_points("event_notifier", events),
        }
        # TODO: replace with datapoint file?
        # if dataset_file_path:
        #     properties["datasets"].extend(
        #         _process_asset_data_set_file_path(file_path=dataset_file_path)
        #     )
        if events_file_path:
            properties["events"].extend(
                _process_asset_sub_points_file_path(file_path=events_file_path)
            )

        # Other properties
        _update_properties(
            properties,
            custom_attributes=custom_attributes,
            default_topic_path=default_topic_path,
            default_topic_retain=default_topic_retain,
            description=description,
            display_name=display_name,
            disabled=disabled,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
            ds_publishing_interval=ds_publishing_interval,
            ds_sampling_interval=ds_sampling_interval,
            ds_queue_size=ds_queue_size,
            ev_publishing_interval=ev_publishing_interval,
            ev_sampling_interval=ev_sampling_interval,
            ev_queue_size=ev_queue_size,
        )
        # discovered
        if discovered:
            self.ops = self.discovered_ops
            properties.pop("enabled", None)
            properties["version"] = 1
            properties["discoveryId"] = "discoveryid1"

        asset_body = {
            "extendedLocation": extended_location,
            "location": location or cluster_location,
            "properties": properties,
            "tags": tags,
        }
        return self.ops.begin_create_or_replace(
            resource_group_name,
            asset_name,
            resource=asset_body
        )

    def delete(self, asset_name: str, resource_group_name: str):
        self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        return self.update_ops.begin_delete(
            resource_group_name,
            asset_name,
        )

    def show(
        self, asset_name: str, resource_group_name: str, check_cluster: bool = False
    ) -> dict:
        # TODO: re-add try except when discovered is exposed
        # try:
        asset = self.ops.get(
            resource_group_name=resource_group_name, asset_name=asset_name
        )
        self.update_ops = self.ops
        # except ResourceNotFoundError:
        #     try:
        #         asset = self.discovered_ops.get(
        #             resource_group_name=resource_group_name, discovered_asset_name=asset_name
        #         )
        #         self.update_ops = self.discovered_ops
        #     except ResourceNotFoundError:
        #         # raise combined exception
        #         raise ResourceNotFoundError(
        #             f"Niether 'Microsoft.DeviceRegistry/assets/{asset_name}' nor "
        #             f"'Microsoft.DeviceRegistry/discoveredAssets/{asset_name}' under resource group "
        #             f"'{resource_group_name}' was not found. For more details please go to "
        #             "https://aka.ms/ARMResourceNotFoundFix"
        #         )
        if check_cluster:
            from .helpers import check_cluster_connectivity
            check_cluster_connectivity(self.cmd, asset)
        return asset

    def list(self, resource_group_name: Optional[str] = None, discovered: bool = False) -> Iterable[dict]:
        if discovered:
            if resource_group_name:
                return self.discovered_ops.list_by_resource_group(resource_group_name=resource_group_name)
            return self.discovered_ops.list_by_subscription()

        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()

    def query_assets(
        self,
        asset_name: Optional[str] = None,
        custom_query: Optional[str] = None,
        default_topic_path: Optional[str] = None,
        default_topic_retain: Optional[str] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        discovered: Optional[bool] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        endpoint_profile: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        location: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        resource_group_name: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
    ):
        query_body = custom_query or _build_query_body(
            asset_name=asset_name,
            default_topic_path=default_topic_path,
            default_topic_retain=default_topic_retain,
            description=description,
            disabled=disabled,
            display_name=display_name,
            documentation_uri=documentation_uri,
            endpoint_profile=endpoint_profile,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            location=location,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            resource_group_name=resource_group_name,
            serial_number=serial_number,
            software_revision=software_revision
        )

        if discovered is not None:
            resource_type = DISCOVERED_ASSET_RESOURCE_TYPE if discovered else ASSET_RESOURCE_TYPE
            query = f"Resources | where type =~\"{resource_type}\" " + query_body
        else:
            # we put the query body into the each type query and then union to avoid the union result from
            # becoming too big
            query = f"Resources | where type =~ \"{ASSET_RESOURCE_TYPE}\" {query_body} "\
                f"| union (Resources | where type =~ \"{DISCOVERED_ASSET_RESOURCE_TYPE}\" {query_body})"

        if any([instance_name, instance_resource_group]):
            instance_query = "Resources | where type =~ 'microsoft.iotoperations/instances' "
            if instance_name:
                instance_query += f"| where name =~ \"{instance_name}\""
            if instance_resource_group:
                instance_query += f"| where resourceGroup =~ \"{instance_resource_group}\""

            # fetch the custom location + join on innerunique. Then remove the extra customLocation1 generated
            query = f"{instance_query} | extend customLocation = tostring(extendedLocation.name) "\
                f"| project customLocation | join kind=innerunique ({query}) on customLocation "\
                "| project-away customLocation1"
        return self.query(query=query)

    def update(
        self,
        asset_name: str,
        resource_group_name: str,
        custom_attributes: Optional[List[str]] = None,
        default_topic_path: Optional[str] = None,
        default_topic_retain: Optional[str] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        ds_publishing_interval: Optional[int] = None,
        ds_sampling_interval: Optional[int] = None,
        ds_queue_size: Optional[int] = None,
        ev_publishing_interval: Optional[int] = None,
        ev_sampling_interval: Optional[int] = None,
        ev_queue_size: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        # get the asset
        original_asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        if tags:
            original_asset["tags"] = tags

        # Other properties
        _update_properties(
            original_asset["properties"],
            custom_attributes=custom_attributes,
            default_topic_path=default_topic_path,
            default_topic_retain=default_topic_retain,
            description=description,
            disabled=disabled,
            documentation_uri=documentation_uri,
            display_name=display_name,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
            ds_publishing_interval=ds_publishing_interval,
            ds_sampling_interval=ds_sampling_interval,
            ds_queue_size=ds_queue_size,
            ev_publishing_interval=ev_publishing_interval,
            ev_sampling_interval=ev_sampling_interval,
            ev_queue_size=ev_queue_size,
        )

        # use this over update since we want to make sure we get the tags in
        poller = self.update_ops.begin_create_or_replace(
            resource_group_name,
            asset_name,
            original_asset
        )
        return poller

    # TODO: add when multi dataset support is added
    # def add_dataset(
    #     self,
    #     asset_name: str,
    #     dataset_name: str,
    #     resource_group_name: str,
    #     data_points: Optional[List[str]] = None,  # allow for datapoint addition during dataset creation
    #     data_point_file_path: Optional[str] = None,
    #     queue_size: Optional[int] = None,
    #     sampling_interval: Optional[int] = None,
    #     publishing_interval: Optional[int] = None,  # note that the swagger mentions this but not sure if used
    #     topic_path: Optional[str] = None,
    #     topic_retain: Optional[str] = None
    # ):
    #     asset = self.show(
    #         asset_name=asset_name,
    #         resource_group_name=resource_group_name,
    #         check_cluster=True
    #     )
    #     asset["properties"]["datasets"] = asset["properties"].get("datasets", [])

    #     dataset = {
    #         "name": dataset_name,
    #         "dataPoints": [],
    #         "datasetConfiguration": _build_default_configuration(
    #             original_configuration="{}",
    #             publishing_interval=publishing_interval,
    #             sampling_interval=sampling_interval,
    #             queue_size=queue_size
    #         )
    #     }
    #     if topic_path or topic_retain:
    #         dataset["topic"] = _build_topic(topic_path=topic_path, topic_retain=topic_retain)
    #     if data_points:
    #         dataset["dataPoints"].extend(_process_asset_sub_points("event_notifier", data_points))
    #     if data_point_file_path:
    #         dataset["dataPoints"].extend(_process_asset_sub_points_file_path(file_path=data_point_file_path))

    #     poller = self.ops.begin_update(
    #         resource_group_name=resource_group_name,
    #         asset_name=asset_name,
    #         properties=asset["properties"]
    #     )
    #     poller.wait()
    #     asset = poller.result()
    #     return _get_dataset(asset, dataset_name)

    # def export_datasets(
    #     self,
    #     asset_name: str,
    #     resource_group_name: str,
    #     extension: str = FileType.json.value,
    #     output_dir: str = ".",
    #     replace: bool = False
    # ):
    #     raise NotImplementedError()

    # def import_datasets(
    #     self,
    #     asset_name: str,
    #     file_path: str,
    #     resource_group_name: str,
    #     replace: bool = False
    # ):
    #     raise NotImplementedError()

    def list_datasets(
        self,
        asset_name: str,
        resource_group_name: str,
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        return asset["properties"].get("datasets", [])

    # TODO: add when multi dataset support is added
    # def remove_dataset(
    #     self,
    #     asset_name: str,
    #     dataset_name: str,
    #     resource_group_name: str,
    # ):
    #     asset = self.show(
    #         asset_name=asset_name,
    #         resource_group_name=resource_group_name,
    #         check_cluster=True
    #     )
    #     asset["properties"]["datasets"] = [
    #         ds for ds in asset["properties"]["datasets"] if ds["name"] != dataset_name
    #     ]
    #     poller = self.update_ops.begin_update(
    #         resource_group_name,
    #         asset_name,
    #         asset["properties"]
    #     )
    #     poller.wait()
    #     asset = poller.result()
    #     if not isinstance(asset, dict):
    #         asset = asset.as_dict()

    #     return asset["properties"]["datasets"]

    def show_dataset(
        self,
        asset_name: str,
        dataset_name: str,
        resource_group_name: str,
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name
        )
        return _get_dataset(asset, dataset_name)

    # Data points
    def add_dataset_data_point(
        self,
        asset_name: str,
        dataset_name: str,
        data_point_name: str,
        data_source: str,
        resource_group_name: str,
        observability_mode: Optional[str] = None,
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        publishing_interval: Optional[int] = None,
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        dataset = _get_dataset(asset, dataset_name)
        if not dataset.get("dataPoints"):
            dataset["dataPoints"] = []

        sub_point = _build_asset_sub_point(
            data_source=data_source,
            name=data_point_name,
            observability_mode=observability_mode,
            queue_size=queue_size,
            sampling_interval=sampling_interval,
            publishing_interval=publishing_interval
        )
        dataset["dataPoints"].append(sub_point)

        poller = self.update_ops.begin_update(
            resource_group_name,
            asset_name,
            asset["properties"]
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()

        return _get_dataset(asset, dataset_name)["dataPoints"]

    def export_dataset_data_points(
        self,
        asset_name: str,
        dataset_name: str,
        resource_group_name: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: Optional[bool] = False
    ):
        from ....util import dump_content_to_file
        dataset = self.show_dataset(
            asset_name=asset_name,
            dataset_name=dataset_name,
            resource_group_name=resource_group_name,
        )
        fieldnames = None
        if extension in [FileType.csv.value, FileType.portal_csv.value]:
            default_configuration = dataset.get("datasetConfiguration", "{}")
            fieldnames = _convert_sub_points_to_csv(
                sub_points=dataset.get("dataPoints", []),
                sub_point_type="dataPoint",
                default_configuration=default_configuration,
                portal_friendly=extension == FileType.portal_csv.value
            )
            extension = extension.replace("-", ".")
        file_path = dump_content_to_file(
            content=dataset.get("dataPoints", []),
            file_name=f"{asset_name}_{dataset_name}_datapoints",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path}

    def import_dataset_data_points(
        self,
        asset_name: str,
        dataset_name: str,
        file_path: str,
        resource_group_name: str,
        replace: bool = False
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        # should get the direct object so this should be enough
        dataset = _get_dataset(asset, dataset_name)
        dataset["events"] = _process_asset_sub_points_file_path(
            file_path=file_path,
            original_items=dataset.get("dataPoints", []),
            point_key="dataSource",
            replace=replace
        )

        poller = self.update_ops.begin_update(
            resource_group_name,
            asset_name,
            asset["properties"]
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()
        return asset["properties"]["events"]

    def list_dataset_data_points(
        self,
        asset_name: str,
        dataset_name: str,
        resource_group_name: str,
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        return _get_dataset(asset, dataset_name).get("dataPoints", [])

    def remove_dataset_data_point(
        self,
        asset_name: str,
        dataset_name: str,
        data_point_name: str,
        resource_group_name: str,
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        dataset = _get_dataset(asset, dataset_name)

        dataset["dataPoints"] = [dp for dp in dataset.get("dataPoints", []) if dp["name"] != data_point_name]

        poller = self.update_ops.begin_update(
            resource_group_name,
            asset_name,
            asset["properties"]
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()

        return _get_dataset(asset, dataset_name)["dataPoints"]

    # Events
    def add_event(
        self,
        asset_name: str,
        resource_group_name: str,
        event_notifier: str,
        event_name: Optional[str] = None,
        observability_mode: Optional[str] = None,
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        publishing_interval: Optional[int] = None,  # note that the swagger mentions this but not sure if used
        topic_path: Optional[str] = None,
        topic_retain: Optional[str] = None
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )

        sub_point = _build_asset_sub_point(
            event_notifier=event_notifier,
            name=event_name,
            observability_mode=observability_mode,
            queue_size=queue_size,
            publishing_interval=publishing_interval,
            sampling_interval=sampling_interval
        )
        if topic_path:
            sub_point["topic"] = {
                "path": topic_path,
                "retain": topic_retain or "Never"
            }
        asset["properties"]["events"] = asset["properties"].get("events", [])
        asset["properties"]["events"].append(sub_point)

        poller = self.update_ops.begin_update(
            resource_group_name,
            asset_name,
            asset["properties"]
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()
        return asset["properties"]["events"]

    def export_events(
        self,
        asset_name: str,
        resource_group_name: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: Optional[bool] = False
    ):
        from ....util import dump_content_to_file
        asset_props = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        fieldnames = None
        if extension in [FileType.csv.value, FileType.portal_csv.value]:
            default_configuration = asset_props.get("defaultEventsConfiguration", "{}")
            fieldnames = _convert_sub_points_to_csv(
                sub_points=asset_props.get("events", []),
                sub_point_type="events",
                default_configuration=default_configuration,
                portal_friendly=extension == FileType.portal_csv.value
            )
            extension = extension.replace("-", ".")
        file_path = dump_content_to_file(
            content=asset_props.get("events", []),
            file_name=f"{asset_name}_events",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path}

    def import_events(
        self,
        asset_name: str,
        file_path: str,
        resource_group_name: str,
        replace: bool = False
    ):
        asset_props = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )["properties"]
        asset_props["events"] = _process_asset_sub_points_file_path(
            file_path=file_path,
            original_items=asset_props.get("events", []),
            point_key="eventNotifier",
            replace=replace
        )

        poller = self.update_ops.begin_update(
            resource_group_name,
            asset_name,
            asset_props
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()
        return asset["properties"]["events"]

    def list_events(
        self,
        asset_name: str,
        resource_group_name: str
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )

        return asset["properties"].get("events", [])

    def remove_event(
        self,
        asset_name: str,
        event_name: str,
        resource_group_name: str,
    ):
        asset = self.show(
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        asset_props = asset["properties"]
        asset_props["events"] = [ev for ev in asset_props.get("events", []) if ev["name"] != event_name]

        poller = self.update_ops.begin_update(
            resource_group_name,
            asset_name,
            asset_props
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()
        return asset["properties"]["events"]


# New Helpers
def _get_dataset(asset: dict, dataset_name: str):
    datasets = asset["properties"].get("datasets", [])
    dataset = [dset for dset in datasets if dset["name"] == dataset_name]
    if not dataset:
        raise InvalidArgumentValueError(f"Dataset {dataset_name} not found in asset {asset['name']}.")
    # should I check for more than one dataset? -> need to see if datasets can have the same name within an asset
    return dataset[0]


def _build_topic(
    original_topic: Optional[Dict[str, str]] = None,
    topic_path: Optional[str] = None,
    topic_retain: Optional[str] = None
) -> Dict[str, str]:
    if not original_topic:
        original_topic = {}
    if topic_path:
        original_topic["path"] = topic_path
    if topic_retain:
        original_topic["retain"] = topic_retain
    elif not original_topic.get("retain"):
        original_topic["retain"] = "Never"

    if not original_topic.get("path"):
        raise RequiredArgumentMissingError("Topic path is needed for a topic configuration.")

    return original_topic


def _process_asset_sub_points_file_path(
    file_path: str,
    original_items: Optional[List[dict]] = None,
    point_key: Optional[str] = None,
    replace: bool = False
) -> List[Dict[str, str]]:
    from ....util import deserialize_file_content
    file_points = list(deserialize_file_content(file_path=file_path))
    _convert_sub_points_from_csv(file_points)

    if replace:
        return file_points

    if not original_items:
        original_items = []
    original_points = {point[point_key]: point for point in original_items}
    file_points = {point[point_key]: point for point in file_points}
    for key in file_points:
        if key in original_points:
            logger.warning(f"{key} is already present in the asset and will be ignored.")
        else:
            original_points[key] = file_points[key]
    return list(original_points.values())


def _build_query_body(
    asset_name: Optional[str] = None,
    default_topic_path: Optional[str] = None,
    default_topic_retain: Optional[str] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
    display_name: Optional[str] = None,
    documentation_uri: Optional[str] = None,
    endpoint_profile: Optional[str] = None,
    external_asset_id: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    location: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_uri: Optional[str] = None,
    model: Optional[str] = None,
    product_code: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    serial_number: Optional[str] = None,
    software_revision: Optional[str] = None,
) -> str:
    query_body = ""
    if resource_group_name:
        query_body += f"| where resourceGroup =~ \"{resource_group_name}\""
    if location:
        query_body += f"| where location =~ \"{location}\""
    if asset_name:
        query_body += f"| where name =~ \"{asset_name}\""
    if default_topic_path:
        query_body += f"| where properties.defaultTopic.path =~ \"{default_topic_path}\""
    if default_topic_retain:
        query_body += f"| where properties.defaultTopic.retain =~ \"{default_topic_retain}\""
    if description:
        query_body += f"| where properties.description =~ \"{description}\""
    if display_name:
        query_body += f"| where properties.displayName =~ \"{display_name}\""
    if disabled is not None:
        query_body += f"| where properties.enabled == {not disabled}"
    if documentation_uri:
        query_body += f"| where properties.documentationUri =~ \"{documentation_uri}\""
    if endpoint_profile:
        query_body += f"| where properties.assetEndpointProfileUri =~ \"{endpoint_profile}\""
    if external_asset_id:
        query_body += f"| where properties.externalAssetId =~ \"{external_asset_id}\""
    if hardware_revision:
        query_body += f"| where properties.hardwareRevision =~ \"{hardware_revision}\""
    if manufacturer:
        query_body += f"| where properties.manufacturer =~ \"{manufacturer}\""
    if manufacturer_uri:
        query_body += f"| where properties.manufacturerUri =~ \"{manufacturer_uri}\""
    if model:
        query_body += f"| where properties.model =~ \"{model}\""
    if product_code:
        query_body += f"| where properties.productCode =~ \"{product_code}\""
    if serial_number:
        query_body += f"| where properties.serialNumber =~ \"{serial_number}\""
    if software_revision:
        query_body += f"| where properties.softwareRevision =~ \"{software_revision}\""

    query_body += "| extend customLocation = tostring(extendedLocation.name) "\
        "| extend provisioningState = properties.provisioningState "\
        "| project id, customLocation, location, name, resourceGroup, provisioningState, tags, "\
        "type, subscriptionId "
    return query_body


# Helpers
def _build_asset_sub_point(
    data_source: Optional[str] = None,
    event_notifier: Optional[str] = None,
    name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    publishing_interval: Optional[int] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
) -> Dict[str, str]:
    custom_configuration = _build_default_configuration(
        original_configuration="{}",
        publishing_interval=publishing_interval,
        sampling_interval=sampling_interval,
        queue_size=queue_size
    )
    result = {"name": name}
    observability_mode = observability_mode.capitalize() if observability_mode else "None"

    if data_source:
        result["dataSource"] = data_source
        result["dataPointConfiguration"] = custom_configuration
        if observability_mode not in VALID_DATA_OBSERVABILITY_MODES:
            raise InvalidArgumentValueError(
                INVALID_OBSERVABILITY_MODE_ERROR.format(data_source, ', '.join(VALID_DATA_OBSERVABILITY_MODES))
            )
    elif event_notifier:
        result["eventNotifier"] = event_notifier
        result["eventConfiguration"] = custom_configuration
        if observability_mode not in VALID_EVENT_OBSERVABILITY_MODES:
            raise InvalidArgumentValueError(
                INVALID_OBSERVABILITY_MODE_ERROR.format(event_notifier, ', '.join(VALID_EVENT_OBSERVABILITY_MODES))
            )

    result["observabilityMode"] = observability_mode
    return result


def _build_default_configuration(
    original_configuration: str,
    publishing_interval: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    queue_size: Optional[int] = None,
) -> str:
    defaults = json.loads(original_configuration)
    if publishing_interval:
        defaults["publishingInterval"] = int(publishing_interval)
    if sampling_interval:
        defaults["samplingInterval"] = int(sampling_interval)
    if queue_size:
        defaults["queueSize"] = int(queue_size)
    return json.dumps(defaults)


def _build_ordered_csv_conversion_map(sub_point_type: str, portal_friendly: bool = False) -> Dict[str, str]:
    """Results in an ordered dict for headers"""
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
        csv_conversion_map.insert(0, ("eventNotifier", "EventNotifier" if portal_friendly else "Event Notifier"))
        csv_conversion_map.insert(1, ("name", "EventName" if portal_friendly else "Name"))

    # datasource, name, queuesize, observabilitymode, samplinginterval, capabilityid
    return OrderedDict(csv_conversion_map)


def _convert_sub_points_from_csv(sub_points: List[Dict[str, str]]):
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
        "TagName" : "name",
    }
    for point in sub_points:
        # point has csv values
        point.pop("", None)
        for key, value in csv_conversion_map.items():
            if key in point:
                point[value] = point.pop(key)
        # now the point has the normal values - do some final transformations
        if point.get("observabilityMode"):
            point["observabilityMode"] = point["observabilityMode"].capitalize()
        configuration = {}
        if point.get("samplingInterval"):
            configuration["samplingInterval"] = int(point.pop("samplingInterval"))
        else:
            point.pop("samplingInterval", None)
        if point.get("queueSize"):
            configuration["queueSize"] = int(point.pop("queueSize"))
        else:
            point.pop("queueSize", None)
        if configuration:
            config_key = "dataPointConfiguration" if "dataSource" in point else "eventConfiguration"
            point[config_key] = json.dumps(configuration)


def _convert_sub_points_to_csv(
    sub_points: List[Dict[str, str]],
    sub_point_type: str,
    default_configuration: str,
    portal_friendly: bool = False
) -> List[str]:
    csv_conversion_map = _build_ordered_csv_conversion_map(sub_point_type, portal_friendly)
    default_configuration = json.loads(default_configuration) if portal_friendly else {}
    for point in sub_points:
        configuration = point.pop(f"{sub_point_type[:-1]}Configuration", "{}")
        point.update(json.loads(configuration))
        if portal_friendly:
            point.pop("capabilityId", None)
            if sub_point_type == "events":
                point.pop("samplingInterval", None)
        for asset_key, csv_key in csv_conversion_map.items():
            point[csv_key] = point.pop(asset_key, default_configuration.get(asset_key))
    return list(csv_conversion_map.values())


def _process_asset_sub_points(required_arg: str, sub_points: Optional[List[str]]) -> List[Dict[str, str]]:
    """This is for the main create/update asset commands"""
    if not sub_points:
        return []
    point_type = "Data point" if required_arg == "data_source" else "Event"
    invalid_arg = "event_notifier" if required_arg == "data_source" else "data_source"
    processed_points = []
    for point in sub_points:
        parsed_points = assemble_nargs_to_dict(point)

        if not parsed_points.get(required_arg):
            raise RequiredArgumentMissingError(f"{point_type} ({point}) is missing the {required_arg}.")
        if parsed_points.get(invalid_arg):
            raise InvalidArgumentValueError(f"{point_type} does not support {invalid_arg}.")

        processed_point = _build_asset_sub_point(**parsed_points)
        processed_points.append(processed_point)

    return processed_points


def _process_custom_attributes(current_attributes: Dict[str, str], custom_attributes: List[str]):
    custom_attributes = assemble_nargs_to_dict(custom_attributes)
    for key, value in custom_attributes.items():
        if value == "":
            current_attributes.pop(key, None)
        else:
            current_attributes[key] = value


def _update_properties(
    properties: Dict[str, Union[str, List[Dict[str, str]]]],
    custom_attributes: Optional[List[str]] = None,
    default_topic_path: Optional[str] = None,
    default_topic_retain: Optional[str] = None,
    description: Optional[str] = None,
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
    ds_publishing_interval: Optional[int] = None,
    ds_sampling_interval: Optional[int] = None,
    ds_queue_size: Optional[int] = None,
    ev_publishing_interval: Optional[int] = None,
    ev_sampling_interval: Optional[int] = None,
    ev_queue_size: Optional[int] = None,
) -> None:
    if description:
        properties["description"] = description
    if disabled is not None:
        properties["enabled"] = not disabled
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

    if custom_attributes:
        if "attributes" not in properties:
            properties["attributes"] = {}
        _process_custom_attributes(
            properties["attributes"], custom_attributes=custom_attributes
        )

    # Defaults
    properties["defaultDatasetsConfiguration"] = _build_default_configuration(
        original_configuration=properties.get("defaultDataPointsConfiguration", "{}"),
        publishing_interval=ds_publishing_interval,
        sampling_interval=ds_sampling_interval,
        queue_size=ds_queue_size
    )

    properties["defaultEventsConfiguration"] = _build_default_configuration(
        original_configuration=properties.get("defaultEventsConfiguration", "{}"),
        publishing_interval=ev_publishing_interval,
        sampling_interval=ev_sampling_interval,
        queue_size=ev_queue_size
    )

    if any([default_topic_path, default_topic_retain]):
        properties["defaultTopic"] = _build_topic(
            original_topic=properties.get("defaultTopic"),
            topic_path=default_topic_path,
            topic_retain=default_topic_retain
        )
