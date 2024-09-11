# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.rpsaas.adr2.assets import Assets

logger = get_logger(__name__)


def create_asset(
    cmd,
    asset_name: str,
    endpoint_profile: str,
    instance_name: str,
    resource_group_name: str,
    custom_attributes: Optional[List[str]] = None,
    description: Optional[str] = None,
    default_topic_path: Optional[str] = None,
    default_topic_retain: Optional[str] = None,
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
):
    return Assets(cmd).create(
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        endpoint_profile=endpoint_profile,
        custom_attributes=custom_attributes,
        description=description,
        default_topic_path=default_topic_path,
        default_topic_retain=default_topic_retain,
        disabled=disabled,
        display_name=display_name,
        documentation_uri=documentation_uri,
        events_file_path=events_file_path,
        events=events,
        external_asset_id=external_asset_id,
        hardware_revision=hardware_revision,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        instance_subscription=instance_subscription,
        location=location,
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
        tags=tags
    )


def delete_asset(
    cmd,
    asset_name: str,
    resource_group_name: str,
) -> dict:
    return Assets(cmd).delete(asset_name=asset_name, resource_group_name=resource_group_name)


# TODO: add in once GA
def list_assets(
    cmd,
    # discovered: bool = False,  # TODO: discovered
    resource_group_name: str = None,
) -> List[dict]:
    return Assets(cmd).list(discovered=False, resource_group_name=resource_group_name)


def query_assets(
    cmd,
    asset_name: Optional[str] = None,
    custom_query: Optional[str] = None,
    default_topic_path: Optional[str] = None,
    default_topic_retain: Optional[str] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
    # discovered: Optional[bool] = None,  # TODO: discovered
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
) -> dict:
    return Assets(cmd).query_assets(
        asset_name=asset_name,
        custom_query=custom_query,
        default_topic_path=default_topic_path,
        default_topic_retain=default_topic_retain,
        description=description,
        display_name=display_name,
        discovered=False,
        disabled=disabled,
        documentation_uri=documentation_uri,
        endpoint_profile=endpoint_profile,
        external_asset_id=external_asset_id,
        hardware_revision=hardware_revision,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
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
    return Assets(cmd).show(asset_name=asset_name, resource_group_name=resource_group_name)


def update_asset(
    cmd,
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
    return Assets(cmd).update(
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        custom_attributes=custom_attributes,
        default_topic_path=default_topic_path,
        default_topic_retain=default_topic_retain,
        description=description,
        disabled=disabled,
        display_name=display_name,
        documentation_uri=documentation_uri,
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
        tags=tags
    )


# Dataset commands
# TODO: multi dataset support
# def add_asset_dataset(
#     cmd,
#     asset_name: str,
#     dataset_name: str,
#     resource_group_name: str,
#     data_points: Optional[List[str]] = None,
#     data_point_file_path: Optional[str] = None,
#     queue_size: Optional[int] = None,
#     sampling_interval: Optional[int] = None,
#     publishing_interval: Optional[int] = None,
#     topic_path: Optional[str] = None,
#     topic_retain: Optional[str] = None
# ):
#     return Assets(cmd).add_dataset(
#         asset_name=asset_name,
#         dataset_name=dataset_name,
#         resource_group_name=resource_group_name,
#         data_points=data_points,
#         data_point_file_path=data_point_file_path,
#         queue_size=queue_size,
#         sampling_interval=sampling_interval,
#         publishing_interval=publishing_interval,
#         topic_path=topic_path,
#         topic_retain=topic_retain,
#     )


# def export_asset_datasets(
#     cmd,
#     asset_name: str,
#     resource_group_name: str,
#     extension: str = "json",
#     output_dir: str = ".",
#     replace: bool = False
# ):
#     return Assets(cmd).export_datasets(
#         asset_name=asset_name,
#         resource_group_name=resource_group_name,
#         extension=extension,
#         output_dir=output_dir,
#         replace=replace
#     )


# def import_asset_datasets(
#     cmd,
#     asset_name: str,
#     file_path: str,
#     resource_group_name: str,
#     replace: bool = False
# ):
#     return Assets(cmd).import_datasets(
#         asset_name=asset_name,
#         file_path=file_path,
#         resource_group_name=resource_group_name,
#         replace=replace
#     )


def list_asset_datasets(
    cmd,
    asset_name: str,
    resource_group_name: str
):
    return Assets(cmd).list_datasets(
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )


def show_asset_dataset(
    cmd,
    asset_name: str,
    dataset_name: str,
    resource_group_name: str
):
    return Assets(cmd).show_dataset(
        asset_name=asset_name,
        dataset_name=dataset_name,
        resource_group_name=resource_group_name
    )


# def remove_asset_dataset(
#     cmd,
#     asset_name: str,
#     dataset_name: str,
#     resource_group_name: str
# ):
#     return Assets(cmd).remove_dataset(
#         asset_name=asset_name,
#         dataset_name=dataset_name,
#         resource_group_name=resource_group_name
#     )


# Data Point sub commands
def add_asset_data_point(
    cmd,
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
    return Assets(cmd).add_dataset_data_point(
        asset_name=asset_name,
        dataset_name=dataset_name,
        data_point_name=data_point_name,
        data_source=data_source,
        observability_mode=observability_mode,
        publishing_interval=publishing_interval,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        resource_group_name=resource_group_name,
    )


def export_asset_data_points(
    cmd,
    asset_name: str,
    dataset_name: str,
    resource_group_name: str,
    extension: str = "json",
    output_dir: Optional[str] = None,
    replace: bool = False,
):
    return Assets(cmd).export_dataset_data_points(
        asset_name=asset_name,
        dataset_name=dataset_name,
        extension=extension,
        output_dir=output_dir,
        replace=replace,
        resource_group_name=resource_group_name
    )


def import_asset_data_points(
    cmd,
    asset_name: str,
    dataset_name: str,
    file_path: str,
    resource_group_name: str,
    replace: bool = False,
):
    return Assets(cmd).import_dataset_data_points(
        asset_name=asset_name,
        dataset_name=dataset_name,
        file_path=file_path,
        replace=replace,
        resource_group_name=resource_group_name
    )


def list_asset_data_points(
    cmd,
    asset_name: str,
    dataset_name: str,
    resource_group_name: str,
):
    return Assets(cmd).list_dataset_data_points(
        asset_name=asset_name,
        dataset_name=dataset_name,
        resource_group_name=resource_group_name
    )


def remove_asset_data_point(
    cmd,
    asset_name: str,
    dataset_name: str,
    data_point_name: str,
    resource_group_name: str,
):
    return Assets(cmd).remove_dataset_data_point(
        asset_name=asset_name,
        dataset_name=dataset_name,
        data_point_name=data_point_name,
        resource_group_name=resource_group_name
    )


# Event sub commands
def add_asset_event(
    cmd,
    asset_name: str,
    event_notifier: str,
    resource_group_name: str,
    event_name: Optional[str] = None,
    observability_mode: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,  # Note: not in DOE
    publishing_interval: Optional[int] = None,  # Note not in DOE
    # topic_path: Optional[str] = None,  # TODO: expose once supported
    # topic_retain: Optional[str] = None
):
    return Assets(cmd).add_event(
        asset_name=asset_name,
        event_notifier=event_notifier,
        event_name=event_name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        publishing_interval=publishing_interval,
        resource_group_name=resource_group_name,
        # topic_path=topic_path,
        # topic_retain=topic_retain
    )


def export_asset_events(
    cmd,
    asset_name: str,
    resource_group_name: str,
    extension: str = "json",
    output_dir: Optional[str] = None,
    replace: bool = False,
):
    return Assets(cmd).export_events(
        asset_name=asset_name,
        extension=extension,
        output_dir=output_dir,
        replace=replace,
        resource_group_name=resource_group_name
    )


def import_asset_events(
    cmd,
    asset_name: str,
    file_path: str,
    resource_group_name: str,
    replace: bool = False,
):
    return Assets(cmd).import_events(
        asset_name=asset_name,
        file_path=file_path,
        replace=replace,
        resource_group_name=resource_group_name
    )


def list_asset_events(
    cmd,
    asset_name: str,
    resource_group_name: str,
):
    return Assets(cmd).list_events(
        asset_name=asset_name, resource_group_name=resource_group_name
    )


def remove_asset_event(
    cmd,
    asset_name: str,
    event_name: str,
    resource_group_name: str,
):
    return Assets(cmd).remove_event(
        asset_name=asset_name,
        event_name=event_name,
        resource_group_name=resource_group_name
    )
