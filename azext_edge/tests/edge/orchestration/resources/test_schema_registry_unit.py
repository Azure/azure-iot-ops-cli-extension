# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional

import pytest
import responses
from azure.cli.core.azclierror import AzureResponseError, ValidationError

from azext_edge.edge.commands_schema import (
    create_registry,
    delete_registry,
    list_registries,
    show_registry,
)
from azext_edge.edge.providers.orchestration.resources.schema_registries import (
    ROLE_DEF_FORMAT_STR,
    STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_ID,
)
from azext_edge.edge.providers.orchestration.rp_namespace import ADR_PROVIDER

from ....generators import generate_random_string
from .conftest import (
    ZEROED_SUBSCRIPTION,
    get_authz_endpoint_pattern,
    get_base_endpoint,
    get_mock_resource,
    get_resource_id,
)

SCHEMA_REGISTRY_RP = "Microsoft.DeviceRegistry"
SCHEMA_REGISTRY_RP_API_VERSION = "2024-09-01-preview"
STORAGE_RP = "Microsoft.Storage"
STORAGE_API_VERSION = "2023-05-01"
RESOURCES_API_VERSION = "2024-03-01"


def get_schema_registry_endpoint(
    resource_group_name: Optional[str] = None, registry_name: Optional[str] = None
) -> str:
    resource_path = "/schemaRegistries"
    if registry_name:
        resource_path += f"/{registry_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=SCHEMA_REGISTRY_RP,
        api_version=SCHEMA_REGISTRY_RP_API_VERSION,
    )


def get_storage_container_endpoint(resource_group_name: str, account_name: str, container_name: str) -> str:
    resource_path = f"/storageAccounts/{account_name}/blobServices/default/containers/{container_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=STORAGE_RP,
        api_version=STORAGE_API_VERSION,
    )


def get_storage_endpoint(resource_group_name: str, account_name: str) -> str:
    resource_path = f"/storageAccounts/{account_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=STORAGE_RP,
        api_version=STORAGE_API_VERSION,
    )


def get_mock_schema_registery_record(name: str, resource_group_name: str, location: Optional[str] = None) -> dict:
    record = get_mock_resource(
        name=name,
        resource_provider=SCHEMA_REGISTRY_RP,
        resource_path=f"/schemaRegistries/{name}",
        location=location,
        identity={
            "principalId": "a4a1d45e-870c-40b8-97b1-4143a4665e32",
            "tenantId": "c3d87c27-b9cf-45f0-90d8-bd82377060a1",
            "type": "SystemAssigned",
        },
        properties={
            "namespace": "mynamespace",
            "provisioningState": "Succeeded",
            "storageAccountContainerUrl": "https://container.blob.core.windows.net/schemas",
            "uuid": "4630b849-a08a-44f9-af0a-9821098b1b1e",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.deviceregistry/schemaregistries",
    )
    record.pop("extendedLocation")
    return record


def get_mock_storage_container(account_name: str, container_name: str, resource_group_name: str) -> dict:
    record = get_mock_resource(
        name=container_name,
        resource_provider=STORAGE_RP,
        resource_path=f"/storageAccounts/{account_name}/blobServices/default/containers/{container_name}",
        properties={"name": container_name},
        resource_group_name=resource_group_name,
        qualified_type="microsoft.storage/storageaccounts/containers",
    )
    record.pop("extendedLocation")
    return record


def get_mock_storage_account(account_name: str, resource_group_name: str) -> dict:
    record = get_mock_resource(
        name=account_name,
        resource_provider=STORAGE_RP,
        resource_path=f"/storageAccounts/{account_name}",
        properties={
            "isHnsEnabled": True,
            "primaryEndpoints": {
                "blob": "https://schemareg.blob.core.windows.net/",
            },
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.storage/storageaccounts",
    )
    record.pop("extendedLocation")
    return record


def test_schema_registry_show(mocked_cmd, mocked_responses: responses):
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_schema_registry_record = get_mock_schema_registery_record(
        resource_group_name=resource_group_name, name=registery_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_schema_registry_endpoint(resource_group_name=resource_group_name, registry_name=registery_name),
        json=mock_schema_registry_record,
        status=200,
        content_type="application/json",
    )
    result = show_registry(
        cmd=mocked_cmd, schema_registry_name=registery_name, resource_group_name=resource_group_name
    )

    assert result == mock_schema_registry_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "resource_group_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_schema_registry_list(mocked_cmd, mocked_responses: responses, resource_group_name: str, records: int):
    mock_schema_registry_records = {
        "value": [
            get_mock_schema_registery_record(name=generate_random_string(), resource_group_name=resource_group_name)
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_schema_registry_endpoint(resource_group_name=resource_group_name),
        json=mock_schema_registry_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_registries(cmd=mocked_cmd, resource_group_name=resource_group_name))

    assert result == mock_schema_registry_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("status", [200, 204])
def test_schema_registry_delete(mocked_cmd, mocked_responses: responses, status: int):
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_schema_registry_endpoint(resource_group_name=resource_group_name, registry_name=registery_name),
        status=status,
    )
    delete_registry(
        cmd=mocked_cmd,
        schema_registry_name=registery_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0,
    )
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "location",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "is_hns_enabled",
    [False, True],
)
@pytest.mark.parametrize(
    "container_fetch_code",
    [200, 404],
)
@pytest.mark.parametrize(
    "create_role_assignment_code",
    [200, 403],
)
@pytest.mark.parametrize(
    "display_name,description,tags,custom_role_id",
    [
        (None, None, None, None),
        (generate_random_string(), generate_random_string(), {"a": "b", "c": "d"}, "/my/custom/role"),
    ],
)
def test_schema_registry_create(
    mocked_cmd,
    mocker,
    mocked_register_providers,
    mocked_responses: responses,
    location: Optional[str],
    display_name: Optional[str],
    description: Optional[str],
    tags: Optional[dict],
    is_hns_enabled: bool,
    container_fetch_code: int,
    create_role_assignment_code: int,
    custom_role_id: Optional[str],
):
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()
    registry_namespace = generate_random_string()
    storage_account_name = generate_random_string()
    storage_container_name = generate_random_string()

    mock_resource_group = {"location": generate_random_string()}
    if not location:
        mocked_responses.add(
            method=responses.GET,
            url=get_base_endpoint(
                resource_group_name=resource_group_name, resource_provider="", api_version=RESOURCES_API_VERSION
            ).replace("resourceGroups", "resourcegroups"),
            json=mock_resource_group,
            status=200,
        )
    expected_location = location or mock_resource_group["location"]

    storage_resource_id = get_resource_id(
        resource_path=f"/storageAccounts/{storage_account_name}",
        resource_group_name=resource_group_name,
        resource_provider=STORAGE_RP,
    )
    mock_storage_record = get_mock_storage_account(
        resource_group_name=resource_group_name, account_name=storage_account_name
    )
    mock_storage_record["properties"]["isHnsEnabled"] = is_hns_enabled
    mocked_responses.add(
        method=responses.GET,
        url=get_storage_endpoint(resource_group_name=resource_group_name, account_name=storage_account_name),
        json=mock_storage_record,
        status=200,
    )
    create_registry_kwargs = {
        "cmd": mocked_cmd,
        "schema_registry_name": registery_name,
        "resource_group_name": resource_group_name,
        "registry_namespace": registry_namespace,
        "storage_account_resource_id": storage_resource_id,
        "storage_container_name": storage_container_name,
        "location": location,
        "display_name": display_name,
        "description": description,
        "tags": tags,
        "custom_role_id": custom_role_id,
        "wait_sec": 0,
    }
    if not is_hns_enabled:
        with pytest.raises(ValidationError):
            create_registry(**create_registry_kwargs)
        return

    mock_storage_container_record = get_mock_storage_container(
        resource_group_name=resource_group_name,
        account_name=storage_account_name,
        container_name=storage_container_name,
    )
    storage_container_endpoint = get_storage_container_endpoint(
        resource_group_name=resource_group_name,
        account_name=storage_account_name,
        container_name=storage_container_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=storage_container_endpoint,
        json=mock_storage_container_record,
        status=container_fetch_code,
    )
    if container_fetch_code == 404:
        mocked_responses.add(
            method=responses.PUT,
            url=storage_container_endpoint,
            json=mock_storage_container_record,
            status=200,
        )

    mock_registry_record = get_mock_schema_registery_record(
        name=registery_name, resource_group_name=resource_group_name
    )
    create_registry_endpoint = get_schema_registry_endpoint(
        resource_group_name=resource_group_name, registry_name=registery_name
    )

    target_role_id = custom_role_id or ROLE_DEF_FORMAT_STR.format(
        subscription_id=ZEROED_SUBSCRIPTION, role_id=STORAGE_BLOB_DATA_CONTRIBUTOR_ROLE_ID
    )

    sr_create_response = mocked_responses.add(
        method=responses.PUT,
        url=create_registry_endpoint,
        json=mock_registry_record,
        status=200,
    )

    get_role_response = mocked_responses.add(
        method=responses.GET,
        url=get_authz_endpoint_pattern(),
        json={"value": []},
        status=200,
    )
    create_role_response = mocked_responses.add(
        method=responses.PUT,
        url=get_authz_endpoint_pattern(),
        json={},
        status=create_role_assignment_code,
    )

    if create_role_assignment_code not in [200, 201]:
        with pytest.raises(AzureResponseError) as error:
            create_registry(**create_registry_kwargs)
        assert str(error.value).startswith("Role assignment failed")
        return

    create_result = create_registry(**create_registry_kwargs)
    mocked_register_providers.assert_called_with(ZEROED_SUBSCRIPTION, ADR_PROVIDER)

    assert get_role_response.calls[0].request.url.endswith(
        f"?$filter=principalId%20eq%20'{mock_registry_record['identity']['principalId']}'&api-version=2022-04-01"
    )

    create_role_request_json = json.loads(create_role_response.calls[0].request.body)
    assert create_role_request_json["properties"]["roleDefinitionId"] == target_role_id
    assert create_role_request_json["properties"]["principalId"] == mock_registry_record["identity"]["principalId"]
    assert create_role_request_json["properties"]["principalType"] == "ServicePrincipal"

    assert create_result == mock_registry_record
    schema_registry_create_payload = json.loads(sr_create_response.calls[0].request.body)
    assert schema_registry_create_payload["location"] == expected_location
    if tags:
        assert schema_registry_create_payload["tags"] == tags
    assert schema_registry_create_payload["identity"]["type"] == "SystemAssigned"
    assert schema_registry_create_payload["properties"]["namespace"] == registry_namespace
    assert schema_registry_create_payload["properties"]["description"] == description
    assert schema_registry_create_payload["properties"]["displayName"] == display_name
    assert (
        schema_registry_create_payload["properties"]["storageAccountContainerUrl"]
        == f"{mock_storage_record['properties']['primaryEndpoints']['blob']}{storage_container_name}"
    )
