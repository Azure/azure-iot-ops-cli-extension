# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums) and constant strings.

"""

from enum import Enum


class ListableEnum(Enum):
    @classmethod
    def list(cls):
        return [c.value for c in cls]


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


class SupportForEdgeServiceType(ListableEnum):
    """
    Edge resource type.
    """

    auto = "auto"
    e4k = "e4k"
    opcua = "opcua"
    bluefin = "bluefin"


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
