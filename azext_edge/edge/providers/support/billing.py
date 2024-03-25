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
    assemble_crd_work,
    process_cron_jobs,
    process_deployments,
    process_jobs,
    process_persistent_volume_claims,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)

logger = get_logger(__name__)

AIO_BILLING_USAGE_NAME_LABEL = "app.kubernetes.io/name in (microsoft-iotoperations)"
ARC_BILLING_EXTENSION_COMP_LABEL = "app.kubernetes.io/component in (billing-operator)"


# Since new pods will be created every 1 hour, we can fetch pods created in the last 3 hours
# or through filter of pod status 
def fetch_pods(
    since_seconds: int = 60 * 60 * 24,
    pod_states: List[str] = PodState.list()
):
    # capture billing pods for aio usage
    billing_pods = process_v1_pods(
        resource_api=BILLING_API_V1,
        label_selector=AIO_BILLING_USAGE_NAME_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
        pod_states=pod_states
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


# def fetch_statefulsets():
#     processed = process_statefulset(
#         resource_api=DATA_PROCESSOR_API_V1,
#         label_selector=DATA_PROCESSOR_LABEL,
#     )

#     return processed


def fetch_replicasets():
    processed = []
    processed.extend(process_replicasets(resource_api=BILLING_API_V1, label_selector=ARC_BILLING_EXTENSION_COMP_LABEL))

    return processed



def fetch_services():
    processed = []
    processed.extend(process_services(resource_api=BILLING_API_V1, label_selector=ARC_BILLING_EXTENSION_COMP_LABEL))

    return processed


# def fetch_persistent_volume_claims():
#     processed = []
#     processed.extend(
#         process_persistent_volume_claims(
#             resource_api=DATA_PROCESSOR_API_V1,
#             label_selector=DATA_PROCESSOR_PVC_APP_LABEL
#         )
#     )
#     processed.extend(
#         process_persistent_volume_claims(
#             resource_api=DATA_PROCESSOR_API_V1,
#             label_selector=DATA_PROCESSOR_NAME_LABEL
#         )
#     )
#     processed.extend(
#         process_persistent_volume_claims(
#             resource_api=DATA_PROCESSOR_API_V1,
#             label_selector=DATA_PROCESSOR_INSTANCE_LABEL
#         )
#     )

#     return processed


support_runtime_elements = {
    "cronjobs": fetch_cron_jobs,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "jobs": fetch_jobs,
}


def prepare_bundle(
        apis: Iterable[EdgeResourceApi],
        log_age_seconds: int = 60 * 60 * 24,
        pod_states: List[str] = PodState.list()
    ) -> dict:
    billing_to_run = {}
    billing_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds, pod_states=pod_states)
    billing_to_run.update(support_runtime_elements)

    return billing_to_run
