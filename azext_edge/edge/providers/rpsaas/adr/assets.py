# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Dict, List, Optional, Union

from knack.log import get_logger

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from .base import ADRBaseProvider
from .user_strings import MISSING_DATA_EVENT_ERROR, ENDPOINT_NOT_FOUND_WARNING
from ....util import assemble_nargs_to_dict, build_query
from ....common import ResourceTypeMapping

logger = get_logger(__name__)


class AssetProvider(ADRBaseProvider):
    def __init__(self, cmd):
        super(AssetProvider, self).__init__(
            cmd=cmd,
            resource_type=ResourceTypeMapping.asset.value,
        )

    def create(
        self,
        asset_name: str,
        resource_group_name: str,
        endpoint: str,
        asset_type: Optional[str] = None,
        cluster_name: Optional[str] = None,
        cluster_resource_group: Optional[str] = None,
        cluster_subscription: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        custom_location_resource_group: Optional[str] = None,
        custom_location_subscription: Optional[str] = None,
        data_points: Optional[List[str]] = None,
        description: Optional[str] = None,
        disabled: bool = False,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        events: Optional[List[str]] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        location: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        dp_publishing_interval: int = 1000,
        dp_sampling_interval: int = 500,
        dp_queue_size: int = 1,
        ev_publishing_interval: int = 1000,
        ev_sampling_interval: int = 500,
        ev_queue_size: int = 1,
        tags: Optional[Dict[str, str]] = None,
    ):
        if not any([data_points, events]):
            raise RequiredArgumentMissingError(MISSING_DATA_EVENT_ERROR)
        extended_location = self.check_cluster_and_custom_location(
            custom_location_name=custom_location_name,
            custom_location_resource_group=custom_location_resource_group,
            custom_location_subscription=custom_location_subscription,
            cluster_name=cluster_name,
            cluster_resource_group=cluster_resource_group,
            cluster_subscription=cluster_subscription
        )
        # Location
        if not location:
            location = self.get_location(resource_group_name)

        # Properties
        properties = {
            "assetEndpointProfileUri": endpoint,
            "dataPoints": _process_asset_sub_points("data_source", data_points),
            "events": _process_asset_sub_points("event_notifier", events),
        }

        # Other properties
        _update_properties(
            properties,
            asset_type=asset_type,
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
            dp_publishing_interval=dp_publishing_interval,
            dp_sampling_interval=dp_sampling_interval,
            dp_queue_size=dp_queue_size,
            ev_publishing_interval=ev_publishing_interval,
            ev_sampling_interval=ev_sampling_interval,
            ev_queue_size=ev_queue_size,
        )

        asset_body = {
            "extendedLocation": extended_location,
            "location": location,
            "properties": properties,
            "tags": tags,
        }
        poller = self.resource_client.resources.begin_create_or_update(
            resource_group_name=resource_group_name,
            resource_provider_namespace=self.provider_namespace,
            parent_resource_path="",
            resource_type=self.resource_type,
            resource_name=asset_name,
            api_version=self.api_version,
            parameters=asset_body
        )
        return poller

    def query(
        self,
        asset_name: Optional[str] = None,
        asset_type: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        description: Optional[str] = None,
        disabled: bool = False,
        documentation_uri: Optional[str] = None,
        display_name: Optional[str] = None,
        endpoint: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        location: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        resource_group_name: Optional[str] = None,
    ) -> dict:
        query = ""
        if asset_name:
            query += f"| where assetName =~ \"{asset_name}\""
        if asset_type:
            query += f"| where properties.assetType =~ \"{asset_type}\""
        if custom_location_name:
            query += f"| where extendedLocation.name contains \"{custom_location_name}\""
        if description:
            query += f"| where properties.description =~ \"{description}\""
        if display_name:
            query += f"| where properties.displayName =~ \"{display_name}\""
        if disabled:
            query += f"| where properties.enabled == {not disabled}"
        if documentation_uri:
            query += f"| where properties.documentationUri =~ \"{documentation_uri}\""
        if endpoint:
            query += f"| where properties.assetEndpointProfileUri =~ \"{endpoint}\""
        if external_asset_id:
            query += f"| where properties.externalAssetId =~ \"{external_asset_id}\""
        if hardware_revision:
            query += f"| where properties.hardwareRevision =~ \"{hardware_revision}\""
        if manufacturer:
            query += f"| where properties.manufacturer =~ \"{manufacturer}\""
        if manufacturer_uri:
            query += f"| where properties.manufacturerUri =~ \"{manufacturer_uri}\""
        if model:
            query += f"| where properties.model =~ \"{model}\""
        if product_code:
            query += f"| where properties.productCode =~ \"{product_code}\""
        if serial_number:
            query += f"| where properties.serialNumber =~ \"{serial_number}\""
        if software_revision:
            query += f"| where properties.softwareRevision =~ \"{software_revision}\""
        return build_query(
            self.cmd,
            subscription_id=self.subscription,
            custom_query=query,
            location=location,
            resource_group=resource_group_name,
            type=ResourceTypeMapping.asset.full_value,
            additional_project="extendedLocation"
        )

    def update(
        self,
        asset_name: str,
        resource_group_name: str,
        asset_type: Optional[str] = None,
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
        dp_publishing_interval: Optional[int] = None,
        dp_sampling_interval: Optional[int] = None,
        dp_queue_size: Optional[int] = None,
        ev_publishing_interval: Optional[int] = None,
        ev_sampling_interval: Optional[int] = None,
        ev_queue_size: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        # get the asset
        original_asset = self.show(
            resource_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster_connectivity=True
        )
        if tags:
            original_asset["tags"] = tags

        # modify the asset
        # Properties
        properties = original_asset.get("properties", {})

        # Other properties
        _update_properties(
            properties,
            asset_type=asset_type,
            description=description,
            disabled=disabled,
            documentation_uri=documentation_uri,
            display_name=display_name,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
            dp_publishing_interval=dp_publishing_interval,
            dp_sampling_interval=dp_sampling_interval,
            dp_queue_size=dp_queue_size,
            ev_publishing_interval=ev_publishing_interval,
            ev_sampling_interval=ev_sampling_interval,
            ev_queue_size=ev_queue_size,
        )

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=original_asset["id"],
            api_version=self.api_version,
            parameters=original_asset
        )
        return poller

    def add_sub_point(
        self,
        asset_name: str,
        resource_group_name: str,
        data_source: Optional[str] = None,
        event_notifier: Optional[str] = None,
        capability_id: Optional[str] = None,
        name: Optional[str] = None,
        observability_mode: Optional[str] = None,
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
    ):
        asset = self.show(
            resource_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster_connectivity=True
        )

        sub_point = _build_asset_sub_point(
            data_source=data_source,
            event_notifier=event_notifier,
            capability_id=capability_id,
            name=name,
            observability_mode=observability_mode,
            queue_size=queue_size,
            sampling_interval=sampling_interval
        )
        sub_point_type = "dataPoints" if data_source else "events"
        if sub_point_type not in asset["properties"]:
            asset["properties"][sub_point_type] = []
        asset["properties"][sub_point_type].append(sub_point)

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=asset["id"],
            api_version=self.api_version,
            parameters=asset,
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()
        return asset["properties"][sub_point_type]

    def list_sub_points(
        self,
        asset_name: str,
        sub_point_type: str,
        resource_group_name: str
    ):
        asset = self.show(
            resource_name=asset_name,
            resource_group_name=resource_group_name
        )

        return asset["properties"].get(sub_point_type, [])

    def remove_sub_point(
        self,
        asset_name: str,
        sub_point_type: str,
        resource_group_name: str,
        data_source: Optional[str] = None,
        event_notifier: Optional[str] = None,
        name: Optional[str] = None,
    ):
        asset = self.show(
            resource_name=asset_name,
            resource_group_name=resource_group_name,
            check_cluster_connectivity=True
        )

        if sub_point_type not in asset["properties"]:
            asset["properties"][sub_point_type] = []
        sub_points = asset["properties"][sub_point_type]
        if data_source:
            sub_points = [dp for dp in sub_points if dp["dataSource"] != data_source]
        elif event_notifier:
            sub_points = [e for e in sub_points if e["eventNotifier"] != event_notifier]
        else:
            sub_points = [dp for dp in sub_points if dp.get("name") != name]

        asset["properties"][sub_point_type] = sub_points

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=asset["id"],
            api_version=self.api_version,
            parameters=asset
        )
        poller.wait()
        asset = poller.result()
        if not isinstance(asset, dict):
            asset = asset.as_dict()
        return asset["properties"][sub_point_type]

    def _check_endpoint(self, endpoint: str):
        possible_endpoints = build_query(
            self.cmd,
            subscription_id=self.subscription,
            name=endpoint
        )
        # future TODO: add option flag to fail on these
        if not possible_endpoints:
            logger.warning(ENDPOINT_NOT_FOUND_WARNING.format(endpoint))


# Helpers
def _build_asset_sub_point(
    data_source: Optional[str] = None,
    event_notifier: Optional[str] = None,
    capability_id: Optional[str] = None,
    name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
) -> Dict[str, str]:
    if capability_id is None:
        capability_id = name
    custom_configuration = {}
    if sampling_interval:
        custom_configuration["samplingInterval"] = int(sampling_interval)
    if queue_size:
        custom_configuration["queueSize"] = int(queue_size)
    result = {
        "capabilityId": capability_id,
        "name": name,
        "observabilityMode": observability_mode
    }

    if data_source:
        result["dataSource"] = data_source
        result["dataPointConfiguration"] = json.dumps(custom_configuration)
    elif event_notifier:
        result["eventNotifier"] = event_notifier
        result["eventConfiguration"] = json.dumps(custom_configuration)
    return result


def _build_default_configuration(
    original_configuration: str,
    publishing_interval: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    queue_size: Optional[int] = None,
) -> str:
    defaults = json.loads(original_configuration)
    if publishing_interval:
        defaults["publishingInterval"] = publishing_interval
    if sampling_interval:
        defaults["samplingInterval"] = sampling_interval
    if queue_size:
        defaults["queueSize"] = queue_size
    return json.dumps(defaults)


def _process_asset_sub_points(required_arg: str, sub_points: Optional[List[str]]) -> Dict[str, str]:
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


def _update_properties(
    properties: Dict[str, Union[str, List[Dict[str, str]]]],
    asset_type: Optional[str] = None,
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
    dp_publishing_interval: Optional[int] = None,
    dp_sampling_interval: Optional[int] = None,
    dp_queue_size: Optional[int] = None,
    ev_publishing_interval: Optional[int] = None,
    ev_sampling_interval: Optional[int] = None,
    ev_queue_size: Optional[int] = None,
) -> None:
    if asset_type:
        properties["assetType"] = asset_type
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

    # Defaults
    properties["defaultDataPointsConfiguration"] = _build_default_configuration(
        original_configuration=properties.get("defaultDataPointsConfiguration", "{}"),
        publishing_interval=dp_publishing_interval,
        sampling_interval=dp_sampling_interval,
        queue_size=dp_queue_size
    )

    properties["defaultEventsConfiguration"] = _build_default_configuration(
        original_configuration=properties.get("defaultEventsConfiguration", "{}"),
        publishing_interval=ev_publishing_interval,
        sampling_interval=ev_sampling_interval,
        queue_size=ev_queue_size
    )
