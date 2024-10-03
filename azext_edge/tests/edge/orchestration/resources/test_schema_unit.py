# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_schema import (
    create_schema,
    delete_schema,
    list_schemas,
    show_schema,
)
from azext_edge.edge.providers.orchestration.common import SchemaFormat
from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource

SCHEMA_RP = "Microsoft.DeviceRegistry"
SCHEMA_REGISTRY_RP_API_VERSION = "2024-09-01-preview"


def get_schema_endpoint(
    resource_group_name: str,
    registry_name: str,
    schema_name: Optional[str] = None
) -> str:
    resource_path =f"/schemaRegistries/{registry_name}/schemas"
    if schema_name:
        resource_path += f"/{schema_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=SCHEMA_RP,
        api_version=SCHEMA_REGISTRY_RP_API_VERSION,
    )


def get_mock_schema_record(
    name: str,
    registry_name: str,
    resource_group_name: str
) -> dict:
    record = get_mock_resource(
        name=name,
        resource_provider=SCHEMA_RP,
        resource_path=f"/schemaRegistries/{registry_name}/schemas/{name}",
        properties={
            "provisioningState": "Succeeded",
            "uuid": "4630b849-a08a-44f9-af0a-9821098b1b1e",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.deviceregistry/schemaregistries/schemas",
    )
    record.pop("extendedLocation")
    record.pop("location")
    return record


def test_schema_show(mocked_cmd, mocked_responses: responses):
    schema_name = generate_random_string()
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_schema_registry_record = get_mock_schema_record(
        name=schema_name,
        registry_name=registery_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registery_name,
            schema_name=schema_name
        ),
        json=mock_schema_registry_record,
        status=200,
        content_type="application/json",
    )
    result = show_schema(
        cmd=mocked_cmd,
        schema_name=schema_name,
        schema_registry_name=registery_name,
        resource_group_name=resource_group_name
    )

    assert result == mock_schema_registry_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_schema_list(mocked_cmd, mocked_responses: responses, records: int):
    resource_group_name = generate_random_string()
    registry_name = generate_random_string()
    mock_schema_registry_records = {
        "value": [
            get_mock_schema_record(
                name=generate_random_string(),
                registry_name=registry_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
        ),
        json=mock_schema_registry_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_schemas(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        schema_registry_name=registry_name
    ))

    assert result == mock_schema_registry_records["value"]
    assert len(mocked_responses.calls) == 1


def test_schema_delete(mocked_cmd, mocked_responses: responses):
    schema_name = generate_random_string()
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registery_name,
            schema_name=schema_name
        ),
        status=200,
        content_type="application/json",
    )
    delete_schema(
        cmd=mocked_cmd,
        schema_name=schema_name,
        schema_registry_name=registery_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
    )
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "schema_format",
    ["delta", "json"]
)
@pytest.mark.parametrize(
    "schema_type",
    ["MessageSchema"],
)
@pytest.mark.parametrize(
    "display_name,description",
    [
        (None, None),
        (generate_random_string(), generate_random_string()),
    ],
)
def test_schema_create(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    schema_type: str,
    schema_format: str,
    display_name: Optional[str],
    description: Optional[str],
):
    schema_name = generate_random_string()
    registery_name = generate_random_string()
    resource_group_name = generate_random_string()

    create_registry_kwargs = {
        "cmd": mocked_cmd,
        "schema_name": schema_name,
        "schema_format": schema_format,
        "schema_type": schema_type,
        "schema_registry_name": registery_name,
        "resource_group_name": resource_group_name,
        "display_name": display_name,
        "description": description,
    }

    mock_registry_record = get_mock_schema_record(
        name=schema_name,
        registry_name=registery_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registery_name,
            schema_name=schema_name
        ),
        json=mock_registry_record,
        status=200,
    )

    create_result = create_schema(**create_registry_kwargs)
    assert create_result == mock_registry_record
    schema_registry_create_payload = json.loads(
        mocked_responses.calls[-1].request.body
    )
    assert schema_registry_create_payload["properties"]["format"] == SchemaFormat[schema_format].full_value
    assert schema_registry_create_payload["properties"]["schemaType"] == schema_type
    assert schema_registry_create_payload["properties"]["description"] == description
    assert schema_registry_create_payload["properties"]["displayName"] == display_name
