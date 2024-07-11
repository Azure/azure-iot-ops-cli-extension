# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger

from ..k8s.config_map import get_config_map
from ..orchestration.base import ARC_CONFIG_MAP, ARC_NAMESPACE
from .base import process_events, process_nodes, process_storage_classes

COMPONENT_LABEL_FORMAT = "app.kubernetes.io/component in ({label})"
NAME_LABEL_FORMAT = "app.kubernetes.io/name in ({label})"

logger = get_logger(__name__)


def process_arc_kpis():
    result = []
    connect_config_map = get_config_map(name=ARC_CONFIG_MAP, namespace=ARC_NAMESPACE)

    if connect_config_map:
        result.append(
            {
                "data": connect_config_map,
                "zinfo": f"{ARC_CONFIG_MAP}.yaml",
            }
        )
    return result


support_shared_elements = {
    "nodes": process_nodes,
    "events": process_events,
    "storageclasses": process_storage_classes,
    "arc": process_arc_kpis,
}


def prepare_bundle() -> dict:
    shared_to_run = {}
    shared_to_run.update(support_shared_elements)

    return shared_to_run
