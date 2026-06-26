# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from unittest.mock import Mock

import pytest
import responses

from azext_edge.edge.commands_dataflow import (
    apply_dataflow_endpoint,
    delete_dataflow_endpoint,
    show_dataflow_endpoint,
    list_dataflow_endpoints,
)
from .conftest import get_dataflow_endpoint_endpoint, get_mock_dataflow_endpoint_record
from ..test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)

from .....generators import generate_random_string


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


def _make_endpoint_provider(cloud_name: str):
    # Bypass the heavy __init__ (which builds mgmt clients); we only need self.cmd
    # to exercise _get_endpoint_host's cloud-aware construction.
    from azext_edge.edge.providers.orchestration.resources.dataflows import DataFlowEndpoints
    from azext_edge.tests.helpers import build_mock_cmd_for_cloud

    provider = DataFlowEndpoints.__new__(DataFlowEndpoints)
    provider.cmd = build_mock_cmd_for_cloud(cloud_name)
    return provider


@pytest.mark.parametrize(
    "cloud_name, expected_suffix",
    [
        ("AzureCloud", "core.windows.net"),
        ("AzureUSGovernment", "core.usgovcloudapi.net"),
        ("AzureChinaCloud", "core.chinacloudapi.cn"),
    ],
)
def test_adls_host_uses_cloud_storage_suffix(cloud_name, expected_suffix):
    from azext_edge.edge.providers.orchestration.common import DataflowEndpointType

    provider = _make_endpoint_provider(cloud_name)
    account = generate_random_string()

    host = provider._get_endpoint_host(
        endpoint_type=DataflowEndpointType.DATALAKESTORAGE.value,
        storage_account_name=account,
    )

    assert host == f"https://{account}.blob.{expected_suffix}"


@pytest.mark.parametrize(
    "cloud_name, expected_suffix",
    [
        ("AzureCloud", "servicebus.windows.net"),
        ("AzureUSGovernment", "servicebus.usgovcloudapi.net"),
        ("AzureChinaCloud", "servicebus.chinacloudapi.cn"),
    ],
)
def test_eventhub_host_uses_cloud_servicebus_suffix(cloud_name, expected_suffix):
    from azext_edge.edge.providers.orchestration.common import DataflowEndpointType

    provider = _make_endpoint_provider(cloud_name)
    namespace = generate_random_string()

    host = provider._get_endpoint_host(
        endpoint_type=DataflowEndpointType.EVENTHUB.value,
        eventhub_namespace=namespace,
    )

    assert host == f"{namespace}.{expected_suffix}:9093"


def test_fabric_onelake_allowed_in_public():
    from azext_edge.edge.providers.orchestration.common import DataflowEndpointType

    provider = _make_endpoint_provider("AzureCloud")

    host = provider._get_endpoint_host(endpoint_type=DataflowEndpointType.FABRICONELAKE.value)

    assert host == "https://onelake.dfs.fabric.microsoft.com"


@pytest.mark.parametrize("cloud_name", ["AzureUSGovernment", "AzureChinaCloud"])
def test_fabric_onelake_blocked_in_non_public(cloud_name):
    from azure.cli.core.azclierror import InvalidArgumentValueError
    from azext_edge.edge.providers.orchestration.common import DataflowEndpointType

    provider = _make_endpoint_provider(cloud_name)

    with pytest.raises(InvalidArgumentValueError) as exc:
        provider._get_endpoint_host(endpoint_type=DataflowEndpointType.FABRICONELAKE.value)

    assert "Fabric OneLake" in str(exc.value)
    assert "Azure Public Cloud" in str(exc.value)
