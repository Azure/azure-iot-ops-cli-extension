# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_custom_kafka,
    update_dataflow_endpoint_custom_kafka,
)
from ..helper import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
