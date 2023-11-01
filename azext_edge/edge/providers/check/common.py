# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums) and constant strings for edge service checks.

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
    data_explorer = "output/dataexplorer"
    fabric = "output/fabric"
    file = "output/file"
    grpc = "output/grpc"
    http = "output/http"
    mqtt = "output/mqtt"
    reference_data = "output/refdata"


ERROR_NO_DETAIL = "<No detail available>"

DATA_PROCESSOR_INTERMEDIATE_STAGE_PROPERTIES = {
    DataProcessorStageType.aggregate.value: [
        ("window.type", "Aggregate window type", False),
        ("window.size", "Aggregate window duration", False),
        ("properties", "Aggregate property", True)
    ],
    DataProcessorStageType.enrich.value: [
        ("dataset", "Enrich dataset ID", False),
        ("conditions", "Enrich condition", True)
    ],
    DataProcessorStageType.filter.value: [("expression", "Filter expression", True)],
    DataProcessorStageType.grpc.value: [
        ("serverAddress", "gRPC server address", False),
        ("rpcName", "gRPC RPC name", False),
        ("descriptor", "gRPC descriptor", False),
        ("request", "gRPC request", True),
        ("response", "gRPC response", True),
        ("retry", "gRPC retry mechanism", True)
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
    DataprocessorDestinationStageType.fabric.value: [
        ("url", "Fabric Endpoint", False),
        ("workspace", "Fabric workspace ID", False),
        ("lakehouse", "Fabric lakehouse ID", False),
        ("table", "Fabric lakehouse table", False),
        ("authentication.type", "Data Explorer authentication type", False),
        ("authentication.tenantId", "Tenant ID", False),
        ("authentication.clientId", "Client ID", False),
        ("authentication.clientSecret", "Client secret", False),
        ("filePath", "Fabric template file path", True),
        ("batch", "Fabric batch method", True),
        ("columns", "Fabric table column", True),
        ("retry", "Fabric retry mechanism", True)
    ],
    DataprocessorDestinationStageType.grpc.value: [
        ("serverAddress", "gRPC server address", False),
        ("rpcName", "gRPC RPC name", False),
        ("descriptor", "gRPC descriptor", False),
        ("request", "gRPC request", True),
        ("retry", "gRPC retry mechanism", True)
    ],
    DataprocessorDestinationStageType.data_explorer.value: [
        ("clusterUrl", "Data Explorer cluster URL", False),
        ("database", "Data Explorer database", False),
        ("table", "Data Explorer table", False),
        ("authentication.type", "Data Explorer authentication type", False),
        ("authentication.tenantId", "Tenant ID", False),
        ("authentication.clientId", "Client ID", False),
        ("authentication.clientSecret", "Client secret", False),
        ("batch", "Data Explorer batch method", True),
        ("columns", "Data Explorer table column", True),
        ("retry", "Data Explorer retry mechanism", True)
    ],
    DataprocessorDestinationStageType.mqtt.value: [
        ("broker", "MQTT broker URL", False), ("qos", "MQTT QoS", False),
        ("topic", "MQTT topic", False),
        ("format", "MQTT format", True),
        ("authentication", "MQTT authentication", True),
        ("userProperties", "MQTT user property", True),
        ("retry", "MQTT retry mechanism", True)
    ],
    DataprocessorDestinationStageType.reference_data.value: [("dataset", "Dataset ID", False)]
}

# Check constants
ALL_NAMESPACES_TARGET = '_all_'


class E4kCheckType(Enum):
    """
    E4K environment check type.
    """

    pre = "pre"
    post = "post"


# E4k connector enums
class KafkaTopicMapRouteType(Enum):
    """
    Kafka Connector Topic Map Route type:
    """

    kafka_to_mqtt = "kafkaToMqtt"
    mqtt_to_kafka = "mqttToKafka"


# Data processor runtime attributes

DATA_PROCESSOR_READER_WORKER_PREFIX = "aio-dp-reader-worker"
DATA_PROCESSOR_RUNNER_WORKER_PREFIX = "aio-dp-runner-worker"
DATA_PROCESSOR_REFDATA_STORE_PREFIX = "aio-dp-refdata-store"
DATA_PROCESSOR_NATS_PREFIX = "aio-dp-msg-store"
DATA_PROCESSOR_OPERATOR = "aio-dp-operator"
DATA_PROCESSOR_NFS_SERVER_PROVISIONER = "aio-dp-nfs-server-provisioner"

# E4k runtime attributes

AZEDGE_DIAGNOSTICS_PROBE_PREFIX = "azedge-diagnostics-probe"
AZEDGE_FRONTEND_PREFIX = "azedge-dmqtt-frontend"
AZEDGE_BACKEND_PREFIX = "azedge-dmqtt-backend"
AZEDGE_AUTH_PREFIX = "azedge-dmqtt-authentication"
AZEDGE_KAFKA_CONFIG_PREFIX = "azedge-kafka-config"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"
