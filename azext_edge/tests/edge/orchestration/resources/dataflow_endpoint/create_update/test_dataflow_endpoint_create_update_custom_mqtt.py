# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_custom_mqtt,
    update_dataflow_endpoint_custom_mqtt,
)
from ..helpers import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
