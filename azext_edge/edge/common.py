# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

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


class ProvisioningState(Enum):
    """
    Resource provisioning state.
    """

    succeeded = "Succeeded"
    failed = "Failed"
    updating = "Updating"
    canceled = "Canceled"
    provisioning = "Provisioning"
    deleting = "Deleting"
    accepted = "Accepted"


class MqDiagnosticPropertyIndex(Enum):
    """
    MQ Diagnostic Property Index Strings
    """

    publishes_received_per_second = "aio_mq_publishes_received_per_second"
    publishes_sent_per_second = "aio_mq_publishes_sent_per_second"
    publish_route_replication_correctness = "aio_mq_publish_route_replication_correctness"
    publish_latency_mu_ms = "aio_mq_publish_latency_mu_ms"
    publish_latency_sigma_ms = "aio_mq_publish_latency_sigma_ms"
    connected_sessions = "aio_mq_connected_sessions"
    total_subscriptions = "aio_mq_total_subscriptions"


class OpsServiceType(ListableEnum):
    """
    IoT Operations service type.
    """

    auto = "auto"
    mq = "mq"
    lnm = "lnm"
    opcua = "opcua"
    dataprocessor = "dataprocessor"
    orc = "orc"
    akri = "akri"
    deviceregistry = "deviceregistry"


class ResourceTypeMapping(Enum):
    """
    Resource type mappings for graph queries.
    """

    asset = "Microsoft.DeviceRegistry/assets"
    asset_endpoint_profile = "Microsoft.DeviceRegistry/assetEndpointProfiles"
    custom_location = "Microsoft.ExtendedLocation/customLocations"
    connected_cluster = "Microsoft.Kubernetes/connectedClusters"
    cluster_extensions = "Microsoft.KubernetesConfiguration/extensions"


class ClusterExtensionsMapping(Enum):
    """
    Cluster extension mappings.
    """

    asset = "microsoft.deviceregistry.assets"


class AEPAuthModes(Enum):
    """
    Authentication modes for asset endpoints
    """
    anonymous = "Anonymous"
    certificate = "Certificate"
    userpass = "UsernamePassword"


class K8sSecretType(Enum):
    """
    Supported k8s secret types.
    """

    opaque = "Opaque"
    tls = "kubernetes.io/tls"


# MQ runtime attributes

AIO_MQ_RESOURCE_PREFIX = "aio-mq-"
AIO_MQ_DIAGNOSTICS_SERVICE = "aio-mq-diagnostics-service"
AIO_MQ_OPERATOR = "aio-mq-operator"
METRICS_SERVICE_API_PORT = 9600
PROTOBUF_SERVICE_API_PORT = 9800
