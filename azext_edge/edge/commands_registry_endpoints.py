# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Registry endpoint commands for Azure IoT Operations.
"""

from typing import Iterable, Optional

from .providers.orchestration.resources import RegistryEndpoints


def add_registry_endpoint(
    cmd,
    instance_name: str,
    resource_group_name: str,
    registry_endpoint_name: str,
    host: str,
    auth_type: Optional[str] = None,
    secret_ref: Optional[str] = None,
    audience: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    no_auth: Optional[bool] = None,
    code_signing_configmap_refs: Optional[list] = None,
    code_signing_secret_refs: Optional[list] = None,
    **kwargs,
) -> dict:
    """Add a registry endpoint to an IoT Operations instance."""
    return RegistryEndpoints(cmd).add(
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=host,
        auth_type=auth_type,
        secret_ref=secret_ref,
        audience=audience,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        no_auth=no_auth,
        code_signing_configmap_refs=code_signing_configmap_refs,
        code_signing_secret_refs=code_signing_secret_refs,
        **kwargs,
    )


def update_registry_endpoint(
    cmd,
    instance_name: str,
    resource_group_name: str,
    registry_endpoint_name: str,
    host: Optional[str] = None,
    auth_type: Optional[str] = None,
    secret_ref: Optional[str] = None,
    audience: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    no_auth: Optional[bool] = None,
    code_signing_configmap_refs: Optional[list] = None,
    code_signing_secret_refs: Optional[list] = None,
    **kwargs,
) -> dict:
    """Update a registry endpoint in an IoT Operations instance."""
    return RegistryEndpoints(cmd).update(
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=host,
        auth_type=auth_type,
        secret_ref=secret_ref,
        audience=audience,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        no_auth=no_auth,
        code_signing_configmap_refs=code_signing_configmap_refs,
        code_signing_secret_refs=code_signing_secret_refs,
        **kwargs,
    )


def show_registry_endpoint(cmd, registry_endpoint_name: str, instance_name: str, resource_group_name: str) -> dict:
    """Show details of a registry endpoint in an IoT Operations instance."""
    return RegistryEndpoints(cmd).show(
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
    )


def list_registry_endpoints(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    """List all registry endpoints in an IoT Operations instance."""
    return RegistryEndpoints(cmd).list(
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def remove_registry_endpoint(
    cmd,
    registry_endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    **kwargs,
) -> None:
    """Remove a registry endpoint from an IoT Operations instance."""
    return RegistryEndpoints(cmd).remove(
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )
