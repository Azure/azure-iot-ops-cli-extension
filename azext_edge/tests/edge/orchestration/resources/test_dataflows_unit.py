# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_dataflow import show_dataflow, list_dataflows

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_dataflow_endpoint(
    profile_name: str, instance_name: str, resource_group_name: str, dataflow_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/dataflowProfiles/{profile_name}/dataflows"
    if dataflow_name:
        resource_path += f"/{dataflow_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_dataflow_record(
    dataflow_name: str, profile_name: str, instance_name: str, resource_group_name: str
) -> dict:
    return get_mock_resource(
        name=dataflow_name,
        resource_path=f"/instances/{instance_name}/dataflowProfiles/{profile_name}/dataflows/{dataflow_name}",
        properties={
            "operations": [
                {
                    "sourceSettings": {"dataSources": ["test/#"], "serializationFormat": "Json"},
                    "destinationSettings": {"dataDestination": "$topic", "endpointRef": "mykafkaendpoint"},
                }
            ],
            "profileRef": "mydataflowprofile",
            "mode": "Enabled",
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
    )


def test_dataflow_profile_show(mocked_cmd, mocked_responses: responses):
    dataflow_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_record = get_mock_dataflow_record(
        dataflow_name=dataflow_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint(
            dataflow_name=dataflow_name,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            profile_name=profile_name,
        ),
        json=mock_dataflow_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow(
        cmd=mocked_cmd,
        dataflow_name=dataflow_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_dataflow_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_dataflow_profile_list(mocked_cmd, mocked_responses: responses, records: int):
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_records = {
        "value": [
            get_mock_dataflow_record(
                dataflow_name=generate_random_string(),
                profile_name=profile_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint(
            profile_name=profile_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_dataflow_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflows(
            cmd=mocked_cmd,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_dataflow_records["value"]
    assert len(mocked_responses.calls) == 1
