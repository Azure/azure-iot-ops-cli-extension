# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_dataflow import show_dataflow_profile, list_dataflow_profiles

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_dataflow_profile_endpoint(
    instance_name: str, resource_group_name: str, profile_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/dataflowProfiles"
    if profile_name:
        resource_path += f"/{profile_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_dataflow_profile_record(profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return get_mock_resource(
        name=profile_name,
        resource_path=f"/instances/{instance_name}/dataflowProfiles/{profile_name}",
        properties={
            "diagnostics": {
                "logs": {
                    "level": "info",
                    "opentelemetryExportConfig": {"otlpGrpcEndpoint": "", "intervalSeconds": 30, "level": "error"},
                },
                "metrics": {
                    "opentelemetryExportConfig": {"otlpGrpcEndpoint": "", "intervalSeconds": 30},
                    "prometheusPort": 9600,
                },
            },
            "instanceCount": 1,
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
    )


def test_dataflow_profile_show(mocked_cmd, mocked_responses: responses):
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_profile_record = get_mock_dataflow_profile_record(
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_profile_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            profile_name=profile_name,
        ),
        json=mock_dataflow_profile_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow_profile(
        cmd=mocked_cmd,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_dataflow_profile_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_dataflow_profile_list(mocked_cmd, mocked_responses: responses, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_profile_records = {
        "value": [
            get_mock_dataflow_profile_record(
                profile_name=generate_random_string(),
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_profile_endpoint(instance_name=instance_name, resource_group_name=resource_group_name),
        json=mock_dataflow_profile_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflow_profiles(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_dataflow_profile_records["value"]
    assert len(mocked_responses.calls) == 1
