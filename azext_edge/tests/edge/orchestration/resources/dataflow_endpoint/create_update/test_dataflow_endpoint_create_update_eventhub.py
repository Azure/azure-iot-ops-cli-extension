# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    create_dataflow_endpoint_eventhub,
    update_dataflow_endpoint_eventhub,
)
from ..helpers import assert_dataflow_endpoint_create_update, assert_dataflow_endpoint_create_update_with_error


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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
                "max_bytes": 1,
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
