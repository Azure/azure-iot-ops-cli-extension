# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_adls,
    update_dataflow_endpoint_adls,
)
from ..helpers import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
        # uami without authentication type and scope
        (
            {
                "storage_account_name": "mystorageaccount",
                "client_id": "client_id",
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
                            "tenantId": "tenant_id",
                            "scope": "https://storage.azure.com/.default",
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
