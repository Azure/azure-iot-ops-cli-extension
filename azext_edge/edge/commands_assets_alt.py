# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from azure.cli.core.azclierror import RequiredArgumentMissingError
from azure.cli.core.commands.client_factory import get_subscription_id

from .util import build_query
from .common import ResourceTypeMapping
from .providers.assets import AssetProvider

logger = get_logger(__name__)


def create_asset(
    cmd,
    asset_name: str,
    resource_group_name: str,
    endpoint_profile: str,
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
    asset_provider = AssetProvider(cmd)
    return asset_provider.create(
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        endpoint_profile=endpoint_profile,
        asset_type=asset_type,
        cluster_name=cluster_name,
        cluster_resource_group=cluster_resource_group,
        cluster_subscription=cluster_subscription,
        custom_location_name=custom_location_name,
        custom_location_resource_group=custom_location_resource_group,
        custom_location_subscription=custom_location_subscription,
        data_points=data_points,
        description=description,
        disabled=disabled,
        documentation_uri=documentation_uri,
        events=events,
        external_asset_id=external_asset_id,
        hardware_revision=hardware_revision,
        location=location,
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
        tags=tags
    )


def delete_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    asset_provider = AssetProvider(cmd)
    return asset_provider.delete(asset_name=asset_name, resource_group_name=resource_group_name)


def list_assets(
    cmd,
    resource_group_name: Optional[str] = None,
) -> dict:
    asset_provider = AssetProvider(cmd)
    return asset_provider.list(resource_group_name=resource_group_name)


def query_assets(
    cmd,
    asset_type: Optional[str] = None,
    custom_location_name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
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
        query += f"| where properties.assetType =~ \"{asset_type}\""
    if custom_location_name:  # ##
        query += f"| where extendedLocation.name contains \"{custom_location_name}\""
    if description:
        query += f"| where properties.description =~ \"{description}\""
    if enabled:
        query += f"| where properties.enabled == {enabled}"
    if documentation_uri:
        query += f"| where properties.documentationUri =~ \"{documentation_uri}\""
    if endpoint_profile:
        query += f"| where properties.connectivityProfileUri =~ \"{endpoint_profile}\""
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
        subscription_id=subscription,
        custom_query=query,
        location=location,
        resource_group=resource_group_name,
        type=ResourceTypeMapping.asset.value,
        additional_project="extendedLocation"
    )


def show_asset(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
) -> dict:
    asset_provider = AssetProvider(cmd)
    return asset_provider.show(asset_name=asset_name, resource_group_name=resource_group_name)


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
    asset_provider = AssetProvider(cmd)
    return asset_provider.update(
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        asset_type=asset_type,
        data_points=data_points,
        description=description,
        disabled=disabled,
        documentation_uri=documentation_uri,
        events=events,
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
        tags=tags
    )


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
    asset_provider = AssetProvider(cmd)
    return asset_provider.add_sub_point(
        asset_name=asset_name,
        data_source=data_source,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        resource_group_name=resource_group_name
    )


def list_asset_data_points(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
):
    asset_provider = AssetProvider(cmd)
    return asset_provider.list_sub_points(
        asset_name=asset_name,
        sub_point_type="dataPoints",
        resource_group_name=resource_group_name
    )


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
    asset_provider = AssetProvider(cmd)
    return asset_provider.remove_sub_point(
        asset_name=asset_name,
        data_source=data_source,
        name=name,
        resource_group_name=resource_group_name
    )


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
    asset_provider = AssetProvider(cmd)
    return asset_provider.add_sub_point(
        asset_name=asset_name,
        event_notifier=event_notifier,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        resource_group_name=resource_group_name
    )


def list_asset_events(
    cmd,
    asset_name: str,
    resource_group_name: Optional[str] = None
):
    asset_provider = AssetProvider(cmd)
    return asset_provider.list_sub_points(
        asset_name=asset_name,
        sub_point_type="events",
        resource_group_name=resource_group_name
    )


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
    asset_provider = AssetProvider(cmd)
    return asset_provider.remove_sub_point(
        asset_name=asset_name,
        event_notifier=event_notifier,
        name=name,
        resource_group_name=resource_group_name
    )
