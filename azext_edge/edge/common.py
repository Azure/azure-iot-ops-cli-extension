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
        return f"[{cls[value].color}]{cls[value].emoji}[/{cls[value].color}]"


class ResourceState(Enum):
    """
    K8s resource state.
    """

    starting = "starting"
    running = "running"
    recovering = "recovering"
    succeeded = "succeeded"
    failed = "failed"
    waiting = "waiting"
    warning = "warning"
    ok = "ok"
    warn = "warn"
    error = "error"
    n_a = "n/a"

    @classmethod
    def map_to_color(cls, value) -> str:
        return cls.map_to_status(value).color

    @classmethod
    def map_to_status(cls, value) -> CheckTaskStatus:
        value = value.lower()
        status_map = {
            cls.starting.value: CheckTaskStatus.warning,
            cls.recovering.value: CheckTaskStatus.warning,
            cls.warn.value: CheckTaskStatus.warning,
            cls.n_a.value: CheckTaskStatus.warning,
            cls.failed.value: CheckTaskStatus.error,
            cls.error.value: CheckTaskStatus.error,
            cls.waiting.value: CheckTaskStatus.warning,
            cls.warning.value: CheckTaskStatus.warning,
        }
        return status_map.get(value, CheckTaskStatus.success)


class PodState(Enum):
    """
    K8s pod state.
    """

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    unknown = "unknown"

    @classmethod
    def map_to_status(cls, value) -> CheckTaskStatus:
        value = value.lower()
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


class OpsServiceType(ListableEnum):
    """
    IoT Operations service type.
    """

    mq = "broker"
    openservicemesh = "osm"
    opcua = "opcua"
    akri = "akri"
    deviceregistry = "deviceregistry"
    billing = "billing"
    dataflow = "dataflow"
    schemaregistry = "schemaregistry"
    arccontainerstorage = "acs"
    secretstore = "secretstore"
    azuremonitor = "azuremonitor"
    certmanager = "certmanager"

    @classmethod
    def list_check_services(cls):
        return [
            cls.mq.value,
            cls.opcua.value,
            cls.akri.value,
            cls.deviceregistry.value,
            cls.dataflow.value,
        ]


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


class AEPAuthModes(Enum):
    """
    Authentication modes for asset endpoints
    """

    anonymous = "Anonymous"
    certificate = "Certificate"
    userpass = "UsernamePassword"


class AEPTypes(ListableEnum):
    """Asset Endpoint Profile (connector) Types"""

    opcua = "Microsoft.OpcUa"
    onvif = "Microsoft.Onvif"


class TopicRetain(Enum):
    """Set the retain flag for messages published to an MQTT broker."""

    keep = "Keep"
    never = "Never"


class SecurityModes(Enum):
    """Security modes for OPCUA connector."""

    none = "none"
    sign = "sign"
    sign_and_encrypt = "signAndEncrypt"


class SecurityPolicies(Enum):
    """Security policies for the OPCUA connector."""

    none = "none"
    basic128 = "Basic128Rsa15"
    basic256 = "Basic256"
    basic256sha256 = "Basic256Sha256"
    aes128 = "Aes128_Sha256_RsaOaep"
    aes256 = "Aes256_Sha256_RsaPss"


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

    json = "json"
    csv = "csv"
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
    configmap = "ConfigMap"


# Broker runtime attributes

AIO_BROKER_RESOURCE_PREFIX = "aio-broker-"
AIO_BROKER_DIAGNOSTICS_SERVICE = "aio-broker-diagnostics-service"
METRICS_SERVICE_API_PORT = 9600
PROTOBUF_SERVICE_API_PORT = 9800

# Broker constants
DEFAULT_BROKER = "default"
DEFAULT_BROKER_LISTENER = "default"
DEFAULT_BROKER_AUTHN = "default"

# Dataflow constants
DEFAULT_DATAFLOW_PROFILE = "default"
DEFAULT_DATAFLOW_ENDPOINT = "default"

# Init Env Control

INIT_NO_PREFLIGHT_ENV_KEY = "AIO_CLI_INIT_PREFLIGHT_DISABLED"
