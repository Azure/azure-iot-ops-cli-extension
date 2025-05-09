# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.rpsaas.adr.namespaces import Namespaces

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
