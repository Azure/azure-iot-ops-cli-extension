# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_eventgrid,
    update_dataflow_endpoint_eventgrid,
)
from ..helpers import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
