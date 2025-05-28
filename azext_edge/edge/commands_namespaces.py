# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.rpsaas.adr.namespaces import Namespaces
from .providers.rpsaas.adr.namespace_assets import NamespaceAssets
from .providers.rpsaas.adr.namespace_devices import NamespaceDevices, DeviceEndpointType

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
    cmd, namespace_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None, **kwargs
):
    Namespaces(cmd).delete(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
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


# DEVICE COMMANDS
def create_namespace_device(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    instance_name: str,
    device_template_id: str,
    custom_attributes: Optional[List[str]] = None,
    device_group_id: Optional[str] = None,
    disabled: Optional[bool] = None,
    instance_resource_group: Optional[str] = None,
    instance_subscription: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    operating_system: Optional[str] = None,
    operating_system_version: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return NamespaceDevices(cmd).create(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        device_group_id=device_group_id,
        device_template_id=device_template_id,
        custom_attributes=custom_attributes,
        disabled=disabled,
        instance_resource_group=instance_resource_group,
        instance_subscription=instance_subscription,
        manufacturer=manufacturer,
        model=model,
        operating_system=operating_system,
        operating_system_version=operating_system_version,
        tags=tags,
        **kwargs
    )


def list_namespace_devices(
    cmd,
    namespace_name: str,
    resource_group_name: str
) -> List[dict]:
    return NamespaceDevices(cmd).list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )


def delete_namespace_device(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = False,
    **kwargs
):
    NamespaceDevices(cmd).delete(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs
    )


def show_namespace_device(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str
) -> dict:
    return NamespaceDevices(cmd).show(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )


def update_namespace_device(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    custom_attributes: Optional[List[str]] = None,
    device_group_id: Optional[str] = None,
    disabled: Optional[bool] = None,
    operating_system_version: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return NamespaceDevices(cmd).update(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        custom_attributes=custom_attributes,
        device_group_id=device_group_id,
        disabled=disabled,
        operating_system_version=operating_system_version,
        tags=tags,
        **kwargs
    )


def list_namespace_device_endpoints(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    inbound: Optional[bool] = False
) -> dict:
    return NamespaceDevices(cmd).list_endpoints(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        inbound=inbound
    )


def add_inbound_custom_device_endpoint(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    endpoint_name: str,
    endpoint_type: str,
    endpoint_address: str,
    additional_configuration: Optional[str] = None,
    certificate_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    trust_list: Optional[str] = None,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_type=endpoint_type,
        endpoint_address=endpoint_address,
        additional_configuration=additional_configuration,
        certificate_reference=certificate_reference,
        password_reference=password_reference,
        username_reference=username_reference,
        trust_list=trust_list,
        **kwargs
    )


def add_inbound_media_device_endpoint(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    endpoint_name: str,
    endpoint_address: str,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.MEDIA.value,
        endpoint_address=endpoint_address,
        password_reference=password_reference,
        username_reference=username_reference,
        **kwargs
    )


def add_inbound_onvif_device_endpoint(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    endpoint_name: str,
    endpoint_address: str,
    accept_invalid_hostnames: Optional[bool] = False,
    accept_invalid_certificates: Optional[bool] = False,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.ONVIF.value,
        endpoint_address=endpoint_address,
        password_reference=password_reference,
        username_reference=username_reference,
        accept_invalid_hostnames=accept_invalid_hostnames,
        accept_invalid_certificates=accept_invalid_certificates,
        **kwargs
    )


def add_inbound_opcua_device_endpoint(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    endpoint_name: str,
    endpoint_address: str,
    application_name: Optional[str] = "OPC UA Broker",
    keep_alive: Optional[int] = 10000,
    publishing_interval: Optional[int] = 1000,
    sampling_interval: Optional[int] = 1000,
    queue_size: Optional[int] = 1,
    key_frame_count: Optional[int] = 0,
    session_timeout: Optional[int] = 60000,
    session_keep_alive_interval: Optional[int] = 10000,
    session_reconnect_period: Optional[int] = 2000,
    session_reconnect_exponential_backoff: Optional[int] = 10000,
    session_enable_tracing_headers: Optional[bool] = False,
    subscription_max_items: Optional[int] = 1000,
    subscription_life_time: Optional[int] = 60000,
    security_auto_accept_certificates: Optional[bool] = False,
    security_policy: Optional[str] = None,
    security_mode: Optional[str] = None,
    run_asset_discovery: Optional[bool] = False,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.OPCUA.value,
        endpoint_address=endpoint_address,
        password_reference=password_reference,
        username_reference=username_reference,
        application_name=application_name,
        keep_alive=keep_alive,
        publishing_interval=publishing_interval,
        sampling_interval=sampling_interval,
        queue_size=queue_size,
        key_frame_count=key_frame_count,
        session_timeout=session_timeout,
        session_keep_alive_interval=session_keep_alive_interval,
        session_reconnect_period=session_reconnect_period,
        session_reconnect_exponential_backoff=session_reconnect_exponential_backoff,
        session_enable_tracing_headers=session_enable_tracing_headers,
        subscription_max_items=subscription_max_items,
        subscription_life_time=subscription_life_time,
        security_auto_accept_certificates=security_auto_accept_certificates,
        security_policy=security_policy,
        security_mode=security_mode,
        run_asset_discovery=run_asset_discovery,
        **kwargs
    )


def list_inbound_device_endpoints(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str
) -> dict:
    return NamespaceDevices(cmd).list_endpoints(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        inbound=True
    )


def remove_inbound_device_endpoints(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    endpoint_names: List[str],
    confirm_yes: Optional[bool] = False,
    **kwargs
):
    return NamespaceDevices(cmd).inbound_remove_endpoint(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_names=endpoint_names,
        confirm_yes=confirm_yes,
        **kwargs
    )


# NAMESPACE ASSET COMMANDS
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
