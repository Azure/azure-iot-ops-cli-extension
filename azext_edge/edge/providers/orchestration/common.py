# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from ...util.x509 import DEFAULT_VALID_DAYS as DEFAULT_X509_CA_VALID_DAYS


# Urls
ARM_ENDPOINT = "https://management.azure.com/"
MCR_ENDPOINT = "https://mcr.microsoft.com/"
GRAPH_ENDPOINT = "https://graph.microsoft.com/"
GRAPH_V1_ENDPOINT = f"{GRAPH_ENDPOINT}v1.0"
GRAPH_V1_SP_ENDPOINT = f"{GRAPH_V1_ENDPOINT}/servicePrincipals"
GRAPH_V1_APP_ENDPOINT = f"{GRAPH_V1_ENDPOINT}/applications"
DEFAULT_SERVICE_PRINCIPAL_SECRET_DAYS = 365
CUSTOM_LOCATIONS_RP_APP_ID = "bc313c14-388c-4e7d-a58e-70017303ee3b"

EXTENDED_LOCATION_ROLE_BINDING = "AzureArc-Microsoft.ExtendedLocation-RP-RoleBinding"
ARC_CONFIG_MAP = "azure-clusterconfig"
ARC_NAMESPACE = "azure-arc"

# Key Vault KPIs
KEYVAULT_ARC_EXTENSION_VERSION = "1.5.5"
KEYVAULT_DATAPLANE_API_VERSION = "7.4"
KEYVAULT_CLOUD_API_VERSION = "2022-07-01"

# Misc
MAX_INSTANCE_LENGTH = 37


class MqMode(Enum):
    auto = "auto"
    distributed = "distributed"


class MqMemoryProfile(Enum):
    tiny = "Tiny"
    low = "Low"
    medium = "Medium"
    high = "High"


class MqServiceType(Enum):
    cluster_ip = "ClusterIp"
    load_balancer = "LoadBalancer"
    node_port = "NodePort"


class KubernetesDistroType(Enum):
    k3s = "k3s"
    k8s = "k8s"
    microk8s = "microk8s"


__all__ = [
    "MqMode",
    "MqMemoryProfile",
    "MqServiceType",
    "KubernetesDistroType",
    "DEFAULT_X509_CA_VALID_DAYS",
    "DEFAULT_SERVICE_PRINCIPAL_SECRET_DAYS",
    "KEYVAULT_ARC_EXTENSION_VERSION",
    "KEYVAULT_DATAPLANE_API_VERSION",
    "KEYVAULT_CLOUD_API_VERSION",
]
