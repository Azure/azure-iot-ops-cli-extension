# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from unittest.mock import Mock

import pytest
import responses

from azext_edge.edge.providers.orchestration.common import DATAFLOW_ENDPOINT_TYPE_SETTINGS
from ..test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)

from .....generators import generate_random_string
from ..conftest import get_base_endpoint, get_mock_resource


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
            DATAFLOW_ENDPOINT_TYPE_SETTINGS[dataflow_endpoint_type or "CustomKafka"]: {
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


def assert_dataflow_endpoint_create_update(
    mocked_responses: Mock,
    expected_payload: dict,
    mocked_cmd: Mock,
    params: dict,
    dataflow_endpoint_func: callable = None,
    is_update: bool = False,
    updating_payload: Optional[dict] = None,
):
    dataflow_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

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

    if is_update:
        mocked_responses.add(
            method=responses.GET,
            url=get_dataflow_endpoint_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=dataflow_endpoint_name,
            ),
            json=updating_payload,
            status=200,
        )

    kwargs = params.copy()
    create_result = dataflow_endpoint_func(
        cmd=mocked_cmd,
        endpoint_name=dataflow_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        show_config=True,
        **kwargs,
    )

    assert create_result == expected_payload


def assert_dataflow_endpoint_create_update_with_error(
    mocked_responses: Mock,
    expected_error_type: type,
    expected_error_text: str,
    mocked_cmd: Mock,
    params: dict,
    dataflow_endpoint_func: callable = None,
    is_update: bool = False,
    updating_payload: Optional[dict] = None,
):
    dataflow_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

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

    if is_update:
        mocked_responses.add(
            method=responses.GET,
            url=get_dataflow_endpoint_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=dataflow_endpoint_name,
            ),
            json=updating_payload,
            status=200,
        )

    kwargs = params.copy()
    with pytest.raises(expected_error_type) as e:
        dataflow_endpoint_func(
            cmd=mocked_cmd,
            endpoint_name=dataflow_endpoint_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            show_config=True,
            **kwargs,
        )

    assert expected_error_text in e.value.args[0]
