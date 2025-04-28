# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import secrets
import string
from typing import List, Optional, Union
from uuid import uuid4

BASE_URL = "https://management.azure.com"


def generate_names(prefix: str = "", count: int = 1, max_length: int = 48) -> Union[str, List[str]]:
    """
    Generic name generator that returns a list of names. If only one
    name is generated, returns only the name as a string.
    """
    names = [(prefix + insecure_random_string())[:max_length] for _ in range(count)]
    return names[0] if count == 1 else names


def get_zeroed_subscription() -> str:
    return "00000000-0000-0000-0000-000000000000"


def insecure_random_string(size: int = 36, force_lower: bool = False) -> str:
    """
    Generates a simple random string of the specified size.
    Suitable for generating randomized resource names, etc.
    """
    from random import choice

    valid_sequence = string.ascii_lowercase + string.digits
    if not force_lower:
        valid_sequence += string.ascii_uppercase
    return "".join(choice(valid_sequence) for _ in range(size))


def generate_random_string(size: int = 36, force_lower: bool = False):
    """
    Generates a crytopgraphically strong random string of the specified size.
    """
    valid_sequence = string.ascii_lowercase + string.digits
    if not force_lower:
        valid_sequence += string.ascii_uppercase
    return "".join(secrets.choice(valid_sequence) for _ in range(size))


def generate_resource_id(
    resource_group_name: Optional[str] = None,
    resource_provider: Optional[str] = None,
    resource_path: Optional[str] = None,
    resource_subscription: Optional[str] = None,
) -> str:
    resource_id = f"/subscriptions/{resource_subscription or get_zeroed_subscription()}"
    if resource_group_name:
        resource_id += f"/resourceGroups/{resource_group_name}"
    if resource_provider:
        resource_id += f"/providers/{resource_provider}"
    if resource_path:
        resource_id += resource_path
    return resource_id


def generate_base_endpoint(
    resource_group_name: Optional[str] = None,
    resource_provider: Optional[str] = None,
    resource_path: Optional[str] = None,
    api_version: Optional[str] = None,
) -> str:
    resource_id = generate_resource_id(
        resource_group_name=resource_group_name, resource_provider=resource_provider, resource_path=resource_path
    )
    expected_endpoint = f"{BASE_URL}{resource_id}"
    if api_version:
        expected_endpoint += f"?api-version={api_version}"
    return expected_endpoint


def generate_uuid() -> str:
    return str(uuid4())
