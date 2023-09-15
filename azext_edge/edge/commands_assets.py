# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
from typing import Dict, List, Optional, Union

from knack.log import get_logger

from azure.cli.core.azclierror import ResourceNotFoundError, RequiredArgumentMissingError
from azure.cli.core.commands.client_factory import get_subscription_id
from azext_edge.common.embedded_cli import EmbeddedCLI

from azext_edge.common.utility import assemble_nargs_to_dict

logger = get_logger(__name__)

# for some reason "2023-08-01-preview" doesnt work with custom location
API_VERSION = "2023-06-21-preview"
cli = EmbeddedCLI()


def list_assets(
    cmd,
    resource_group_name: Optional[str] = None,
) -> dict:
    subscription = get_subscription_id(cmd.cli_ctx)
    uri = f"/subscriptions/{subscription}"
    if resource_group_name:
        uri += f"/resourceGroups/{resource_group_name}"
    uri += "/providers/Microsoft.DeviceRegistry/assets"
    cli.invoke(f"rest --method GET --uri {uri}?api-version={API_VERSION}")
    return cli.as_json()["value"]


def show_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    subscription = get_subscription_id(cmd.cli_ctx)
    if resource_group_name:
        resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/"\
            f"Microsoft.DeviceRegistry/assets/{asset_name}"
        cli.invoke(f"rest --method GET --uri {resource_path}?api-version={API_VERSION}")
        return cli.as_json()

    assets_list = list_assets(cmd)
    for asset in assets_list:
        if asset["name"] == asset_name:
            return asset

    raise ResourceNotFoundError(f"Asset {asset_name} not found in subscription {subscription}.")


def delete_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    subscription = get_subscription_id(cmd.cli_ctx)
    if not resource_group_name:
        assets_list = list_assets(cmd)
        for asset in assets_list:
            if asset["name"] == asset_name:
                resource_group_name = asset["resourceGroup"]
                break

    resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/"\
        f"Microsoft.DeviceRegistry/assets/{asset_name}"
    cli.invoke(f"rest --method DELETE --uri {resource_path}?api-version={API_VERSION}")


def create_asset(
    cmd,
    asset_name: str,
    resource_group_name: str,
    endpoint_profile: str,
    custom_location: str,
    asset_type: Optional[str] = None,
    custom_location_resource_group: Optional[str] = None,
    custom_location_subscription: Optional[str] = None,
    data_points: Optional[List[str]] = None,
    description: Optional[str] = None,
    disabled: bool = False,
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
    subscription = get_subscription_id(cmd.cli_ctx)
    resource_type = "Microsoft.DeviceRegistry/assets"

    # extended location
    if not custom_location_subscription:
        custom_location_subscription = subscription
    if not custom_location_resource_group:
        custom_location_resource_group = resource_group_name
    extended_location = {
        "type": "CustomLocation",
        "name": f"/subscriptions/{custom_location_subscription}/resourcegroups/{custom_location_resource_group}"
        f"/providers/microsoft.extendedlocation/customlocations/{custom_location}"
    }
    # Location
    if not location:
        cli.invoke(f"group show -n {resource_group_name}")
        location = cli.as_json()["location"]

    # Properties
    properties = {
        "connectivityProfileUri": endpoint_profile,
        "dataPoints": process_data_points(data_points),
        "events": process_events(events),
    }

    # Other properties
    update_properties(
        properties,
        asset_type=asset_type,
        description=description,
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

    resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/{resource_type}"\
        f"/{asset_name}"
    asset_body = {
        "extendedLocation": extended_location,
        "location": location,
        "properties": properties,
        "tags": tags,
    }

    cli.invoke(f"rest --method PUT --uri {resource_path}?api-version={API_VERSION} --body '{json.dumps(asset_body)}'")
    return cli.as_json()


def update_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None,
    asset_type: Optional[str] = None,
    data_points: Optional[List[str]] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
    documentation_uri: Optional[str] = None,
    events: Optional[List[str]] = None,
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
    original_asset = show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    if tags:
        original_asset["tags"] = tags

    # modify the asset
    # Properties
    properties = original_asset.get("properties", {})
    if data_points:
        properties["dataPoints"] = process_data_points(data_points)
    if events:
        properties["events"] = process_events(events)

    # version cannot be bumped :D

    # Other properties
    update_properties(
        properties,
        asset_type=asset_type,
        description=description,
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

    resource_path = original_asset["id"]
    # TODO: change to patch once supported
    cli.invoke(
        f"rest --method PUT --uri {resource_path}?api-version={API_VERSION} --body '{json.dumps(original_asset)}'"
    )
    return cli.as_json()


def build_configuration(
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


def process_data_points(data_points: Optional[List[str]]) -> Dict[str, str]:
    if not data_points:
        return []
    processed_dps = []
    for data_point in data_points:
        parsed_dp = assemble_nargs_to_dict(data_point)

        if not parsed_dp.get("data_source"):
            raise RequiredArgumentMissingError(f"Data point ({data_point}) is missing the data_source.")

        custom_configuration = {}
        if parsed_dp.get("sampling_interval"):
            custom_configuration["samplingInterval"] = int(parsed_dp.get("sampling_interval"))
        if parsed_dp.get("queue_size"):
            custom_configuration["queueSize"] = int(parsed_dp.get("queue_size"))

        if not parsed_dp.get("capability_id"):
            parsed_dp["capability_id"] = parsed_dp.get("name")

        processed_dp = {
            "capabilityId": parsed_dp.get("capability_id"),
            "dataPointConfiguration": json.dumps(custom_configuration),
            "dataSource": parsed_dp.get("data_source"),
            "name": parsed_dp.get("name"),
            "observabilityMode": parsed_dp.get("observability_mode")
        }
        processed_dps.append(processed_dp)

    return processed_dps


def process_events(events: Optional[List[List[str]]]) -> Dict[str, str]:
    if not events:
        return []
    processed_events = []
    for event in events:
        parsed_event = assemble_nargs_to_dict(event)

        if not parsed_event.get("event_notifier"):
            raise RequiredArgumentMissingError(f"Event ({event}) is missing the event_notifier.")

        custom_configuration = {}
        if parsed_event.get("sampling_interval"):
            custom_configuration["samplingInterval"] = int(parsed_event.get("sampling_interval"))
        if parsed_event.get("queue_size"):
            custom_configuration["queueSize"] = int(parsed_event.get("queue_size"))

        if not parsed_event.get("capability_id"):
            parsed_event["capability_id"] = parsed_event.get("name")

        processed_event = {
            "capabilityId": parsed_event.get("capability_id"),
            "eventConfiguration": json.dumps(custom_configuration),
            "eventNotifier": parsed_event.get("event_notifier"),
            "name": parsed_event.get("name"),
            "observabilityMode": parsed_event.get("observability_mode")
        }
        processed_events.append(processed_event)

    return processed_events


def update_properties(
    properties: Dict[str, Union[str, List[Dict[str, str]]]],
    asset_type: Optional[str] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
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
    properties["defaultDataPointsConfiguration"] = build_configuration(
        original_configuration=properties.get("defaultDataPointsConfiguration", "{}"),
        publishing_interval=dp_publishing_interval,
        sampling_interval=dp_sampling_interval,
        queue_size=dp_queue_size
    )

    properties["defaultEventsConfiguration"] = build_configuration(
        original_configuration=properties.get("defaultEventsConfiguration", "{}"),
        publishing_interval=ev_publishing_interval,
        sampling_interval=ev_sampling_interval,
        queue_size=ev_queue_size
    )
