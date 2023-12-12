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
    assemble_crd_work,
    process_daemonsets,
    process_deployments,
    process_v1_pods,
    process_services,
    process_replicasets,
)

logger = get_logger(__name__)


AKRI_NAME_LABEL = "name in (aio-akri-agent)"
AKRI_SERVICE_LABEL = "service in (aio-akri-metrics)"
AKRI_PREFIXES = ["aio-akri-", "akri-"]


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    processed = process_v1_pods(
        resource_api=AKRI_API_V0,
        prefix_names=AKRI_PREFIXES,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    processed.extend(
        process_v1_pods(
            resource_api=AKRI_API_V0,
            label_selector=AKRI_NAME_LABEL,
            since_seconds=since_seconds,
            capture_previous_logs=True,
        )
    )

    return processed


def fetch_deployments():
    return process_deployments(
        resource_api=AKRI_API_V0,
        prefix_names=AKRI_PREFIXES,
    )


def fetch_daemonsets():
    return process_daemonsets(resource_api=AKRI_API_V0, prefix_names=AKRI_PREFIXES)


def fetch_services():
    return process_services(resource_api=AKRI_API_V0, label_selector=AKRI_SERVICE_LABEL)


def fetch_replicasets():
    return process_replicasets(resource_api=AKRI_API_V0, prefix_names=AKRI_PREFIXES)


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
