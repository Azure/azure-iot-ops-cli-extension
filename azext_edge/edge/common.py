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


class ProvisioningState(Enum):
    """
    edge resource provisioning state.
    """

    succeeded = "Succeeded"
    failed = "Failed"
    updating = "Updating"
    canceled = "Canceled"
    provisioning = "Provisioning",
    deleting = "Deleting"
    accepted = "Accepted"


class E4kCheckType(Enum):
    """
    E4K environment check type.
    """

    pre = "pre"
    post = "post"


class E4kDiagnosticPropertyIndex(Enum):
    """
    E4K Diagnostic Property Index Strings
    """
    publishes_received_per_second = "e4k_publishes_received_per_second"
    publishes_sent_per_second = "e4k_publishes_sent_per_second"
    publish_route_replication_correctness = "e4k_publish_route_replication_correctness"
    publish_latency_mu_ms = "e4k_publish_latency_mu_ms"
    publish_latency_sigma_ms = "e4k_publish_latency_sigma_ms"
    connected_sessions = "e4k_connected_sessions"
    total_subscriptions = "e4k_total_subscriptions"


class SupportForEdgeServiceType(ListableEnum):
    """
    Edge resource type.
    """

    auto = "auto"
    e4k = "e4k"
    opcua = "opcua"
    bluefin = "bluefin"
    symphony = "symphony"


class AkriK8sDistroType(ListableEnum):
    """
    Akri K8s distro type.
    """

    k8s = "k8s"
    k3s = "k3s"
    minik8s = "minik8s"


class DeployablePasVersions(ListableEnum):
    """
    Deployable PAS versions.
    """

    v011 = "0.1.1"


# E4K runtime attributes

AZEDGE_DIAGNOSTICS_SERVICE = "azedge-diagnostics-service"
METRICS_SERVICE_API_PORT = 9600

AZEDGE_DIAGNOSTICS_PROBE_PREFIX = "azedge-diagnostics-probe"
AZEDGE_FRONTEND_PREFIX = "azedge-dmqtt-frontend"
AZEDGE_BACKEND_PREFIX = "azedge-dmqtt-backend"
AZEDGE_AUTH_PREFIX = "azedge-dmqtt-authentication"
AZEDGE_KAFKA_CONFIG_PREFIX = "azedge-kafka-config"

# Bluefin runtime attributes

BLUEFIN_READER_WORKER_PREFIX = "bluefin-reader-worker"
BLUEFIN_RUNNER_WORKER_PREFIX = "bluefin-runner-worker"
BLUEFIN_REFDATA_STORE_PREFIX = "bluefin-refdata-store"
BLUEFIN_NATS_PREFIX = "bluefin-nats"
BLUEFIN_OPERATOR_CONTROLLER_MANAGER = "bluefin-operator-controller-manager"

# Pre-deployment KPIs

MIN_K8S_VERSION = "1.20"
MIN_HELM_VERSION = "3.8.0"
