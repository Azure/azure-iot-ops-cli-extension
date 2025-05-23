# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_fabric_onelake,
    update_dataflow_endpoint_fabric_onelake,
)
from ..helpers import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
