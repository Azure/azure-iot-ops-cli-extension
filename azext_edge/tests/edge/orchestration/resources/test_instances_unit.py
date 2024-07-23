# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_edge import list_instances, show_instance, update_instance

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_instance_endpoint(resource_group_name: Optional[str] = None, instance_name: Optional[str] = None):
    resource_path = "/instances"
    if instance_name:
        resource_path += f"/{instance_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_instance_record(name: str, resource_group_name: str):
    return get_mock_resource(
        name=name,
        properties={"description": "AIO Instance description.", "provisioningState": "Succeeded"},
        resource_group_name=resource_group_name,
    )


def test_instance_show(mocked_cmd, mocked_responses: responses):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    result = show_instance(cmd=mocked_cmd, instance_name=instance_name, resource_group_name=resource_group_name)

    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "resource_group_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_instance_list(mocked_cmd, mocked_responses: responses, resource_group_name: str, records: int):
    # If no resource_group_name, oh well
    mock_instance_records = {
        "value": [
            get_mock_instance_record(name=generate_random_string(), resource_group_name=resource_group_name)
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(resource_group_name=resource_group_name),
        json=mock_instance_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_instances(cmd=mocked_cmd, resource_group_name=resource_group_name))

    assert result == mock_instance_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "description",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "tags",
    [None, {"a": "b", "c": "d"}],
)
def test_instance_update(mocked_cmd, mocked_responses: responses, description: Optional[str], tags: Optional[dict]):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PUT,
        url=instance_endpoint,
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    result = update_instance(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        instance_description=description,
        wait_sec=0.5,
    )
    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 2

    update_request = json.loads(mocked_responses.calls[1].request.body)
    if description:
        assert update_request["properties"]["description"] == description

    if tags:
        assert update_request["tags"] == tags

    if not any([description, tags]):
        assert update_request == mock_instance_record
