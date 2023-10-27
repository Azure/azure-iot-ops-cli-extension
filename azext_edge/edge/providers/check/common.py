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


class BluefinProcessorStageType(ListableEnum):
    """
    Bluefin data processor stage type.
    """
    aggregate = "processor/aggregate"
    enrich = "processor/enrich"
    filter = "processor/filter"
    grpc = "processor/grpc"
    http = "processor/http"
    lkv = "processor/lkv"
    transform = "processor/transform"


class BluefinDestinationStageType(ListableEnum):
    """
    Bluefin data destination stage type.
    """
    data_explorer = "output/dataexplorer"
    fabric = "output/fabric"
    file = "output/file"
    grpc = "output/grpc"
    http = "output/http"
    mqtt = "output/mqtt"
    reference_data = "output/refdata"


ERROR_NO_DETAIL = "<No detail available>"

BLUEFIN_INTERMEDIATE_STAGE_PROPERTIES = {
    BluefinProcessorStageType.aggregate.value: [("window.type", "Aggregate window type", False),
                                                ("window.size", "Aggregate window duration", False),
                                                ("properties", "Aggregate property", True)],
    BluefinProcessorStageType.enrich.value: [("dataset", "Enrich dataset ID", False),
                                             ("conditions", "Enrich condition", True)],
    BluefinProcessorStageType.filter.value: [("expression", "Filter expression", True)],
    BluefinProcessorStageType.grpc.value: [("serverAddress", "gRPC server address", False),
                                           ("rpcName", "gRPC RPC name", False),
                                           ("descriptor", "gRPC descriptor", False),
                                           ("request", "gRPC request", True),
                                           ("response", "gRPC response", True),
                                           ("retry", "gRPC retry mechanism", True)],
    BluefinProcessorStageType.http.value: [("url", "Request URL", False),
                                           ("method", "Request method", False),
                                           ("request", "gRPC request", True),
                                           ("response", "gRPC response", True),
                                           ("retry", "gRPC retry mechanism", True)],
    BluefinProcessorStageType.lkv.value: [("properties", "LKV property", True)],
    BluefinProcessorStageType.transform.value: [("expression", "Transform expression", True)]
}

BLUEFIN_DESTINATION_STAGE_PROPERTIES = {
    BluefinDestinationStageType.fabric.value: [("url", "Fabric Endpoint", False),
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
                                               ("retry", "Fabric retry mechanism", True)],
    BluefinDestinationStageType.grpc.value: [("serverAddress", "gRPC server address", False),
                                             ("rpcName", "gRPC RPC name", False),
                                             ("descriptor", "gRPC descriptor", False),
                                             ("request", "gRPC request", True),
                                             ("retry", "gRPC retry mechanism", True)],
    BluefinDestinationStageType.data_explorer.value: [("clusterUrl", "Data Explorer cluster URL", False),
                                                      ("database", "Data Explorer database", False),
                                                      ("table", "Data Explorer table", False),
                                                      ("authentication.type", "Data Explorer authentication type", False),
                                                      ("authentication.tenantId", "Tenant ID", False),
                                                      ("authentication.clientId", "Client ID", False),
                                                      ("authentication.clientSecret", "Client secret", False),
                                                      ("batch", "Data Explorer batch method", True),
                                                      ("columns", "Data Explorer table column", True),
                                                      ("retry", "Data Explorer retry mechanism", True)],
    BluefinDestinationStageType.mqtt.value: [("broker", "MQTT broker URL", False), ("qos", "MQTT QoS", False),
                                             ("topic", "MQTT topic", False),
                                             ("authentication.type", "MQTT authentication type", False),
                                             ("format.type", "MQTT format", False),
                                             ("format", "MQTT format", True),
                                             ("authentication", "MQTT authentication", True),
                                             ("userProperties", "MQTT user property", True),
                                             ("retry", "MQTT retry mechanism", True)],
    BluefinDestinationStageType.reference_data.value: [("dataset", "Dataset ID", False)]
}

# Check constants
ALL_NAMESPACES_TARGET = '_all_'


class MqCheckType(Enum):
    """
    MQ environment check type.
    """

    pre = "pre"
    post = "post"


# MQ connector enums
class KafkaTopicMapRouteType(Enum):
    """
    Kafka Connector Topic Map Route type:
    """

    kafka_to_mqtt = "kafkaToMqtt"
    mqtt_to_kafka = "mqttToKafka"


# Bluefin runtime attributes

BLUEFIN_READER_WORKER_PREFIX = "bluefin-reader-worker"
BLUEFIN_RUNNER_WORKER_PREFIX = "bluefin-runner-worker"
BLUEFIN_REFDATA_STORE_PREFIX = "bluefin-refdata-store"
BLUEFIN_NATS_PREFIX = "bluefin-nats"
BLUEFIN_OPERATOR_CONTROLLER_MANAGER = "bluefin-operator-controller-manager"

# MQ runtime attributes

AIO_MQ_DIAGNOSTICS_PROBE_PREFIX = "aio-mq-diagnostics-probe"
AIO_MQ_FRONTEND_PREFIX = "aio-mq-dmqtt-frontend"
AIO_MQ_BACKEND_PREFIX = "aio-mq-dmqtt-backend"
AIO_MQ_AUTH_PREFIX = "aio-mq-dmqtt-authentication"
AIO_MQ_KAFKA_CONFIG_PREFIX = "aio-mq-kafka-config"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"
