# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from knack.log import get_logger

from .providers.orchestration.resources import SchemaRegistries

logger = get_logger(__name__)


def show_registry(cmd, schema_registry_name: str, resource_group_name: str) -> dict:
    return SchemaRegistries(cmd).show(name=schema_registry_name, resource_group_name=resource_group_name)


def list_registries(cmd, resource_group_name: Optional[str] = None) -> Iterable[dict]:
    return SchemaRegistries(cmd).list(resource_group_name=resource_group_name)
