# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from knack.log import get_logger

from .providers.orchestration.resources import SchemaRegistries

logger = get_logger(__name__)


def create_registry(
    cmd,
    schema_registry_name: str,
    resource_group_name: str,
    namespace: str,
    storage_account_resource_id: str,
    storage_container_name: Optional[str] = "schemas",
    location: Optional[str] = None,
    description: Optional[str] = None,
    display_name: Optional[str] = None,
    tags: Optional[str] = None,
    custom_role_id: Optional[str] = None,
) -> dict:
    return SchemaRegistries(cmd).create(
        name=schema_registry_name,
        resource_group_name=resource_group_name,
        location=location,
        namespace=namespace,
        storage_account_resource_id=storage_account_resource_id,
        storage_container_name=storage_container_name,
        description=description,
        display_name=display_name,
        tags=tags,
        custom_role_id=custom_role_id,
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
