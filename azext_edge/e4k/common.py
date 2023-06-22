# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums) and constant strings.

"""

from enum import Enum
from collections import namedtuple


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


IotEdgeBrokerResource = namedtuple(
    "IoTEdgeBrokerResource", ["group", "version", "resource"]
)
BROKER_RESOURCE = IotEdgeBrokerResource("az-edge.com", "v1alpha2", "brokers")
BRIDGE_RESOURCE = IotEdgeBrokerResource(
    "az-edge.com", "v1alpha2", "mqttbridgeconnectors"
)

AZEDGE_DIAGNOSTICS_SERVICE = "azedge-diagnostics-service"

AZEDGE_DIAGNOSTICS_POD_PREFIX = "azedge-diagnostics"
AZEDGE_DIAGNOSTICS_PROBE = "azedge-diagnostics-probe"

AZEDGE_FRONTEND_PREFIX = "azedge-dmqtt-frontend"
AZEDGE_KAFKA_CONFIG_PREFIX = "azedge-kafka-config"

OPCUA_RESOURCE = IotEdgeBrokerResource("e4i.microsoft.com", "v1", "")

MIN_K8S_VERSION = "1.20"
MIN_HELM_VERSION = "3.8.0"
CONSOLE_WIDTH = 120
