# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from ...util.x509 import DEFAULT_VALID_DAYS as DEFAULT_X509_CA_VALID_DAYS
from .base import DEFAULT_SERVICE_PRINCIPAL_SECRET_DAYS


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
