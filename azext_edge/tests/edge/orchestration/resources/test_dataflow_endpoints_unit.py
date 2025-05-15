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

from azure.core.exceptions import ResourceNotFoundError
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.providers.orchestration.common import DATAFLOW_ENDPOINT_TYPE_SETTINGS
from azext_edge.edge.commands_dataflow import (
    apply_dataflow_endpoint,
    create_dataflow_endpoint_adls,
    create_dataflow_endpoint_adx,
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


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # uami without authentication type
        (
            {
                "host": "https://cluster.region.kusto.windows.net",
                "database_name": "mydb",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
            },
            {
                "dataExplorerSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "database": "mydb",
                    "host": "https://cluster.region.kusto.windows.net",
                },
                "endpointType": "DataExplorer",
            },
        ),
        # uami with authentication type
        (
            {
                "host": "https://cluster.region.kusto.windows.net",
                "database_name": "mydb",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "dataExplorerSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "database": "mydb",
                    "host": "https://cluster.region.kusto.windows.net",
                },
                "endpointType": "DataExplorer",
            },
        ),
        # sami without authentication type
        (
            {
                "host": "https://cluster.region.kusto.windows.net",
                "database_name": "mydb",
                "audience": "audience",
                "latency": 1,
                "message_count": 1,
            },
            {
                "dataExplorerSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "database": "mydb",
                    "host": "https://cluster.region.kusto.windows.net",
                },
                "endpointType": "DataExplorer",
            },
        ),
        # sami with authentication type
        (
            {
                "host": "https://cluster.region.kusto.windows.net",
                "database_name": "mydb",
                "audience": "audience",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "dataExplorerSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "database": "mydb",
                    "host": "https://cluster.region.kusto.windows.net",
                },
                "endpointType": "DataExplorer",
            },
        ),
    ]
)
def test_dataflow_endpoint_create_adx(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
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

    kwargs = params.copy()
    create_result = create_dataflow_endpoint_adx(
        cmd=mocked_cmd,
        endpoint_name=dataflow_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        show_config=True,
        **kwargs,
    )

    assert create_result == expected_payload


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_message",
    [
        # unsupported authentication type
        (
            {
                "host": "https://cluster.region.kusto.windows.net",
                "database_name": "mydb",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is not allowed for endpoint type 'DataExplorer'. Allowed methods are: ['SystemAssignedManagedIdentity', 'UserAssignedManagedIdentity'].",
        ),
        # missing required parameters for uami
        (
            {
                "host": "https://cluster.region.kusto.windows.net",
                "database_name": "mydb",
                "latency": 1,
                "message_count": 1,
                "client_id": "client_id",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': tenant_id.",
        ),
    ]
)
def test_dataflow_endpoint_create_adx_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_message: str,
    mocked_responses: Mock,
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

    kwargs = params.copy()
    with pytest.raises(expected_error_type) as e:
        create_dataflow_endpoint_adx(
            cmd=mocked_cmd,
            endpoint_name=dataflow_endpoint_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            show_config=True,
            **kwargs,
        )

    assert expected_error_message in e.value.args[0]


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # uami without authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
            },
            {
                "dataLakeStorageSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
        # uami with authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "dataLakeStorageSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
        # sami without authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "audience": "audience",
                "latency": 1,
                "message_count": 1,
            },
            {
                "dataLakeStorageSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
        # sami with authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "audience": "audience",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "dataLakeStorageSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
        # access token without authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "latency": 1,
                "message_count": 1,
                "secret_name": "mysecret",
            },
            {
                "dataLakeStorageSettings": {
                    "authentication": {
                        "method": "AccessToken",
                        "accessTokenSettings": {
                            "secretRef": "mysecret"
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
        # access token with authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "latency": 1,
                "message_count": 1,
                "secret_name": "mysecret",
                "authentication_type": "AccessToken",
            },
            {
                "dataLakeStorageSettings": {
                    "authentication": {
                        "method": "AccessToken",
                        "accessTokenSettings": {
                            "secretRef": "mysecret"
                        },
                    },
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
    ]
)
def test_dataflow_endpoint_create_adls(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
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

    kwargs = params.copy()
    create_result = create_dataflow_endpoint_adls(
        cmd=mocked_cmd,
        endpoint_name=dataflow_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        show_config=True,
        **kwargs,
    )

    assert create_result == expected_payload


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "storage_account_name": "mystorageaccount",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is not allowed for endpoint type 'DataLakeStorage'. Allowed methods are: ['AccessToken', 'SystemAssignedManagedIdentity', 'UserAssignedManagedIdentity'].",
        ),
        # missing required parameters for uami
        (
            {
                "storage_account_name": "mystorageaccount",
                "latency": 1,
                "message_count": 1,
                "client_id": "client_id",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': tenant_id.",
        ),
    ]
)
def test_dataflow_endpoint_create_adls_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
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

    kwargs = params.copy()
    with pytest.raises(expected_error_type) as e:
        create_dataflow_endpoint_adls(
            cmd=mocked_cmd,
            endpoint_name=dataflow_endpoint_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            show_config=True,
            **kwargs,
        )

    assert expected_error_text in e.value.args[0]
