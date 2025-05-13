# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional
from unittest.mock import Mock

import pytest
import responses

from azext_edge.edge.commands_mq import (
    delete_broker_authz,
    list_broker_authzs,
    show_broker_authz,
    apply_broker_authz,
)

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource
from .test_instances_unit import get_instance_endpoint, get_mock_instance_record
from azext_edge.edge.common import DEFAULT_BROKER


def get_broker_authz_endpoint(
    instance_name: str, broker_name: str, resource_group_name: str, authz_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/brokers/{broker_name}/authorizations"
    if authz_name:
        resource_path += f"/{authz_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_authz_record(
    authz_name: str, broker_name: str, instance_name: str, resource_group_name: str
) -> dict:
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
        qualified_type="microsoft.iotoperations/instances/brokers/authorizations",
        is_proxy_resource=True,
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
        broker_name=broker_name,
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
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_broker_authz_records["value"]
    assert len(mocked_responses.calls) == 1


def test_broker_authz_delete(mocked_cmd, mocked_responses: responses):
    authz_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_broker_authz_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            authz_name=authz_name,
        ),
        status=204,
    )
    delete_broker_authz(
        cmd=mocked_cmd,
        authz_name=authz_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        {"file_payload": {generate_random_string(): generate_random_string()}},
        {
            "file_payload": {generate_random_string(): generate_random_string()},
            "broker_name": generate_random_string(),
        },
    ],
)
def test_broker_authz_apply(mocked_cmd, mocked_responses: responses, mocked_get_file_config: Mock, scenario: dict):
    authz_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    broker_name = scenario.get("broker_name")

    expected_payload = None
    file_payload = scenario.get("file_payload")
    if file_payload:
        expected_payload = file_payload
        expected_file_content = json.dumps(file_payload)
    mocked_get_file_config.return_value = expected_file_content

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    put_response = mocked_responses.add(
        method=responses.PUT,
        url=get_broker_authz_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            authz_name=authz_name,
        ),
        json=expected_payload,
        status=200,
    )
    kwargs = {}
    if broker_name:
        kwargs["broker_name"] = broker_name
    create_result = apply_broker_authz(
        cmd=mocked_cmd,
        authz_name=authz_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
        **kwargs,
    )
    assert len(mocked_responses.calls) == 2
    assert create_result == expected_payload
    request_payload = json.loads(put_response.calls[0].request.body)
    assert request_payload["extendedLocation"] == mock_instance_record["extendedLocation"]
