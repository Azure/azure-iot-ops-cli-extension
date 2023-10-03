# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, List

from knack.log import get_logger

from ..edge_api import BLUEFIN_API_V1, EdgeResourceApi
from .base import (
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)

logger = get_logger(__name__)


BLUEFIN_APP_LABEL = (
    "app in (bluefin-reader-worker,bluefin-refdata-store,bf-instance-nats-box,nats"
    ",bluefin-scheduler,bluefin-runner-worker,bluefin-portal,bluefin-api-proxy"
    ",bluefin-operator-controller-manager)"
)
BLUEFIN_RELEASE_LABEL = "release in (bf-instance)"
BLUEFIN_INSTANCE_LABEL = "app.kubernetes.io/instance in (bf-instance)"
BLUEFIN_PART_OF_LABEL = "app.kubernetes.io/part-of in (bluefin-operator)"
BLUEFIN_ONEOFF_LABEL = "control-plane in (controller-manager)"


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    bluefin_pods = process_v1_pods(
        resource_api=BLUEFIN_API_V1,
        label_selector=BLUEFIN_APP_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    bluefin_pods.extend(
        process_v1_pods(
            resource_api=BLUEFIN_API_V1,
            label_selector=BLUEFIN_INSTANCE_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )
    bluefin_pods.extend(
        process_v1_pods(
            resource_api=BLUEFIN_API_V1,
            label_selector=BLUEFIN_RELEASE_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )

    # @digimaun - TODO, depends on consistent labels
    temp_oneoffs = process_v1_pods(
        resource_api=BLUEFIN_API_V1,
        label_selector=BLUEFIN_ONEOFF_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )

    bluefin_pods.extend(_process_oneoff_label_entities(temp_oneoffs=temp_oneoffs))

    return bluefin_pods


def fetch_deployments():
    processed = process_deployments(resource_api=BLUEFIN_API_V1, label_selector=BLUEFIN_APP_LABEL)
    processed.extend(process_deployments(resource_api=BLUEFIN_API_V1, label_selector=BLUEFIN_PART_OF_LABEL))

    return processed


def fetch_statefulsets():
    processed = process_statefulset(
        resource_api=BLUEFIN_API_V1,
        label_selector=BLUEFIN_APP_LABEL,
    )
    processed.extend(process_statefulset(resource_api=BLUEFIN_API_V1, label_selector=BLUEFIN_RELEASE_LABEL))
    processed.extend(process_statefulset(resource_api=BLUEFIN_API_V1, label_selector=BLUEFIN_INSTANCE_LABEL))
    return processed


def fetch_replicasets():
    processed = []
    processed.extend(process_replicasets(resource_api=BLUEFIN_API_V1, label_selector=BLUEFIN_APP_LABEL))

    # @digimaun - TODO, depends on consistent labels
    temp_oneoffs = process_replicasets(resource_api=BLUEFIN_API_V1, label_selector=BLUEFIN_ONEOFF_LABEL)
    processed.extend(_process_oneoff_label_entities(temp_oneoffs=temp_oneoffs))

    return processed


def fetch_services():
    return process_services(resource_api=BLUEFIN_API_V1, label_selector=None, prefix_names=["bf-", "bluefin-"])


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_deployments,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    bluefin_to_run = {}
    bluefin_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    bluefin_to_run.update(support_runtime_elements)

    return bluefin_to_run


def _process_oneoff_label_entities(temp_oneoffs: List[dict]):
    processed = []
    for oneoff in temp_oneoffs:
        if "data" in oneoff and oneoff["data"] and isinstance(oneoff["data"], dict):
            name: str = oneoff["data"].get("metadata", {}).get("name")
            if name and any([name.startswith("bluefin-"), name.startswith("bf-")]):
                processed.append(oneoff)
    return processed
