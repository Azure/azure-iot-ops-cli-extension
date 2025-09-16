# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_otel,
    update_dataflow_endpoint_otel,
)
from ..helpers import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        # x509 without authentication type
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "secret_name": "secret_name"
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret_name"
                        }
                    },
                    "host": "https://otel-collector.monitoring.svc.cluster.local:4317",
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    'tls': {'mode': 'Enabled'}
                },
            },
        ),
        # x509 with authentication type
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "secret_name": "secret_name",
                "authentication_type": "X509Certificate"
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "secret_name"
                        }
                    },
                    "host": "https://otel-collector.monitoring.svc.cluster.local:4317",
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    'tls': {'mode': 'Enabled'}
                },
            },
        ),
        # service account token without authentication type
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "audience": "audience",
                "tls_disabled": True
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "audience": "audience"
                        }
                    },
                    "host": "https://otel-collector.monitoring.svc.cluster.local:4317",
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    'tls': {'mode': 'Disabled'}
                },
            },
        ),
        # service account token with authentication type
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "audience": "audience",
                "tls_disabled": True,
                "authentication_type": "ServiceAccountToken",
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "audience": "audience"
                        }
                    },
                    "host": "https://otel-collector.monitoring.svc.cluster.local:4317",
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    'tls': {'mode': 'Disabled'}
                },
            },
        ),
        # no auth
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "tls_disabled": True,
                "no_auth": True,
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "Anonymous",
                        "anonymousSettings": {},
                    },
                    "host": "https://otel-collector.monitoring.svc.cluster.local:4317",
                    "batching": {
                        "latencySeconds": 1,
                        "maxMessages": 1,
                    },
                    'tls': {'mode': 'Disabled'}
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_otel(
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
        dataflow_endpoint_func=create_dataflow_endpoint_otel,
    )


@pytest.mark.parametrize(
    "params, expected_error_type, expected_error_text",
    [
        # unsupported authentication type
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "audience": "audience",
                "tls_disabled": True,
                "authentication_type": "UnsupportedType",
            },
            InvalidArgumentValueError,
            "Authentication method 'UnsupportedType' is "
            "not allowed for endpoint type 'OpenTelemetry'. "
            "Allowed methods are: ['ServiceAccountToken', "
            "'X509Certificate'].",
        ),
        # missing required parameters for service account token
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "tls_disabled": True,
                "authentication_type": "ServiceAccountToken",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'ServiceAccountToken': --audience.",
        ),
        # missing required parameters for x509 certificate
        (
            {
                "hostname": "https://otel-collector.monitoring.svc.cluster.local",
                "port": 4317,
                "latency": 1,
                "message_count": 1,
                "tls_disabled": True,
                "authentication_type": "X509Certificate",
            },
            InvalidArgumentValueError,
            "Missing required parameters for authentication method 'X509Certificate': --secret-name.",
        ),
    ]
)
def test_dataflow_endpoint_create_otel_with_error(
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
        dataflow_endpoint_func=create_dataflow_endpoint_otel,
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
                    "endpointType": "OpenTelemetry",
                    "openTelemetrySettings": {
                        "authentication": {
                            "method": "ServiceAccountToken",
                            "serviceAccountTokenSettings": {
                                "secretRef": "mysecret"
                            },
                        },
                        "batching": {
                            "latencySeconds": 1,
                            "maxMessages": 1,
                        },
                        "host": "https://mystorageaccount.blob.core.windows.net",
                    },
                },
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {
                            "secretRef": "mysecret"
                        },
                    },
                    "batching": {
                        "latencySeconds": 2,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
            },
        ),
        # update authentication settings
        (
            {
                "authentication_type": "X509Certificate",
                "secret_name": "mysecret"
            },
            {
                "properties": {
                    "endpointType": "OpenTelemetry",
                    "openTelemetrySettings": {
                        "authentication": {
                            "method": "ServiceAccountToken",
                            "serviceAccountTokenSettings": {
                                "secretRef": "mysecret"
                            },
                        },
                        "batching": {
                            "latencySeconds": 2,
                            "maxMessages": 1,
                        },
                        "host": "https://mystorageaccount.blob.core.windows.net",
                    },
                },
            },
            {
                "endpointType": "OpenTelemetry",
                "openTelemetrySettings": {
                    "authentication": {
                        "method": "X509Certificate",
                        "x509CertificateSettings": {
                            "secretRef": "mysecret"
                        },
                    },
                    "batching": {
                        "latencySeconds": 2,
                        "maxMessages": 1,
                    },
                    "host": "https://mystorageaccount.blob.core.windows.net",
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_update_otel(
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
        dataflow_endpoint_func=update_dataflow_endpoint_otel,
        updating_payload=updating_payload,
        is_update=True,
    )
