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
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_persistent_volume_claims,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)
from .shared import EXTENSION_LABELS, NAME_LABEL_FORMAT

logger = get_logger(__name__)

# TODO: @jiacju - will remove old labels once new labels are stabled
DATA_PROCESSOR_READER_WORKER_PREFIX = "aio-dp-reader-worker-"
DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL = "aio-dp-runner-worker"
DATA_PROCESSOR_REFDATA_STORE_APP_LABEL = "aio-dp-refdata-store"
DATA_PROCESSOR_NATS_APP_LABEL = "nats"
DATA_PROCESSOR_RUNNER_WORKER_PREFIX = f"{DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL}-"
DATA_PROCESSOR_APP_LABELS = [
    DATA_PROCESSOR_REFDATA_STORE_APP_LABEL,
    DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL,
    DATA_PROCESSOR_NATS_APP_LABEL,
    'aio-dp-reader-worker',
    'aio-dp-operator',
]
DATA_PROCESSOR_PVC_APP_LABELS = [
    DATA_PROCESSOR_REFDATA_STORE_APP_LABEL,
    DATA_PROCESSOR_RUNNER_WORKER_APP_LABEL,
]

DATA_PROCESSOR_LABEL = f"app in ({','.join(DATA_PROCESSOR_APP_LABELS)})"
DATA_PROCESSOR_NAME_LABEL = NAME_LABEL_FORMAT.format(label="dataprocessor")
DATA_PROCESSOR_INSTANCE_LABEL = "app.kubernetes.io/instance in (processor)"
DATA_PROCESSOR_PVC_APP_LABEL = NAME_LABEL_FORMAT.format(label=','.join(DATA_PROCESSOR_PVC_APP_LABELS))

# TODO: @jiacju - will remove once the nats issue the fixed
DATA_PROCESSOR_ONEOFF_LABEL = f"app in ({DATA_PROCESSOR_NATS_APP_LABEL})"
DATA_PROCESSOR_NAME_LABEL_V2 = NAME_LABEL_FORMAT.format(label=EXTENSION_LABELS["billing"])


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    dataprocessor_pods = process_v1_pods(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_LABEL,
        since_seconds=since_seconds,
        pod_prefix_for_init_container_logs=[
            DATA_PROCESSOR_READER_WORKER_PREFIX,
            DATA_PROCESSOR_RUNNER_WORKER_PREFIX,
        ],
    )

    dataprocessor_pods.extend(
        process_v1_pods(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
            since_seconds=since_seconds,
            pod_prefix_for_init_container_logs=[
                DATA_PROCESSOR_READER_WORKER_PREFIX,
                DATA_PROCESSOR_RUNNER_WORKER_PREFIX,
            ],
        )
    )

    return dataprocessor_pods


def fetch_deployments():
    processed = process_deployments(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL)
    processed.extend(
        process_deployments(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_NAME_LABEL_V2)
    )

    return processed


def fetch_statefulsets():
    processed = process_statefulset(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_LABEL,
    )
    processed.extend(
        process_statefulset(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_NAME_LABEL_V2,
        )
    )

    return processed


def fetch_replicasets():
    processed = process_replicasets(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL)
    processed.extend(
        process_replicasets(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_NAME_LABEL_V2)
    )

    return processed


def fetch_services():
    processed = []
    service_name_labels = [
        DATA_PROCESSOR_LABEL,
        DATA_PROCESSOR_NAME_LABEL,
    ]
    for service_name_label in service_name_labels:
        processed.extend(
            process_services(
                resource_api=DATA_PROCESSOR_API_V1,
                label_selector=service_name_label,
            )
        )

    processed.extend(
        process_services(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_NAME_LABEL_V2)
    )

    return processed


def fetch_persistent_volume_claims():
    processed = []
    persistent_volume_claims_name_labels = [
        DATA_PROCESSOR_PVC_APP_LABEL,
        DATA_PROCESSOR_NAME_LABEL,
        DATA_PROCESSOR_INSTANCE_LABEL,
        DATA_PROCESSOR_ONEOFF_LABEL,
    ]
    for persistent_volume_claims_name_label in persistent_volume_claims_name_labels:
        processed.extend(
            process_persistent_volume_claims(
                resource_api=DATA_PROCESSOR_API_V1,
                label_selector=persistent_volume_claims_name_label,
            )
        )

    processed.extend(
        process_persistent_volume_claims(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_NAME_LABEL_V2
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


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    dataprocessor_to_run = {}
    dataprocessor_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    dataprocessor_to_run.update(support_runtime_elements)

    return dataprocessor_to_run
