# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, List

from knack.log import get_logger

from ..edge_api import DATA_PROCESSOR_API_V1, EdgeResourceApi
from .base import (
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)

logger = get_logger(__name__)

DATA_PROCESSOR_APP_LABELS = [
    'aio-dp-reader-worker',
    'aio-dp-refdata-store',
    'nats',
    'aio-dp-runner-worker',
    'aio-dp-operator',
    'nfs-server-provisioner'
]

DATA_PROCESSOR_LABEL = f"app in ({','.join(DATA_PROCESSOR_APP_LABELS)})"
DATA_PROCESSOR_RELEASE_LABEL = "release in (processor)"
DATA_PROCESSOR_INSTANCE_LABEL = "app.kubernetes.io/instance in (processor)"
DATA_PROCESSOR_PART_OF_LABEL = "app.kubernetes.io/part-of in (aio-dp-operator)"
DATA_PROCESSOR_NAME_LABEL = "app.kubernetes.io/name in (dataprocessor)"
DATA_PROCESSOR_ONEOFF_LABEL = "control-plane in (controller-manager)"


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    dataprocessor_pods = process_v1_pods(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    dataprocessor_pods.extend(
        process_v1_pods(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_INSTANCE_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )
    dataprocessor_pods.extend(
        process_v1_pods(
            resource_api=DATA_PROCESSOR_API_V1,
            label_selector=DATA_PROCESSOR_RELEASE_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )

    # @digimaun - TODO, depends on consistent labels
    temp_oneoffs = process_v1_pods(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_ONEOFF_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )

    dataprocessor_pods.extend(_process_oneoff_label_entities(temp_oneoffs=temp_oneoffs))

    return dataprocessor_pods


def fetch_deployments():
    processed = process_deployments(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL)
    processed.extend(
        process_deployments(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_PART_OF_LABEL)
    )

    return processed


def fetch_statefulsets():
    processed = process_statefulset(
        resource_api=DATA_PROCESSOR_API_V1,
        label_selector=DATA_PROCESSOR_LABEL,
    )
    processed.extend(
        process_statefulset(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_RELEASE_LABEL)
    )
    processed.extend(
        process_statefulset(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_INSTANCE_LABEL)
    )
    return processed


def fetch_replicasets():
    processed = []
    processed.extend(process_replicasets(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL))

    # @digimaun - TODO, depends on consistent labels
    temp_oneoffs = process_replicasets(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_ONEOFF_LABEL)
    processed.extend(_process_oneoff_label_entities(temp_oneoffs=temp_oneoffs))

    return processed


def fetch_services():
    processed = []
    processed.extend(process_services(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_LABEL))
    processed.extend(
        process_services(resource_api=DATA_PROCESSOR_API_V1, label_selector=DATA_PROCESSOR_NAME_LABEL)
    )

    return processed


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_deployments,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    dataprocessor_to_run = {}
    dataprocessor_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    dataprocessor_to_run.update(support_runtime_elements)

    return dataprocessor_to_run


def _process_oneoff_label_entities(temp_oneoffs: List[dict]):
    processed = []
    for oneoff in temp_oneoffs:
        if "data" in oneoff and oneoff["data"] and isinstance(oneoff["data"], dict):
            name: str = oneoff["data"].get("metadata", {}).get("name")
            if name and name.startswith("aio-dp-"):
                processed.append(oneoff)
    return processed
