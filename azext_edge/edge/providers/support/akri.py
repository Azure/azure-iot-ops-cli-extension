# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import AKRI_API_V0, EdgeResourceApi
from .base import (
    assemble_crd_work, 
    process_daemonsets, 
    process_deployments, 
    process_v1_pods, 
    process_services, 
    process_replicasets
)

logger = get_logger(__name__)


AKRI_INSTANCE_LABEL = "app.kubernetes.io/instance in (akri-installation)"
AKRI_APP_LABEL = "app in (akri-controller, otel-collector)"
AKRI_NAME_LABEL = "name in (akri-agent, akri-opcua-asset-discovery)"
AKRI_SERVICE_LABEL = "service in (akri-metrics)"


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    processed = process_v1_pods(
        resource_api=AKRI_API_V0,
        label_selector=AKRI_INSTANCE_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    processed.extend(
        process_v1_pods(
            resource_api=AKRI_API_V0,
            label_selector=AKRI_APP_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )
    # TODO: Use with label when available.
    processed.extend(
        process_v1_pods(
            resource_api=AKRI_API_V0,
            label_selector=AKRI_NAME_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
            # prefix_names=["akri-"],
        )
    )

    return processed


def fetch_deployments():
    processed = []
    # there was one that had no freakin labels
    # TODO: Use with more specific label when available.
    processed.extend(
        process_deployments(
            resource_api=AKRI_API_V0,
            prefix_names=["akri-"],
        )
    )
    return processed


def fetch_daemonsets():
    return process_daemonsets(resource_api=AKRI_API_V0, label_selector=AKRI_NAME_LABEL)


def fetch_services():
    processed = process_services(resource_api=AKRI_API_V0, label_selector=AKRI_INSTANCE_LABEL)
    processed.extend(process_services(resource_api=AKRI_API_V0, label_selector=AKRI_SERVICE_LABEL))
    return processed


def fetch_replicasets():
    processed = process_replicasets(resource_api=AKRI_API_V0, label_selector=AKRI_INSTANCE_LABEL)
    processed.extend(process_replicasets(resource_api=AKRI_API_V0, label_selector=AKRI_APP_LABEL))
    return processed


support_runtime_elements = {
    "deployments": fetch_deployments,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
    "daemonsets": fetch_daemonsets,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    akri_to_run = {}
    akri_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    akri_to_run.update(support_runtime_elements)

    return akri_to_run
