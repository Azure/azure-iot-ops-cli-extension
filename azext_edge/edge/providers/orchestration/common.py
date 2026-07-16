# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum

# Urls
ARM_ENDPOINT = "https://management.azure.com/"
MCR_ENDPOINT = "https://mcr.microsoft.com/"
DEFAULT_REGISTRY_HOST = "mcr.microsoft.com"

# App IDs
CUSTOM_LOCATIONS_RP_APP_ID = "bc313c14-388c-4e7d-a58e-70017303ee3b"
ADR_RP_APP_ID = "6ce3f5ab-5f16-4633-a660-21ceb8d74c01"

# Role IDs
CONTRIBUTOR_ROLE_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"
AZURE_DEVICE_REGISTRY_ADMINISTRATOR_ROLE_ID = "12675fd7-7f59-493f-9201-f7944860a2f1"
KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID = "5d3f1697-4507-4d08-bb4a-477695db5f82"

EXTENDED_LOCATION_ROLE_BINDING = "AzureArc-Microsoft.ExtendedLocation-RP-RoleBinding"
ARC_CONFIG_MAP = "azure-clusterconfig"
ARC_NAMESPACE = "azure-arc"

AIO_MQTT_DEFAULT_CONFIG_MAP = "azure-iot-operations-aio-ca-trust-bundle"
PROVISIONING_STATE_SUCCESS = "Succeeded"
PROVISIONING_STATE_FAILED = "Failed"

# Commonly used API versions
KEYVAULT_CLOUD_API_VERSION = "2022-07-01"
CUSTOM_LOCATIONS_API_VERSION = "2021-08-31-preview"
SECRET_SYNC_API_VERSION = "2024-08-21-preview"
ROLE_ASSIGNMENT_API_VERSION = "2022-04-01"
MANAGED_IDENTITY_API_VERSION = "2023-01-31"
CLUSTER_EXTENSIONS_API_VERSION = "2023-05-01"

# Version threshold: init deployed ACS only on versions up to and including this.
MAX_INSTANCE_VERSION_ACS_DEPENDENCY = "1.1.69"

# Health check defaults
DEFAULT_HEALTH_CHECKS_MAX = 4
DEFAULT_HEALTH_CHECKS_INTERVAL = 30

AIO_INSECURE_LISTENER_NAME = "default-insecure"
AIO_INSECURE_LISTENER_SERVICE_NAME = "aio-broker-insecure"
AIO_INSECURE_LISTENER_SERVICE_PORT = 1883

KAFKA_ENDPOINT_TYPE = "Kafka"
MQTT_ENDPOINT_TYPE = "Mqtt"

ADLS_ENDPOINT_USER_ASSIGNED_DEFAULT_SCOPE = "https://storage.azure.com/.default"

TRUST_ISSUER_KIND_KEY = "issuerKind"
TRUST_SETTING_KEYS = ["issuerName", TRUST_ISSUER_KIND_KEY, "configMapName", "configMapKey"]

EXTENSION_TYPE_PLATFORM = "microsoft.iotoperations.platform"
EXTENSION_TYPE_ACS = "microsoft.arc.containerstorage"
EXTENSION_TYPE_SSC = "microsoft.azure.secretstore"
EXTENSION_TYPE_OPS = "microsoft.iotoperations"
EXTENSION_TYPE_CM = "microsoft.certmanagement"

EXTENSION_MONIKER_CM = "certManager"
EXTENSION_MONIKER_OPS = "iotOperations"
EXTENSION_MONIKER_ACS = "containerStorage"
EXTENSION_MONIKER_PLATFORM = "platform"
EXTENSION_MONIKER_SSC = "secretStore"

OPS_EXTENSION_DEPS = frozenset([EXTENSION_TYPE_CM, EXTENSION_TYPE_SSC])

EXTENSION_TYPE_TO_MONIKER_MAP = {
    EXTENSION_TYPE_CM: EXTENSION_MONIKER_CM,
    EXTENSION_TYPE_PLATFORM: EXTENSION_MONIKER_PLATFORM,
    EXTENSION_TYPE_SSC: EXTENSION_MONIKER_SSC,
    EXTENSION_TYPE_ACS: EXTENSION_MONIKER_ACS,
    EXTENSION_TYPE_OPS: EXTENSION_MONIKER_OPS,
}

EXTENSION_MONIKER_TO_ALIAS_MAP = {
    EXTENSION_MONIKER_CM: "cm",
    EXTENSION_MONIKER_PLATFORM: "plat",
    EXTENSION_MONIKER_SSC: "ssc",
    EXTENSION_MONIKER_ACS: "acs",
    EXTENSION_MONIKER_OPS: "ops",
}

EXTENSION_ALIAS_TO_TYPE_MAP = {
    "cm": EXTENSION_TYPE_CM,
    "plat": EXTENSION_TYPE_PLATFORM,
    "ssc": EXTENSION_TYPE_SSC,
    "acs": EXTENSION_TYPE_ACS,
    "ops": EXTENSION_TYPE_OPS,
}


class ClusterConnectStatus(Enum):
    CONNECTED = "Connected"


class MqMemoryProfile(Enum):
    tiny = "Tiny"
    low = "Low"
    medium = "Medium"
    high = "High"


class MqServiceType(Enum):
    CLUSTERIP = "ClusterIp"
    LOADBALANCER = "LoadBalancer"
    NODEPORT = "NodePort"


class IdentityUsageType(Enum):
    DATAFLOW = "dataflow"
    SCHEMA = "schema"
    WASM_GRAPH = "wasm-graph"


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
    OPENTELEMETRY = "OpenTelemetry"


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
    DataflowEndpointType.OPENTELEMETRY.value: {
        DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value,
        DataflowEndpointAuthenticationType.X509.value,
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
    DataflowEndpointType.OPENTELEMETRY.value: "openTelemetrySettings",
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
CLONE_INSTANCE_VERS_MAX = "1.4.0"
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
    ADR_NAMESPACE_ID = "adrNamespaceId"
    ADR_NAMESPACE_LOCATION = "adrNamespaceLocation"


class X509FileExtension(Enum):
    PEM = ".pem"
    DER = ".der"
    CRL = ".crl"
    CRT = ".crt"


class RegistryEndpointAuthenticationType(Enum):
    ANONYMOUS = "Anonymous"
    ARTIFACTPULLSECRET = "ArtifactPullSecret"
    SYSTEMASSIGNED = "SystemAssignedManagedIdentity"
    USERASSIGNED = "UserAssignedManagedIdentity"


class TrustedSigningKeyType(Enum):
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"


# Registry Endpoint Authentication Configuration
REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS = {
    RegistryEndpointAuthenticationType.ANONYMOUS.value: "anonymousSettings",
    RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value: "artifactPullSecretSettings",
    RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value: "systemAssignedManagedIdentitySettings",
    RegistryEndpointAuthenticationType.USERASSIGNED.value: "userAssignedManagedIdentitySettings",
}

REGISTRY_ENDPOINT_AUTHENTICATION_REQUIRED_PARAMS = {
    RegistryEndpointAuthenticationType.ANONYMOUS.value: set(),
    RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value: {"secret_ref"},
    RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value: set(),
    RegistryEndpointAuthenticationType.USERASSIGNED.value: {"client_id", "tenant_id"},
}

REGISTRY_ENDPOINT_AUTHENTICATION_OPTIONAL_PARAMS = {
    RegistryEndpointAuthenticationType.ANONYMOUS.value: set(),
    RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value: set(),
    RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value: {"audience"},
    RegistryEndpointAuthenticationType.USERASSIGNED.value: {"scope"},
}

REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP = {
    "secret_ref": "--secret-ref",
    "client_id": "--client-id",
    "tenant_id": "--tenant-id",
    "audience": "--audience",
    "scope": "--scope",
}

DATAFLOW_GRAPH_MEDIA_TYPE = "application/vnd.microsoft.dataflow.graph.v1+json"
DATAFLOW_GRAPH_ANNOTATION_DISPLAY_NAME = "org.opencontainers.artifact.displayName"
DATAFLOW_GRAPH_ANNOTATION_DESCRIPTION = "org.opencontainers.artifact.description"

# Notable instance versions
MIN_INSTANCE_VERSION_V2 = "1.2.36"
MIN_INSTANCE_VERSION_V1_FOR_V2_UPGRADE = "1.1.59"
MIN_INSTANCE_VERSION_FOR_CM_MIGRATE = "1.2.83"

# Management Actions
EG_TOPICSPACES_PUBLISHER_ROLE_ID = "a12b0b94-b317-4dcd-84a8-502ce99884c6"
EG_TOPICSPACES_SUBSCRIBER_ROLE_ID = "4b0f2fd7-60b4-4eca-896f-4435034f8bf5"
MIN_INSTANCE_VERSION_MGMT_ACTIONS = "1.3.14"
MGMT_ACTIONS_RESOURCE_PREFIX = "mgmt-actions"
MGMT_ACTIONS_DEFAULT_EG_CLIENT_GROUP = "$all"
MGMT_ACTIONS_DEFAULT_DATAFLOW_PROFILE = "default"
MGMT_ACTIONS_DEFAULT_MQTT_ENDPOINT = "default"
MGMT_ACTIONS_REQUEST_TOPIC_TEMPLATE = "actions/requests/{scope_id}/#"
MGMT_ACTIONS_RESPONSE_TOPIC_TEMPLATE = "actions/responses/{scope_id}/#"
MGMT_ACTIONS_DEFAULT_REGISTRY_ENDPOINT = "default"
MGMT_ACTIONS_ADR_ENDPOINT_TYPE = "Microsoft.EventGrid/Namespaces"
MGMT_ACTIONS_GRAPH_ARTIFACT = "azureiotoperations/graph-dataflow-map:1.0.0"
MGMT_ACTIONS_GRAPH_RULES_VERSION = "1.0.0"
MIN_EG_CLIENT_SESSIONS_PER_AUTH_NAME = 4
