# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from .base import (
    DAY_IN_SECONDS,
    process_cluster_role_bindings,
    process_cluster_roles,
    process_config_maps,
    process_daemonsets,
    process_deployments,
    process_mutating_webhook_configurations,
    process_replicasets,
    process_services,
    process_v1_pods,
    process_validating_webhook_configurations,
)
from .common import NAME_LABEL_FORMAT, RESOURCE_NAME_FIELD_FORMAT

logger = get_logger(__name__)

MESO_NAME_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-observability")
MESO_CLUSTER_METRICS_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-observability-cluster-metrics")
MESO_OPERATOR_MANAGER_FIELD_SELECTOR = RESOURCE_NAME_FIELD_FORMAT.format(name="aio-observability-operator-manager-role")
MESO_DIRECTORY_PATH = "meso"

# List of label selectors to iterate through for most resources
MESO_LABEL_SELECTORS = [MESO_NAME_LABEL, MESO_CLUSTER_METRICS_LABEL]


def fetch_deployments():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_deployments(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_replicasets():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_replicasets(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_v1_pods(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
                since_seconds=since_seconds,
            )
        )
    return results


def fetch_services():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_services(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_config_maps():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_config_maps(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_cluster_roles():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_cluster_roles(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    # Fetch specific cluster role by name
    results.extend(
        process_cluster_roles(directory_path=MESO_DIRECTORY_PATH, field_selector=MESO_OPERATOR_MANAGER_FIELD_SELECTOR)
    )
    return results


def fetch_cluster_role_bindings():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_cluster_role_bindings(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_mutating_webhooks():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_mutating_webhook_configurations(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_validating_webhooks():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_validating_webhook_configurations(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


def fetch_daemonsets():
    results = []
    for label_selector in MESO_LABEL_SELECTORS:
        results.extend(
            process_daemonsets(
                directory_path=MESO_DIRECTORY_PATH,
                label_selector=label_selector,
            )
        )
    return results


support_runtime_elements = {
    "configmaps": fetch_config_maps,
    "deployments": fetch_deployments,
    "daemonsets": fetch_daemonsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "clusterroles": fetch_cluster_roles,
    "clusterrolebindings": fetch_cluster_role_bindings,
    "mutatingwebhooks": fetch_mutating_webhooks,
    "validatingwebhooks": fetch_validating_webhooks,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    meso_to_run = {}

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    meso_to_run.update(support_runtime_elements)

    return meso_to_run
