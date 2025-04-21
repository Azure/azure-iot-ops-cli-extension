# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import CERTMANAGER_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_config_maps,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

CERT_DIRECTORY_PATH = CERTMANAGER_API_V1.moniker
# No common label for azuremonitor
CERT_MANAGER_NAMESPACE = "cert-manager"
TRUST_BUNDLE_LABEL = "trust.cert-manager.io/bundle"


def fetch_deployments():
    return process_deployments(
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=CERT_DIRECTORY_PATH,
        since_seconds=since_seconds,
        namespace=CERT_MANAGER_NAMESPACE,
    )


def fetch_services():
    return process_services(
        directory_path=CERT_DIRECTORY_PATH,
        namespace=CERT_MANAGER_NAMESPACE,
    )


def fetch_configmaps():
    processed = process_config_maps(
        directory_path=CERT_DIRECTORY_PATH,
        label_selector=TRUST_BUNDLE_LABEL,
    )

    processed.extend(
        process_config_maps(
            directory_path=CERT_DIRECTORY_PATH,
            namespace=CERT_MANAGER_NAMESPACE,
        )
    )

    return processed


support_runtime_elements = {
    "configmaps": fetch_configmaps,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    monitor_to_run = {}

    if apis:
        monitor_to_run.update(assemble_crd_work(apis=apis, fallback_namespace=CERT_MANAGER_NAMESPACE))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    monitor_to_run.update(support_runtime_elements)

    return monitor_to_run
