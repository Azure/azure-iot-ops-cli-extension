# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from azext_edge.edge.providers.edge_api.base import EdgeResourceApi

from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
    process_validating_webhook_configurations,
)
from .common import NAME_LABEL_FORMAT, MANAGED_BY_LABEL_FORMAT

logger = get_logger(__name__)

AKRI_NAME_LABEL_V2 = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-akri")
AKRI_MANAGED_BY_OPERATOR_LABEL = MANAGED_BY_LABEL_FORMAT.format(label="aio-akri-operator")
AKRI_DIRECTORY_PATH = "akri"


def fetch_services():
    return process_services(
        directory_path=AKRI_DIRECTORY_PATH,
        label_selector=AKRI_NAME_LABEL_V2,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    pods = []
    for label in [AKRI_NAME_LABEL_V2, AKRI_MANAGED_BY_OPERATOR_LABEL]:
        pods.extend(
            process_v1_pods(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=label,
                since_seconds=since_seconds,
            )
        )
    return pods


def fetch_deployments():
    return process_deployments(
        directory_path=AKRI_DIRECTORY_PATH,
        label_selector=AKRI_NAME_LABEL_V2,
    )


def fetch_statefulsets():
    pods = []
    for label in [AKRI_NAME_LABEL_V2, AKRI_MANAGED_BY_OPERATOR_LABEL]:
        pods.extend(
            process_statefulset(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=label,
            )
        )
    return pods


def fetch_replicasets():
    return process_replicasets(directory_path=AKRI_DIRECTORY_PATH, label_selector=AKRI_NAME_LABEL_V2)


def fetch_validating_webhook_configurations():
    return process_validating_webhook_configurations(
        directory_path=AKRI_DIRECTORY_PATH,
        label_selector=AKRI_NAME_LABEL_V2,
    )


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "statefulsets": fetch_statefulsets,
    "services": fetch_services,
    "validatingwebhooks": fetch_validating_webhook_configurations,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS, apis: Optional[Iterable[EdgeResourceApi]] = None) -> dict:
    akri_to_run = {}

    if apis:
        akri_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    akri_to_run.update(support_runtime_elements)

    return akri_to_run
