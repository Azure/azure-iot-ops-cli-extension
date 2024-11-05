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
    BROKER_AUTHENTICATION = "brokerauthentication"
    BROKER_AUTHORIZATION = "brokerauthorization"


MQTT_BROKER_API_V1 = EdgeResourceApi(
    group="mqttbroker.iotoperations.azure.com",
    version="v1",
    moniker="broker",
    label="microsoft-iotoperations-mqttbroker",
)

MQ_ACTIVE_API = MQTT_BROKER_API_V1
