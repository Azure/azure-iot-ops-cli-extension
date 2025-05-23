# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from unittest.mock import Mock

import pytest
import responses

from .conftest import get_dataflow_endpoint_endpoint
from ..test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)

from .....generators import generate_random_string


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
