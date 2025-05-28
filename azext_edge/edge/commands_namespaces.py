# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.rpsaas.adr.namespaces import Namespaces
from .providers.rpsaas.adr.namespace_assets import NamespaceAssets

logger = get_logger(__name__)


def create_namespace(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    endpoints: Optional[List[List[str]]] = None,
    location: Optional[str] = None,
    mi_system_identity: Optional[bool] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return Namespaces(cmd).create(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoints=endpoints,
        mi_system_identity=mi_system_identity,
        location=location,
        tags=tags,
        **kwargs
    )


def delete_namespace(
    cmd, namespace_name: str, resource_group_name: str, **kwargs
) -> dict:
    return Namespaces(cmd).delete(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        **kwargs
    )


def list_namespaces(cmd, resource_group_name: str = None) -> List[dict]:
    return Namespaces(cmd).list(resource_group_name=resource_group_name)


def show_namespace(cmd, namespace_name: str, resource_group_name: str) -> dict:
    return Namespaces(cmd).show(namespace_name=namespace_name, resource_group_name=resource_group_name)


def update_namespace(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    mi_system_identity: Optional[bool] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return Namespaces(cmd).update(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        mi_system_identity=mi_system_identity,
        tags=tags,
        **kwargs
    )


def add_namespace_endpoint(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    endpoints: List[List[str]],
    **kwargs
):
    return Namespaces(cmd).add_endpoint(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoints=endpoints,
        **kwargs
    )


def list_namespace_endpoints(
    cmd,
    namespace_name: str,
    resource_group_name: str,
):
    return Namespaces(cmd).list_endpoints(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def remove_namespace_endpoint(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    endpoint_names: List[str],
    **kwargs
):
    return Namespaces(cmd).remove_endpoint(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_names=endpoint_names,
        **kwargs
    )


def create_namespace_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    device_name: str,
    device_endpoint_name: str,
    instance_name: str,
    instance_resource_group: Optional[str] = None,
    instance_subscription: Optional[str] = None,
    location: Optional[str] = None,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    default_dataset_publishing_interval: Optional[int] = None,
    default_dataset_sampling_interval: Optional[int] = None,
    default_dataset_queue_size: Optional[int] = None,
    default_dataset_key_frame_count: Optional[int] = None,
    default_dataset_start_instance: Optional[str] = None,
    default_datasets_custom_configuration: Optional[str] = None,
    default_datasets_destinations: Optional[str] = None,
    default_events_publishing_interval: Optional[int] = None,
    default_events_queue_size: Optional[int] = None,
    default_events_start_instance: Optional[str] = None,
    default_events_filter_type: Optional[str] = None,
    default_events_filter_clauses: Optional[List[str]] = None,
    default_events_custom_configuration: Optional[str] = None,
    default_events_destinations: Optional[str] = None,
    default_mgmtg_custom_configuration: Optional[str] = None,
    default_streams_custom_configuration: Optional[str] = None,
    default_streams_destinations: Optional[str] = None,
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
):
    return NamespaceAssets(cmd).create(
        asset_name=asset_name,
        namespace_name=namespace_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        instance_resource_group=instance_resource_group,
        instance_subscription=instance_subscription,
        location=location,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        default_dataset_publishing_interval=default_dataset_publishing_interval,
        default_dataset_sampling_interval=default_dataset_sampling_interval,
        default_dataset_queue_size=default_dataset_queue_size,
        default_dataset_key_frame_count=default_dataset_key_frame_count,
        default_dataset_start_instance=default_dataset_start_instance,
        default_datasets_custom_configuration=default_datasets_custom_configuration,
        default_datasets_destinations=default_datasets_destinations,
        default_events_publishing_interval=default_events_publishing_interval,
        default_events_queue_size=default_events_queue_size,
        default_events_start_instance=default_events_start_instance,
        default_events_filter_type=default_events_filter_type,
        default_events_filter_clauses=default_events_filter_clauses,
        default_events_custom_configuration=default_events_custom_configuration,
        default_events_destinations=default_events_destinations,
        default_mgmtg_custom_configuration=default_mgmtg_custom_configuration,
        default_streams_custom_configuration=default_streams_custom_configuration,
        default_streams_destinations=default_streams_destinations,
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
        tags=tags,
        **kwargs
    )


def show_namespace_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str
) -> dict:
    return NamespaceAssets(cmd).show(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )


def delete_namespace_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).delete(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        **kwargs
    )


def update_namespace_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    default_dataset_publishing_interval: Optional[int] = None,
    default_dataset_sampling_interval: Optional[int] = None,
    default_dataset_queue_size: Optional[int] = None,
    default_dataset_key_frame_count: Optional[int] = None,
    default_dataset_start_instance: Optional[str] = None,
    default_datasets_custom_configuration: Optional[str] = None,
    default_datasets_destinations: Optional[str] = None,
    default_events_publishing_interval: Optional[int] = None,
    default_events_queue_size: Optional[int] = None,
    default_events_start_instance: Optional[str] = None,
    default_events_filter_type: Optional[str] = None,
    default_events_filter_clauses: Optional[List[str]] = None,
    default_events_custom_configuration: Optional[str] = None,
    default_events_destinations: Optional[str] = None,
    default_mgmtg_custom_configuration: Optional[str] = None,
    default_streams_custom_configuration: Optional[str] = None,
    default_streams_destinations: Optional[str] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
    discovered_asset_refs: Optional[List[str]] = None,
    display_name: Optional[str] = None,
    documentation_uri: Optional[str] = None,
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
    return NamespaceAssets(cmd).update(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        default_dataset_publishing_interval=default_dataset_publishing_interval,
        default_dataset_sampling_interval=default_dataset_sampling_interval,
        default_dataset_queue_size=default_dataset_queue_size,
        default_dataset_key_frame_count=default_dataset_key_frame_count,
        default_dataset_start_instance=default_dataset_start_instance,
        default_datasets_custom_configuration=default_datasets_custom_configuration,
        default_datasets_destinations=default_datasets_destinations,
        default_events_publishing_interval=default_events_publishing_interval,
        default_events_queue_size=default_events_queue_size,
        default_events_start_instance=default_events_start_instance,
        default_events_filter_type=default_events_filter_type,
        default_events_filter_clauses=default_events_filter_clauses,
        default_events_custom_configuration=default_events_custom_configuration,
        default_events_destinations=default_events_destinations,
        default_mgmtg_custom_configuration=default_mgmtg_custom_configuration,
        default_streams_custom_configuration=default_streams_custom_configuration,
        default_streams_destinations=default_streams_destinations,
        description=description,
        disabled=disabled,
        discovered_asset_refs=discovered_asset_refs,
        display_name=display_name,
        documentation_uri=documentation_uri,
        hardware_revision=hardware_revision,
        manufacturer=manufacturer,
        manufacturer_uri=manufacturer_uri,
        model=model,
        product_code=product_code,
        serial_number=serial_number,
        software_revision=software_revision,
        tags=tags,
        **kwargs
    )


def query_namespace_assets(
    cmd,
    asset_name: Optional[str] = None,
    custom_query: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    device_name: Optional[str] = None,
    device_endpoint_name: Optional[str] = None,
) -> dict:
    return NamespaceAssets(cmd).query_assets(
        asset_name=asset_name,
        custom_query=custom_query,
        resource_group_name=resource_group_name,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name
    )
