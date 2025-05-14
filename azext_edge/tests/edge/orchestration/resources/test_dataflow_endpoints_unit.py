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

from azext_edge.edge.providers.orchestration.common import DATAFLOW_ENDPOINT_TYPE_SETTINGS
from azext_edge.edge.commands_dataflow import (
    apply_dataflow_endpoint,
    delete_dataflow_endpoint,
    show_dataflow_endpoint,
    list_dataflow_endpoints,
)
from azext_edge.tests.edge.orchestration.resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_dataflow_endpoint_endpoint(
    instance_name: str, resource_group_name: str, dataflow_endpoint_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/dataflowEndpoints"
    if dataflow_endpoint_name:
        resource_path += f"/{dataflow_endpoint_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_dataflow_endpoint_record(
    dataflow_endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    dataflow_endpoint_type: Optional[str] = None,
    host: Optional[str] = None,
    group_id: Optional[str] = None,
) -> dict:
    return get_mock_resource(
        name=dataflow_endpoint_name,
        resource_path=f"/instances/{instance_name}/dataflowEndpoints/{dataflow_endpoint_name}",
        properties={
            "authentication": {"method": "AccessToken"},
            "accessTokenSecretRef": "mysecret",
            "endpointType": dataflow_endpoint_type or "Kafka",
            DATAFLOW_ENDPOINT_TYPE_SETTINGS[dataflow_endpoint_type or "Kafka"]: {
                "tls": {"mode": "Enabled", "trustedCaCertificateConfigMapRef": "myconfigmap"},
                "host": host or "myhost",
                "consumerGroupId": group_id or "",
            },
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/dataflowendpoints",
        is_proxy_resource=True,
    )


def test_dataflow_endpoint_show(mocked_cmd, mocked_responses: responses):
    dataflow_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_endpoint_record = get_mock_dataflow_endpoint_record(
        dataflow_endpoint_name=dataflow_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=dataflow_endpoint_name,
        ),
        json=mock_dataflow_endpoint_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow_endpoint(
        cmd=mocked_cmd,
        endpoint_name=dataflow_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_dataflow_endpoint_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_dataflow_endpoint_list(mocked_cmd, mocked_responses: responses, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_endpoint_records = {
        "value": [
            get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name=generate_random_string(),
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(instance_name=instance_name, resource_group_name=resource_group_name),
        json=mock_dataflow_endpoint_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflow_endpoints(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_dataflow_endpoint_records["value"]
    assert len(mocked_responses.calls) == 1


def test_dataflow_endpoint_delete(mocked_cmd, mocked_responses: responses):
    dataflow_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_dataflow_endpoint_endpoint(
            dataflow_endpoint_name=dataflow_endpoint_name,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        status=204,
    )
    delete_dataflow_endpoint(
        cmd=mocked_cmd,
        endpoint_name=dataflow_endpoint_name,
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
    ],
)
def test_dataflow_endpoint_apply(mocked_cmd, mocked_responses: responses, mocked_get_file_config: Mock, scenario: dict):
    dataflow_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

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
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=dataflow_endpoint_name,
        ),
        json=expected_payload,
        status=200,
    )
    kwargs = {}
    create_result = apply_dataflow_endpoint(
        cmd=mocked_cmd,
        endpoint_name=dataflow_endpoint_name,
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
