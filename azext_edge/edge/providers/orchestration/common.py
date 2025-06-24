# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum

# Urls
ARM_ENDPOINT = "https://management.azure.com/"
MCR_ENDPOINT = "https://mcr.microsoft.com/"

CUSTOM_LOCATIONS_RP_APP_ID = "bc313c14-388c-4e7d-a58e-70017303ee3b"

CONTRIBUTOR_ROLE_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"

EXTENDED_LOCATION_ROLE_BINDING = "AzureArc-Microsoft.ExtendedLocation-RP-RoleBinding"
ARC_CONFIG_MAP = "azure-clusterconfig"
ARC_NAMESPACE = "azure-arc"

AIO_MQTT_DEFAULT_CONFIG_MAP = "azure-iot-operations-aio-ca-trust-bundle"
PROVISIONING_STATE_SUCCESS = "Succeeded"

# Key Vault KPIs
KEYVAULT_CLOUD_API_VERSION = "2022-07-01"

# Custom Locations KPIs
CUSTOM_LOCATIONS_API_VERSION = "2021-08-31-preview"

AIO_INSECURE_LISTENER_NAME = "default-insecure"
AIO_INSECURE_LISTENER_SERVICE_NAME = "aio-broker-insecure"
AIO_INSECURE_LISTENER_SERVICE_PORT = 1883

KAFKA_ENDPOINT_TYPE = "Kafka"
MQTT_ENDPOINT_TYPE = "Mqtt"

ADLS_ENDPOINT_USER_ASSIGNED_DEFAULT_SCOPE = "https://storage.azure.com/.default"

TRUST_ISSUER_KIND_KEY = "issuerKind"
TRUST_SETTING_KEYS = ["issuerName", TRUST_ISSUER_KIND_KEY, "configMapName", "configMapKey"]

EXTENSION_TYPE_PLATFORM = "microsoft.iotoperations.platform"
EXTENSION_TYPE_OSM = "microsoft.openservicemesh"
EXTENSION_TYPE_ACS = "microsoft.arc.containerstorage"
EXTENSION_TYPE_SSC = "microsoft.azure.secretstore"
EXTENSION_TYPE_OPS = "microsoft.iotoperations"

OPS_EXTENSION_DEPS = frozenset([EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_SSC, EXTENSION_TYPE_ACS])

EXTENSION_TYPE_TO_MONIKER_MAP = {
    EXTENSION_TYPE_PLATFORM: "platform",
    EXTENSION_TYPE_OSM: "openServiceMesh",
    EXTENSION_TYPE_ACS: "containerStorage",
    EXTENSION_TYPE_SSC: "secretStore",
    EXTENSION_TYPE_OPS: "iotOperations",
}

EXTENSION_MONIKER_TO_ALIAS_MAP = {
    "platform": "plat",
    "openServiceMesh": "osm",
    "secretStore": "ssc",
    "containerStorage": "acs",
    "iotOperations": "ops",
}

EXTENSION_ALIAS_TO_TYPE_MAP = {
    "plat": EXTENSION_TYPE_PLATFORM,
    "osm": EXTENSION_TYPE_OSM,
    "ssc": EXTENSION_TYPE_SSC,
    "acs": EXTENSION_TYPE_ACS,
    "ops": EXTENSION_TYPE_OPS,
}


class ClusterConnectStatus(Enum):
    CONNECTED = "Connected"


class MqMode(Enum):
    auto = "auto"
    distributed = "distributed"


class MqMemoryProfile(Enum):
    tiny = "Tiny"
    low = "Low"
    medium = "Medium"
    high = "High"


class MqServiceType(Enum):
    CLUSTERIP = "ClusterIp"
    LOADBALANCER = "LoadBalancer"
    NODEPORT = "NodePort"


class KubernetesDistroType(Enum):
    k3s = "K3s"
    k8s = "K8s"
    microk8s = "MicroK8s"


class IdentityUsageType(Enum):
    DATAFLOW = "dataflow"
    SCHEMA = "schema"


class SchemaType(Enum):
    """value is user friendly, full_value is the service friendly"""

    message = "message"

    @property
    def full_value(self) -> str:
        type_map = {SchemaType.message: "MessageSchema"}
        return type_map[self]


class SchemaFormat(Enum):
    """value is user friendly, full_value is the service friendly"""

    json = "json"
    delta = "delta"

    @property
    def full_value(self) -> str:
        format_map = {SchemaFormat.json: "JsonSchema/draft-07", SchemaFormat.delta: "Delta/1.0"}
        return format_map[self]


class ConfigSyncModeType(Enum):
    ADD = "add"
    FULL = "full"
    NONE = "none"


class ListenerProtocol(Enum):
    MQTT = "Mqtt"
    WEBSOCKETS = "WebSockets"


class TlsKeyAlgo(Enum):
    EC256 = "Ec256"
    EC384 = "Ec384"
    EC521 = "Ec521"
    ED25519 = "Ed25519"
    RSA2048 = "Rsa2048"
    RSA4096 = "Rsa4096"
    RSA8192 = "Rsa8192"


class TlsKeyRotation(Enum):
    ALWAYS = "Always"
    NEVER = "Never"


class DataflowOperationType(Enum):
    SOURCE = "Source"
    TRANSFORMATION = "BuiltInTransformation"
    DESTINATION = "Destination"


class DataflowEndpointType(Enum):
    DATAEXPLORER = "DataExplorer"
    DATALAKESTORAGE = "DataLakeStorage"
    FABRICONELAKE = "FabricOneLake"
    LOCALSTORAGE = "LocalStorage"
    AIOLOCALMQTT = "AIOLocalMqtt"
    EVENTGRID = "EventGrid"
    CUSTOMMQTT = "CustomMqtt"
    EVENTHUB = "EventHub"
    FABRICREALTIME = "FabricRealTime"
    CUSTOMKAFKA = "CustomKafka"


class DataflowEndpointAuthenticationType(Enum):
    ACCESSTOKEN = "AccessToken"
    ANONYMOUS = "Anonymous"
    SASL = "Sasl"
    SERVICEACCESSTOKEN = "ServiceAccountToken"
    SYSTEMASSIGNED = "SystemAssignedManagedIdentity"
    USERASSIGNED = "UserAssignedManagedIdentity"
    X509 = "X509Certificate"


class OperationalModeType(Enum):
    ENABLED = "Enabled"
    DISABLED = "Disabled"


class DataflowEndpointFabricPathType(Enum):
    FILES = "Files"
    TABLES = "Tables"


class DataflowEndpointKafkaAcksType(Enum):
    ZERO = "Zero"
    ONE = "One"
    ALL = "All"


class KafkaCloudEventAttributeType(Enum):
    PROPAGATE = "Propagate"
    CREATEORREMAP = "CreateOrRemap"


class KafkaCompressionType(Enum):
    NONE = "None"
    GZIP = "Gzip"
    LZ4 = "Lz4"
    SNAPPY = "Snappy"


class KafkaPartitionStrategyType(Enum):
    DEFAULT = "Default"
    STATIC = "Static"
    TOPIC = "Topic"
    PROPERTY = "Property"


class AuthenticationSaslType(Enum):
    PLAIN = "Plain"
    SCRAMSHA256 = "ScramSha256"
    SCRAMSHA512 = "ScramSha512"


class MqttRetainType(Enum):
    KEEP = "Keep"
    NEVER = "Never"


DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP = {
    DataflowEndpointType.DATAEXPLORER.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
    },
    DataflowEndpointType.DATALAKESTORAGE.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
        DataflowEndpointAuthenticationType.ACCESSTOKEN.value,
    },
    DataflowEndpointType.FABRICONELAKE.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
    },
    DataflowEndpointType.AIOLOCALMQTT.value: {
        DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value,
        DataflowEndpointAuthenticationType.X509.value,
        DataflowEndpointAuthenticationType.ANONYMOUS.value,
    },
    DataflowEndpointType.EVENTGRID.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
        DataflowEndpointAuthenticationType.X509.value,
    },
    DataflowEndpointType.CUSTOMMQTT.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
        DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value,
        DataflowEndpointAuthenticationType.X509.value,
        DataflowEndpointAuthenticationType.ANONYMOUS.value,
    },
    DataflowEndpointType.EVENTHUB.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
        DataflowEndpointAuthenticationType.SASL.value,
    },
    DataflowEndpointType.FABRICREALTIME.value: {
        DataflowEndpointAuthenticationType.SASL.value,
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
    },
    DataflowEndpointType.CUSTOMKAFKA.value: {
        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
        DataflowEndpointAuthenticationType.USERASSIGNED.value,
        DataflowEndpointAuthenticationType.SASL.value,
        DataflowEndpointAuthenticationType.ANONYMOUS.value,
    },
}

DATAFLOW_ENDPOINT_TYPE_SETTINGS = {
    DataflowEndpointType.DATAEXPLORER.value: "dataExplorerSettings",
    DataflowEndpointType.DATALAKESTORAGE.value: "dataLakeStorageSettings",
    DataflowEndpointType.FABRICONELAKE.value: "fabricOneLakeSettings",
    DataflowEndpointType.EVENTHUB.value: "kafkaSettings",
    DataflowEndpointType.FABRICREALTIME.value: "kafkaSettings",
    DataflowEndpointType.CUSTOMKAFKA.value: "kafkaSettings",
    DataflowEndpointType.LOCALSTORAGE.value: "localStorageSettings",
    DataflowEndpointType.AIOLOCALMQTT.value: "mqttSettings",
    DataflowEndpointType.EVENTGRID.value: "mqttSettings",
    DataflowEndpointType.CUSTOMMQTT.value: "mqttSettings",
    KAFKA_ENDPOINT_TYPE: "kafkaSettings",
    MQTT_ENDPOINT_TYPE: "mqttSettings",
}

AUTHENTICATION_TYPE_REQUIRED_PARAMS = {
    DataflowEndpointAuthenticationType.ACCESSTOKEN.value: {"at_secret_name"},
    DataflowEndpointAuthenticationType.SASL.value: {"sasl_secret_name", "sasl_type"},
    DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value: {},
    DataflowEndpointAuthenticationType.USERASSIGNED.value: {"client_id", "tenant_id"},
    DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value: {"sat_audience"},
    DataflowEndpointAuthenticationType.X509.value: {"x509_secret_name"},
    DataflowEndpointAuthenticationType.ANONYMOUS.value: {},
}

AUTHENTICATION_TYPE_REQUIRED_PARAMS_TEXT_MAP = {
    "client_id": "--client-id",
    "tenant_id": "--tenant-id",
    "audience": "--audience",
    "at_secret_name": "--secret-name",
    "sasl_secret_name": "--secret-name",
    "x509_secret_name": "--secret-name",
    "sasl_type": "--sasl-type",
    "sat_audience": "--audience",
}

DATAFLOW_OPERATION_TYPE_SETTINGS = {
    DataflowOperationType.SOURCE.value: "sourceSettings",
    DataflowOperationType.TRANSFORMATION.value: "builtInTransformationSettings",
    DataflowOperationType.DESTINATION.value: "destinationSettings",
}


X509_ISSUER_REF_KEYS = ["group", "kind", "name"]

# Clone
CLONE_INSTANCE_VERS_MAX = "1.2.0"
CLONE_INSTANCE_VERS_MIN = "1.0.34"


class CloneSummaryMode(Enum):
    SIMPLE = "simple"
    DETAILED = "detailed"


class CloneTemplateMode(Enum):
    NESTED = "nested"
    LINKED = "linked"


class CloneTemplateParams(Enum):
    INSTANCE_NAME = "instanceName"
    CLUSTER_NAME = "clusterName"
    CLUSTER_NAMESPACE = "clusterNamespace"
    CUSTOM_LOCATION_NAME = "customLocationName"
    OPS_EXTENSION_NAME = "opsExtensionName"
    SCHEMA_REGISTRY_ID = "schemaRegistryId"
    RESOURCE_SLUG = "resourceSlug"
    LOCATION = "location"
    APPLY_ROLE_ASSIGNMENTS = "applyRoleAssignments"


class X509FileExtension(Enum):
    PEM = ".pem"
    DER = ".der"
    CRL = ".crl"
    CRT = ".crt"
