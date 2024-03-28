# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, List

from azext_edge.edge.common import PodState
from knack.log import get_logger

from ..edge_api import BILLING_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_cron_jobs,
    process_deployments,
    process_jobs,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

AIO_BILLING_USAGE_NAME_LABEL = "app.kubernetes.io/name in (microsoft-iotoperations)"
ARC_BILLING_EXTENSION_COMP_LABEL = "app.kubernetes.io/component in (billing-operator)"


def fetch_pods(
    since_seconds: int = DAY_IN_SECONDS,
) -> List[PodState]:
    # capture billing pods for aio usage
    billing_pods = process_v1_pods(
        resource_api=BILLING_API_V1,
        label_selector=AIO_BILLING_USAGE_NAME_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )

    # capture billing pods for arc extension
    billing_pods.extend(
        process_v1_pods(
            resource_api=BILLING_API_V1,
            label_selector=ARC_BILLING_EXTENSION_COMP_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )

    return billing_pods


def fetch_jobs():
    processed = process_jobs(resource_api=BILLING_API_V1, label_selector=AIO_BILLING_USAGE_NAME_LABEL)

    return processed


def fetch_cron_jobs():
    processed = process_cron_jobs(resource_api=BILLING_API_V1, label_selector=AIO_BILLING_USAGE_NAME_LABEL)

    return processed


def fetch_deployments():
    processed = process_deployments(resource_api=BILLING_API_V1, label_selector=ARC_BILLING_EXTENSION_COMP_LABEL)

    return processed


def fetch_replicasets():
    processed = []
    processed.extend(process_replicasets(resource_api=BILLING_API_V1, label_selector=ARC_BILLING_EXTENSION_COMP_LABEL))

    return processed


def fetch_services():
    processed = []
    processed.extend(process_services(resource_api=BILLING_API_V1, label_selector=ARC_BILLING_EXTENSION_COMP_LABEL))

    return processed


support_runtime_elements = {
    "cronjobs": fetch_cron_jobs,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "jobs": fetch_jobs,
}


def prepare_bundle(
    apis: Iterable[EdgeResourceApi],
    log_age_seconds: int = DAY_IN_SECONDS,
) -> dict:
    billing_to_run = {}
    billing_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    billing_to_run.update(support_runtime_elements)

    return billing_to_run
