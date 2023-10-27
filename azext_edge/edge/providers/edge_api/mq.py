# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

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


MQ_API_V1A2 = EdgeResourceApi(group="az-edge.com", version="v1alpha2", moniker="e4k")
MQ_API_V1A3 = EdgeResourceApi(group="az-edge.com", version="v1alpha3", moniker="e4k")
MQ_API_V1A4 = EdgeResourceApi(group="az-edge.com", version="v1alpha4", moniker="e4k")
MQ_API_V1B1 = EdgeResourceApi(group="mq.iotoperations.azure.com", version="v1beta1", moniker="mq")

MQ_ACTIVE_API = MQ_API_V1B1
