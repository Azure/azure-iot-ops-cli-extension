# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses

from azext_edge.edge.commands_dataflow import (
    list_dataflow_graph_registries,
    remove_dataflow_graph_registry,
    show_dataflow_graph_registry,
)

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_registry_endpoint_endpoint(
    instance_name: str, resource_group_name: str, registry_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/registryEndpoints"
    if registry_name:
        resource_path += f"/{registry_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_registry_endpoint_record(
    registry_name: str, instance_name: str, resource_group_name: str, host: str = "myregistry.azurecr.io"
) -> dict:
    return get_mock_resource(
        name=registry_name,
        resource_path=f"/instances/{instance_name}/registryEndpoints/{registry_name}",
        properties={
            "host": host,
            "authentication": {"method": "Anonymous"},
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/registryendpoints",
        is_proxy_resource=True,
    )


def test_registry_endpoint_show(mocked_cmd, mocked_responses: responses):
    registry_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_registry_record = get_mock_registry_endpoint_record(
        registry_name=registry_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_name=registry_name,
        ),
        json=mock_registry_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow_graph_registry(
        cmd=mocked_cmd,
        registry_name=registry_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_registry_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("records", [0, 2])
def test_registry_endpoint_list(mocked_cmd, mocked_responses: responses, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_registry_records = {
        "value": [
            get_mock_registry_endpoint_record(
                registry_name=generate_random_string(),
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                host=f"registry{i}.azurecr.io",
            )
            for i in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(instance_name=instance_name, resource_group_name=resource_group_name),
        json=mock_registry_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflow_graph_registries(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_registry_records["value"]
    assert len(mocked_responses.calls) == 1


def test_registry_endpoint_remove(mocked_cmd, mocked_responses: responses):
    registry_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_name=registry_name,
        ),
        status=204,
    )

    remove_dataflow_graph_registry(
        cmd=mocked_cmd,
        registry_name=registry_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0,
    )

    assert len(mocked_responses.calls) == 1
