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

logger = get_logger(__name__)


AKRI_INSTANCE_LABEL = "app.kubernetes.io/instance in (akri)"
AKRI_APP_LABEL = "app in (otel-collector)"
AKRI_SERVICE_LABEL = "service in (aio-akri-metrics)"
AKRI_PREFIX = "aio-akri-"

AKRI_AGENT_LABEL = "aio-akri-agent"
AKRI_WEBHOOK_LABEL = "aio-akri-webhook-configuration"

AKRI_NAME_LABEL = "app.kubernetes.io/name in (0)"

# TODO: @jiacju - this label will be used near future for consistency
# AKRI_NAME_LABEL = "app.kubernetes.io/name in (microsoft-iotoperations-akri)"


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = process_v1_pods(
        resource_api=AKRI_API_V0,
        label_selector=AKRI_INSTANCE_LABEL,
        since_seconds=since_seconds,
    )
    processed.extend(
        process_v1_pods(
            resource_api=AKRI_API_V0,
            label_selector=AKRI_APP_LABEL,
            since_seconds=since_seconds,
        )
    )

    pod_name_label = AKRI_NAME_LABEL.replace("0", f"{AKRI_AGENT_LABEL}, {AKRI_WEBHOOK_LABEL}")
    processed.extend(
        process_v1_pods(
            resource_api=AKRI_API_V0,
            label_selector=pod_name_label,
            since_seconds=since_seconds,
        )
    )
    return processed


def fetch_deployments():
    processed = process_deployments(
        resource_api=AKRI_API_V0,
        label_selector=AKRI_INSTANCE_LABEL,
    )
    processed.extend(
        process_deployments(
            resource_api=AKRI_API_V0,
            label_selector=AKRI_APP_LABEL,
        )
    )

    deployment_name_label = AKRI_NAME_LABEL.replace("0", f"{AKRI_WEBHOOK_LABEL}")
    processed.extend(
        process_deployments(
            resource_api=AKRI_API_V0,
            label_selector=deployment_name_label,
        )
    )
    return processed


def fetch_daemonsets():
    processed = process_daemonsets(resource_api=AKRI_API_V0, label_selector=AKRI_INSTANCE_LABEL)

    daemonset_name_label = AKRI_NAME_LABEL.replace("0", f"{AKRI_AGENT_LABEL}")
    processed.extend(
        process_daemonsets(resource_api=AKRI_API_V0, label_selector=daemonset_name_label)
    )
    return processed


def fetch_services():
    processed = process_services(resource_api=AKRI_API_V0, label_selector=AKRI_SERVICE_LABEL)
    processed.extend(
        process_services(resource_api=AKRI_API_V0, label_selector=AKRI_INSTANCE_LABEL)
    )

    service_name_label = AKRI_NAME_LABEL.replace("0", f"{AKRI_WEBHOOK_LABEL}")
    processed.extend(
        process_services(resource_api=AKRI_API_V0, label_selector=service_name_label)
    )
    return processed


def fetch_replicasets():
    processed = process_replicasets(resource_api=AKRI_API_V0, label_selector=AKRI_INSTANCE_LABEL)
    processed.extend(
        process_replicasets(resource_api=AKRI_API_V0, label_selector=AKRI_APP_LABEL)
    )

    replicaset_name_label = AKRI_NAME_LABEL.replace("0", f"{AKRI_WEBHOOK_LABEL}")
    processed.extend(
        process_replicasets(resource_api=AKRI_API_V0, label_selector=replicaset_name_label)
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
