# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_mq import show_broker_authz, list_broker_authzs

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_broker_authz_endpoint(
    instance_name: str, broker_name: str, resource_group_name: str, authz_name: Optional[str] = None
):
    resource_path = f"/instances/{instance_name}/brokers/{broker_name}/authorizations"
    if authz_name:
        resource_path += f"/{authz_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_authz_record(authz_name: str, broker_name: str, instance_name: str, resource_group_name: str):
    return get_mock_resource(
        name=authz_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}/authorizations/{authz_name}",
        properties={
            "authorizationPolicies": {
                "cache": "Disabled",
                "rules": {
                    "brokerResources": [{"method": "Connect", "topics": ["*"]}],
                    "principals": {"attributes": [], "clientIds": [], "usernames": []},
                    "stateStoreResources": [],
                },
            },
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
    )


def test_broker_authz_show(mocked_cmd, mocked_responses: responses):
    authz_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_authz_record = get_mock_broker_authz_record(
        authz_name=authz_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authz_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            authz_name=authz_name,
        ),
        json=mock_broker_authz_record,
        status=200,
        content_type="application/json",
    )

    result = show_broker_authz(
        cmd=mocked_cmd,
        authz_name=authz_name,
        mq_broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_broker_authz_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_authz_list(mocked_cmd, mocked_responses: responses, records: int):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_authz_records = {
        "value": [
            get_mock_broker_authz_record(
                authz_name=generate_random_string(),
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authz_endpoint(
            broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_broker_authz_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_broker_authzs(
            cmd=mocked_cmd,
            mq_broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_broker_authz_records["value"]
    assert len(mocked_responses.calls) == 1
