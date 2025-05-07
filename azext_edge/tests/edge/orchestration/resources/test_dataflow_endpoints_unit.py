# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_dataflow import show_dataflow_endpoint, list_dataflow_endpoints

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
    dataflow_endpoint_name: str, instance_name: str, resource_group_name: str
) -> dict:
    return get_mock_resource(
        name=dataflow_endpoint_name,
        resource_path=f"/instances/{instance_name}/dataflowEndpoints/{dataflow_endpoint_name}",
        properties={
            "authentication": {"method": "AccessToken"},
            "accessTokenSecretRef": "mysecret",
            "endpointType": "Kafka",
            "kafkaSettings": {"tls": {"mode": "Enabled", "trustedCaCertificateConfigMapRef": "myconfigmap"}},
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
