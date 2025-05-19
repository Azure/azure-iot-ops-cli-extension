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

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.providers.orchestration.common import DATAFLOW_ENDPOINT_TYPE_SETTINGS
from azext_edge.edge.commands_dataflow import (
    apply_dataflow_endpoint,
    create_dataflow_endpoint_adls,
    create_dataflow_endpoint_adx,
    create_dataflow_endpoint_aio,
    create_dataflow_endpoint_custom_kafka,
    create_dataflow_endpoint_custom_mqtt,
    create_dataflow_endpoint_eventgrid,
    create_dataflow_endpoint_eventhub,
    create_dataflow_endpoint_fabric_onelake,
    create_dataflow_endpoint_fabric_realtime,
    create_dataflow_endpoint_localstorage,
    delete_dataflow_endpoint,
    show_dataflow_endpoint,
    list_dataflow_endpoints,
    update_dataflow_endpoint_adls,
    update_dataflow_endpoint_adx,
    update_dataflow_endpoint_aio,
    update_dataflow_endpoint_custom_kafka,
    update_dataflow_endpoint_custom_mqtt,
    update_dataflow_endpoint_eventgrid,
    update_dataflow_endpoint_eventhub,
    update_dataflow_endpoint_fabric_onelake,
    update_dataflow_endpoint_fabric_realtime,
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
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_adx,
    )


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
            "Authentication method 'UnsupportedType' is not allowed for endpoint type 'DataExplorer'."
            " Allowed methods are: ['SystemAssignedManagedIdentity', 'UserAssignedManagedIdentity'].",
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
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': --tenant-id.",
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
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_message,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_adx,
    )


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
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_adls,
    )


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
            "Authentication method 'UnsupportedType' is "
            "not allowed for endpoint type 'DataLakeStorage'. "
            "Allowed methods are: ['AccessToken', "
            "'SystemAssignedManagedIdentity', 'UserAssignedManagedIdentity'].",
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
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': --tenant-id.",
        ),
        # missing required parameters for access token
        (
            {
                "storage_account_name": "mystorageaccount",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "AccessToken",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'AccessToken': --secret-name.",
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
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_adls,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # uami without authentication type
        (
            {
                "lakehouse_name": "mylakehouse",
                "workspace_name": "myworkspace",
                "path_type": "Files",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
            },
            {
                "endpointType": "FabricOneLake",
                "fabricOneLakeSettings": {
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
                    "host": "https://onelake.dfs.fabric.microsoft.com",
                    "names": {
                        "lakehouseName": "mylakehouse",
                        "workspaceName": "myworkspace",
                    },
                    "oneLakePathType": "Files",
                },
            },
        ),
        # uami with authentication type
        (
            {
                "lakehouse_name": "mylakehouse",
                "workspace_name": "myworkspace",
                "path_type": "Files",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "endpointType": "FabricOneLake",
                "fabricOneLakeSettings": {
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
                    "host": "https://onelake.dfs.fabric.microsoft.com",
                    "names": {
                        "lakehouseName": "mylakehouse",
                        "workspaceName": "myworkspace",
                    },
                    "oneLakePathType": "Files",
                },
            },
        ),
        # sami without authentication type
        (
            {
                "lakehouse_name": "mylakehouse",
                "workspace_name": "myworkspace",
                "path_type": "Files",
                "latency": 1,
                "message_count": 1,
                "audience": "audience",
            },
            {
                "endpointType": "FabricOneLake",
                "fabricOneLakeSettings": {
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
                    "host": "https://onelake.dfs.fabric.microsoft.com",
                    "names": {
                        "lakehouseName": "mylakehouse",
                        "workspaceName": "myworkspace",
                    },
                    "oneLakePathType": "Files",
                },
            },
        ),
        # sami with authentication type
        (
            {
                "lakehouse_name": "mylakehouse",
                "workspace_name": "myworkspace",
                "path_type": "Files",
                "latency": 1,
                "message_count": 1,
                "audience": "audience",
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "endpointType": "FabricOneLake",
                "fabricOneLakeSettings": {
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
                    "host": "https://onelake.dfs.fabric.microsoft.com",
                    "names": {
                        "lakehouseName": "mylakehouse",
                        "workspaceName": "myworkspace",
                    },
                    "oneLakePathType": "Files",
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_fabric_onelake(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_fabric_onelake,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "lakehouse_name": "mylakehouse",
                "workspace_name": "myworkspace",
                "path_type": "Files",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "latency": 1,
                "message_count": 1,
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is "
            "not allowed for endpoint type 'FabricOneLake'. "
            "Allowed methods are: ['SystemAssignedManagedIdentity', "
            "'UserAssignedManagedIdentity'].",
        ),
        # missing required parameters for uami
        (
            {
                "lakehouse_name": "mylakehouse",
                "workspace_name": "myworkspace",
                "path_type": "Files",
                "latency": 1,
                "message_count": 1,
                "client_id": "client_id",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': --tenant-id.",
        ),
    ]
)
def test_dataflow_endpoint_create_fabric_onelake_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_fabric_onelake,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # uami without authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "myeventhubnamespace.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # uami with authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "myeventhubnamespace.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sami without authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "audience": "audience",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "myeventhubnamespace.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sami with authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "audience": "audience",
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "myeventhubnamespace.servicebus.windows.net:9093",
                    "kafkaAcks": "All",
                    "partitionStrategy": "Default",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sasl without authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "secret_name": "secret",
                "sasl_type": "Plain",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings" : {
                            "secretRef" : "secret",
                            "saslType" : "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "myeventhubnamespace.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sasl with authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "secret_name": "secret",
                "sasl_type": "Plain",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
                "authentication_type": "Sasl",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings" : {
                            "secretRef" : "secret",
                            "saslType" : "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "myeventhubnamespace.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_eventhub(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_eventhub,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is "
            "not allowed for endpoint type 'EventHub'. "
            "Allowed methods are: ['Sasl', 'SystemAssignedManagedIdentity', "
            "'UserAssignedManagedIdentity'].",
        ),
        # missing required parameters for uami
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "tenant_id": "tenant_id",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': --client-id.",
        ),
        # missing required parameters for sasl
        (
            {
                "eventhub_namespace": "myeventhubnamespace",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
                "authentication_type": "Sasl",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'Sasl': --secret-name, --sasl-type.",
        ),
    ]
)
def test_dataflow_endpoint_create_eventhub_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_eventhub,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # uami without authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "tls_disabled": True,
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Disabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # uami with authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sami without authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "audience": "audience",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sami with authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "audience": "audience",
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sasl without authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "secret_name": "secret",
                "sasl_type": "Plain",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings" : {
                            "secretRef" : "secret",
                            "saslType" : "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sasl with authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "secret_name": "secret",
                "sasl_type": "Plain",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
                "authentication_type": "Sasl",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings" : {
                            "secretRef" : "secret",
                            "saslType" : "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_fabric_realtime(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_fabric_realtime,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is "
            "not allowed for endpoint type 'FabricRealTime'. "
            "Allowed methods are: ['Sasl', 'SystemAssignedManagedIdentity', "
            "'UserAssignedManagedIdentity'].",
        ),
        # missing required parameters for uami
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "tenant_id": "tenant_id",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                # missing client_id
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': --client-id.",
        ),
        # missing required parameters for sasl
        (
            {
                "host": "test.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "secret_name": "secret",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'Sasl': --sasl-type.",
        ),
    ],
)
def test_dataflow_endpoint_create_fabric_realtime_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_fabric_realtime,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # custom kafka without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "no_auth": True,
                "tls_disabled": True,
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Anonymous",
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Disabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # custom kafka uami with not authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # custom kafka uami with authentication type
        (
            {
                "hostname": "this.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "scope": "scope",
                            "tenantId": "tenant_id",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "this.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # custom kafka sami without authentication type
        (
            {
                "hostname": "this.servicebus.windows.net",
                "port": 9093,
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "audience": "audience",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "this.servicebus.windows.net:9093",
                    "kafkaAcks": "All",
                    "partitionStrategy": "Default",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # custom kafka sami with authentication type
        (
            {
                "hostname": "this.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "audience": "audience",
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings": {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "this.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # custom kafka sasl without authentication type
        (
            {
                "hostname": "this.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "secret_name": "secret",
                "sasl_type": "Plain",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings": {
                            "secretRef": "secret",
                            "saslType": "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "this.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # custom kafka sasl with authentication type
        (
            {
                "hostname": "this.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "secret_name": "secret",
                "sasl_type": "Plain",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "group_id": "mygroupid",
                "authentication_type": "Sasl",
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings": {
                            "secretRef": "secret",
                            "saslType": "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "this.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Property",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_custom_kafka(
    mocked_cmd,
    mocked_responses: Mock,
    params: dict,
    expected_payload: dict,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_custom_kafka,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "client_id": "client_id",
                "scope": "scope",
                "tenant_id": "tenant_id",
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' "
            "is not allowed for endpoint type 'CustomKafka'. "
            "Allowed methods are: ['Sasl', 'SystemAssignedManagedIdentity', "
            "'UserAssignedManagedIdentity'].",
        ),
        # missing required parameters for uami
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "tenant_id": "tenant_id",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                # missing client_id
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'UserAssignedManagedIdentity': --client-id.",
        ),
        # missing required parameters for sasl
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "acks": "One",
                "compression": "Gzip",
                "copy_broker_props_disabled": False,
                "group_id": "mygroupid",
                "partition_strategy": "Property",
                "batching_disabled": False,
                "latency": 1,
                "max_byte": 1,
                "message_count": 1,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "myconfigmap",
                "authentication_type": "Sasl",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'Sasl': --secret-name, --sasl-type.",
        ),
    ],
)
def test_dataflow_endpoint_create_custom_kafka_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_custom_kafka,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        (
            {
                "pvc_reference": "mypvc",
            },
            {
                "endpointType": "LocalStorage",
                "localStorageSettings": {
                    "persistentVolumeClaimRef": "mypvc",
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_localstorage(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_localstorage,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # service account token without authentication type
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "audience": "audience",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "audience": "audience",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "aio-broker:9093",
                    "keepAliveSeconds": 60,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                    },
                },
            },
        ),
        # service account token with authentication type
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "audience": "audience",
                "authentication_type": "ServiceAccountToken",
                "qos": 2,
                "retain": "Never",
                "session_expiry": 7200,
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "audience": "audience",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "aio-broker:9093",
                    "keepAliveSeconds": 60,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 2,
                    "retain": "Never",
                    "sessionExpirySeconds": 7200,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                    },
                },
            },
        ),
        # x509 without authentication type
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "secret_name": "secret",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "aio-broker:9093",
                    "keepAliveSeconds": 60,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                    },
                },
            },
        ),
        # x509 with authentication type
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "secret_name": "secret",
                "authentication_type": "X509Certificate",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "aio-broker:9093",
                    "keepAliveSeconds": 60,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                    },
                },
            },
        ),
        # no authentication
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "no_auth": True,
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "Anonymous",
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "aio-broker:9093",
                    "keepAliveSeconds": 60,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_aio(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_aio,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "audience": "audience",
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is "
            "not allowed for endpoint type 'AIOLocalMqtt'. "
            "Allowed methods are: ['ServiceAccountToken', 'X509Certificate'].",
        ),
        # missing required parameters for x509
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "authentication_type": "X509Certificate",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'X509Certificate': --secret-name.",
        ),
        # missing required parameters for service account token
        (
            {
                "hostname": "aio-broker",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "authentication_type": "ServiceAccountToken",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'ServiceAccountToken': --audience.",
        ),
    ],
)
def test_dataflow_endpoint_create_aio_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_aio,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # uami without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "client_id": "client_id",
                "tenant_id": "tenant_id",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "tenantId": "tenant_id",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # uami with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "client_id": "client_id",
                "tenant_id": "tenant_id",
                "authentication_type": "UserAssignedManagedIdentity",
                "config_map_reference": "myconfigmap",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "tenantId": "tenant_id",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # sami without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "audience": "audience",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings" : {
                            "audience": "audience",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # sami with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "SystemAssignedManagedIdentity",
                "config_map_reference": "myconfigmap",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings" : {},
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        # x509 without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "secret_name": "secret",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # x509 with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "secret_name": "secret",
                "authentication_type": "X509Certificate",
                "config_map_reference": "myconfigmap",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_eventgrid(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_eventgrid,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "audience": "audience",
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is not "
            "allowed for endpoint type 'EventGrid'. Allowed "
            "methods are: ['SystemAssignedManagedIdentity', "
            "'UserAssignedManagedIdentity', 'X509Certificate'].",
        ),
        # missing required parameters for x509
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "X509Certificate",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'X509Certificate': --secret-name.",
        ),
        # missing required parameters for uami
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "UserAssignedManagedIdentity",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method "
            "'UserAssignedManagedIdentity': --client-id, --tenant-id.",
        ),
    ],
)
def test_dataflow_endpoint_create_eventgrid_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_eventgrid,
    )


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # service account token without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "sat_audience": "audience",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "audience": "audience",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # service account token with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "sat_audience": "audience",
                "authentication_type": "ServiceAccountToken",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "audience": "audience",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # x509 without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "secret_name": "secret",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # x509 with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "secret_name": "secret",
                "authentication_type": "X509Certificate",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # uami without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "client_id": "client_id",
                "tenant_id": "tenant_id",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "tenantId": "tenant_id",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # uami with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "client_id": "client_id",
                "tenant_id": "tenant_id",
                "authentication_type": "UserAssignedManagedIdentity",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings" : {
                            "clientId": "client_id",
                            "tenantId": "tenant_id",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # sami without authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "sami_audience": "audience",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings" : {
                            "audience": "audience",
                        },
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # sami with authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "SystemAssignedManagedIdentity",
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings" : {},
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        # no authentication
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "no_auth": True,
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "Anonymous",
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "Propagate",
                    "host": "test.servicebus.windows.net:9093",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_custom_mqtt(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_custom_mqtt,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "sami_audience": "audience",
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is not "
            "allowed for endpoint type 'CustomMqtt'. Allowed "
            "methods are: ['ServiceAccountToken', "
            "'SystemAssignedManagedIdentity', 'UserAssignedManagedIdentity', "
            "'X509Certificate'].",
        ),
        # missing required parameters for x509
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "X509Certificate",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'X509Certificate': --secret-name.",
        ),
        # missing required parameters for uami
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "UserAssignedManagedIdentity",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method "
            "'UserAssignedManagedIdentity': --client-id, --tenant-id.",
        ),
        # missing required parameters for service account token
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "ServiceAccountToken",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'ServiceAccountToken': --audience.",
        ),
    ],
)
def test_dataflow_endpoint_create_custom_mqtt_with_error(
    mocked_cmd,
    params: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_custom_mqtt,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update host
        (
            {
                "host": "https://newcluster.region.kusto.windows.net",
            },
            {
                "properties": {
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
            },
            {
                "endpointType": "DataExplorer",
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
                    "host": "https://newcluster.region.kusto.windows.net",
                },
            },
        ),
        # update authentication type
        (
            {
                "client_id": "client_id",
                "tenant_id": "tenant_id",
            },
            {
                "properties": {
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
            },
            {
                "endpointType": "DataExplorer",
                "dataExplorerSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "client_id",
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
            },
        ),
    ]
)
def test_dataflow_endpoint_update_adx(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_adx,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update batching values
        (
            {
                "latency": 2,
            },
            {
                "properties": {
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
                        "latencySeconds": 2,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
                "endpointType": "DataLakeStorage",
            },
        ),
    ]
)
def test_dataflow_endpoint_update_adls(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_adls,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update lakehouse name
        (
            {
                "lakehouse_name": "newlakehouse",
            },
            {
                "properties": {
                    "endpointType": "FabricOneLake",
                    "fabricOneLakeSettings": {
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
                        "host": "https://onelake.dfs.fabric.microsoft.com",
                        "names": {
                            "lakehouseName": "mylakehouse",
                            "workspaceName": "myworkspace",
                        },
                        "oneLakePathType": "Files",
                    },
                },
            },
            {
                "endpointType": "FabricOneLake",
                "fabricOneLakeSettings": {
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
                    "host": "https://onelake.dfs.fabric.microsoft.com",
                    "names": {
                        "lakehouseName": "newlakehouse",
                        "workspaceName": "myworkspace",
                    },
                    "oneLakePathType": "Files",
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_fabric_onelake(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_fabric_onelake,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update multiple values
        (
            {
                "eventhub_namespace": "neweventhubnamespace",
                "client_id": "newclientid",
                "tenant_id": "newtenantid",
                "latency": 2,
                "cloud_event_attribute": "Propagate",
            },
            {
                "properties": {
                    "endpointType": "Kafka",
                    "kafkaSettings": {
                        "authentication": {
                            "method": "Sasl",
                            "saslSettings" : {
                                "secretRef" : "secret",
                                "saslType" : "Plain",
                            },
                        },
                        "batching": {
                            "latencyMs": 1,
                            "maxBytes": 1,
                            "maxMessages": 1,
                        },
                        "cloudEventAttributes": "CreateOrRemap",
                        "compression": "Gzip",
                        "consumerGroupId": "mygroupid",
                        "host": "myeventhubnamespace.servicebus.windows.net:9093",
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "newclientid",
                            "tenantId": "newtenantid",
                        },
                    },
                    "batching": {
                        "latencyMs": 2,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "Propagate",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "neweventhubnamespace.servicebus.windows.net:9093",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_eventhub(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_eventhub,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update multiple values
        (
            {
                "host": "newtest.servicebus.windows.net:9093",
                "acks": "One",
                "compression": "Snappy",
                "copy_broker_props_disabled": True,
                "group_id": "newgroupid",
                "partition_strategy": "Static",
                "tenant_id": "newtenantid",
                "client_id": "newclientid",
            },
            {
                "properties": {
                    "endpointType": "Kafka",
                    "kafkaSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "newclientid",
                                "tenantId": "newtenantid",
                            },
                        },
                        "batching": {
                            "latencyMs": 1,
                            "maxBytes": 1,
                            "maxMessages": 1,
                        },
                        "cloudEventAttributes": "CreateOrRemap",
                        "compression": "Gzip",
                        "consumerGroupId": "mygroupid",
                        "host": "test.servicebus.windows.net:9093",
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "newclientid",
                            "tenantId": "newtenantid",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Snappy",
                    "consumerGroupId": "newgroupid",
                    "copyMqttProperties": "Disabled",
                    "host": "newtest.servicebus.windows.net:9093",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Static",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        (
            {
                "batching_disabled": True,
                "latency": 20,
                "max_byte": 20,
                "message_count": 20,
                "cloud_event_attribute": "Propagate",
                "audience": "audience",
                "tls_disabled": True,
                "config_map_reference": "mynewconfigmap",
            },
            {
                "properties": {
                    "endpointType": "Kafka",
                    "kafkaSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "newclientid",
                                "tenantId": "newtenantid",
                            },
                        },
                        "batching": {
                            "latencyMs": 1,
                            "maxBytes": 1,
                            "maxMessages": 1,
                            "mode": "Enabled",
                        },
                        "cloudEventAttributes": "CreateOrRemap",
                        "compression": "Gzip",
                        "consumerGroupId": "mygroupid",
                        "host": "test.servicebus.windows.net:9093",
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "SystemAssignedManagedIdentity",
                        "systemAssignedManagedIdentitySettings" : {
                            "audience": "audience",
                        },
                    },
                    "batching": {
                        "latencyMs": 20,
                        "maxBytes": 20,
                        "maxMessages": 20,
                        "mode": "Disabled",
                    },
                    "cloudEventAttributes": "Propagate",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "tls": {
                        "mode": "Disabled",
                        "trustedCaCertificateConfigMapRef": "mynewconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_fabric_realtime(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_fabric_realtime,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update multiple values
        (
            {
                "hostname": "newtest.servicebus.windows.net",
                "port": 9091,
                "acks": "One",
                "compression": "Snappy",
                "copy_broker_props_disabled": True,
                "group_id": "newgroupid",
                "partition_strategy": "Static",
                "sasl_type": "Plain",
                "secret_name": "newsecret",
            },
            {
                "properties": {
                    "endpointType": "Kafka",
                    "kafkaSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "newclientid",
                                "tenantId": "newtenantid",
                            },
                        },
                        "batching": {
                            "latencyMs": 1,
                            "maxBytes": 1,
                            "maxMessages": 1,
                        },
                        "cloudEventAttributes": "CreateOrRemap",
                        "compression": "Gzip",
                        "consumerGroupId": "mygroupid",
                        "host": "test.servicebus.windows.net:9093",
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Sasl",
                        "saslSettings" : {
                            "secretRef" : "newsecret",
                            "saslType" : "Plain",
                        },
                    },
                    "batching": {
                        "latencyMs": 1,
                        "maxBytes": 1,
                        "maxMessages": 1,
                    },
                    "cloudEventAttributes": "CreateOrRemap",
                    "compression": "Snappy",
                    "consumerGroupId": "newgroupid",
                    "copyMqttProperties": "Disabled",
                    "host": "newtest.servicebus.windows.net:9091",
                    "kafkaAcks": "One",
                    "partitionStrategy": "Static",
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        (
            {
                "batching_disabled": True,
                "latency": 20,
                "max_byte": 20,
                "message_count": 20,
                "cloud_event_attribute": "Propagate",
                "no_auth": True,
                "tls_disabled": True,
                "config_map_reference": "mynewconfigmap",
            },
            {
                "properties": {
                    "endpointType": "Kafka",
                    "kafkaSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "newclientid",
                                "tenantId": "newtenantid",
                            },
                        },
                        "batching": {
                            "latencyMs": 1,
                            "maxBytes": 1,
                            "maxMessages": 1,
                            "mode": "Enabled",
                        },
                        "cloudEventAttributes": "CreateOrRemap",
                        "compression": "Gzip",
                        "consumerGroupId": "mygroupid",
                        "host": "test.servicebus.windows.net:9093",
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Kafka",
                "kafkaSettings": {
                    "authentication": {
                        "method": "Anonymous",
                    },
                    "batching": {
                        "latencyMs": 20,
                        "maxBytes": 20,
                        "maxMessages": 20,
                        "mode": "Disabled",
                    },
                    "cloudEventAttributes": "Propagate",
                    "compression": "Gzip",
                    "consumerGroupId": "mygroupid",
                    "host": "test.servicebus.windows.net:9093",
                    "tls": {
                        "mode": "Disabled",
                        "trustedCaCertificateConfigMapRef": "mynewconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_custom_kafka(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_custom_kafka,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update multiple values
        (
            {
                "hostname": "aio-newbroker",
                "port": 9091,
                "client_id_prefix": "aio-newclient",
                "keep_alive": 61,
                "authentication_type": "X509Certificate",
                "secret_name": "newsecret",
                "max_inflight_messages": 200,
                "protocol": "Websocket",
                "qos": 2,
                "retain": "Never",
                "session_expiry": 7200,
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "Anonymous",
                        },
                        "clientIdPrefix": "aio-client",
                        "cloudEventAttributes": "Propagate",
                        "host": "aio-broker:9093",
                        "keepAliveSeconds": 60,
                        "maxInflightMessages": 100,
                        "protocol": "Mqtt",
                        "qos": 1,
                        "retain": "Keep",
                        "sessionExpirySeconds": 3600,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                        },
                    },
                },
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "newsecret",
                        },
                    },
                    "clientIdPrefix": "aio-newclient",
                    "cloudEventAttributes": "Propagate",
                    "host": "aio-newbroker:9091",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 200,
                    "protocol": "Websocket",
                    "qos": 2,
                    "retain": "Never",
                    "sessionExpirySeconds": 7200,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "azure-iot-operations-aio-ca-trust-bundle",
                    },
                },
            },
        ),
        (
            {
                "no_auth": True,
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "mynewconfigmap",
                "tls_disabled": True,
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "Anonymous",
                        },
                        "clientIdPrefix": "aio-client",
                        "cloudEventAttributes": "Propagate",
                        "host": "aio-broker:9093",
                        "keepAliveSeconds": 60,
                        "maxInflightMessages": 100,
                        "protocol": "Mqtt",
                        "qos": 1,
                        "retain": "Keep",
                        "sessionExpirySeconds": 3600,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": None,
                        },
                    },
                },
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "Anonymous",
                    },
                    "clientIdPrefix": "aio-client",
                    "cloudEventAttributes": "CreateOrRemap",
                    "host": "aio-broker:9093",
                    "keepAliveSeconds": 60,
                    "maxInflightMessages": 100,
                    "protocol": "Mqtt",
                    "qos": 1,
                    "retain": "Keep",
                    "sessionExpirySeconds": 3600,
                    "tls": {
                        "mode": "Disabled",
                        "trustedCaCertificateConfigMapRef": "mynewconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_aio(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_aio,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update multiple values
        (
            {
                "hostname": "namespace.region-1.ts.eventgrid.azure.net",
                "port": 9091,
                "client_id_prefix": "aio-newclient",
                "keep_alive": 61,
                "authentication_type": "UserAssignedManagedIdentity",
                "client_id": "newclientid",
                "tenant_id": "newtenantid",
                "scope": "https://eventgrid.azure.net/.default",
                "max_inflight_messages": 200,
                "protocol": "Websocket",
                "qos": 2,
                "retain": "Never",
                "session_expiry": 7200,
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "X509Certificate",
                            "x509CertificateSettings": {
                                "secretRef": "secret",
                            },
                        },
                        "clientIdPrefix": "aio-client",
                        "cloudEventAttributes": "Propagate",
                        "host": "test.servicebus.windows.net:9093",
                        "keepAliveSeconds": 61,
                        "maxInflightMessages": 100,
                        "protocol": "Mqtt",
                        "qos": 1,
                        "retain": "Keep",
                        "sessionExpirySeconds": 3600,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "newclientid",
                            "tenantId": "newtenantid",
                            "scope": "https://eventgrid.azure.net/.default",
                        },
                    },
                    "clientIdPrefix": "aio-newclient",
                    "cloudEventAttributes": "Propagate",
                    "host": "namespace.region-1.ts.eventgrid.azure.net:9091",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 200,
                    "protocol": "Websocket",
                    "qos": 2,
                    "retain": "Never",
                    "sessionExpirySeconds": 7200,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "myconfigmap",
                    },
                },
            },
        ),
        (
            {
                "scope": "https://neweventgrid.azure.net/.default",
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "mynewconfigmap",
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "clientid",
                                "tenantId": "tenantid",
                                "scope": "https://eventgrid.azure.net/.default",
                            },
                        },
                        "clientIdPrefix": "aio-newclient",
                        "cloudEventAttributes": "Propagate",
                        "host": "namespace.region-1.ts.eventgrid.azure.net:9091",
                        "keepAliveSeconds": 61,
                        "maxInflightMessages": 200,
                        "protocol": "Websocket",
                        "qos": 2,
                        "retain": "Never",
                        "sessionExpirySeconds": 7200,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": None,
                        },
                    },
                },
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "clientid",
                            "tenantId": "tenantid",
                            "scope": "https://neweventgrid.azure.net/.default",
                        },
                    },
                    "clientIdPrefix": "aio-newclient",
                    "cloudEventAttributes": "CreateOrRemap",
                    "host": "namespace.region-1.ts.eventgrid.azure.net:9091",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 200,
                    "protocol": "Websocket",
                    "qos": 2,
                    "retain": "Never",
                    "sessionExpirySeconds": 7200,
                    "tls": {
                        "mode": "Enabled",
                        "trustedCaCertificateConfigMapRef": "mynewconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_eventgrid(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_eventgrid,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_payload",
    [
        # update multiple values
        (
            {
                "hostname": "hostname",
                "port": 9091,
                "client_id_prefix": "aio-newclient",
                "keep_alive": 61,
                "authentication_type": "UserAssignedManagedIdentity",
                "client_id": "newclientid",
                "tenant_id": "newtenantid",
                "scope": "newscope",
                "max_inflight_messages": 200,
                "protocol": "Websocket",
                "qos": 2,
                "retain": "Never",
                "session_expiry": 7200,
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "Anonymous",
                        },
                        "clientIdPrefix": "aio-client",
                        "cloudEventAttributes": "Propagate",
                        "host": "test.servicebus.windows.net:9093",
                        "keepAliveSeconds": 61,
                        "maxInflightMessages": 100,
                        "protocol": "Mqtt",
                        "qos": 1,
                        "retain": "Keep",
                        "sessionExpirySeconds": 3600,
                        "tls": {
                            "mode": "Enabled",
                        },
                    },
                },
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "newclientid",
                            "tenantId": "newtenantid",
                            "scope": "newscope",
                        },
                    },
                    "clientIdPrefix": "aio-newclient",
                    "cloudEventAttributes": "Propagate",
                    "host": "hostname:9091",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 200,
                    "protocol": "Websocket",
                    "qos": 2,
                    "retain": "Never",
                    "sessionExpirySeconds": 7200,
                    "tls": {
                        "mode": "Enabled",
                    },
                },
            },
        ),
        (
            {
                "cloud_event_attribute": "CreateOrRemap",
                "config_map_reference": "mynewconfigmap",
                "tls_disabled": True,
                "client_id": "newclientid",
                "tenant_id": "newtenantid",
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "clientid",
                                "tenantId": "tenantid",
                                "scope": "scope",
                            },
                        },
                        "clientIdPrefix": "aio-newclient",
                        "cloudEventAttributes": "Propagate",
                        "host": "hostname:9091",
                        "keepAliveSeconds": 61,
                        "maxInflightMessages": 200,
                        "protocol": "Websocket",
                        "qos": 2,
                        "retain": "Never",
                        "sessionExpirySeconds": 7200,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            {
                "endpointType": "Mqtt",
                "mqttSettings": {
                    "authentication": {
                        "method": "UserAssignedManagedIdentity",
                        "userAssignedManagedIdentitySettings": {
                            "clientId": "newclientid",
                            "tenantId": "newtenantid",
                            "scope": "scope",
                        },
                    },
                    "clientIdPrefix": "aio-newclient",
                    "cloudEventAttributes": "CreateOrRemap",
                    "host": "hostname:9091",
                    "keepAliveSeconds": 61,
                    "maxInflightMessages": 200,
                    "protocol": "Websocket",
                    "qos": 2,
                    "retain": "Never",
                    "sessionExpirySeconds": 7200,
                    "tls": {
                        "mode": "Disabled",
                        "trustedCaCertificateConfigMapRef": "mynewconfigmap",
                    },
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_custom_mqtt(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_custom_mqtt,
        updating_payload=updating_payload,
        is_update=True,
    )


@pytest.mark.parametrize(
    "params, updating_payload, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "sami_audience": "audience",
                "authentication_type": "UnsupportedType",
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "clientid",
                                "tenantId": "tenantid",
                                "scope": "scope",
                            },
                        },
                        "clientIdPrefix": "aio-newclient",
                        "cloudEventAttributes": "Propagate",
                        "host": "hostname:9091",
                        "keepAliveSeconds": 61,
                        "maxInflightMessages": 200,
                        "protocol": "Websocket",
                        "qos": 2,
                        "retain": "Never",
                        "sessionExpirySeconds": 7200,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "myconfigmap",
                        },
                    },
                },
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is not allowed for endpoint type "
            "'CustomMqtt'. Allowed methods are: ['ServiceAccountToken', "
            "'SystemAssignedManagedIdentity', 'UserAssignedManagedIdentity', 'X509Certificate'].",
        ),
        # missing required parameters for x509
        (
            {
                "hostname": "test.servicebus.windows.net",
                "port": 9093,
                "client_id_prefix": "aio-client",
                "keep_alive": 61,
                "authentication_type": "X509Certificate",
            },
            {
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "authentication": {
                            "method": "UserAssignedManagedIdentity",
                            "userAssignedManagedIdentitySettings": {
                                "clientId": "clientid",
                                "tenantId": "tenantid",
                                "scope": "scope",
                            },
                        },
                        "clientIdPrefix": "aio-newclient",
                        "cloudEventAttributes": "Propagate",
                        "host": "hostname:9091",
                        "keepAliveSeconds": 61,
                        "maxInflightMessages": 200,
                        "protocol": "Websocket",
                        "qos": 2,
                        "retain": "Never",
                        "sessionExpirySeconds": 7200,
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": None,
                        },
                    },
                },
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'X509Certificate': --secret-name.",
        ),
    ],
)
def test_dataflow_endpoint_update_with_error(
    mocked_cmd,
    params: dict,
    updating_payload: dict,
    expected_error_type: type,
    expected_error_text: str,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update_with_error(
        mocked_responses=mocked_responses,
        expected_error_type=expected_error_type,
        expected_error_text=expected_error_text,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=update_dataflow_endpoint_custom_mqtt,
        is_update=True,
        updating_payload=updating_payload,
    )
