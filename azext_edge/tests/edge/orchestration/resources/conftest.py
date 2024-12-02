# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import re
from typing import Optional

from ....generators import generate_random_string, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
BASE_URL = "https://management.azure.com"
RESOURCE_PROVIDER = "Microsoft.IoTOperations"
QUALIFIED_INSTANCE_TYPE = f"{RESOURCE_PROVIDER}/instances"
INSTANCES_API_VERSION = "2024-11-01"
CUSTOM_LOCATION_NAME = generate_random_string()


def get_base_endpoint(
    resource_group_name: Optional[str] = None,
    resource_provider: Optional[str] = RESOURCE_PROVIDER,
    resource_path: Optional[str] = None,
    api_version: Optional[str] = INSTANCES_API_VERSION,
) -> str:
    expected_endpoint = f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}"
    if resource_group_name:
        expected_endpoint += f"/resourceGroups/{resource_group_name}"
    if resource_provider:
        expected_endpoint += f"/providers/{resource_provider}"
        if resource_path:
            expected_endpoint += resource_path

    expected_endpoint += f"?api-version={api_version}"
    return expected_endpoint


def get_mock_resource(
    name: str,
    properties: dict,
    resource_group_name: str,
    resource_provider: Optional[str] = None,
    resource_path: str = "",
    location: Optional[str] = None,
    subscription_id: str = ZEROED_SUBSCRIPTION,
    custom_location_name: str = CUSTOM_LOCATION_NAME,
    identity: dict = {},
    qualified_type: Optional[str] = None,
) -> dict:
    if not location:
        location = "northeurope"
    resource = {
        "extendedLocation": {
            "name": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.ExtendedLocation/customLocations/{custom_location_name}",
            "type": "CustomLocation",
        },
        "id": get_base_endpoint(
            resource_group_name=resource_group_name,
            resource_path=resource_path,
            resource_provider=resource_provider or RESOURCE_PROVIDER,
        ).split("?")[0][len(BASE_URL) :],
        "location": location,
        "name": name,
        "properties": properties,
        "resourceGroup": resource_group_name,
        "systemData": {
            "createdAt": "2024-06-21T19:04:29.2176544Z",
            "createdBy": "",
            "createdByType": "Application",
            "lastModifiedAt": "2024-06-21T19:04:29.2176544Z",
            "lastModifiedBy": "",
            "lastModifiedByType": "Application",
        },
        "type": qualified_type or QUALIFIED_INSTANCE_TYPE,
    }

    if identity:
        resource["identity"] = identity
    return resource


def get_resource_id(
    resource_path: str,
    resource_group_name: str,
    resource_provider: Optional[str] = RESOURCE_PROVIDER,
) -> str:
    return get_base_endpoint(
        resource_group_name=resource_group_name, resource_path=resource_path, resource_provider=resource_provider
    ).split("?")[0][len(BASE_URL) :]


def get_authz_endpoint_pattern() -> re.Pattern:
    return re.compile(r"https:\/\/.*\/providers\/Microsoft\.Authorization\/roleAssignments.*")
