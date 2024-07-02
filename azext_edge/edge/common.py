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

    @property
    def color(self) -> str:
        color_map = {
            CheckTaskStatus.success: "green",
            CheckTaskStatus.warning: "yellow",
            CheckTaskStatus.error: "red",
            CheckTaskStatus.skipped: "bright white",
        }
        return color_map[self]

    @property
    def emoji(self) -> str:
        emoji_map = {
            CheckTaskStatus.success: "heavy_check_mark",
            CheckTaskStatus.warning: "warning",
            CheckTaskStatus.error: "stop_sign",
            CheckTaskStatus.skipped: "hammer",
        }
        return f":{emoji_map[self]}:"

    @classmethod
    def map_to_colored_emoji(cls, value) -> str:
        return f"[{cls[value].color}]{cls[value].emoji}[{cls[value].color}]"


class ResourceState(Enum):
    """
    K8s resource state.
    """

    starting = "Starting"
    running = "Running"
    recovering = "Recovering"
    succeeded = "Succeeded"
    failed = "Failed"
    ok = "OK"
    warn = "warn"
    error = "Error"
    n_a = "N/A"

    @classmethod
    def map_to_color(cls, value) -> str:
        return cls.map_to_status(value).color

    @classmethod
    def map_to_status(cls, value) -> CheckTaskStatus:
        status_map = {
            cls.starting.value: CheckTaskStatus.warning,
            cls.recovering.value: CheckTaskStatus.warning,
            cls.warn.value: CheckTaskStatus.warning,
            cls.n_a.value: CheckTaskStatus.warning,
            cls.failed.value: CheckTaskStatus.error,
            cls.error.value: CheckTaskStatus.error,
        }
        return status_map.get(value, CheckTaskStatus.success)


class PodState(Enum):
    """
    K8s pod state.
    """

    pending = "Pending"
    running = "Running"
    succeeded = "Succeeded"
    failed = "Failed"
    unknown = "Unknown"

    @classmethod
    def map_to_status(cls, value) -> CheckTaskStatus:
        status_map = {
            cls.pending.value: CheckTaskStatus.warning,
            cls.unknown.value: CheckTaskStatus.warning,
            cls.failed.value: CheckTaskStatus.error,
        }
        return status_map.get(value, CheckTaskStatus.success)


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
    mq = "broker"
    opcua = "opcua"
    dataprocessor = "dataprocessor"
    orc = "orc"
    akri = "akri"
    deviceregistry = "deviceregistry"
    # TODO: re-enable billing once service is available post 0.6.0 release
    # billing = "billing"


class ResourceProviderMapping(ListableEnum):
    """
    Resource Provider mappings for graph queries.
    """

    deviceregistry = "Microsoft.DeviceRegistry"
    extended_location = "Microsoft.ExtendedLocation"
    kubernetes = "Microsoft.Kubernetes"
    kubernetes_configuration = "Microsoft.KubernetesConfiguration"


class ResourceTypeMapping(Enum):
    """
    Resource type mappings for graph queries.
    """

    asset = "assets"
    asset_endpoint_profile = "assetEndpointProfiles"
    custom_location = "customLocations"
    connected_cluster = "connectedClusters"
    cluster_extensions = "extensions"

    @property
    def full_resource_path(self):
        return f"{self.provider}/{self.value}"

    @property
    def provider(self):
        mapping = {
            ResourceTypeMapping.asset: ResourceProviderMapping.deviceregistry.value,
            ResourceTypeMapping.asset_endpoint_profile: ResourceProviderMapping.deviceregistry.value,
            ResourceTypeMapping.custom_location: ResourceProviderMapping.extended_location.value,
            ResourceTypeMapping.connected_cluster: ResourceProviderMapping.kubernetes.value,
            ResourceTypeMapping.cluster_extensions: ResourceProviderMapping.kubernetes_configuration.value,
        }
        return mapping[self]


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


class FileType(ListableEnum):
    """
    Supported file types/extensions for bulk asset operations.
    """
    csv = "csv"
    json = "json"
    portal_csv = "portal-csv"
    yaml = "yaml"


class BundleResourceKind(Enum):
    deployment = "Deployment"
    statefulset = "Statefulset"
    service = "Service"
    replicaset = "Replicaset"
    daemonset = "Daemonset"
    pvc = "PersistentVolumeClaim"
    job = "Job"
    cronjob = "CronJob"


# MQ runtime attributes

AIO_MQ_RESOURCE_PREFIX = "aio-mq-"
AIO_MQ_DIAGNOSTICS_SERVICE = "aio-mq-diagnostics-service"
AIO_MQ_OPERATOR = "aio-mq-operator"
METRICS_SERVICE_API_PORT = 9600
PROTOBUF_SERVICE_API_PORT = 9800

# Init Env Control

INIT_NO_PREFLIGHT_ENV_KEY = "AIO_CLI_INIT_PREFLIGHT_DISABLED"
