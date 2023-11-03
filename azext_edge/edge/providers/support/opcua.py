# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import OPCUA_API_V1, EdgeResourceApi
from .base import assemble_crd_work, process_deployments, process_services, process_v1_pods, process_replicasets

logger = get_logger(__name__)


OPC_SUPERVISOR_SELECTOR = "metadata.name=aio-opc-supervisor"
SIMULATOR_SELECTOR = "metadata.name=opcplc-000000"
OPC_ORCHESTRATOR_LABEL = "orchestrator=opcuabroker"
OPC_APP_LABEL = "app in (aio-opc-supervisor, aio-opc-admission-controller)"
OPC_NAME_LABEL = "app.kubernetes.io/name in (aio-opc-opcua-connector, opcplc)"
# TODO: add daemonset once service confirms


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    opcua_pods = process_v1_pods(
        resource_api=OPCUA_API_V1,
        label_selector=OPC_APP_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    opcua_pods.extend(
        process_v1_pods(
            resource_api=OPCUA_API_V1,
            label_selector=OPC_NAME_LABEL,
            since_seconds=since_seconds,
            include_metrics=True,
            capture_previous_logs=True,
        )
    )
    return opcua_pods


def fetch_deployments():
    processed = process_deployments(resource_api=OPCUA_API_V1, field_selector=OPC_SUPERVISOR_SELECTOR)
    processed.extend(
        process_deployments(resource_api=OPCUA_API_V1, field_selector=SIMULATOR_SELECTOR)
    )
    processed.extend(
        process_deployments(resource_api=OPCUA_API_V1, label_selector=OPC_ORCHESTRATOR_LABEL)
    )
    processed.extend(
        process_deployments(resource_api=OPCUA_API_V1, label_selector=OPC_APP_LABEL)
    )
    return processed


def fetch_replicasets():
    processed = process_replicasets(resource_api=OPCUA_API_V1, label_selector=OPC_APP_LABEL)
    processed.extend(
        process_replicasets(resource_api=OPCUA_API_V1, label_selector=OPC_NAME_LABEL)
    )
    return processed


def fetch_services():
    processed = process_services(resource_api=OPCUA_API_V1, label_selector=OPC_APP_LABEL)
    processed.extend(
        process_services(resource_api=OPCUA_API_V1, field_selector=SIMULATOR_SELECTOR)
    )
    return processed


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    opcua_to_run = {}
    opcua_to_run.update(assemble_crd_work(apis))

    opcua_to_run.update({"pods": partial(fetch_pods, since_seconds=log_age_seconds)})
    opcua_to_run.update(support_runtime_elements)

    return opcua_to_run
