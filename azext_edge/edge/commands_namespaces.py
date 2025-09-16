# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.adr.namespaces import Namespaces
from .providers.adr.namespace_assets import NamespaceAssets
from .providers.adr.namespace_devices import NamespaceDevices, DeviceEndpointType

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
    instance_name: str,
    instance_resource_group: str,
    custom_attributes: Optional[List[str]] = None,
    disabled: Optional[bool] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    operating_system: Optional[str] = None,
    operating_system_version: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return NamespaceDevices(cmd).create(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        custom_attributes=custom_attributes,
        disabled=disabled,
        manufacturer=manufacturer,
        model=model,
        operating_system=operating_system,
        operating_system_version=operating_system_version,
        tags=tags,
        **kwargs
    )


def query_namespace_devices(
    cmd,
    device_name: Optional[str] = None,
    instance_name: Optional[str] = None,
    instance_resource_group: Optional[str] = None,
    custom_query: Optional[str] = None,
    disabled: Optional[bool] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    operating_system: Optional[str] = None,
    operating_system_version: Optional[str] = None,
) -> dict:
    return NamespaceDevices(cmd).query_devices(
        device_name=device_name,
        disabled=disabled,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        custom_query=custom_query,
        manufacturer=manufacturer,
        model=model,
        operating_system=operating_system,
        operating_system_version=operating_system_version,
    )


def delete_namespace_device(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    confirm_yes: Optional[bool] = False,
    **kwargs
):
    NamespaceDevices(cmd).delete(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        confirm_yes=confirm_yes,
        **kwargs
    )


def show_namespace_device(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
) -> dict:
    return NamespaceDevices(cmd).show(
        device_name=device_name,
        instance_name=instance_name,
        resource_group=instance_resource_group
    )


def update_namespace_device(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    custom_attributes: Optional[List[str]] = None,
    disabled: Optional[bool] = None,
    operating_system_version: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
):
    return NamespaceDevices(cmd).update(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        custom_attributes=custom_attributes,
        disabled=disabled,
        operating_system_version=operating_system_version,
        tags=tags,
        **kwargs
    )


def list_namespace_device_endpoints(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    inbound: Optional[bool] = False
) -> dict:
    return NamespaceDevices(cmd).list_endpoints(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        inbound=inbound
    )


# later, might want to add in update
def add_inbound_custom_device_endpoint(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    endpoint_name: str,
    endpoint_type: str,
    endpoint_address: str,
    endpoint_version: Optional[str] = None,
    additional_configuration: Optional[str] = None,
    certificate_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    trust_list: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_type=endpoint_type,
        endpoint_address=endpoint_address,
        endpoint_version=endpoint_version,
        additional_configuration=additional_configuration,
        certificate_reference=certificate_reference,
        password_reference=password_reference,
        username_reference=username_reference,
        trust_list=trust_list,
        replace=replace,
        **kwargs
    )


def add_inbound_media_device_endpoint(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    endpoint_name: str,
    endpoint_address: str,
    endpoint_version: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.MEDIA.value,
        endpoint_address=endpoint_address,
        endpoint_version=endpoint_version,
        password_reference=password_reference,
        username_reference=username_reference,
        replace=replace,
        **kwargs
    )


def add_inbound_onvif_device_endpoint(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    endpoint_name: str,
    endpoint_address: str,
    endpoint_version: Optional[str] = None,
    accept_invalid_hostnames: Optional[bool] = False,
    accept_invalid_certificates: Optional[bool] = False,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.ONVIF.value,
        endpoint_address=endpoint_address,
        endpoint_version=endpoint_version,
        password_reference=password_reference,
        username_reference=username_reference,
        accept_invalid_hostnames=accept_invalid_hostnames,
        accept_invalid_certificates=accept_invalid_certificates,
        replace=replace,
        **kwargs
    )


def add_inbound_opcua_device_endpoint(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    endpoint_name: str,
    endpoint_address: str,
    endpoint_version: Optional[str] = None,
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
    replace: Optional[bool] = False,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.OPCUA.value,
        endpoint_address=endpoint_address,
        endpoint_version=endpoint_version,
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
        replace=replace,
        **kwargs
    )


def add_inbound_rest_device_endpoint(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    endpoint_name: str,
    endpoint_address: str,
    endpoint_version: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
):
    return NamespaceDevices(cmd).add_inbound_endpoint(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_name=endpoint_name,
        endpoint_type=DeviceEndpointType.REST.value,
        endpoint_address=endpoint_address,
        endpoint_version=endpoint_version,
        password_reference=password_reference,
        username_reference=username_reference,
        replace=replace,
        **kwargs
    )


def list_inbound_device_endpoints(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    inbound_endpoint_type: Optional[str] = None,
) -> dict:
    return NamespaceDevices(cmd).list_endpoints(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        inbound=True,
        inbound_endpoint_type=inbound_endpoint_type
    )


def remove_inbound_device_endpoints(
    cmd,
    device_name: str,
    instance_name: str,
    instance_resource_group: str,
    endpoint_names: List[str],
    confirm_yes: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceDevices(cmd).inbound_remove_endpoint(
        device_name=device_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        endpoint_names=endpoint_names,
        confirm_yes=confirm_yes,
        **kwargs
    )


# NAMESPACE ASSET COMMANDS
def create_namespace_custom_asset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    device_name: str,
    device_endpoint_name: str,
    # default configs + destinations
    dataset_custom_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    event_custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    mgmt_custom_configuration: Optional[str] = None,
    stream_custom_configuration: Optional[str] = None,
    stream_destinations: Optional[str] = None,
    asset_type_refs: Optional[List[str]] = None,
    # other params
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type="custom",
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        dataset_custom_configuration=dataset_custom_configuration,
        dataset_destinations=dataset_destinations,
        event_custom_configuration=event_custom_configuration,
        event_destinations=event_destinations,
        mgmt_custom_configuration=mgmt_custom_configuration,
        stream_custom_configuration=stream_custom_configuration,
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
    instance_name: str,
    instance_resource_group: str,
    device_name: str,
    device_endpoint_name: str,
    # default stream config
    task_type: Optional[str] = None,
    disable_autostart: Optional[bool] = None,
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
    # other params
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.MEDIA.value,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        task_type=task_type,
        disable_autostart=disable_autostart,
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
    instance_name: str,
    instance_resource_group: str,
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.ONVIF.value,
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
    instance_name: str,
    instance_resource_group: str,
    device_name: str,
    device_endpoint_name: str,
    # default configs + destinations
    dataset_publishing_interval: Optional[int] = None,
    dataset_sampling_interval: Optional[int] = None,
    dataset_queue_size: Optional[int] = None,
    dataset_key_frame_count: Optional[int] = None,
    dataset_destinations: Optional[str] = None,
    events_publishing_interval: Optional[int] = None,
    events_queue_size: Optional[int] = None,
    event_destinations: Optional[str] = None,
    # other params
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
    # waiting on service for mgmt schemas
    return NamespaceAssets(cmd).create(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.OPCUA.value,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        opcua_dataset_publishing_interval=dataset_publishing_interval,
        opcua_dataset_sampling_interval=dataset_sampling_interval,
        opcua_dataset_queue_size=dataset_queue_size,
        opcua_dataset_key_frame_count=dataset_key_frame_count,
        dataset_destinations=dataset_destinations,
        opcua_event_publishing_interval=events_publishing_interval,
        opcua_event_queue_size=events_queue_size,
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


def create_namespace_rest_asset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    device_name: str,
    device_endpoint_name: str,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    rest_dataset_sampling_interval: Optional[int] = None,
    dataset_destinations: Optional[str] = None,
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.REST.value,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        rest_dataset_sampling_interval=rest_dataset_sampling_interval,
        dataset_destinations=dataset_destinations,
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


def show_namespace_asset(
    cmd,
    asset_name: str,
    instance_name: str,
    resource_group_name: str
) -> dict:
    return NamespaceAssets(cmd).show(
        asset_name=asset_name,
        instance_name=instance_name,
        resource_group=resource_group_name
    )


def delete_namespace_asset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    confirm_yes: bool = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).delete(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        confirm_yes=confirm_yes,
        **kwargs
    )


def update_namespace_custom_asset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    # default configs + destinations
    dataset_custom_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    event_custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    mgmt_custom_configuration: Optional[str] = None,
    stream_custom_configuration: Optional[str] = None,
    stream_destinations: Optional[str] = None,
    # other params
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type="custom",
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        dataset_custom_configuration=dataset_custom_configuration,
        dataset_destinations=dataset_destinations,
        event_custom_configuration=event_custom_configuration,
        event_destinations=event_destinations,
        mgmt_custom_configuration=mgmt_custom_configuration,
        stream_custom_configuration=stream_custom_configuration,
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
    instance_name: str,
    instance_resource_group: str,
    # default stream config
    task_type: Optional[str] = None,
    disable_autostart: Optional[bool] = None,
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
    # other params
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.MEDIA.value,
        task_type=task_type,
        disable_autostart=disable_autostart,
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
    instance_name: str,
    instance_resource_group: str,
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.ONVIF.value,
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
    instance_name: str,
    instance_resource_group: str,
    # default configs + destinations
    dataset_publishing_interval: Optional[int] = None,
    dataset_sampling_interval: Optional[int] = None,
    dataset_queue_size: Optional[int] = None,
    dataset_key_frame_count: Optional[int] = None,
    dataset_destinations: Optional[str] = None,
    events_publishing_interval: Optional[int] = None,
    events_queue_size: Optional[int] = None,
    event_destinations: Optional[str] = None,
    # other params
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
    # waiting on service for mgmt schemas
    return NamespaceAssets(cmd).update(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.OPCUA.value,
        asset_type_refs=asset_type_refs,
        attributes=attributes,
        opcua_dataset_publishing_interval=dataset_publishing_interval,
        opcua_dataset_sampling_interval=dataset_sampling_interval,
        opcua_dataset_queue_size=dataset_queue_size,
        opcua_dataset_key_frame_count=dataset_key_frame_count,
        dataset_destinations=dataset_destinations,
        opcua_event_publishing_interval=events_publishing_interval,
        opcua_event_queue_size=events_queue_size,
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


def update_namespace_rest_asset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    rest_dataset_sampling_interval: Optional[int] = None,
    dataset_destinations: Optional[str] = None,
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_type=DeviceEndpointType.REST.value,
        rest_dataset_sampling_interval=rest_dataset_sampling_interval,
        dataset_destinations=dataset_destinations,
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


def query_namespace_assets(
    cmd,
    asset_name: Optional[str] = None,
    instance_name: Optional[str] = None,
    instance_resource_group: Optional[str] = None,
    custom_query: Optional[str] = None,
    device_name: Optional[str] = None,
    device_endpoint_name: Optional[str] = None,
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
) -> dict:
    return NamespaceAssets(cmd).query_assets(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        custom_query=custom_query,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
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
    )


# ASSET DATASET COMMANDS
def add_namespace_custom_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    data_source: str,
    dataset_custom_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type="custom",
        data_source=data_source,
        dataset_custom_configuration=dataset_custom_configuration,
        dataset_destinations=dataset_destinations,
        type_ref=type_ref,
        replace=replace,
        **kwargs
    )


def add_namespace_opcua_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    data_source: str,
    dataset_destinations: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        dataset_destinations=dataset_destinations,
        opcua_dataset_publishing_interval=opcua_dataset_publishing_interval,
        opcua_dataset_sampling_interval=opcua_dataset_sampling_interval,
        opcua_dataset_queue_size=opcua_dataset_queue_size,
        opcua_dataset_key_frame_count=opcua_dataset_key_frame_count,
        replace=replace,
        **kwargs
    )


def add_namespace_rest_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    data_source: str,
    rest_dataset_sampling_interval: Optional[int] = None,
    dataset_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.REST.value,
        data_source=data_source,
        rest_dataset_sampling_interval=rest_dataset_sampling_interval,
        dataset_destinations=dataset_destinations,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_datasets(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
) -> List[dict]:
    return NamespaceAssets(cmd).list_datasets(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
    )


def show_namespace_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str
) -> dict:
    return NamespaceAssets(cmd).show_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name
    )


def update_namespace_custom_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    data_source: Optional[str] = None,
    dataset_custom_configuration: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type="custom",
        data_source=data_source,
        dataset_custom_configuration=dataset_custom_configuration,
        dataset_destinations=dataset_destinations,
        type_ref=type_ref,
        **kwargs
    )


def update_namespace_opcua_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    data_source: Optional[str] = None,
    dataset_destinations: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        dataset_destinations=dataset_destinations,
        opcua_dataset_publishing_interval=opcua_dataset_publishing_interval,
        opcua_dataset_sampling_interval=opcua_dataset_sampling_interval,
        opcua_dataset_queue_size=opcua_dataset_queue_size,
        opcua_dataset_key_frame_count=opcua_dataset_key_frame_count,
        **kwargs
    )


def update_namespace_rest_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    rest_dataset_sampling_interval: Optional[int] = None,
    dataset_destinations: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type=DeviceEndpointType.REST.value,
        rest_dataset_sampling_interval=rest_dataset_sampling_interval,
        dataset_destinations=dataset_destinations,
        **kwargs
    )


def remove_namespace_asset_dataset(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_dataset(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        **kwargs
    )


# ASSET DATASET DATAPOINT COMMANDS
def add_namespace_custom_asset_dataset_point(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    datapoint_name: str,
    data_source: str,
    custom_configuration: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_dataset_datapoint(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        asset_type="custom",
        datapoint_name=datapoint_name,
        data_source=data_source,
        custom_configuration=custom_configuration,
        replace=replace,
        type_ref=type_ref,
        **kwargs
    )


def add_namespace_opcua_asset_dataset_point(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
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
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
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
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_dataset_datapoints(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name
    )


def remove_namespace_asset_dataset_point(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    dataset_name: str,
    datapoint_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_dataset_datapoint(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        dataset_name=dataset_name,
        datapoint_name=datapoint_name,
        **kwargs
    )


# ASSET EVENT GROUP COMMANDS
def add_namespace_custom_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: str,
    event_custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type="custom",
        data_source=data_source,
        event_custom_configuration=event_custom_configuration,
        event_destinations=event_destinations,
        type_ref=type_ref,
        replace=replace,
        **kwargs
    )


def add_namespace_opcua_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: str,
    event_destinations: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        event_destinations=event_destinations,
        opcua_event_publishing_interval=opcua_event_publishing_interval,
        opcua_event_queue_size=opcua_event_queue_size,
        replace=replace,
        **kwargs
    )


def add_namespace_onvif_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: str,
    event_destinations: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        data_source=data_source,
        event_destinations=event_destinations,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_event_groups(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
) -> List[dict]:
    return NamespaceAssets(cmd).list_event_groups(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
    )


def show_namespace_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str
) -> dict:
    return NamespaceAssets(cmd).show_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name
    )


def update_namespace_custom_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: Optional[str] = None,
    event_custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type="custom",
        data_source=data_source,
        event_custom_configuration=event_custom_configuration,
        event_destinations=event_destinations,
        type_ref=type_ref,
        **kwargs
    )


def update_namespace_opcua_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: Optional[str] = None,
    event_destinations: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        event_destinations=event_destinations,
        opcua_event_publishing_interval=opcua_event_publishing_interval,
        opcua_event_queue_size=opcua_event_queue_size,
        **kwargs
    )


def update_namespace_onvif_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: Optional[str] = None,
    event_destinations: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        data_source=data_source,
        event_destinations=event_destinations,
        **kwargs
    )


def remove_namespace_asset_event_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_event_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        **kwargs
    )


# ASSET EVENT GROUP EVENT COMMANDS
def add_namespace_custom_asset_event_group_event(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    event_name: str,
    data_source: str,
    custom_configuration: Optional[str] = None,
    event_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_group_event(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        event_name=event_name,
        asset_type="custom",
        data_source=data_source,
        custom_configuration=custom_configuration,
        event_destinations=event_destinations,
        type_ref=type_ref,
        replace=replace,
        **kwargs
    )


# TODO: not exposed for now but this will be supported in the near future
def add_namespace_opcua_asset_event_group_event(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    event_name: str,
    data_source: str,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_event_group_event(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        event_name=event_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_event_group_events(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_event_group_events(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name
    )


def remove_namespace_asset_event_group_event(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    event_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_event_group_event(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        event_name=event_name,
        **kwargs
    )


# STREAM COMMANDS
def add_namespace_custom_asset_stream(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    stream_name: str,
    stream_custom_configuration: Optional[str] = None,
    stream_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_stream(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        asset_type="custom",
        stream_custom_configuration=stream_custom_configuration,
        stream_destinations=stream_destinations,
        type_ref=type_ref,
        replace=replace,
        **kwargs
    )


def add_namespace_media_asset_stream(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    stream_name: str,
    task_type: Optional[str] = None,
    disable_autostart: Optional[bool] = None,
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
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_stream(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        asset_type=DeviceEndpointType.MEDIA.value,
        task_type=task_type,
        disable_autostart=disable_autostart,
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
        replace=replace,
        **kwargs
    )


def list_namespace_asset_streams(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_streams(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


def show_namespace_asset_stream(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    stream_name: str
) -> dict:
    return NamespaceAssets(cmd).show_stream(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name
    )


def update_namespace_custom_asset_stream(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    stream_name: str,
    stream_custom_configuration: Optional[str] = None,
    stream_destinations: Optional[str] = None,
    type_ref: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_stream(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        asset_type="custom",
        stream_custom_configuration=stream_custom_configuration,
        stream_destinations=stream_destinations,
        type_ref=type_ref,
        **kwargs
    )


def update_namespace_media_asset_stream(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    stream_name: str,
    task_type: Optional[str] = None,
    disable_autostart: Optional[bool] = None,
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
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_stream(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        asset_type=DeviceEndpointType.MEDIA.value,
        task_type=task_type,
        disable_autostart=disable_autostart,
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
        **kwargs
    )


def remove_namespace_asset_stream(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    stream_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_stream(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        **kwargs
    )


# MANAGEMENT GROUP COMMANDS
def add_namespace_custom_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: str,
    default_topic: Optional[str] = None,
    default_timeout: Optional[int] = None,
    mgmt_custom_configuration: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type="custom",
        data_source=data_source,
        default_timeout=default_timeout,
        default_topic=default_topic,
        mgmt_custom_configuration=mgmt_custom_configuration,
        type_ref=type_ref,
        replace=replace,
        **kwargs
    )


def add_namespace_opcua_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: str,
    default_topic: Optional[str] = None,
    default_timeout: Optional[int] = None,
    # mgmt_custom_configuration: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        default_timeout=default_timeout,
        default_topic=default_topic,
        # mgmt_custom_configuration=mgmt_custom_configuration,
        replace=replace,
        **kwargs
    )


def add_namespace_onvif_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: str,
    default_topic: Optional[str] = None,
    default_timeout: Optional[int] = None,
    # mgmt_custom_configuration: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        data_source=data_source,
        default_timeout=default_timeout,
        default_topic=default_topic,
        # mgmt_custom_configuration=mgmt_custom_configuration,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_management_groups(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_management_groups(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


def show_namespace_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str
) -> dict:
    return NamespaceAssets(cmd).show_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name
    )


def update_namespace_custom_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: Optional[str] = None,
    default_topic: Optional[str] = None,
    default_timeout: Optional[int] = None,
    mgmt_custom_configuration: Optional[str] = None,
    type_ref: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type="custom",
        data_source=data_source,
        default_timeout=default_timeout,
        default_topic=default_topic,
        mgmt_custom_configuration=mgmt_custom_configuration,
        type_ref=type_ref,
        **kwargs
    )


def update_namespace_opcua_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: Optional[str] = None,
    default_topic: Optional[str] = None,
    default_timeout: Optional[int] = None,
    # mgmt_custom_configuration: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        data_source=data_source,
        default_timeout=default_timeout,
        default_topic=default_topic,
        # mgmt_custom_configuration=mgmt_custom_configuration,
        **kwargs
    )


def update_namespace_onvif_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    data_source: Optional[str] = None,
    default_topic: Optional[str] = None,
    default_timeout: Optional[int] = None,
    # mgmt_custom_configuration: Optional[str] = None,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).update_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        data_source=data_source,
        default_timeout=default_timeout,
        default_topic=default_topic,
        # mgmt_custom_configuration=mgmt_custom_configuration,
        **kwargs
    )


def remove_namespace_asset_management_group(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_management_group(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        **kwargs
    )


# MANAGEMENT GROUP ACTION COMMANDS
def add_namespace_custom_asset_management_group_action(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    action_name: str,
    target_uri: str,
    action_type: Optional[str] = None,
    custom_configuration: Optional[str] = None,
    timeout: Optional[int] = None,
    topic: Optional[str] = None,
    type_ref: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_management_group_action(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        action_name=action_name,
        asset_type="custom",
        target_uri=target_uri,
        action_type=action_type,
        custom_configuration=custom_configuration,
        timeout=timeout,
        topic=topic,
        type_ref=type_ref,
        replace=replace,
        **kwargs
    )


def add_namespace_opcua_asset_management_group_action(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    action_name: str,
    target_uri: str,
    action_type: Optional[str] = None,
    # custom_configuration: Optional[str] = None,
    timeout: Optional[int] = None,
    topic: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_management_group_action(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        action_name=action_name,
        asset_type=DeviceEndpointType.OPCUA.value,
        target_uri=target_uri,
        action_type=action_type,
        # custom_configuration=custom_configuration,
        timeout=timeout,
        topic=topic,
        replace=replace,
        **kwargs
    )


# TODO: not exposed for now but this will be supported in the near future
def add_namespace_onvif_asset_management_group_action(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    action_name: str,
    target_uri: str,
    action_type: Optional[str] = None,
    # custom_configuration: Optional[str] = None,
    timeout: Optional[int] = None,
    topic: Optional[str] = None,
    replace: Optional[bool] = False,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).add_management_group_action(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        action_name=action_name,
        asset_type=DeviceEndpointType.ONVIF.value,
        target_uri=target_uri,
        action_type=action_type,
        # custom_configuration=custom_configuration,
        timeout=timeout,
        topic=topic,
        replace=replace,
        **kwargs
    )


def list_namespace_asset_management_group_actions(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str
) -> List[dict]:
    return NamespaceAssets(cmd).list_management_group_actions(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name
    )


def remove_namespace_asset_management_group_action(
    cmd,
    asset_name: str,
    instance_name: str,
    instance_resource_group: str,
    group_name: str,
    action_name: str,
    **kwargs
) -> dict:
    return NamespaceAssets(cmd).remove_management_group_action(
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        action_name=action_name,
        **kwargs
    )
