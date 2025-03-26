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
MESO_DIRECTORY_PATH = "meso"


def fetch_deployments():
    return process_deployments(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
        since_seconds=since_seconds,
    )


def fetch_services():
    return process_services(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    )


def fetch_config_maps():
    return process_config_maps(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    )


def fetch_cluster_roles():
    return process_cluster_roles(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    )


def fetch_cluster_role_bindings():
    return process_cluster_role_bindings(
        directory_path=MESO_DIRECTORY_PATH,
        label_selector=MESO_NAME_LABEL,
    )


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
