# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_adx,
    update_dataflow_endpoint_adx,
)
from ..helper import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
