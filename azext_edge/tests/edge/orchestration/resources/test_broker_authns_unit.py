# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_mq import show_broker_authn, list_broker_authns, delete_broker_authn

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_broker_authn_endpoint(
    instance_name: str, broker_name: str, resource_group_name: str, authn_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/brokers/{broker_name}/authentications"
    if authn_name:
        resource_path += f"/{authn_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_authn_record(
    authn_name: str, broker_name: str, instance_name: str, resource_group_name: str
) -> dict:
    return get_mock_resource(
        name=authn_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}/authentications/{authn_name}",
        properties={
            "authenticationMethods": [
                {"method": "ServiceAccountToken", "serviceAccountToken": {"audiences": ["aio-mq"]}}
            ],
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
    )


def test_broker_authn_show(mocked_cmd, mocked_responses: responses):
    authn_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_authn_record = get_mock_broker_authn_record(
        authn_name=authn_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authn_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            authn_name=authn_name,
        ),
        json=mock_broker_authn_record,
        status=200,
        content_type="application/json",
    )

    result = show_broker_authn(
        cmd=mocked_cmd,
        authn_name=authn_name,
        mq_broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_broker_authn_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_authn_list(mocked_cmd, mocked_responses: responses, records: int):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_authn_records = {
        "value": [
            get_mock_broker_authn_record(
                authn_name=generate_random_string(),
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authn_endpoint(
            broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_broker_authn_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_broker_authns(
            cmd=mocked_cmd,
            mq_broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_broker_authn_records["value"]
    assert len(mocked_responses.calls) == 1


def test_broker_authn_delete(mocked_cmd, mocked_responses: responses):
    authn_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_broker_authn_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            authn_name=authn_name,
        ),
        status=204,
    )
    delete_broker_authn(
        cmd=mocked_cmd,
        authn_name=authn_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1
