# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class MqResourceKinds(ListableEnum):
    BROKER = "broker"
    BROKER_LISTENER = "brokerlistener"
    BROKER_DIAGNOSTIC = "brokerdiagnostic"
    DIAGNOSTIC_SERVICE = "diagnosticservice"
    BROKER_AUTHENTICATION = "brokerauthentication"
    BROKER_AUTHORIZATION = "brokerauthorization"
    MQTT_BRIDGE_TOPIC_MAP = "mqttbridgetopicmap"
    MQTT_BRIDGE_CONNECTOR = "mqttbridgeconnector"
    DATALAKE_CONNECTOR = "datalakeconnector"
    DATALAKE_CONNECTOR_TOPIC_MAP = "datalakeconnectortopicmap"
    KAFKA_CONNECTOR = "kafkaconnector"
    KAFKA_CONNECTOR_TOPIC_MAP = "kafkaconnectortopicmap"


MQTT_BROKER_API_V1B1 = EdgeResourceApi(
    group="mqttbroker.iotoperations.azure.com",
    version="v1beta1",
    moniker="broker",
    label="microsoft-iotoperations-mq",
)

MQ_ACTIVE_API = MQTT_BROKER_API_V1B1
