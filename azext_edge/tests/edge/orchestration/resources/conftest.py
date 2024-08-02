# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from ....generators import get_zeroed_subscription, generate_random_string

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
BASE_URL = "https://management.azure.com"
RESOURCE_PROVIDER = "Microsoft.IoTOperations"
QUALIFIED_INSTANCE_TYPE = f"{RESOURCE_PROVIDER}/instances"
INSTANCES_API_VERSION = "2024-07-01-preview"
CUSTOM_LOCATION_NAME = generate_random_string()


def get_base_endpoint(
    resource_group_name: Optional[str] = None,
    resource_provider: Optional[str] = RESOURCE_PROVIDER,
    resource_path: Optional[str] = None,
) -> str:
    expected_endpoint = f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}"
    if resource_group_name:
        expected_endpoint += f"/resourceGroups/{resource_group_name}"
    if resource_provider:
        expected_endpoint += f"/providers/{resource_provider}"
        if resource_path:
            expected_endpoint += resource_path

    expected_endpoint += f"?api-version={INSTANCES_API_VERSION}"

    return expected_endpoint


def get_mock_resource(
    name: str,
    properties: dict,
    resource_group_name: str,
    resource_path: str = "",
    subscription_id: str = ZEROED_SUBSCRIPTION,
    custom_location_name: str = CUSTOM_LOCATION_NAME,
) -> dict:

    return {
        "extendedLocation": {
            "name": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.ExtendedLocation/customLocations/{custom_location_name}",
            "type": "CustomLocation",
        },
        "id": get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path).split("?")[0][
            len(BASE_URL) :
        ],
        "location": "northeurope",
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
        "type": QUALIFIED_INSTANCE_TYPE,
    }
