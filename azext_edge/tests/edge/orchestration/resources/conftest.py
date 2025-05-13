# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from typing import NamedTuple, Optional, Tuple

import pytest
import requests

from ....generators import generate_random_string, get_zeroed_subscription

ZEROED_SUBSCRIPTION = get_zeroed_subscription()
BASE_URL = "https://management.azure.com"
RESOURCE_PROVIDER = "Microsoft.IoTOperations"
QUALIFIED_INSTANCE_TYPE = f"{RESOURCE_PROVIDER}/instances"
INSTANCES_API_VERSION = "2025-04-01"
CUSTOM_LOCATIONS_API_VERSION = "2021-08-31-preview"
CONNECTED_CLUSTER_API_VERSION = "2024-07-15-preview"
CLUSTER_EXTENSIONS_API_VERSION = "2023-05-01"
CUSTOM_LOCATION_NAME = generate_random_string()
CLUSTER_EXTENSIONS_URL_MATCH_RE = re.compile(
    r"^https:\/\/management\.azure\.com\/subscriptions\/[0-9a-fA-F\-]{36}\/resourceGroups\/[a-zA-Z0-9]+\/"
    r"providers\/Microsoft\.Kubernetes\/connectedClusters\/[a-zA-Z0-9]+\/providers\/"
    r"Microsoft\.KubernetesConfiguration\/extensions\/[a-zA-Z0-9]+(\?api-version=2023-05-01)?$"
)
ROLE_ASSIGNMENT_RP = "Microsoft.Authorization"
ROLE_ASSIGNMENT_API_VERSION = "2022-04-01"

ARG_API_VERSION = "2022-10-01"
ARG_ENDPOINT = f"{BASE_URL}/providers/Microsoft.ResourceGraph/resources?api-version={ARG_API_VERSION}"


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
    tags: Optional[dict] = None,
    is_proxy_resource: bool = False,
) -> dict:
    kwargs = {}
    if not location:
        location = "northeurope"
    if not is_proxy_resource:
        kwargs["location"] = location
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
        **kwargs,
    }

    if identity:
        resource["identity"] = identity
    if tags is not None:
        resource["tags"] = tags
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


@pytest.fixture
def mocked_get_file_config(mocker):
    yield mocker.patch("azext_edge.edge.providers.orchestration.resources.reskit.read_file_content")


def get_request_kpis(request: requests.PreparedRequest) -> "RequestKPIs":
    """Extracts key performance indicators from a request object."""
    return RequestKPIs(
        method=request.method,
        url=request.url,
        params=request.params,
        path_url=request.path_url.split("?")[0],
        body_str=request.body,
    )


class RequestKPIs(NamedTuple):
    method: str
    url: str
    params: dict
    path_url: str
    body_str: str

    @classmethod
    def respond_with(
        cls,
        response_code: int,
        response_headers: Optional[dict] = None,
        response_body: Optional[dict] = None,
    ) -> Tuple[int, dict, dict]:
        if isinstance(response_body, dict):
            response_body = json.dumps(response_body)
        if not response_headers and response_body:
            response_headers = {"Content-Type": "application/json"}
        return response_code, response_headers, response_body


def append_role_assignment_endpoint(
    resource_endpoint: str, ra_name: Optional[str] = None, filter_query: Optional[str] = None
) -> str:
    endpoint = resource_endpoint.split("?")[0]
    endpoint = f"{endpoint}/providers/Microsoft.Authorization/roleAssignments"
    if ra_name:
        endpoint += f"/{ra_name}"
    endpoint += "?"
    if filter_query:
        endpoint += f"$filter={filter_query}&"

    return f"{endpoint}api-version={ROLE_ASSIGNMENT_API_VERSION}"
