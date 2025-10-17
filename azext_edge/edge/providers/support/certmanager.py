# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from azext_edge.edge.providers.support.common import NAME_LABEL_FORMAT, RESOURCE_NAME_FIELD_FORMAT
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
    process_validating_webhook_configurations,
    process_mutating_webhook_configurations
)

logger = get_logger(__name__)

CERT_DIRECTORY_PATH = CERTMANAGER_API_V1.moniker
# No common label for azuremonitor
CERT_MANAGER_NAMESPACE = "cert-manager"
TRUST_BUNDLE_LABEL = "trust.cert-manager.io/bundle"
CERT_MANAGER_WEBHOOK_NAME = "cert-manager-webhook"
CERT_MANAGER_WEBHOOK_NAME_FIELD_SELECTOR = RESOURCE_NAME_FIELD_FORMAT.format(name=CERT_MANAGER_WEBHOOK_NAME)
TRUST_MANAGER_WEBHOOK_NAME = "trust-manager"
TRUST_MANAGER_WEBHOOK_LABEL = NAME_LABEL_FORMAT.format(label=TRUST_MANAGER_WEBHOOK_NAME)
TRUST_MANAGER_WEBHOOK_NAME_FIELD_SELECTOR = RESOURCE_NAME_FIELD_FORMAT.format(name=TRUST_MANAGER_WEBHOOK_NAME)


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


def fetch_validating_webhooks():
    results = []
    results.extend(
        process_validating_webhook_configurations(
            directory_path=CERT_DIRECTORY_PATH,
            label_selector=TRUST_MANAGER_WEBHOOK_LABEL,
        )
    )
    results.extend(
        process_validating_webhook_configurations(
            directory_path=CERT_DIRECTORY_PATH,
            field_selector=CERT_MANAGER_WEBHOOK_NAME_FIELD_SELECTOR,
        )
    )
    results.extend(
        process_mutating_webhook_configurations(
            directory_path=CERT_DIRECTORY_PATH,
            field_selector=CERT_MANAGER_WEBHOOK_NAME_FIELD_SELECTOR,
        )
    )
    return results


support_runtime_elements = {
    "configmaps": fetch_configmaps,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "validatingwebhooks": fetch_validating_webhooks,
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
