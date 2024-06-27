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

DATA_PROCESSOR_INTERMEDIATE_REQUIRED_PROPERTIES = {
    DataProcessorStageType.aggregate.value: ["window", "properties"],
    DataProcessorStageType.enrich.value: ["dataset", "outputPath"],
    DataProcessorStageType.filter.value: ["expression"],
    DataProcessorStageType.grpc.value: ["serverAddress", "rpcName", "descriptor"],
    DataProcessorStageType.http.value: ["url", "method"],
    DataProcessorStageType.lkv.value: ["properties"],
    DataProcessorStageType.transform.value: ["expression"],
}

DATA_PROCESSOR_INTERMEDIATE_STAGE_PROPERTIES = {
    DataProcessorStageType.aggregate.value: [],
    DataProcessorStageType.enrich.value: [
        ("conditions", "Enrich condition", True),
        ("alwaysArray", "Enrich always array", True),
        ("limit", "Enrich limit", True)
    ],
    DataProcessorStageType.filter.value: [],
    DataProcessorStageType.grpc.value: [
        ("request", "gRPC request", True),
        ("response", "gRPC response", True),
        ("retry", "gRPC retry mechanism", True),
        ("tls", "gRPC TLS", True),
    ],
    DataProcessorStageType.http.value: [
        ("request", "gRPC request", True),
        ("response", "gRPC response", True),
        ("retry", "gRPC retry mechanism", True)
    ],
    DataProcessorStageType.transform.value: []
}

DATA_PROCESSOR_DESTINATION_REQUIRED_PROPERTIES = {
    DataprocessorDestinationStageType.blob_storage.value: ["accountName", "containerName"],
    DataprocessorDestinationStageType.data_explorer.value: ["clusterUrl", "database", "table"],
    DataprocessorDestinationStageType.fabric.value: ["workspace", "lakehouse", "table"],
    DataprocessorDestinationStageType.file.value: ["rootDirectory"],
    DataprocessorDestinationStageType.grpc.value: ["serverAddress", "rpcName", "descriptor"],
    DataprocessorDestinationStageType.http.value: ["url", "method"],
    DataprocessorDestinationStageType.mqtt.value: ["broker", "topic"],
    DataprocessorDestinationStageType.reference_data.value: ["dataset"]
}

DATA_PROCESSOR_DESTINATION_STAGE_PROPERTIES = {
    DataprocessorDestinationStageType.blob_storage.value: [
        ("blobPath", "Blob path", True),
        ("batch", "Batch method", True),
        ("retry", "Retry mechanism", True),
    ],
    DataprocessorDestinationStageType.fabric.value: [
        ("filePath", "Template file path", True),
        ("batch", "Batch method", True),
        ("columns", "Table column", True),
        ("retry", "Retry mechanism", True)
    ],
    DataprocessorDestinationStageType.file.value: [
        ("filePath", "File path", False),
        ("batch", "Batch method", True),
        ("filePermissions", "File permissions", True),
    ],
    DataprocessorDestinationStageType.grpc.value: [
        ("request", "gRPC request", True),
        ("retry", "Retry mechanism", True),
    ],
    DataprocessorDestinationStageType.http.value: [
        ("request", "HTTP request", True),
        ("retry", "Retry mechanism", True),
    ],
    DataprocessorDestinationStageType.data_explorer.value: [
        ("batch", "Batch method", True),
        ("columns", "Table column", True),
        ("retry", "Retry mechanism", True)
    ],
    DataprocessorDestinationStageType.mqtt.value: [
        ("qos", "QoS", False),
        ("userProperties", "MQTT user property", True),
        ("retry", "MQTT retry mechanism", True)
    ],
    DataprocessorDestinationStageType.reference_data.value: []
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


# Akri runtime attributes
AKRI_PREFIX = "aio-akri-"

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
AIO_MQ_HEALTH_MANAGER = "aio-mq-dmqtt-health-manager"

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
