# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums) and constant strings for edge service checks.

"""

from enum import Enum
from azext_edge.edge.common import ListableEnum


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


BLUEFIN_INTERMEDIATE_STAGE_PROPERTIES = {
    BluefinProcessorStageType.aggregate.value: [("window.type", "Aggregate window type"),
                                                ("window.size", "Aggregate window duration")],
    BluefinProcessorStageType.enrich.value: [("dataset", "Enrich dataset ID")],
    BluefinProcessorStageType.grpc.value: [("serverAddress", "gRPC server address"),
                                           ("rpcName", "gRPC RPC name"),
                                           ("descriptor", "gRPC descriptor")],
    BluefinProcessorStageType.http.value: [("url", "Request URL"),
                                           ("method", "Request method")]
}

BLUEFIN_DESTINATION_STAGE_PROPERTIES = {
    BluefinDestinationStageType.fabric.value: [("url", "Fabric Endpoint"),
                                               ("workspace", "Fabric workspace ID"),
                                               ("lakehouse", "Fabric lakehouse ID"),
                                               ("table", "Fabric lakehouse table"),
                                               ("authentication.type", "Data Explorer authentication type"),
                                               ("authentication.tenantId", "Tenant ID"),
                                               ("authentication.clientId", "Client ID"),
                                               ("authentication.clientSecret", "Client secret")],
    BluefinDestinationStageType.grpc.value: [("serverAddress", "gRPC server address"),
                                             ("rpcName", "gRPC RPC name"),
                                             ("descriptor", "gRPC descriptor")],
    BluefinDestinationStageType.data_explorer.value: [("clusterUrl", "Data Explorer cluster URL"),
                                                      ("database", "Data Explorer database"),
                                                      ("table", "Data Explorer table"),
                                                      ("authentication.type", "Data Explorer authentication type"),
                                                      ("authentication.tenantId", "Tenant ID"),
                                                      ("authentication.clientId", "Client ID"),
                                                      ("authentication.clientSecret", "Client secret")],
    BluefinDestinationStageType.mqtt.value: [("broker", "MQTT broker URL"), ("qos", "MQTT QoS"),
                                             ("topic", "MQTT topic"),
                                             ("authentication.type", "MQTT authentication type"),
                                             ("format.type", "MQTT format")],
    BluefinDestinationStageType.reference_data.value: [("dataset", "Dataset ID")]
}


class E4kCheckType(Enum):
    """
    E4K environment check type.
    """

    pre = "pre"
    post = "post"


# Bluefin runtime attributes

BLUEFIN_READER_WORKER_PREFIX = "bluefin-reader-worker"
BLUEFIN_RUNNER_WORKER_PREFIX = "bluefin-runner-worker"
BLUEFIN_REFDATA_STORE_PREFIX = "bluefin-refdata-store"
BLUEFIN_NATS_PREFIX = "bluefin-nats"
BLUEFIN_OPERATOR_CONTROLLER_MANAGER = "bluefin-operator-controller-manager"

# E4k runtime attributes

AZEDGE_DIAGNOSTICS_PROBE_PREFIX = "azedge-diagnostics-probe"
AZEDGE_FRONTEND_PREFIX = "azedge-dmqtt-frontend"
AZEDGE_BACKEND_PREFIX = "azedge-dmqtt-backend"
AZEDGE_AUTH_PREFIX = "azedge-dmqtt-authentication"
AZEDGE_KAFKA_CONFIG_PREFIX = "azedge-kafka-config"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"
MIN_HELM_VERSION = "3.8.0"
