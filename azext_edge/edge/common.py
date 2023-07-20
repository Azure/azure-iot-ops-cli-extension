# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums) and constant strings.

"""

from enum import Enum
from typing import NamedTuple


class CheckTaskStatus(Enum):
    """
    Status of a check task.
    """

    success = "success"
    warning = "warning"
    error = "error"
    skipped = "skipped"


class ResourceState(Enum):
    """
    K8s resource state.
    """

    starting = "Starting"
    running = "Running"
    recovering = "Recovering"
    failed = "Failed"
    ok = "OK"
    warn = "warn"
    error = "Error"


class PodState(Enum):
    """
    K8s pod state.
    """

    pending = "Pending"
    running = "Running"
    succeeded = "Succeeded"
    failed = "Failed"
    unknown = "Unknown"


class E4kCheckType(Enum):
    """
    E4K environment check type.
    """

    pre = "pre"
    post = "post"


class EdgeServiceType(Enum):
    """
    Edge resource type.
    """

    auto = "auto"
    e4k = "e4k"
    opcua = "opcua"
    bluefin = "bluefin"

    @classmethod
    def list(cls):
        return [c.value for c in cls]


class EdgeResourceApi(NamedTuple):
    group: str
    version: str
    moniker: str

    def as_str(self):
        return f"{self.group}/{self.version}"


class EdgeResource(NamedTuple):
    api: EdgeResourceApi
    resource: str

    @property
    def plural(self):
        return f"{self.resource}s"


# Supported API versions

E4K_API_V1A2 = EdgeResourceApi(group="az-edge.com", version="v1alpha2", moniker="e4k")
OPCUA_API_V1 = EdgeResourceApi(group="e4i.microsoft.com", version="v1", moniker="opcua")
BLUEFIN_API_V1 = EdgeResourceApi(group="bluefin.az-bluefin.com", version="v1", moniker="bluefin")
SYMPHONY_API_V1 = EdgeResourceApi(group="symphony.microsoft.com", version="v1", moniker="symphony")


# E4K Resources

E4K_BROKER = EdgeResource(api=E4K_API_V1A2, resource="broker")
E4K_BROKER_LISTENER = EdgeResource(api=E4K_API_V1A2, resource="brokerlistener")
E4K_BROKER_DIAGNOSTIC = EdgeResource(api=E4K_API_V1A2, resource="brokerdiagnostic")
E4K_DIAGNOSTIC_SERVICE = EdgeResource(api=E4K_API_V1A2, resource="diagnosticservice")
E4K_BROKER_AUTHENTICATION = EdgeResource(api=E4K_API_V1A2, resource="brokerauthentication")
E4K_BROKER_AUTHORIZATION = EdgeResource(api=E4K_API_V1A2, resource="brokerauthorization")
E4K_MQTT_BRIDGE_TOPIC_MAP = EdgeResource(api=E4K_API_V1A2, resource="mqttbridgetopicmap")
E4K_MQTT_BRIDGE_CONNECTOR = EdgeResource(api=E4K_API_V1A2, resource="mqttbridgeconnector")


# OPC-UA Resources

OPCUA_APPLICATION = EdgeResource(api=OPCUA_API_V1, resource="application")
OPCUA_MODULE_TYPE = EdgeResource(api=OPCUA_API_V1, resource="moduletype")
OPCUA_MODULE = EdgeResource(api=OPCUA_API_V1, resource="module")
OPCUA_ASSET_TYPE = EdgeResource(api=OPCUA_API_V1, resource="assettype")
OPCUA_ASSET = EdgeResource(api=OPCUA_API_V1, resource="asset")


# Bluefin Resources

BLUEFIN_DATASET = EdgeResource(api=BLUEFIN_API_V1, resource="dataset")
BLUEFIN_INSTANCE = EdgeResource(api=BLUEFIN_API_V1, resource="instance")
BLUEFIN_PIPELINE = EdgeResource(api=BLUEFIN_API_V1, resource="pipeline")


# E4K runtime attributes

AZEDGE_DIAGNOSTICS_SERVICE = "azedge-diagnostics-service"
METRICS_SERVICE_API_PORT = 9600

AZEDGE_DIAGNOSTICS_PROBE_PREFIX = "azedge-diagnostics-probe"
AZEDGE_FRONTEND_PREFIX = "azedge-dmqtt-frontend"
AZEDGE_BACKEND_PREFIX = "azedge-dmqtt-backend"
AZEDGE_AUTH_PREFIX = "azedge-dmqtt-authentication"
AZEDGE_KAFKA_CONFIG_PREFIX = "azedge-kafka-config"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"
MIN_HELM_VERSION = "3.8.0"
