# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import AKRI_API_V0, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_daemonsets,
    process_deployments,
    process_v1_pods,
    process_services,
    process_replicasets,
)
from .shared import NAME_LABEL_FORMAT

logger = get_logger(__name__)

# TODO: @jiacju - will remove old labels once new labels are stabled
AKRI_INSTANCE_LABEL = "app.kubernetes.io/instance in (akri)"
AKRI_APP_LABEL = "app in (otel-collector)"
AKRI_SERVICE_LABEL = "service in (aio-akri-metrics)"

AKRI_AGENT_LABEL = "aio-akri-agent"
AKRI_WEBHOOK_LABEL = "aio-akri-webhook-configuration"

AKRI_NAME_LABEL_V2 = NAME_LABEL_FORMAT.format(label=AKRI_API_V0.label)
AKRI_POD_NAME_LABEL = NAME_LABEL_FORMAT.format(label=f"{AKRI_AGENT_LABEL}, {AKRI_WEBHOOK_LABEL}")
AKRI_DIRECTORY_PATH = AKRI_API_V0.moniker


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = []
    pod_name_labels = [
        AKRI_INSTANCE_LABEL,
        AKRI_APP_LABEL,
        AKRI_POD_NAME_LABEL,
    ]
    for pod_name_label in pod_name_labels:
        processed.extend(
            process_v1_pods(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=pod_name_label,
                since_seconds=since_seconds,
            )
        )

    processed.extend(
        process_v1_pods(
            directory_path=AKRI_DIRECTORY_PATH,
            label_selector=AKRI_NAME_LABEL_V2,
            since_seconds=since_seconds,
        )
    )
    return processed


def fetch_deployments():
    processed = []
    deployment_name_labels = [
        AKRI_INSTANCE_LABEL,
        AKRI_APP_LABEL,
        NAME_LABEL_FORMAT.format(label=AKRI_WEBHOOK_LABEL),
    ]
    for deployment_name_label in deployment_name_labels:
        processed.extend(
            process_deployments(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=deployment_name_label,
            )
        )

    processed.extend(
        process_deployments(
            directory_path=AKRI_DIRECTORY_PATH,
            label_selector=AKRI_NAME_LABEL_V2,
        )
    )
    return processed


def fetch_daemonsets():
    processed = []
    daemonset_name_labels = [
        AKRI_INSTANCE_LABEL,
        NAME_LABEL_FORMAT.format(label=AKRI_AGENT_LABEL),
    ]
    for daemonset_name_label in daemonset_name_labels:
        processed.extend(
            process_daemonsets(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=daemonset_name_label,
            )
        )

    processed.extend(
        process_daemonsets(directory_path=AKRI_DIRECTORY_PATH, label_selector=AKRI_NAME_LABEL_V2)
    )
    return processed


def fetch_services():
    processed = []
    service_name_labels = [
        AKRI_SERVICE_LABEL,
        AKRI_INSTANCE_LABEL,
        NAME_LABEL_FORMAT.format(label=AKRI_WEBHOOK_LABEL),
    ]
    for service_name_label in service_name_labels:
        processed.extend(
            process_services(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=service_name_label,
            )
        )

    processed.extend(
        process_services(directory_path=AKRI_DIRECTORY_PATH, label_selector=AKRI_NAME_LABEL_V2)
    )
    return processed


def fetch_replicasets():
    processed = []
    replicaset_name_labels = [
        AKRI_INSTANCE_LABEL,
        AKRI_APP_LABEL,
        NAME_LABEL_FORMAT.format(label=AKRI_WEBHOOK_LABEL),
    ]
    for replicaset_name_label in replicaset_name_labels:
        processed.extend(
            process_replicasets(
                directory_path=AKRI_DIRECTORY_PATH,
                label_selector=replicaset_name_label,
            )
        )

    processed.extend(
        process_replicasets(directory_path=AKRI_DIRECTORY_PATH, label_selector=AKRI_NAME_LABEL_V2)
    )
    return processed


support_runtime_elements = {
    "deployments": fetch_deployments,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
    "daemonsets": fetch_daemonsets,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    akri_to_run = {}
    akri_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    akri_to_run.update(support_runtime_elements)

    return akri_to_run
