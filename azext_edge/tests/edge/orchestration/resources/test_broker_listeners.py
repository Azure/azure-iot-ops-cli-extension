# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.providers.orchestration.resources import Brokers

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_broker_listener_endpoint(
    instance_name: str, broker_name: str, resource_group_name: str, listener_name: Optional[str] = None
):
    resource_path = f"/instances/{instance_name}/brokers/{broker_name}/listeners"
    if listener_name:
        resource_path += f"/{listener_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_listener_record(
    listener_name: str, broker_name: str, instance_name: str, resource_group_name: str
):
    return get_mock_resource(
        name=broker_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}/listeners/{listener_name}",
        properties={
            "brokerRef": broker_name,
            "ports": [
                {
                    "authenticationRef": "authn",
                    "port": 8883,
                    "protocol": "Mqtt",
                    "tls": {
                        "automatic": {
                            "issuerRef": {"apiGroup": "cert-manager.io", "kind": "Issuer", "name": "mq-dmqtt-frontend"}
                        },
                        "mode": "Automatic",
                    },
                }
            ],
            "provisioningState": "Succeeded",
            "serviceName": "aio-mq-dmqtt-frontend",
            "serviceType": "ClusterIp",
        },
        resource_group_name=resource_group_name,
    )


def test_broker_listener_show(mocked_cmd, mocked_responses: responses):
    listener_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_listener_record = get_mock_broker_listener_record(
        listener_name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_broker_listener_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            listener_name=listener_name,
        ),
        json=mock_broker_listener_record,
        status=200,
        content_type="application/json",
    )

    brokers = Brokers(mocked_cmd)
    result = brokers.listeners.show(
        name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )
    assert result == mock_broker_listener_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_list(mocked_cmd, mocked_responses: responses, records: int):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_listener_records = {
        "value": [
            get_mock_broker_listener_record(
                listener_name=generate_random_string(),
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_listener_endpoint(
            broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_broker_listener_records,
        status=200,
        content_type="application/json",
    )

    brokers = Brokers(mocked_cmd)
    result = list(
        brokers.listeners.list(
            broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
        )
    )
    assert result == mock_broker_listener_records["value"]
    assert len(mocked_responses.calls) == 1
