# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.rpsaas.adr.namespaces import Namespaces
from .providers.rpsaas.adr.namespace_devices import NamespaceDevices

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
):
    Namespaces(cmd).delete(
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
    **kwargs
):
    NamespaceDevices(cmd).delete(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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
