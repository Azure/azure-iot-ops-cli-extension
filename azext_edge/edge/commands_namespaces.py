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
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return Namespaces(cmd).create(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return Namespaces(cmd).update(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        tags=tags,
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


# later, might want to add in update
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
) -> dict:
    return NamespaceDevices(cmd).inbound_remove_endpoint(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        endpoint_names=endpoint_names,
        confirm_yes=confirm_yes,
        **kwargs
    )


# NAMESPACE ASSET COMMANDS
def create_namespace_custom_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    device_name: str,
    device_endpoint_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    datasets_custom_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    events_custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    mgmt_custom_configuration: Optional[str] = None,
    streams_custom_configuration: Optional[str] = None,
    stream_destinations: Optional[str] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).create(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type="custom",
        resource_group_name=resource_group_name,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        datasets_custom_configuration=datasets_custom_configuration,
        dataset_destinations=dataset_destinations,
        events_custom_configuration=events_custom_configuration,
        event_destinations=event_destinations,
        mgmt_custom_configuration=mgmt_custom_configuration,
        streams_custom_configuration=streams_custom_configuration,
        stream_destinations=stream_destinations,
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
        tags=tags,
        **kwargs
    )


def create_namespace_media_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    device_name: str,
    device_endpoint_name: str,
    task_type: Optional[str] = None,
    task_format: Optional[str] = None,
    snapshots_per_second: Optional[int] = None,
    path: Optional[str] = None,
    duration: Optional[int] = None,
    media_server_address: Optional[str] = None,
    media_server_path: Optional[str] = None,
    media_server_port: Optional[int] = None,
    media_server_username: Optional[str] = None,
    media_server_password: Optional[str] = None,
    media_server_certificate: Optional[str] = None,
    stream_destinations: Optional[str] = None,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).create(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type=DeviceEndpointType.MEDIA.value,
        resource_group_name=resource_group_name,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        task_type=task_type,
        task_format=task_format,
        snapshots_per_second=snapshots_per_second,
        path=path,
        duration=duration,
        media_server_address=media_server_address,
        media_server_path=media_server_path,
        media_server_port=media_server_port,
        media_server_username=media_server_username,
        media_server_password=media_server_password,
        media_server_certificate=media_server_certificate,
        stream_destinations=stream_destinations,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
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
        tags=tags,
        **kwargs
    )


def create_namespace_onvif_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    device_name: str,
    device_endpoint_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).create(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        resource_group_name=resource_group_name,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
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
        tags=tags,
        **kwargs
    )


def create_namespace_opcua_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    device_name: str,
    device_endpoint_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    dataset_publishing_interval: Optional[int] = None,
    dataset_sampling_interval: Optional[int] = None,
    dataset_queue_size: Optional[int] = None,
    dataset_key_frame_count: Optional[int] = None,
    dataset_start_instance: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    events_publishing_interval: Optional[int] = None,
    events_queue_size: Optional[int] = None,
    events_start_instance: Optional[str] = None,
    events_filter_type: Optional[str] = None,
    events_filter_clauses: Optional[List[List[str]]] = None,
    event_destinations: Optional[str] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    # waiting on service for mgmt schemas
    return NamespaceAssets(cmd).create(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        resource_group_name=resource_group_name,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        opcua_dataset_publishing_interval=dataset_publishing_interval,
        opcua_dataset_sampling_interval=dataset_sampling_interval,
        opcua_dataset_queue_size=dataset_queue_size,
        opcua_dataset_key_frame_count=dataset_key_frame_count,
        opcua_dataset_start_instance=dataset_start_instance,
        dataset_destinations=dataset_destinations,
        opcua_event_publishing_interval=events_publishing_interval,
        opcua_event_queue_size=events_queue_size,
        opcua_event_start_instance=events_start_instance,
        opcua_event_filter_type=events_filter_type,
        opcua_event_filter_clauses=events_filter_clauses,
        event_destinations=event_destinations,
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
    confirm_yes: bool = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).delete(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs
    )


def update_namespace_custom_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    datasets_custom_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    events_custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    mgmt_custom_configuration: Optional[str] = None,
    streams_custom_configuration: Optional[str] = None,
    stream_destinations: Optional[str] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type="custom",
        resource_group_name=resource_group_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        datasets_custom_configuration=datasets_custom_configuration,
        dataset_destinations=dataset_destinations,
        events_custom_configuration=events_custom_configuration,
        event_destinations=event_destinations,
        mgmt_custom_configuration=mgmt_custom_configuration,
        streams_custom_configuration=streams_custom_configuration,
        stream_destinations=stream_destinations,
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
        tags=tags,
        **kwargs
    )


def update_namespace_media_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    task_type: Optional[str] = None,
    task_format: Optional[str] = None,
    snapshots_per_second: Optional[int] = None,
    path: Optional[str] = None,
    duration: Optional[int] = None,
    media_server_address: Optional[str] = None,
    media_server_path: Optional[str] = None,
    media_server_port: Optional[int] = None,
    media_server_username: Optional[str] = None,
    media_server_password: Optional[str] = None,
    media_server_certificate: Optional[str] = None,
    stream_destinations: Optional[str] = None,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type=DeviceEndpointType.MEDIA.value,
        resource_group_name=resource_group_name,
        task_type=task_type,
        task_format=task_format,
        snapshots_per_second=snapshots_per_second,
        path=path,
        duration=duration,
        media_server_address=media_server_address,
        media_server_path=media_server_path,
        media_server_port=media_server_port,
        media_server_username=media_server_username,
        media_server_password=media_server_password,
        media_server_certificate=media_server_certificate,
        stream_destinations=stream_destinations,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
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
        tags=tags,
        **kwargs
    )


def update_namespace_onvif_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        resource_group_name=resource_group_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
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
        tags=tags,
        **kwargs
    )


def update_namespace_opcua_asset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    dataset_publishing_interval: Optional[int] = None,
    dataset_sampling_interval: Optional[int] = None,
    dataset_queue_size: Optional[int] = None,
    dataset_key_frame_count: Optional[int] = None,
    dataset_start_instance: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    events_publishing_interval: Optional[int] = None,
    events_queue_size: Optional[int] = None,
    events_start_instance: Optional[str] = None,
    events_filter_type: Optional[str] = None,
    events_filter_clauses: Optional[List[List[str]]] = None,
    event_destinations: Optional[str] = None,
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
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    # waiting on service for mgmt schemas
    return NamespaceAssets(cmd).update(
        asset_name=asset_name,
        namespace_name=namespace_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        resource_group_name=resource_group_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        opcua_dataset_publishing_interval=dataset_publishing_interval,
        opcua_dataset_sampling_interval=dataset_sampling_interval,
        opcua_dataset_queue_size=dataset_queue_size,
        opcua_dataset_key_frame_count=dataset_key_frame_count,
        opcua_dataset_start_instance=dataset_start_instance,
        dataset_destinations=dataset_destinations,
        opcua_event_publishing_interval=events_publishing_interval,
        opcua_event_queue_size=events_queue_size,
        opcua_event_start_instance=events_start_instance,
        opcua_event_filter_type=events_filter_type,
        opcua_event_filter_clauses=events_filter_clauses,
        event_destinations=event_destinations,
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


# ASSET DATASET COMMANDS
def add_namespace_custom_asset_dataset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    dataset_data_source: str,
    dataset_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        asset_type="custom",
        dataset_data_source=dataset_data_source,
        datasets_custom_configuration=dataset_configuration,
        dataset_destinations=dataset_destinations,
        replace=replace,
        **kwargs
    )


def add_namespace_opcua_asset_dataset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    dataset_data_source: str,
    dataset_destinations: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        dataset_data_source=dataset_data_source,
        dataset_destinations=dataset_destinations,
        opcua_dataset_publishing_interval=opcua_dataset_publishing_interval,
        opcua_dataset_sampling_interval=opcua_dataset_sampling_interval,
        opcua_dataset_queue_size=opcua_dataset_queue_size,
        opcua_dataset_key_frame_count=opcua_dataset_key_frame_count,
        opcua_dataset_start_instance=opcua_dataset_start_instance,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_datasets(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_datasets(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )


def show_namespace_asset_dataset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str
) -> dict:
    return NamespaceAssets(cmd).show_dataset(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name
    )


def update_namespace_custom_asset_dataset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    dataset_data_source: Optional[str] = None,
    dataset_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_dataset(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        asset_type="custom",
        dataset_data_source=dataset_data_source,
        datasets_custom_configuration=dataset_configuration,
        dataset_destinations=dataset_destinations,
        **kwargs
    )


def update_namespace_opcua_asset_dataset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    dataset_data_source: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_dataset(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        dataset_data_source=dataset_data_source,
        dataset_destinations=dataset_destinations,
        opcua_dataset_publishing_interval=opcua_dataset_publishing_interval,
        opcua_dataset_sampling_interval=opcua_dataset_sampling_interval,
        opcua_dataset_queue_size=opcua_dataset_queue_size,
        opcua_dataset_key_frame_count=opcua_dataset_key_frame_count,
        opcua_dataset_start_instance=opcua_dataset_start_instance,
        **kwargs
    )


def remove_namespace_asset_dataset(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_dataset(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        **kwargs
    )


# ASSET DATASET DATAPOINT COMMANDS
def add_namespace_custom_asset_dataset_point(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    datapoint_name: str,
    data_source: str,
    custom_configuration: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset_datapoint(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        asset_type="custom",
        datapoint_name=datapoint_name,
        data_source=data_source,
        custom_configuration=custom_configuration,
        replace=replace,
        **kwargs
    )


def add_namespace_opcua_asset_dataset_point(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    datapoint_name: str,
    data_source: str,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset_datapoint(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        datapoint_name=datapoint_name,
        data_source=data_source,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_dataset_points(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_dataset_datapoints(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name
    )


def remove_namespace_asset_dataset_point(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    dataset_name: str,
    datapoint_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_dataset_datapoint(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        datapoint_name=datapoint_name,
        **kwargs
    )


# ASSET EVENT COMMANDS
def add_namespace_custom_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    event_notifier: str,
    event_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type="custom",
        event_notifier=event_notifier,
        events_custom_configuration=event_configuration,
        event_destinations=event_destinations,
        replace=replace,
        **kwargs
    )


# TODO: needs schema confirmation
def add_namespace_opcua_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    event_notifier: str,
    event_destinations: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_filter_type: Optional[str] = None,
    opcua_event_filter_clauses: Optional[List[List[str]]] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        event_notifier=event_notifier,
        event_destinations=event_destinations,
        opcua_event_publishing_interval=opcua_event_publishing_interval,
        opcua_event_queue_size=opcua_event_queue_size,
        opcua_event_filter_type=opcua_event_filter_type,
        opcua_event_filter_clauses=opcua_event_filter_clauses,
        replace=replace,
        **kwargs
    )


def add_namespace_onvif_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    event_notifier: str,
    event_destinations: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        event_notifier=event_notifier,
        event_destinations=event_destinations,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_events(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_events(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )


def show_namespace_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str
) -> dict:
    return NamespaceAssets(cmd).show_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name
    )


def update_namespace_custom_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    event_notifier: Optional[str] = None,
    event_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type="custom",
        event_notifier=event_notifier,
        events_custom_configuration=event_configuration,
        event_destinations=event_destinations,
        **kwargs
    )


def update_namespace_opcua_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    event_notifier: Optional[str] = None,
    event_destinations: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_filter_type: Optional[str] = None,
    opcua_event_filter_clauses: Optional[List[List[str]]] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        event_notifier=event_notifier,
        event_destinations=event_destinations,
        opcua_event_publishing_interval=opcua_event_publishing_interval,
        opcua_event_queue_size=opcua_event_queue_size,
        opcua_event_filter_type=opcua_event_filter_type,
        opcua_event_filter_clauses=opcua_event_filter_clauses,
        **kwargs
    )


def update_namespace_onvif_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    event_notifier: Optional[str] = None,
    event_destinations: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        event_notifier=event_notifier,
        event_destinations=event_destinations,
        **kwargs
    )


def remove_namespace_asset_event(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_event(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        **kwargs
    )


# ASSET EVENT DATAPOINT COMMANDS
def add_namespace_custom_asset_event_point(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    datapoint_name: str,
    data_source: str,
    custom_configuration: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_datapoint(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type="custom",
        datapoint_name=datapoint_name,
        data_source=data_source,
        custom_configuration=custom_configuration,
        replace=replace,
        **kwargs
    )


# note: not exposed for now but this will be supported in the near future
def add_namespace_opcua_asset_event_point(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    datapoint_name: str,
    data_source: str,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_datapoint(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        datapoint_name=datapoint_name,
        data_source=data_source,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_event_points(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_event_datapoints(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name
    )


def remove_namespace_asset_event_point(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    event_name: str,
    datapoint_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_event_datapoint(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        datapoint_name=datapoint_name,
        **kwargs
    )
