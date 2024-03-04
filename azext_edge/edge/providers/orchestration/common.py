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

EXTENDED_LOCATION_ROLE_BINDING = "AzureArc-Microsoft.ExtendedLocation-RP-RoleBinding"


class MqMode(Enum):
    auto = "auto"
    distributed = "distributed"


class MqMemoryProfile(Enum):
    tiny = "tiny"
    low = "low"
    medium = "medium"
    high = "high"


class MqServiceType(Enum):
    cluster_ip = "clusterIp"
    load_balancer = "loadBalancer"
    node_port = "nodePort"


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
]
