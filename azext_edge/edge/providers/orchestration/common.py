# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

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
