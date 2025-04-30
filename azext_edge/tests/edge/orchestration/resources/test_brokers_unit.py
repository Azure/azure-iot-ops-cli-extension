# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_mq import list_brokers, show_broker, delete_broker

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_broker_endpoint(instance_name: str, resource_group_name: str, broker_name: Optional[str] = None) -> str:
    resource_path = f"/instances/{instance_name}/brokers"
    if broker_name:
        resource_path += f"/{broker_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_record(broker_name: str, instance_name: str, resource_group_name: str) -> dict:
    return get_mock_resource(
        name=broker_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}",
        properties={
            "advanced": {"encryptInternalTraffic": "Enabled"},
            "cardinality": {
                "backendChain": {"partitions": 2, "redundancyFactor": 2, "workers": 2},
                "frontend": {"replicas": 2, "workers": 2},
            },
            "diagnostics": {
                "logs": {"level": "info"},
                "metrics": {"prometheusPort": 9600},
                "selfCheck": {"intervalSeconds": 30, "mode": "Enabled", "timeoutSeconds": 15},
                "traces": {
                    "cacheSizeMegabytes": 16,
                    "mode": "Enabled",
                    "selfTracing": {"intervalSeconds": 30, "mode": "Enabled"},
                    "spanChannelCapacity": 1000,
                },
            },
            "generateResourceLimits": {"cpu": "Disabled"},
            "memoryProfile": "Medium",
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/brokers"
    )


def test_broker_show(mocked_cmd, mocked_responses: responses):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_record = get_mock_broker_record(
        broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_broker_endpoint(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        ),
        json=mock_broker_record,
        status=200,
        content_type="application/json",
    )

    result = show_broker(
        cmd=mocked_cmd,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )
    assert result == mock_broker_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_list(mocked_cmd, mocked_responses: responses, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_records = {
        "value": [
            get_mock_broker_record(
                broker_name=generate_random_string(),
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_endpoint(instance_name=instance_name, resource_group_name=resource_group_name),
        json=mock_broker_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_brokers(cmd=mocked_cmd, instance_name=instance_name, resource_group_name=resource_group_name))
    assert result == mock_broker_records["value"]
    assert len(mocked_responses.calls) == 1


def test_broker_delete(mocked_cmd, mocked_responses: responses):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_broker_endpoint(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        ),
        status=204,
    )
    delete_broker(
        cmd=mocked_cmd,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1
