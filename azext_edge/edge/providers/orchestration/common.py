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


__all__ = [
    "MqMode",
    "MqMemoryProfile",
    "MqServiceType",
    "DEFAULT_X509_CA_VALID_DAYS",
    "DEFAULT_SERVICE_PRINCIPAL_SECRET_DAYS",
]
