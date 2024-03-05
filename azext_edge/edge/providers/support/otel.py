# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from .base import DAY_IN_SECONDS, process_v1_pods, process_deployments, process_services, process_replicasets
from ..edge_api import EdgeResourceApi

logger = get_logger(__name__)


OTEL_NAME_LABEL = "app.kubernetes.io/name in (aio-opentelemetry-collector)"

# Defined here as this is not an IoT Operations API
OTEL_API = EdgeResourceApi(group="otel", version="v1", moniker="otel")


def fetch_otel_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(resource_api=OTEL_API, label_selector=OTEL_NAME_LABEL, since_seconds=since_seconds)


def fetch_otel_deployments():
    return process_deployments(resource_api=OTEL_API, label_selector=OTEL_NAME_LABEL)


def fetch_otel_replicasets():
    return process_replicasets(resource_api=OTEL_API, label_selector=OTEL_NAME_LABEL)


def fetch_otel_services():
    return process_services(resource_api=OTEL_API, label_selector=OTEL_NAME_LABEL)


support_runtime_elements = {
    "deployments": fetch_otel_deployments,
    "replicasets": fetch_otel_replicasets,
    "services": fetch_otel_services,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    shared_to_run = {}

    shared_to_run["pods"] = partial(fetch_otel_pods, since_seconds=log_age_seconds)
    shared_to_run.update(support_runtime_elements)

    return shared_to_run
