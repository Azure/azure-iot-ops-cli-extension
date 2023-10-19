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


class ProvisioningState(Enum):
    """
    edge resource provisioning state.
    """

    succeeded = "Succeeded"
    failed = "Failed"
    updating = "Updating"
    canceled = "Canceled"
    provisioning = "Provisioning"
    deleting = "Deleting"
    accepted = "Accepted"


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


class DeployablePasVersions(ListableEnum):
    """
    Deployable PAS versions.
    """

    v012 = "0.1.2"


class ResourceTypeMapping(Enum):
    """
    Resource type mappings for graph queries.
    """
    asset = "Microsoft.DeviceRegistry/assets"
    asset_endpoint_profile = "Microsoft.DeviceRegistry/assetEndpointProfiles"
    custom_location = "Microsoft.ExtendedLocation/customLocations"
    connected_cluster = "Microsoft.Kubernetes/connectedClusters"
    cluster_extensions = "Microsoft.KubernetesConfiguration/extensions"


# E4K runtime attributes

AZEDGE_DIAGNOSTICS_SERVICE = "azedge-diagnostics-service"
METRICS_SERVICE_API_PORT = 9600
PROTOBUF_SERVICE_API_PORT = 9800
