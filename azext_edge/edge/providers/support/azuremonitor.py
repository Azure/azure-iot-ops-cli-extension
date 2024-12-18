# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import AZUREMONITOR_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_config_maps,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)

logger = get_logger(__name__)

MONITOR_DIRECTORY_PATH = AZUREMONITOR_API_V1.moniker
# No common label for azuremonitor
MONITOR_NAMESPACE = "azure-arc"
DIAGNOSTICS_OPERATOR_PREFIX = "diagnostics-operator"
DIAGNOSTICS_V1_PREFIX = "diagnostics-v1"


def fetch_deployments():
    return process_deployments(
        directory_path=MONITOR_DIRECTORY_PATH, namespace=MONITOR_NAMESPACE, prefix_names=[DIAGNOSTICS_OPERATOR_PREFIX]
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=MONITOR_DIRECTORY_PATH, namespace=MONITOR_NAMESPACE, prefix_names=[DIAGNOSTICS_OPERATOR_PREFIX]
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        since_seconds=since_seconds,
        prefix_names=[DIAGNOSTICS_OPERATOR_PREFIX, DIAGNOSTICS_V1_PREFIX],
    )


def fetch_services():
    return process_services(
        directory_path=MONITOR_DIRECTORY_PATH,
        namespace=MONITOR_NAMESPACE,
        prefix_names=[DIAGNOSTICS_OPERATOR_PREFIX, DIAGNOSTICS_V1_PREFIX],
    )


def fetch_statefulsets():
    return process_statefulset(
        directory_path=MONITOR_DIRECTORY_PATH,
        return_namespaces=False,
        namespace=MONITOR_NAMESPACE,
        prefix_names=[DIAGNOSTICS_V1_PREFIX],
    )


def fetch_configmaps():
    return process_config_maps(
        directory_path=MONITOR_DIRECTORY_PATH,
        prefix_names=[DIAGNOSTICS_V1_PREFIX],
    )


support_runtime_elements = {
    "configmaps": fetch_configmaps,
    "deployments": fetch_deployments,
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    monitor_to_run = {}

    if apis:
        monitor_to_run.update(assemble_crd_work(apis=apis, fallback_namespace=MONITOR_NAMESPACE))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    monitor_to_run.update(support_runtime_elements)

    return monitor_to_run
