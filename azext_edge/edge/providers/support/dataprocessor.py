# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import DATA_PROCESSOR_API_V1, EdgeResourceApi
from .base import (
    assemble_crd_work,
    process_deployments,
    process_persistent_volume_claims,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)

logger = get_logger(__name__)

DATA_PROCESSOR_READER_WORKER_PREFIX = "aio-dp-reader-worker-"
DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL = "aio-dp-runner-worker"
DATA_PROCESSOR_REFDATA_STORE_APP_LABEL = "aio-dp-refdata-store"
DATA_PROCESSOR_RUNNER_WORKER_PREFIX = f"{DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL}-"
DATA_PROCESSOR_APP_LABELS = [
    DATA_PROCESSOR_REFDATA_STORE_APP_LABEL,
    DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL,
    'aio-dp-reader-worker',
    'nats',
    'aio-dp-operator',
]
DATA_PROCESSOR_PVC_APP_LABELS = [
    DATA_PROCESSOR_REFDATA_STORE_APP_LABEL,
    DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL,
]

DATA_PROCESSOR_LABEL = f"app in ({','.join(DATA_PROCESSOR_APP_LABELS)})"
DATA_PROCESSOR_NAME_LABEL = "app.kubernetes.io/name in (dataprocessor)"
DATA_PROCESSOR_INSTANCE_LABEL = "app.kubernetes.io/instance in (processor)"
DATA_PROCESSOR_PVC_APP_LABEL = f"app in ({','.join(DATA_PROCESSOR_PVC_APP_LABELS)})"


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    dataprocessor_pods = process_v1_pods(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_LABEL,
        since_seconds=since_seconds,
        pod_prefix_for_init_container_logs=[
            DATA_PROCESSOR_READER_WORKER_PREFIX,
            DATA_PROCESSOR_RUNNER_WORKER_PREFIX,
        ],
    )

    return dataprocessor_pods


def fetch_deployments():
    processed = process_deployments(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL)

    return processed


def fetch_statefulsets():
    processed = process_statefulset(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_LABEL,
    )

    return processed


def fetch_replicasets():
    processed = []
    processed.extend(process_replicasets(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL))

    return processed


def fetch_services():
    processed = []
    processed.extend(process_services(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL))
    processed.extend(
        process_services(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_NAME_LABEL)
    )

    return processed


def fetch_persistent_volume_claims():
    processed = []
    processed.extend(
        process_persistent_volume_claims(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_PVC_APP_LABEL
        )
    )
    processed.extend(
        process_persistent_volume_claims(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_NAME_LABEL
        )
    )
    processed.extend(
        process_persistent_volume_claims(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_INSTANCE_LABEL
        )
    )

    return processed


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_deployments,
    "persistentvolumeclaims": fetch_persistent_volume_claims,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    dataprocessor_to_run = {}
    dataprocessor_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    dataprocessor_to_run.update(support_runtime_elements)

    return dataprocessor_to_run
