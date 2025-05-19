# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional, List

from knack.log import get_logger

from .providers.orchestration.resources import Brokers
from .common import DEFAULT_BROKER
from .providers.orchestration.common import MqServiceType

logger = get_logger(__name__)


def list_dataflow_graphs(cmd, instance_name: str, resource_group_name: str):
    pass


def list_dataflow_graph_registries(cmd, instance_name: str, resource_group_name: str):
    pass


def create_dataflow_graph_registry(
    cmd,
    registry_name: str,
    endpoint_url: str,
    instance_name: str,
    credentials: str,
    resource_group_name: str,
    description: Optional[str] = None,
):
    pass
