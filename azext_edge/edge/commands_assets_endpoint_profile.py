# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Optional
from azure.cli.core.azclierror import CLIInternalError

import json

from knack.log import get_logger

from azure.cli.core.commands.client_factory import get_subscription_id
from azext_edge.common.embedded_cli import EmbeddedCLI

logger = get_logger(__name__)

API_VERSION = "2023-08-01-preview"
cli = EmbeddedCLI()
SUBSCRIPTION = get_subscription_id(cli.az_cli)


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


def list_asset_endpoint_profiles(
    cmd,
    resource_group_name: Optional[str] = None,
) -> dict:
    # additions:
    # resource group
    # subscription
    # see if there is some server side querying

    uri = f"/subscriptions/{SUBSCRIPTION}"
    if resource_group_name:
        uri += f"/resourceGroups/{resource_group_name}"
    uri += f"/providers/Microsoft.DeviceRegistry/assetEndpointProfiles?api-version={API_VERSION}"
    cli.invoke(f"rest --method GET --uri {uri}")
    return cli.as_json()["value"]


def show_asset(
    cmd,
    profile_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    if resource_group_name:
        resource_path = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry/assetEndpointProfiles/{profile_name}"
        cli.invoke(f"rest --method GET --uri {resource_path}")
        return cli.as_json()

    assets_list = list_asset_endpoint_profiles(cmd)
    for asset in assets_list:
        if asset["name"] == profile_name:
            return asset

    raise ResourceNotFound()


def delete_asset_endpoint_profile(
    cmd,
    profile_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    if not resource_group_name:
        assets_list = list_asset_endpoint_profiles(cmd)
        for asset in assets_list:
            if asset["name"] == profile_name:
                resource_group_name = asset["resourceGroup"]
                break

    resource_path = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry/assetEndpointProfiles/{profile_name}"
    cli.invoke(f"rest --method DELETE --uri {resource_path}")


def create_asset_endpoint_profile(
    cmd,
    profile_name: str,
    resource_group_name: str,
    endpoint_profile: str,
    custom_location: str,
    location: Optional[str] = None,
    data_points=None,
    description: Optional[str] = None,
    documentation_uri: Optional[str] = None,
    events=None,
    external_asset_id: Optional[str] = None,
    hardware_version: Optional[str] = None,
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
    resource_type = "Microsoft.DeviceRegistry/assets"

    # extended location
    extended_location = {
        "type": "CustomLocation",
        "name": f"/subscriptions/{SUBSCRIPTION}/resourcegroups/{resource_group_name}/providers/microsoft.extendedlocation"
        f"/customlocations/{custom_location}"
    }
    # Location
    if not location:
        cli.invoke(f"group show -n {resource_group_name}")
        location = cli.as_json()["location"]

    # Properties
    properties = {
        "connectivityProfileUri": endpoint_profile,
        "enabled": True
    }

    # Optional properties
    # assetType
    # defaultEventsConfiguration
    if description:
        properties["description"] = description
    if documentation_uri:
        properties["documentationUri"] = documentation_uri
    if external_asset_id:
        properties["externalAssetId"] = external_asset_id
    if hardware_version:
        properties["hardwareRevision"] = hardware_version
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
    if not data_points:
        data_points = []
    parsed_data_points = []
    for data_point in data_points:
        custom_configuration = {}
        if data_point.get("samplingInterval"):
            custom_configuration["samplingInterval"] = data_point.get("samplingInterval")
        if data_point.get("queueSize"):
            custom_configuration["queueSize"] = data_point.get("queueSize")

        parsed_data_point = {
            "capabilityId": data_point["capabilityId"],
            "dataPointConfiguration": json.dumps(custom_configuration),
            "dataSource": data_point["nodeId"],
            "name": data_point["name"],
            "observabilityMode": data_point["observabilityMode"]
        }
        parsed_data_points.append(parsed_data_point)
    properties["dataPoints"] = parsed_data_points

    # Events
    if not events:
        events = []
    parsed_events = []
    for event in events:
        custom_configuration = {}
        if event.get("samplingInterval"):
            custom_configuration["samplingInterval"] = event.get("samplingInterval")
        if event.get("queueSize"):
            custom_configuration["queueSize"] = event.get("queueSize")

        parsed_event = {
            "capabilityId": event["capabilityId"],
            "eventConfiguration": json.dumps(custom_configuration),
            "eventNotifier": event["eventNotifier"],
            "name": event["name"],
            "observabilityMode": event["observabilityMode"]
        }
        parsed_events.append(parsed_event)
    properties["events"] = parsed_events

    resource_path = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry/assets/{profile_name}"
    asset_body = {
        "extendedLocation": extended_location,
        "id": resource_path,
        "location": location,
        "name": profile_name,
        "properties": properties,
        "resourceGroup": resource_group_name,
        "tags": tags,
        "type": resource_type
    }

    cli.invoke(f"rest --method PUT --uri {resource_path} --body '{json.dumps(asset_body)}'")
    return cli.as_json()


def update_asset_endpoint_profile(
    cmd,
    profile_name: str,
    resource_group_name: str,
    data_points=None,
    description: Optional[str] = None,
    documentation_uri: Optional[str] = None,
    events=None,
    external_asset_id: Optional[str] = None,
    hardware_version: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_uri: Optional[str] = None,
    model: Optional[str] = None,
    product_code: Optional[str] = None,
    serial_number: Optional[str] = None,
    software_revision: Optional[str] = None,
    publishing_interval: int = 1000,
    sampling_interval: int = 500,
    queue_size: int = 1,
):
    resource_type = "Microsoft.DeviceRegistry/assets"
    resource_command = f"resource create --resource-type {resource_type} -n {profile_name} -g {resource_group_name}"

     # Properties
    properties = {}

    # Optional properties
    # assetType
    # enabled
    # connectivityProfileUri
    # defaultEventsConfiguration
    if description:
        properties["description"] = description
    if documentation_uri:
        properties["documentationUri"] = documentation_uri
    if external_asset_id:
        properties["externalAssetId"] = external_asset_id
    if hardware_version:
        properties["hardwareRevision"] = hardware_version
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
    parsed_data_points = []
    for data_point in data_points:
        custom_configuration = {}
        if data_point.get("samplingInterval"):
            custom_configuration["samplingInterval"] = data_point.get("samplingInterval")
        if data_point.get("queueSize"):
            custom_configuration["queueSize"] = data_point.get("queueSize")

        parsed_data_point = {
            "capabilityId": data_point["capabilityId"],
            "dataPointConfiguration": json.dumps(custom_configuration),
            "dataSource": data_point["nodeId"],
            "name": data_point["name"],
            "observabilityMode": data_point["observabilityMode"]
        }
        parsed_data_points.append(parsed_data_point)
    properties["dataPoints"] = parsed_data_points

    # Events
    parsed_events = []
    for event in events:
        custom_configuration = {}
        if event.get("samplingInterval"):
            custom_configuration["samplingInterval"] = event.get("samplingInterval")
        if event.get("queueSize"):
            custom_configuration["queueSize"] = event.get("queueSize")

        parsed_event = {
            "capabilityId": event["capabilityId"],
            "eventConfiguration": json.dumps(custom_configuration),
            "eventNotifier": event["eventNotifier"],
            "name": event["name"],
            "observabilityMode": event["observabilityMode"]
        }
        parsed_events.append(parsed_event)
    properties["events"] = parsed_events
