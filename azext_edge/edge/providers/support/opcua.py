# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import OPCUA_API_V1, EdgeResourceApi
from .base import (
    assemble_crd_work,
    process_deployments,
    process_services,
    process_v1_pods,
    process_replicasets,
    process_daemonsets,
)

logger = get_logger(__name__)


SIMULATOR_PREFIX = "opcplc-"
OPC_PREFIX = "aio-opc-"
OPC_APP_LABEL = "app in (aio-opc-supervisor, aio-opc-admission-controller)"
OPC_NAME_LABEL = "app.kubernetes.io/name in (aio-opc-opcua-connector, opcplc)"
OPC_NAME_VAR_LABEL = "name in (aio-opc-asset-discovery)"


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    opcua_pods = process_v1_pods(
        resource_api=OPCUA_API_V1,
        label_selector=OPC_APP_LABEL,
        since_seconds=since_seconds,
        include_metrics=True,
    )
    opcua_pods.extend(
        process_v1_pods(
            resource_api=OPCUA_API_V1,
            label_selector=OPC_NAME_LABEL,
            since_seconds=since_seconds,
            include_metrics=True,
        )
    )
    opcua_pods.extend(
        process_v1_pods(
            resource_api=OPCUA_API_V1,
            label_selector=OPC_NAME_VAR_LABEL,
            since_seconds=since_seconds,
            include_metrics=True,
        )
    )
    return opcua_pods


def fetch_deployments():
    processed = process_deployments(resource_api=OPCUA_API_V1, prefix_names=[OPC_PREFIX, SIMULATOR_PREFIX])
    return processed


def fetch_replicasets():
    processed = process_replicasets(resource_api=OPCUA_API_V1, label_selector=OPC_APP_LABEL)
    processed.extend(process_replicasets(resource_api=OPCUA_API_V1, label_selector=OPC_NAME_LABEL))
    return processed


def fetch_services():
    processed = process_services(resource_api=OPCUA_API_V1, label_selector=OPC_APP_LABEL)
    processed.extend(process_services(resource_api=OPCUA_API_V1, prefix_names=[SIMULATOR_PREFIX]))
    return processed


def fetch_daemonsets():
    processed = process_daemonsets(
        resource_api=OPCUA_API_V1,
        field_selector="metadata.name==aio-opc-asset-discovery",
    )
    return processed


support_runtime_elements = {
    "daemonsets": fetch_daemonsets,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    opcua_to_run = {}
    opcua_to_run.update(assemble_crd_work(apis))

    opcua_to_run["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    opcua_to_run.update(support_runtime_elements)

    return opcua_to_run
