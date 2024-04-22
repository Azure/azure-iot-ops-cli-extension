# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azext_edge.edge.common import OpsServiceType
from knack.log import get_logger
from .base import process_nodes, process_events, process_storage_classes

# Map for extension labels
EXTENSION_LABELS = {
    OpsServiceType.akri.value: "microsoft-iotoperations-akri",
    OpsServiceType.billing.value: "microsoft-iotoperations",
    OpsServiceType.dataprocessor.value: "microsoft-iotoperations-dp",
    OpsServiceType.mq.value: "microsoft-iotoperations-mq",
    OpsServiceType.opcua.value: "microsoft-iotoperations-opcuabroker",
}

NAME_LABEL_FORMAT = "app.kubernetes.io/name in ({label})"

logger = get_logger(__name__)

support_shared_elements = {"nodes": process_nodes, "events": process_events, "storageclasses": process_storage_classes}


def prepare_bundle() -> dict:
    shared_to_run = {}
    shared_to_run.update(support_shared_elements)

    return shared_to_run
