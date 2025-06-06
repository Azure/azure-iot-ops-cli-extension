# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional, Dict

from knack.log import get_logger

from .providers.orchestration.resources import SchemaRegistries, Schemas

logger = get_logger(__name__)


def create_registry(
    cmd,
    schema_registry_name: str,
    resource_group_name: str,
    registry_namespace: str,
    storage_account_resource_id: str,
    storage_container_name: Optional[str] = "schemas",
    location: Optional[str] = None,
    description: Optional[str] = None,
    display_name: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    skip_role_assignments: Optional[bool] = None,
    custom_role_id: Optional[str] = None,
    **kwargs
) -> dict:
    return SchemaRegistries(cmd).create(
        name=schema_registry_name,
        resource_group_name=resource_group_name,
        location=location,
        registry_namespace=registry_namespace,
        storage_account_resource_id=storage_account_resource_id,
        storage_container_name=storage_container_name,
        description=description,
        display_name=display_name,
        tags=tags,
        skip_role_assignments=skip_role_assignments,
        custom_role_id=custom_role_id,
        **kwargs,
    )


def show_registry(cmd, schema_registry_name: str, resource_group_name: str) -> dict:
    return SchemaRegistries(cmd).show(name=schema_registry_name, resource_group_name=resource_group_name)


def list_registries(cmd, resource_group_name: Optional[str] = None) -> Iterable[dict]:
    return SchemaRegistries(cmd).list(resource_group_name=resource_group_name)


def delete_registry(
    cmd,
    schema_registry_name: str,
    resource_group_name: Optional[str] = None,
    confirm_yes: Optional[bool] = None,
    **kwargs
):
    return SchemaRegistries(cmd).delete(
        name=schema_registry_name, resource_group_name=resource_group_name, confirm_yes=confirm_yes, **kwargs
    )


# Schemas
def create_schema(
    cmd,
    schema_name: str,
    schema_registry_name: str,
    resource_group_name: str,
    schema_type: str,
    schema_format: str,
    schema_version_content: str,
    schema_version: int = 1,
    description: Optional[str] = None,
    display_name: Optional[str] = None,
    schema_version_description: Optional[str] = None
) -> dict:
    return Schemas(cmd).create(
        name=schema_name,
        schema_registry_name=schema_registry_name,
        schema_type=schema_type,
        schema_format=schema_format,
        description=description,
        display_name=display_name,
        resource_group_name=resource_group_name,
        schema_version_content=schema_version_content,
        schema_version=schema_version,
        schema_version_description=schema_version_description
    )


def show_schema(cmd, schema_name: str, schema_registry_name: str, resource_group_name: str) -> dict:
    return Schemas(cmd).show(
        name=schema_name,
        schema_registry_name=schema_registry_name,
        resource_group_name=resource_group_name
    )


def list_schemas(cmd, schema_registry_name: str, resource_group_name: str) -> dict:
    return Schemas(cmd).list(schema_registry_name=schema_registry_name, resource_group_name=resource_group_name)


def list_schema_versions_dataflow_format(
    cmd,
    schema_registry_name: str,
    resource_group_name: str,
    schema_name: Optional[str] = None,
    schema_version: Optional[str] = None,
    latest: Optional[bool] = None
) -> dict:
    return Schemas(cmd).list_dataflow_friendly_versions(
        schema_registry_name=schema_registry_name,
        resource_group_name=resource_group_name,
        schema_name=schema_name,
        schema_version=schema_version,
        latest=latest
    )


def delete_schema(
    cmd,
    schema_name: str,
    schema_registry_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
) -> dict:
    return Schemas(cmd).delete(
        name=schema_name,
        schema_registry_name=schema_registry_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
    )


# Versions
def add_version(
    cmd,
    version_name: int,
    schema_name: str,
    schema_registry_name: str,
    resource_group_name: str,
    schema_version_content: str,
    description: Optional[str] = None,
) -> dict:
    return Schemas(cmd).add_version(
        name=version_name,
        schema_name=schema_name,
        schema_registry_name=schema_registry_name,
        schema_version_content=schema_version_content,
        description=description,
        resource_group_name=resource_group_name,
    )


def show_version(
    cmd, version_name: int, schema_name: str, schema_registry_name: str, resource_group_name: str
) -> dict:
    return Schemas(cmd).show_version(
        name=version_name,
        schema_name=schema_name,
        schema_registry_name=schema_registry_name,
        resource_group_name=resource_group_name
    )


def list_versions(
    cmd, schema_name: str, schema_registry_name: str, resource_group_name: str
) -> dict:
    return Schemas(cmd).list_versions(
        schema_name=schema_name,
        schema_registry_name=schema_registry_name,
        resource_group_name=resource_group_name
    )


def remove_version(
    cmd,
    version_name: int,
    schema_name: str,
    schema_registry_name: str,
    resource_group_name: str,
) -> dict:
    return Schemas(cmd).remove_version(
        name=version_name,
        schema_name=schema_name,
        schema_registry_name=schema_registry_name,
        resource_group_name=resource_group_name
    )
