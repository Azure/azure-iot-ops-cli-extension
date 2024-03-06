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


class DataProcessorStageType(ListableEnum):
    """
    Data processor stage type.
    """
    aggregate = "processor/aggregate"
    enrich = "processor/enrich"
    filter = "processor/filter"
    grpc = "processor/grpc"
    http = "processor/http"
    lkv = "processor/lkv"
    transform = "processor/transform"


class DataprocessorDestinationStageType(ListableEnum):
    """
    Data processor destination stage type.
    """
    blob_storage = "output/blobstorage"
    data_explorer = "output/dataexplorer"
    fabric = "output/fabric"
    file = "output/file"
    grpc = "output/grpc"
    http = "output/http"
    mqtt = "output/mqtt"
    reference_data = "output/refdata"


class DataprocessorAuthenticationType(ListableEnum):
    """
    Data processor authentication type.
    """
    accessKey = "accessKey"
    accessToken = "accessToken"
    header = "header"
    metadata = "metadata"
    none = "none"
    serviceAccountToken = "serviceAccountToken"
    servicePrincipal = "servicePrincipal"
    systemAssignedManagedIdentity = "systemAssignedManagedIdentity"
    usernamePassword = "usernamePassword"


ERROR_NO_DETAIL = "<No detail available>"

DATA_PROCESSOR_SOURCE_REQUIRED_PROPERTIES = {
    DataSourceStageType.mqtt.value: ["broker", "topics"],
    DataSourceStageType.sql.value: ["query", "server", "database", "interval"],
    DataSourceStageType.influxdb.value: ["query", "url", "interval", "organization"],
    DataSourceStageType.http.value: ["url", "interval"],
}

DATA_PROCESSOR_SOURCE_DISPLAY_PROPERTIES = {
    DataSourceStageType.http.value: [
        ("method", "Request method", True),
        ("request", "HTTP request", True),
    ],
    DataSourceStageType.influxdb.value: [
        ("port", "Port", True),
    ],
    DataSourceStageType.mqtt.value: [
        ("qos", "MQTT QoS", True),
        ("cleanSession", "MQTT Clean Session", True),
    ],
    DataSourceStageType.sql.value: [
        ("port", "Port", True),
    ],
}

DATA_PROCESSOR_INTERMEDIATE_STAGE_PROPERTIES = {
    DataProcessorStageType.aggregate.value: [
        ("window.type", "Aggregate window type", False),
        ("window.size", "Aggregate window duration", False),
        ("properties", "Aggregate property", True)
    ],
    DataProcessorStageType.enrich.value: [
        ("dataset", "Enrich dataset ID", False),
        ("outputPath", "Enrich output path", False),
        ("conditions", "Enrich condition", True),
        ("alwaysArray", "Enrich always array", True),
        ("limit", "Enrich limit", True)
    ],
    DataProcessorStageType.filter.value: [("expression", "Filter expression", True)],
    DataProcessorStageType.grpc.value: [
        ("serverAddress", "gRPC server address", False),
        ("rpcName", "gRPC RPC name", False),
        ("descriptor", "gRPC descriptor", False),
        ("request", "gRPC request", True),
        ("response", "gRPC response", True),
        ("retry", "gRPC retry mechanism", True),
        ("tls", "gRPC TLS", True),
    ],
    DataProcessorStageType.http.value: [
        ("url", "Request URL", False),
        ("method", "Request method", False),
        ("request", "gRPC request", True),
        ("response", "gRPC response", True),
        ("retry", "gRPC retry mechanism", True)
    ],
    DataProcessorStageType.lkv.value: [("properties", "LKV property", True)],
    DataProcessorStageType.transform.value: [("expression", "Transform expression", True)]
}

DATA_PROCESSOR_DESTINATION_STAGE_PROPERTIES = {
    DataprocessorDestinationStageType.blob_storage.value: [
        ("accountName", "Account name", False),
        ("containerName", "Container name", False),
        ("blobPath", "Blob path", True),
        ("batch", "Batch method", True),
        ("retry", "Retry mechanism", True),
    ],
    DataprocessorDestinationStageType.fabric.value: [
        ("workspace", "Fabric workspace ID", False),
        ("lakehouse", "Fabric lakehouse ID", False),
        ("table", "Fabric lakehouse table", False),
        ("filePath", "Fabric template file path", True),
        ("batch", "Fabric batch method", True),
        ("columns", "Fabric table column", True),
        ("retry", "Fabric retry mechanism", True)
    ],
    DataprocessorDestinationStageType.file.value: [
        ("rootDirectory", "Root directory", False),
        ("filePath", "File path", False),
        ("batch", "File batch method", True),
        ("filePermissions", "File permissions", True),
    ],
    DataprocessorDestinationStageType.grpc.value: [
        ("serverAddress", "gRPC server address", False),
        ("rpcName", "gRPC RPC name", False),
        ("descriptor", "gRPC descriptor", False),
        ("request", "gRPC request", True),
        ("retry", "gRPC retry mechanism", True),
    ],
    DataprocessorDestinationStageType.http.value: [
        ("url", "Request URL", False),
        ("method", "Request method", False),
        ("request", "HTTP request", True),
        ("retry", "HTTP retry mechanism", True),
    ],
    DataprocessorDestinationStageType.data_explorer.value: [
        ("clusterUrl", "Data Explorer cluster URL", False),
        ("database", "Data Explorer database", False),
        ("table", "Data Explorer table", False),
        ("batch", "Data Explorer batch method", True),
        ("columns", "Data Explorer table column", True),
        ("retry", "Data Explorer retry mechanism", True)
    ],
    DataprocessorDestinationStageType.mqtt.value: [
        ("broker", "MQTT broker URL", False),
        ("qos", "MQTT QoS", False),
        ("topic", "MQTT topic", False),
        ("userProperties", "MQTT user property", True),
        ("retry", "MQTT retry mechanism", True)
    ],
    DataprocessorDestinationStageType.reference_data.value: [("dataset", "Dataset ID", False)]
}

DATA_PROCESSOR_AUTHENTICATION_REQUIRED_PROPERTIES = {
    DataprocessorAuthenticationType.accessToken.value: ["accessToken"],
    DataprocessorAuthenticationType.accessKey.value: ["accessKey"],
    DataprocessorAuthenticationType.header.value: ["key", "value"],
    DataprocessorAuthenticationType.metadata.value: ["key", "value"],
    DataprocessorAuthenticationType.none.value: [],
    DataprocessorAuthenticationType.serviceAccountToken.value: [],
    DataprocessorAuthenticationType.servicePrincipal.value: ["tenantId", "clientId", "clientSecret"],
    DataprocessorAuthenticationType.systemAssignedManagedIdentity.value: [],
    DataprocessorAuthenticationType.usernamePassword.value: ["username", "password"],
}

DATA_PROCESSOR_AUTHENTICATION_SECRET_REF = "(Secret reference)"

LNM_ALLOWLIST_PROPERTIES = [
    ("domains", "[bright_blue]Domains[/bright_blue]", False),
    ("enableArcDomains", "[bright_blue]Enable Arc Domains[/bright_blue]", False),
    ("sourceIpRange", "[bright_blue]Source Ip Range[/bright_blue]", False),
]

LNM_IMAGE_PROPERTIES = [
    ("repository", "[bright_blue]Repository[/bright_blue]", True),
    ("tag", "[bright_blue]Tag[/bright_blue]", True),
]

LNM_REST_PROPERTIES = [
    ("endpointType", "Endpoint Type", False),
    ("level", "Level", True),
    ("logLevel", "Log Level", True),
    ("nodeTolerations", "Node to Tolerations", True),
    ("openTelemetryMetricsCollectorAddr", "Open Telemetry Metrics Collector Address", True),
    ("parentIpAddr", "Parent IP Address", True),
    ("parentPort", "Parent Port", True),
    ("port", "Port", False),
    ("replicas", "Replicas", False),
]

LNM_POD_CONDITION_TEXT_MAP = {
    "Ready": "Pod Readiness",
    "Initialized": "Pod Initialized",
    "ContainersReady": "Containers Readiness",
    "PodScheduled": "Pod Scheduled",
}

LNM_EXCLUDED_SUBRESOURCE = [
    "lnmz/scale",
    "lnmz/status",
]

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


# MQ connector enums
class KafkaTopicMapRouteType(Enum):
    """
    Kafka Connector Topic Map Route type:
    """

    kafka_to_mqtt = "kafkaToMqtt"
    mqtt_to_kafka = "mqttToKafka"


class DataLakeConnectorTargetType(ListableEnum):
    """
    Data Lake Connector Target type:
    """

    data_lake_storage = "datalakeStorage"
    fabric_onelake = "fabricOneLake"
    local_storage = "localStorage"


# Data processor runtime attributes

DATA_PROCESSOR_READER_WORKER_PREFIX = "aio-dp-reader-worker"
DATA_PROCESSOR_RUNNER_WORKER_PREFIX = "aio-dp-runner-worker"
DATA_PROCESSOR_REFDATA_STORE_PREFIX = "aio-dp-refdata-store"
DATA_PROCESSOR_NATS_PREFIX = "aio-dp-msg-store"
DATA_PROCESSOR_OPERATOR = "aio-dp-operator"

# MQ runtime attributes

AIO_MQ_DIAGNOSTICS_PROBE_PREFIX = "aio-mq-diagnostics-probe"
AIO_MQ_FRONTEND_PREFIX = "aio-mq-dmqtt-frontend"
AIO_MQ_BACKEND_PREFIX = "aio-mq-dmqtt-backend"
AIO_MQ_AUTH_PREFIX = "aio-mq-dmqtt-authentication"
AIO_MQ_KAFKA_CONFIG_PREFIX = "aio-mq-kafka-config"

# Lnm runtime attributes
AIO_LNM_PREFIX = "aio-lnm"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"

PADDING_SIZE = 4
