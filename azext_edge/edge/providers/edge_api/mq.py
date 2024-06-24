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
    IOT_HUB_CONNECTOR = "iothubconnector"
    IOT_HUB_CONNECTOR_ROUTE_MAP = "iothubconnectorroutesmap"


MQ_API_V1B1 = EdgeResourceApi(
    group="mq.iotoperations.azure.com", version="v1beta1", moniker="mq", label="microsoft-iotoperations-mq"
)
MQTT_BROKER_API_V1B1 = EdgeResourceApi(
    group="mqttbroker.iotoperations.azure.com",
    version="v1beta1",
    moniker="mqttbroker",
    label="microsoft-iotoperations-mqttbroker",
)

MQ_ACTIVE_API = MQ_API_V1B1
