# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class E4kResourceKinds(ListableEnum):
    BROKER = "broker"
    BROKER_LISTENER = "brokerlistener"
    BROKER_DIAGNOSTIC = "brokerdiagnostic"
    DIAGNOSTIC_SERVICE = "diagnosticservice"
    BROKER_AUTHENTICATION = "brokerauthentication"
    BROKER_AUTHORIZATION = "brokerauthorization"
    MQTT_BRIDGE_TOPIC_MAP = "mqttbridgetopicmap"
    MQTT_BRIDGE_CONNECTOR = "mqttbridgeconnector"


E4K_API_V1A2 = EdgeResourceApi(
    group="az-edge.com", version="v1alpha2", moniker="e4k", kinds=frozenset(E4kResourceKinds.list())
)
E4K_API_V1A3 = EdgeResourceApi(
    group="az-edge.com", version="v1alpha3", moniker="e4k", kinds=frozenset(E4kResourceKinds.list())
)

E4K_ACTIVE_API = E4K_API_V1A3
