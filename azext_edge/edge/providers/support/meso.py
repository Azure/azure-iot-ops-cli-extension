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
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

MESO_NAME_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-observability")
MESO_CLUSTER_METRICS_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-observability-cluster-metrics")
MESO_DIRECTORY_PATH = "meso"


def fetch_deployments():
    results = []
    results.extend(process_deployments(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    ))
    results.extend(process_deployments(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
    ))
    return results


def fetch_replicasets():
    results = []
    results.extend(process_replicasets(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    ))
    results.extend(process_replicasets(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
    ))
    return results


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    results = []
    results.extend(process_v1_pods(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
        since_seconds=since_seconds,
    ))
    results.extend(process_v1_pods(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
        since_seconds=since_seconds,
    ))
    return results


def fetch_services():
    results = []
    results.extend(process_services(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    ))
    results.extend(process_services(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
    ))
    return results


def fetch_config_maps():
    results = []
    results.extend(process_config_maps(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    ))
    results.extend(process_config_maps(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
    ))
    return results


def fetch_cluster_roles():
    results = []
    results.extend(process_cluster_roles(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    ))
    results.extend(process_cluster_roles(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
    ))
    # Fetch specific cluster role by name
    results.extend(process_cluster_roles(
        directory_path=MESO_DIRECTORY_PATH,
        field_selector="metadata.name=aio-observability-operator-manager-role",
    ))
    return results


def fetch_cluster_role_bindings():
    results = []
    results.extend(process_cluster_role_bindings(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    ))
    results.extend(process_cluster_role_bindings(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_CLUSTER_METRICS_LABEL,
    ))
    return results


support_runtime_elements = {
    "configmaps": fetch_config_maps,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "clusterroles": fetch_cluster_roles,
    "clusterrolebindings": fetch_cluster_role_bindings,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    meso_to_run = {}

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    meso_to_run.update(support_runtime_elements)

    return meso_to_run
