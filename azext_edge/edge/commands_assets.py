# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
from typing import Optional

from knack.log import get_logger

from azure.cli.core.azclierror import ResourceNotFoundError, RequiredArgumentMissingError
from azure.cli.core.commands.client_factory import get_subscription_id
from azext_edge.common.embedded_cli import EmbeddedCLI

from azure.mgmt.resource import ResourceManagementClient
from azure.identity import DefaultAzureCredential

from azext_edge.common.utility import assemble_nargs_to_dict

logger = get_logger(__name__)

API_VERSION = "2023-06-21-preview"  # "2023-08-01-preview"
cli = EmbeddedCLI()


# def log_round_trip(response, *args, **kwargs):
#     try:
#         logger.debug("Request URL: %r", response.request.url)
#         logger.debug("Request method: %r", response.request.method)
#         logger.debug("Request headers:")
#         for header, value in response.request.headers.items():
#             if header.lower() == "authorization":
#                 value = "*****"
#             logger.debug("    %r: %r", header, value)
#         logger.debug("Request body:")
#         logger.debug(str(response.request.body))
#     except Exception as e:
#         logger.debug("Failed to log request: %r", e)


# session = requests.Session()
# session.headers.update({"User-Agent": USER_AGENT, "x-ms-client-request-id": str(uuid1()), "Accept": "application/json"})
# session.hooks["response"].append(log_round_trip)


def list_assets(
    cmd,
    resource_group_name: Optional[str] = None,
) -> dict:
    subscription = get_subscription_id(cmd.az_cli)
    # additions:
    # resource group
    # subscription
    # see if there is some server side querying
    uri = f"/subscriptions/{subscription}"
    if resource_group_name:
        uri += f"/resourceGroups/{resource_group_name}"
    uri += f"/providers/Microsoft.DeviceRegistry/assets?api-version={API_VERSION}"
    cli.invoke(f"rest --method GET --uri {uri}")

    # resource_type = "Microsoft.DeviceRegistry/assets"
    # cli.invoke(f"resource list --resource-type {resource_type}")
    return cli.as_json()["value"]


def show_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    subscription = get_subscription_id(cmd.az_cli)
    if resource_group_name:
        resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry/assets/{asset_name}?api-version={API_VERSION}"
        cli.invoke(f"rest --method GET --uri {resource_path}")
        return cli.as_json()

    assets_list = list_assets(cmd)
    for asset in assets_list:
        if asset["name"] == asset_name:
            return asset

    raise ResourceNotFoundError()


def delete_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    subscription = get_subscription_id(cmd.az_cli)
    if not resource_group_name:
        assets_list = list_assets(cmd)
        for asset in assets_list:
            if asset["name"] == asset_name:
                resource_group_name = asset["resourceGroup"]
                break

    resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry/assets/{asset_name}?api-version={API_VERSION}"
    cli.invoke(f"rest --method DELETE --uri {resource_path}")


def create_asset(
    cmd,
    asset_name: str,
    resource_group_name: str,
    endpoint_profile: str,
    custom_location: str,
    asset_type: Optional[str] = None,
    custom_location_resource_group: Optional[str] = None,
    custom_location_subscription: Optional[str] = None,
    data_points=None,
    description: Optional[str] = None,
    disabled: bool = False,
    documentation_uri: Optional[str] = None,
    events=None,
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
    tags=None,
):
    subscription = get_subscription_id(cmd.az_cli)
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
        "enabled": not disabled
    }

    # Optional properties
    # assetType
    # defaultEventsConfiguration
    if asset_type:
        properties["assetType"] = asset_type
    if description:
        properties["description"] = description
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
    data_point_defaults = {
        "publishingInterval": dp_publishing_interval,
        "samplingInterval": dp_sampling_interval,
        "queueSize": dp_queue_size
    }
    properties["defaultDataPointsConfiguration"] = json.dumps(data_point_defaults)

    event_defaults = {
        "publishingInterval": ev_publishing_interval,
        "samplingInterval": ev_sampling_interval,
        "queueSize": ev_queue_size
    }
    properties["defaultEventsConfiguration"] = json.dumps(event_defaults)

    # Data points
    properties["dataPoints"] = process_data_points(data_points)

    # Events
    properties["events"] = process_events(events)

    resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/{resource_type}/{asset_name}?api-version={API_VERSION}"
    asset_body = {
        "extendedLocation": extended_location,
        "id": resource_path,
        "location": location,
        "name": asset_name,
        "properties": properties,
        "tags": tags,
        "type": resource_type
    }

    cli.invoke(f"rest --method PUT --uri {resource_path} --body '{json.dumps(asset_body)}'")
    return cli.as_json()


def update_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None,
    location: Optional[str] = None,
    data_points=None,
    description: Optional[str] = None,
    documentation_uri: Optional[str] = None,
    events=None,
    external_asset_id: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_uri: Optional[str] = None,
    model: Optional[str] = None,
    product_code: Optional[str] = None,
    serial_number: Optional[str] = None,
    software_revision: Optional[str] = None,
    publishing_interval: int = 1000,
    sampling_interval: int = 500,
    queue_size: int = 1,
    tags=None,
):
    subscription = get_subscription_id(cmd.az_cli)
    resource_type = "Microsoft.DeviceRegistry/assets"
    # Properties
    properties = {}

    # Optional properties
    if description:
        properties["description"] = description
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
    data_point_defaults = {
        "publishingInterval": publishing_interval,
        "samplingInterval": sampling_interval,
        "queueSize": queue_size
    }
    properties["defaultDataPointsConfiguration"] = json.dumps(data_point_defaults)

    event_defaults = {
        "publishingInterval": publishing_interval,
        "samplingInterval": sampling_interval,
        "queueSize": queue_size
    }
    properties["defaultEventsConfiguration"] = json.dumps(event_defaults)

    # Data points
    properties["dataPoints"] = process_data_points(data_points)

    # Events
    properties["events"] = process_events(events)

    resource_path = f"/subscriptions/{subscription}/resourceGroups/{resource_group_name}/providers/{resource_type}/{asset_name}?api-version={API_VERSION}"
    asset_body = {
        "properties": properties,
        "tags": tags,
    }
    cli.invoke(f"rest --method PATCH --uri {resource_path} --body '{json.dumps(asset_body)}'")
    return cli.as_json()


def process_data_points(data_points):
    if not data_points:
        return []
    processed_dps = []
    for data_point in data_points:
        parsed_dp = assemble_nargs_to_dict(data_point)

        if not parsed_dp.get("data_source"):
            raise RequiredArgumentMissingError(f"Data point is missing the data_source.")

        custom_configuration = {}
        if parsed_dp.get("sampling_interval"):
            custom_configuration["samplingInterval"] = int(parsed_dp.get("sampling_interval"))
        if parsed_dp.get("queue_size"):
            custom_configuration["queueSize"] = int(parsed_dp.get("queue_size"))

        if parsed_dp.get("capability_id"):
            parsed_dp["capabilityId"] = parsed_dp.get("name")

        processed_dp = {
            "capabilityId": parsed_dp.get("capability_id"),
            "dataPointConfiguration": json.dumps(custom_configuration),
            "dataSource": parsed_dp.get("data_source"),
            "name": parsed_dp.get("name"),
            "observabilityMode": parsed_dp.get("observability_mode")
        }
        processed_dps.append(processed_dp)

    return processed_dps


def process_events(events):
    if not events:
        return []
    processed_events = []
    for event in events:
        parsed_event = assemble_nargs_to_dict(event)

        if not parsed_event.get("event_notifier"):
            raise RequiredArgumentMissingError(f"Event is missing the event notifier.")

        custom_configuration = {}
        if parsed_event.get("sampling_interval"):
            custom_configuration["samplingInterval"] = int(parsed_event.get("sampling_interval"))
        if parsed_event.get("queueSize"):
            custom_configuration["queueSize"] = int(parsed_event.get("queueSize"))

        if parsed_event.get("capability_id"):
            parsed_event["capabilityId"] = parsed_event.get("name")

        processed_event = {
            "capabilityId": parsed_event.get("capability_id"),
            "eventConfiguration": json.dumps(custom_configuration),
            "eventNotifier": parsed_event.get("event_notifier"),
            "name": parsed_event.get("name"),
            "observabilityMode": parsed_event.get("observability_mode")
        }
        processed_events.append(processed_event)

    return processed_events
