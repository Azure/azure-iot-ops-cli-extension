# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from enum import Enum


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
