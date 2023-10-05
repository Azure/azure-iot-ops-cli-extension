# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
from typing import Dict, List, Optional, Union

from knack.log import get_logger

from azure.cli.core.azclierror import InvalidArgumentValueError, ResourceNotFoundError, RequiredArgumentMissingError
from azure.cli.core.commands.client_factory import get_subscription_id

from ..common.embedded_cli import EmbeddedCLI
from .util import assemble_nargs_to_dict, build_query
from .common import ResourceTypeMapping

logger = get_logger(__name__)

# for some reason "2023-08-01-preview" doesnt work with custom location
API_VERSION = "2023-06-21-preview"
cli = EmbeddedCLI()


def create_asset(
    cmd,
    asset_name: str,
    resource_group_name: str,
    endpoint_profile: str,
    asset_type: Optional[str] = None,
    cluster_name: Optional[str] = None,
    # cluster_resource_group: Optional[str] = None, TODO: check if you can have multiple same name cluster within a sub
    cluster_subscription: Optional[str] = None,
    custom_location: Optional[str] = None,
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
    custom_location_id = _check_asset_cluster_and_custom_location(
        subscription=subscription,
        custom_location_name=custom_location,
        custom_location_resource_group=custom_location_resource_group,
        custom_location_subscription=custom_location_subscription,
        cluster_name=cluster_name,
        cluster_subscription=cluster_subscription
    )
    resource_type = "Microsoft.DeviceRegistry/assets"

    # extended location
    extended_location = {
        "type": "CustomLocation",
        "name": custom_location_id
    }
    # Location
    if not location:
        cli.invoke(f"group show -n {resource_group_name}")
        location = cli.as_json()["location"]

    # Properties
    properties = {
        "connectivityProfileUri": endpoint_profile,
        "dataPoints": _process_asset_sub_points("data_source", data_points),
        "events": _process_asset_sub_points("event_notifier", events),
    }

    # Other properties
    _update_properties(
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


def list_assets(
    cmd,
    resource_group_name: Optional[str] = None,
) -> dict:
    # Note the usage of az rest over resource
    # az resource list will omit properties
    subscription = get_subscription_id(cmd.cli_ctx)
    uri = f"/subscriptions/{subscription}"
    if resource_group_name:
        uri += f"/resourceGroups/{resource_group_name}"
    uri += "/providers/Microsoft.DeviceRegistry/assets"
    cli.invoke(f"rest --method GET --uri {uri}?api-version={API_VERSION}")
    return cli.as_json()["value"]


def query_assets(
    cmd,
    asset_type: Optional[str] = None,
    custom_location: Optional[str] = None,
    description: Optional[str] = None,
    disabled: bool = False,
    documentation_uri: Optional[str] = None,
    endpoint_profile: Optional[str] = None,
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
    subscription = get_subscription_id(cmd.cli_ctx)
    query = ""
    if asset_type:
        query += f"| where properties.assetType =~ '{asset_type}'"
    if custom_location:  # ##
        query += f"| where extendedLocation contains '{asset_type}'"
    if description:
        query += f"| where properties.description =~ '{description}'"
    if disabled:  # ###
        query += f"| where properties.enabled == {not disabled}"
    if documentation_uri:
        query += f"| where properties.documentationUri =~ '{documentation_uri}'"
    if endpoint_profile:
        query += f"| where properties.connectivityProfileUri =~ '{endpoint_profile}'"
    if external_asset_id:
        query += f"| where properties.externalAssetId =~ '{external_asset_id}'"
    if hardware_revision:
        query += f"| where properties.hardwareRevision =~ '{hardware_revision}'"
    if manufacturer:
        query += f"| where properties.manufacturer =~ '{manufacturer}'"
    if manufacturer_uri:
        query += f"| where properties.manufacturerUri =~ '{manufacturer_uri}'"
    if model:
        query += f"| where properties.model =~ '{model}'"
    if product_code:
        query += f"| where properties.productCode =~ '{product_code}'"
    if serial_number:
        query += f"| where properties.serialNumber =~ '{serial_number}'"
    if software_revision:
        query += f"| where properties.softwareRevision =~ '{software_revision}'"

    return build_query(
        subscription_id=subscription,
        custom_query=query,
        location=location,
        resource_group=resource_group_name,
        type=ResourceTypeMapping.asset.value,
    )


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
        properties["dataPoints"] = _process_asset_sub_points("data_source", data_points)
    if events:
        properties["events"] = _process_asset_sub_points("event_notifier", events)

    # version cannot be bumped with PUT :D

    # Other properties
    _update_properties(
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


# Data Point sub commands - TODO: there is some redundancy with Event
def add_asset_data_point(
    cmd,
    asset_name: str,
    data_source: str,
    capability_id: Optional[str] = None,
    name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    resource_group_name: Optional[str] = None
):
    asset = show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )

    data_point = _build_asset_sub_point(
        data_source=data_source,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval
    )
    asset["properties"]["dataPoints"].append(data_point)
    resource_path = asset["id"]
    # TODO: change to patch once supported
    cli.invoke(
        f"rest --method PUT --uri {resource_path}?api-version={API_VERSION} --body '{json.dumps(asset)}'"
    )
    return cli.as_json()["properties"]["dataPoints"]


def list_asset_data_points(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
):
    return show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )["properties"]["dataPoints"]


def remove_asset_data_point(
    cmd,
    asset_name: str,
    data_source: Optional[str] = None,
    name: Optional[str] = None,
    resource_group_name: Optional[str] = None
):
    if not any([data_source, name]):
        raise RequiredArgumentMissingError(
            "Provide either the data source via --data-source or name via --name to identify the data point to remove."
        )
    asset = show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )

    data_points = asset["properties"]["dataPoints"]
    if data_source:
        data_points = [dp for dp in data_points if dp["dataSource"] != data_source]
    else:
        data_points = [dp for dp in data_points if dp.get("name") != name]

    asset["properties"]["dataPoints"] = data_points

    resource_path = asset["id"]
    # TODO: change to patch once supported
    cli.invoke(
        f"rest --method PUT --uri {resource_path}?api-version={API_VERSION} --body '{json.dumps(asset)}'"
    )
    return cli.as_json()["properties"]["dataPoints"]


# Event sub commands
def add_asset_event(
    cmd,
    asset_name: str,
    event_notifier: str,
    capability_id: Optional[str] = None,
    name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    resource_group_name: Optional[str] = None
):
    asset = show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )

    event = _build_asset_sub_point(
        event_notifier=event_notifier,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval
    )
    asset["properties"]["events"].append(event)
    resource_path = asset["id"]
    # TODO: change to patch once supported
    cli.invoke(
        f"rest --method PUT --uri {resource_path}?api-version={API_VERSION} --body '{json.dumps(asset)}'"
    )
    return cli.as_json()["properties"]["events"]


def list_asset_events(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
):
    return show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )["properties"]["events"]


def remove_asset_event(
    cmd,
    asset_name: str,
    event_notifier: Optional[str] = None,
    name: Optional[str] = None,
    resource_group_name: Optional[str] = None
):
    if not any([event_notifier, name]):
        raise RequiredArgumentMissingError(
            "Provide either the event notifier via --event-notifier or name via --name to identify the event to remove."
        )
    asset = show_asset(
        cmd=cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )

    events = asset["properties"]["events"]
    if event_notifier:
        events = [e for e in events if e["eventNotifier"] != event_notifier]
    else:
        events = [e for e in events if e.get("name") != name]

    asset["properties"]["events"] = events

    resource_path = asset["id"]
    # TODO: change to patch once supported
    cli.invoke(
        f"rest --method PUT --uri {resource_path}?api-version={API_VERSION} --body '{json.dumps(asset)}'"
    )
    return cli.as_json()["properties"]["events"]


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


def _check_asset_cluster_and_custom_location(
    subscription,
    custom_location_name: str = None,
    custom_location_resource_group: str = None,
    custom_location_subscription: str = None,
    cluster_name: str = None,
    cluster_subscription: str = None,
):
    if not any([cluster_name, custom_location_name]):
        raise Exception("need to provide either cluster name or custom location")
    query = ""
    cluster = None
    if not custom_location_subscription:
        custom_location_subscription = subscription
    if not cluster_subscription:
        cluster_subscription = subscription

    # provide cluster name - start with checking for the cluster (if can)
    if cluster_name:
        query = f'| where name =~ "{cluster_name}" '
        cluster_query_result = build_query(
            cluster_subscription,
            custom_query=query,
            type=ResourceTypeMapping.connected_cluster.value,
        )
        if len(cluster_query_result) == 0:
            raise Exception(f"Cluster {cluster_name} does not exist")
        cluster = cluster_query_result[0]
        # reset query so the location query will ensure that the cluster is associated
        query = f'| where hostResourceId =~ "{cluster["id"]}" '

    # try to find location, either from given param and/or from cluster
    # if only location is provided, will look just by location name
    # if both cluster name and location are provided, should also include cluster id to narrow association
    if custom_location_name:
        query += f'| where name =~ "{custom_location_name}" '
    if custom_location_resource_group:
        query += f'| where resourceGroup =~ "{custom_location_resource_group}" '
    location_query_result = build_query(
        custom_location_subscription,
        custom_query=query,
        type=ResourceTypeMapping.custom_location.value
    )
    if len(location_query_result) == 0:
        error_details = ""
        if custom_location_name:
            error_details += f"{custom_location_name} "
        if cluster_name:
            error_details += f"for cluster {cluster_name} "
        raise Exception(f"Custom location {error_details} not found.")

    if len(location_query_result) > 1 and cluster_name is None:
        raise Exception(
            f"Found {len(location_query_result)} custom locations with the name {custom_location_name}. Please "
            "provide the resource group for the custom location."
        )
    # by this point there should be at least one custom location
    # if cluster name was given (and no custom_location_names), there can be more than one
    # otherwise, if no cluster name, needs to be only one

    # should trigger if only the location name was provided - there should be one location
    if not cluster_name:
        query = f'| where id =~ "{location_query_result[0]["hostResourceId"]}"'
        cluster_query_result = build_query(
            cluster_subscription,
            custom_query=query,
            type=ResourceTypeMapping.connected_cluster.value
        )
        if len(cluster_query_result) == 0:
            raise Exception(f"Cluster associated with custom location {custom_location_name} does not exist.")
        cluster = cluster_query_result[0]
    # by this point, cluster is populated

    # extensions check - see that the cluster and the location have the same (correct) extension.
    # start with getting all suitable extensions within the cluster.
    query = f'| where id startswith "{cluster["id"]}" | where properties.extensionType =~ '\
        '"microsoft.deviceregistry.assets" '
    extension_query_result = build_query(
        cluster_subscription,
        custom_query=query,
        type=ResourceTypeMapping.cluster_extensions.value
    )
    # throw if there are no suitable extensions (in the cluster)
    if len(extension_query_result) == 0:
        raise Exception(f"Cluster {cluster['name']} is missing the microsoft.deviceregistry.assets extension.")
    # here we warn about multiple custom locations (cluster name given, multiple locations possible)
    if len(location_query_result) > 1:
        logger.warn(
            f"More than one custom location for cluster {cluster['id']} found. Will pick first one that satisfies "
            "the conditions for asset creation."
        )

    # here we go through all locations + cluster extensions to narrow down to a location to use
    # ideally these for loops will loop once (as both results should contain one object)
    for location in location_query_result:
        for extension in extension_query_result:
            if extension["id"] in location["clusterExtensionIds"]:
                return location["id"]

    # here the location(s) do not have the correct extension
    error_details = f"{custom_location_name} " if custom_location_name else "s "
    error_details += f"for cluster {cluster_name} are" if cluster_name else "is"
    raise Exception(f"Custom location{error_details} missing the microsoft.deviceregistry.assets extension.")


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
