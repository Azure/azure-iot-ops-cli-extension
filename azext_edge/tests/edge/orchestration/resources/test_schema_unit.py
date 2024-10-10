# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from random import randint
from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_schema import (
    create_schema,
    delete_schema,
    list_schemas,
    show_schema,
    add_version,
    show_version,
    list_versions,
    remove_version
)
from azext_edge.edge.providers.orchestration.common import SchemaFormat, SchemaType
from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource

SCHEMA_RP = "Microsoft.DeviceRegistry"
SCHEMA_REGISTRY_RP_API_VERSION = "2024-09-01-preview"


def get_schema_endpoint(
    resource_group_name: str,
    registry_name: str,
    schema_name: Optional[str] = None
) -> str:
    resource_path = f"/schemaRegistries/{registry_name}/schemas"
    if schema_name:
        resource_path += f"/{schema_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=SCHEMA_RP,
        api_version=SCHEMA_REGISTRY_RP_API_VERSION,
    )


def get_schema_version_endpoint(
    resource_group_name: str,
    registry_name: str,
    schema_name: str,
    schema_version: Optional[str] = None
) -> str:
    resource_path = "/schemaVersions"
    if schema_version:
        resource_path += f"/{schema_version}"
    resource_path = get_schema_endpoint(
        resource_group_name=resource_group_name,
        registry_name=registry_name,
        schema_name=schema_name + resource_path
    )
    return resource_path


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


def get_mock_schema_version_record(
    name: int,
    schema_name: str,
    registry_name: str,
    resource_group_name: str
) -> dict:
    record = get_mock_resource(
        name=str(name),
        resource_provider=SCHEMA_RP,
        resource_path=f"/schemaRegistries/{registry_name}/schemas/{schema_name}/schemaVersions/{name}",
        properties={
            "provisioningState": "Succeeded",
            "uuid": "4630b849-a08a-44f9-af0a-9821098b1b1e",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.deviceregistry/schemaregistries/schemas/schemaversions",
    )
    record.pop("extendedLocation")
    record.pop("location")
    return record


def test_schema_show(mocked_cmd, mocked_responses: responses):
    schema_name = generate_random_string()
    registry_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_record = get_mock_schema_record(
        name=schema_name,
        registry_name=registry_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name
        ),
        json=mock_record,
        status=200,
        content_type="application/json",
    )
    result = show_schema(
        cmd=mocked_cmd,
        schema_name=schema_name,
        schema_registry_name=registry_name,
        resource_group_name=resource_group_name
    )

    assert result == mock_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_schema_list(mocked_cmd, mocked_responses: responses, records: int):
    resource_group_name = generate_random_string()
    registry_name = generate_random_string()
    mock_records = {
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
        json=mock_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_schemas(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        schema_registry_name=registry_name
    ))

    assert result == mock_records["value"]
    assert len(mocked_responses.calls) == 1


def test_schema_delete(mocked_cmd, mocked_responses: responses):
    schema_name = generate_random_string()
    registry_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name
        ),
        status=200,
        content_type="application/json",
    )
    delete_schema(
        cmd=mocked_cmd,
        schema_name=schema_name,
        schema_registry_name=registry_name,
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
    ["message"],
)
@pytest.mark.parametrize(
    "display_name,description,version_num,version_description",
    [
        (None, None, None, None),
        (generate_random_string(), generate_random_string(), randint(2, 10), generate_random_string()),
    ],
)
def test_schema_create(
    mocked_cmd,
    mocked_responses: responses,
    schema_type: str,
    schema_format: str,
    display_name: Optional[str],
    description: Optional[str],
    version_num: Optional[int],
    version_description: Optional[str]
):
    schema_name = generate_random_string()
    registry_name = generate_random_string()
    resource_group_name = generate_random_string()
    schema_content = generate_random_string()

    create_registry_kwargs = {
        "cmd": mocked_cmd,
        "schema_name": schema_name,
        "schema_format": schema_format,
        "schema_type": schema_type,
        "schema_registry_name": registry_name,
        "resource_group_name": resource_group_name,
        "display_name": display_name,
        "description": description,
        "schema_content": schema_content,
        "schema_version_description": version_description
    }
    if version_num:
        create_registry_kwargs["schema_version"] = version_num

    mock_record = get_mock_schema_record(
        name=schema_name,
        registry_name=registry_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_schema_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name
        ),
        json=mock_record,
        status=200,
    )

    version_record = get_mock_schema_version_record(
        schema_name=schema_name,
        name=version_num or 1,
        registry_name=registry_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_schema_version_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name,
            schema_version=version_num or 1
        ),
        json=version_record,
        status=200,
        content_type="application/json",
    )

    create_result = create_schema(**create_registry_kwargs)
    assert create_result == mock_record
    create_payload = json.loads(
        mocked_responses.calls[-2].request.body
    )
    assert create_payload["properties"]["format"] == SchemaFormat[schema_format].full_value
    assert create_payload["properties"]["schemaType"] == SchemaType[schema_type].full_value
    assert create_payload["properties"]["description"] == description
    assert create_payload["properties"]["displayName"] == display_name

    version_payload = json.loads(
        mocked_responses.calls[-1].request.body
    )
    version_url = mocked_responses.calls[-1].request.url.split("?")[0]
    version_url = version_url.split("/")[-1]
    assert version_url == str(version_num or 1)
    assert version_payload["properties"]["schemaContent"] == schema_content
    assert version_payload["properties"]["description"] == version_description


def test_version_show(mocked_cmd, mocked_responses: responses):
    version_num = randint(1, 10)
    schema_name = generate_random_string()
    registry_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_record = get_mock_schema_version_record(
        schema_name=schema_name,
        name=version_num,
        registry_name=registry_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_schema_version_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name,
            schema_version=version_num
        ),
        json=mock_record,
        status=200,
        content_type="application/json",
    )
    result = show_version(
        cmd=mocked_cmd,
        version_name=version_num,
        schema_name=schema_name,
        schema_registry_name=registry_name,
        resource_group_name=resource_group_name
    )
    assert result == mock_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_version_list(mocked_cmd, mocked_responses: responses, records: int):
    resource_group_name = generate_random_string()
    registry_name = generate_random_string()
    schema_name = generate_random_string()
    mock_records = {
        "value": [
            get_mock_schema_version_record(
                schema_name=schema_name,
                name=randint(0, 10),
                registry_name=registry_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_schema_version_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name,
        ),
        json=mock_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_versions(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        schema_registry_name=registry_name,
        schema_name=schema_name
    ))

    assert result == mock_records["value"]
    assert len(mocked_responses.calls) == 1


def test_version_remove(mocked_cmd, mocked_responses: responses):
    version_num = randint(1, 10)
    schema_name = generate_random_string()
    registry_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_schema_version_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name,
            schema_version=version_num
        ),
        status=200,
        content_type="application/json",
    )
    remove_version(
        cmd=mocked_cmd,
        version_name=version_num,
        schema_name=schema_name,
        schema_registry_name=registry_name,
        resource_group_name=resource_group_name
    )
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("description", [None, generate_random_string()])
def test_version_add(mocked_cmd, mocked_responses: responses, description: Optional[str]):
    version_num = randint(1, 10)
    schema_name = generate_random_string()
    registry_name = generate_random_string()
    resource_group_name = generate_random_string()
    schema_content = generate_random_string()

    create_registry_kwargs = {
        "cmd": mocked_cmd,
        "version_name": version_num,
        "schema_name": schema_name,
        "schema_registry_name": registry_name,
        "resource_group_name": resource_group_name,
        "description": description,
        "schema_content": schema_content
    }

    mock_record = get_mock_schema_version_record(
        schema_name=schema_name,
        name=version_num,
        registry_name=registry_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_schema_version_endpoint(
            resource_group_name=resource_group_name,
            registry_name=registry_name,
            schema_name=schema_name,
            schema_version=version_num
        ),
        json=mock_record,
        status=200,
        content_type="application/json",
    )

    create_result = add_version(**create_registry_kwargs)
    assert create_result == mock_record
    create_payload = json.loads(
        mocked_responses.calls[-1].request.body
    )

    assert create_payload["properties"]["schemaContent"] == schema_content
    assert create_payload["properties"]["description"] == description


def test_version_add_error(mocked_cmd):
    from azure.cli.core.azclierror import InvalidArgumentValueError
    with pytest.raises(InvalidArgumentValueError):
        add_version(
            cmd=mocked_cmd,
            version_name=-1,
            schema_name=generate_random_string(),
            schema_registry_name=generate_random_string(),
            schema_content=generate_random_string(),
            resource_group_name=generate_random_string()
        )
