# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_schema import (
    delete_registry,
    list_registries,
    show_registry,
    create_registry,
)

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource, get_resource_id

SCHEMA_REGISTRY_RP = "Microsoft.DeviceRegistry"
STORAGE_RP = "Microsoft.Storage"


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
        api_version="2024-07-01-preview",
    )


def get_storage_container_endpoint(resource_group_name: str, account_name: str, container_name: str) -> str:
    resource_path = f"/storageAccounts/{account_name}/blobServices/default/containers/{container_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=STORAGE_RP,
        api_version="2022-09-01",
    )


def get_storage_endpoint(resource_group_name: str, account_name: str) -> str:
    resource_path = f"/storageAccounts/{account_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=STORAGE_RP,
        api_version="2022-09-01",
    )


def get_mock_schema_registery_record(name: str, resource_group_name: str) -> dict:
    record = get_mock_resource(
        name=name,
        resource_provider=SCHEMA_REGISTRY_RP,
        resource_path=f"/schemaRegistries/{name}",
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
        name=account_name,
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


def test_schema_registry_delete(mocked_cmd, mocked_responses: responses):
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_schema_registry_endpoint(resource_group_name=resource_group_name, registry_name=registery_name),
        status=204,
    )
    delete_registry(
        cmd=mocked_cmd,
        schema_registry_name=registery_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1


def test_schema_registry_create(mocked_cmd, mocked_responses: responses, mocker):
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace = generate_random_string()
    storage_account_name = generate_random_string()
    storage_container_name = generate_random_string()

    mock_permission_manager = mocker.patch("azext_edge.edge.providers.orchestration.resources.schema_registries.PermissionManager")

    storage_resource_id = get_resource_id(
        resource_path=f"/storageAccounts/{storage_account_name}",
        resource_group_name=resource_group_name,
        resource_provider=STORAGE_RP,
    )
    mock_storage_record = get_mock_storage_account(
        resource_group_name=resource_group_name, account_name=storage_account_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_storage_endpoint(resource_group_name=resource_group_name, account_name=storage_account_name),
        json=mock_storage_record,
        status=200,
    )

    mock_storage_container_record = get_mock_storage_container(
        resource_group_name=resource_group_name,
        account_name=storage_account_name,
        container_name=storage_container_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_storage_container_endpoint(
            resource_group_name=resource_group_name,
            account_name=storage_account_name,
            container_name=storage_container_name,
        ),
        json=mock_storage_container_record,
        status=200,
    )

    mock_registry_record = get_mock_schema_registery_record(
        name=registery_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_schema_registry_endpoint(resource_group_name=resource_group_name, registry_name=registery_name),
        json=mock_registry_record,
        status=200,
    )
    result = create_registry(
        cmd=mocked_cmd,
        schema_registry_name=registery_name,
        resource_group_name=resource_group_name,
        namespace=namespace,
        storage_account_resource_id=storage_resource_id,
        storage_container_name=storage_container_name,
        location="westus2",
        wait_sec=0.25,
    )

    assert result == mock_registry_record
    #import pdb; pdb.set_trace()
    pass
