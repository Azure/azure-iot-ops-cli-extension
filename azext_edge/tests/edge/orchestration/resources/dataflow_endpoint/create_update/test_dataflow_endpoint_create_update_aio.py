# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_aio,
    update_dataflow_endpoint_aio,
)
from ..helper import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
