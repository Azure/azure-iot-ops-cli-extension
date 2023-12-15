# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from azure.cli.core.azclierror import RequiredArgumentMissingError

from .providers.rpsaas.adr.assets import AssetProvider

logger = get_logger(__name__)


def create_asset(
    cmd,
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
    asset_provider = AssetProvider(cmd)
    return asset_provider.create(
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        endpoint=endpoint,
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
        display_name=display_name,
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
    resource_group_name: str,
) -> dict:
    asset_provider = AssetProvider(cmd)
    return asset_provider.delete(
        resource_name=asset_name,
        resource_group_name=resource_group_name,
        check_cluster_connectivity=True
    )


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
    disabled: Optional[bool] = None,
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
    asset_provider = AssetProvider(cmd)
    return asset_provider.query(
        asset_type=asset_type,
        custom_location_name=custom_location_name,
        description=description,
        display_name=display_name,
        disabled=disabled,
        documentation_uri=documentation_uri,
        endpoint=endpoint,
        external_asset_id=external_asset_id,
        hardware_revision=hardware_revision,
        location=location,
        manufacturer=manufacturer,
        manufacturer_uri=manufacturer_uri,
        model=model,
        product_code=product_code,
        serial_number=serial_number,
        software_revision=software_revision,
        resource_group_name=resource_group_name
    )


def show_asset(
    cmd,
    asset_name: str,
    resource_group_name: str,
) -> dict:
    asset_provider = AssetProvider(cmd)
    return asset_provider.show(resource_name=asset_name, resource_group_name=resource_group_name)


def update_asset(
    cmd,
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
    asset_provider = AssetProvider(cmd)
    return asset_provider.update(
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        asset_type=asset_type,
        description=description,
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
        dp_publishing_interval=dp_publishing_interval,
        dp_sampling_interval=dp_sampling_interval,
        dp_queue_size=dp_queue_size,
        ev_publishing_interval=ev_publishing_interval,
        ev_sampling_interval=ev_sampling_interval,
        ev_queue_size=ev_queue_size,
        tags=tags
    )


# Data Point sub commands
def add_asset_data_point(
    cmd,
    asset_name: str,
    data_source: str,
    resource_group_name: str,
    capability_id: Optional[str] = None,
    name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
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
    resource_group_name: str,
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
    resource_group_name: str,
    data_source: Optional[str] = None,
    name: Optional[str] = None,
):
    if not any([data_source, name]):
        raise RequiredArgumentMissingError(
            "Provide either the data source via --data-source or name via --data-point-name to identify "
            "the data point to remove."
        )
    asset_provider = AssetProvider(cmd)
    return asset_provider.remove_sub_point(
        asset_name=asset_name,
        data_source=data_source,
        name=name,
        sub_point_type="dataPoints",
        resource_group_name=resource_group_name
    )


# Event sub commands
def add_asset_event(
    cmd,
    asset_name: str,
    event_notifier: str,
    resource_group_name: str,
    capability_id: Optional[str] = None,
    name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
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
    resource_group_name: str,
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
    resource_group_name: str,
    event_notifier: Optional[str] = None,
    name: Optional[str] = None,
):
    if not any([event_notifier, name]):
        raise RequiredArgumentMissingError(
            "Provide either the event notifier via --event-notifier or name via --event-name to identify "
            "the event to remove."
        )
    asset_provider = AssetProvider(cmd)
    return asset_provider.remove_sub_point(
        asset_name=asset_name,
        event_notifier=event_notifier,
        name=name,
        sub_point_type="events",
        resource_group_name=resource_group_name
    )
