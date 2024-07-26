# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums) and constant strings for IoT Operations service checks.

"""

from enum import Enum
from ...common import ListableEnum


class ResourceOutputDetailLevel(ListableEnum):
    """
    Level of detail in check output.
    """

    summary = "0"  # summary
    detail = "1"  # detail
    verbose = "2"  # verbose


class DataSourceStageType(ListableEnum):
    """
    Data source stage type.
    """
    http = "input/http"
    influxdb = "input/influxdb"
    mqtt = "input/mqtt"
    sql = "input/mssql"


ERROR_NO_DETAIL = "<No detail available>"

POD_CONDITION_TEXT_MAP = {
    "Ready": "Pod Readiness",
    "Initialized": "Pod Initialized",
    "ContainersReady": "Containers Readiness",
    "PodScheduled": "Pod Scheduled",
    "PodReadyToStartContainers": "Pod Ready To Start Containers",
}

ASSET_DATAPOINT_PROPERTIES = [
    ("name", "Name", False),
    ("capabilityId", "Capability Id", True),
    ("dataPointConfiguration", "Configuration", True),
    ("observabilityMode", "Observability Mode", False),
]

ASSET_PROPERTIES = [
    ("description", "Description", True),
    ("assetType", "Asset Type", False),
    ("attributes", "Attributes", True),
    ("defaultDataPointsConfiguration", "Default Data Points Configuration", False),
    ("defaultEventsConfiguration", "Default Events Configuration", False),
    ("displayName", "Display Name", False),
    ("documentationUri", "Documentation Uri", False),
    ("enabled", "Enabled", False),
    ("observabilityMode", "Observability Mode", False),
    ("externalAssetId", "External Asset Id", False),
    ("hardwareRevision", "Hardware Revision", False),
    ("manufacturer", "Manufacturer", False),
    ("manufacturerUri", "Manufacturer Uri", True),
    ("model", "Model", False),
    ("productCode", "Product Code", False),
    ("serialNumber", "Serial Number", False),
    ("softwareRevision", "Software Revision", False),
    ("uuid", "Uuid", False),
    ("version", "Version", False),
]

ASSET_EVENT_PROPERTIES = [
    ("name", "Name", False),
    ("capabilityId", "Capability Id", True),
    ("eventConfiguration", "Configuration", False),
    ("observabilityMode", "Observability Mode", False),
]

BROKER_DIAGNOSTICS_PROPERTIES = [
    ("logs.level", "Log Level", False),
    ("metrics.mode", "Metrics Mode", False),
    ("selfCheck.mode", "Self Check Mode", False),
    ("traces.mode", "Trace Mode", False),
]

MAX_ASSET_EVENTS = 1000
MAX_ASSET_DATAPOINTS = 1000

# Check constants
ALL_NAMESPACES_TARGET = '_all_'


# when there are runtime resources related to the service but not
# related to any service resource, use this as the resource name
class CoreServiceResourceKinds(Enum):
    """
    Core service resource kinds:
    """

    RUNTIME_RESOURCE = "coreServiceRuntimeResource"


# Akri runtime attributes
AKRI_PREFIX = "aio-akri-"

# MQ runtime attributes
AIO_MQ_DIAGNOSTICS_PROBE_PREFIX = "aio-mq-diagnostics-probe"
AIO_MQ_FRONTEND_PREFIX = "aio-mq-dmqtt-frontend"
AIO_MQ_BACKEND_PREFIX = "aio-mq-dmqtt-backend"
AIO_MQ_AUTH_PREFIX = "aio-mq-dmqtt-authentication"
AIO_MQ_HEALTH_MANAGER = "aio-mq-dmqtt-health-manager"
AIO_MQ_OPERATOR = "aio-mq-operator"
AIO_MQ_FLUENT_BIT = "aio-mq-fluent-bit"

# OPCUA runtime attributes
AIO_OPCUA_PREFIX = "aio-opc-"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"

# Node prerequisite constants

MIN_NODE_MEMORY = "16G"
MIN_NODE_STORAGE = "30G"
MIN_NODE_VCPU = "4"
AIO_SUPPORTED_ARCHITECTURES = ["amd64"]  # someday arm64

DISPLAY_BYTES_PER_GIGABYTE = 10 ** 9

# UI constants
PADDING_SIZE = 4

COLOR_STR_FORMAT = "[{color}]{value}[/{color}]"
