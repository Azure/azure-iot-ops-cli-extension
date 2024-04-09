# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import ORC_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_v1_pods,
    process_services,
    process_replicasets
)

logger = get_logger(__name__)


ORC_INSTANCE_LABEL = "app.kubernetes.io/instance in (azure-iot-operations)"
ORC_APP_LABEL = "app in (aio-orc-api)"
ORC_CONTROLLER_LABEL = "control-plane in (aio-orc-controller-manager)"

# TODO: @jiacju - this label will be used near future for consistency
# META_AIO_NAME_LABEL = "app.kubernetes.io/name in (microsoft-iotoperations)"


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = process_v1_pods(
        resource_api=ORC_API_V1,
        label_selector=ORC_INSTANCE_LABEL,
        since_seconds=since_seconds,
    )
    processed.extend(
        process_v1_pods(
            resource_api=ORC_API_V1,
            label_selector=ORC_APP_LABEL,
            since_seconds=since_seconds,
        )
    )
    processed.extend(
        process_v1_pods(
            resource_api=ORC_API_V1,
            label_selector=ORC_CONTROLLER_LABEL,
            since_seconds=since_seconds,
        )
    )

    return processed


def fetch_deployments():
    processed = process_deployments(resource_api=ORC_API_V1, label_selector=ORC_INSTANCE_LABEL)
    processed.extend(process_deployments(resource_api=ORC_API_V1, label_selector=ORC_APP_LABEL))
    processed.extend(process_deployments(resource_api=ORC_API_V1, label_selector=ORC_CONTROLLER_LABEL))
    return processed


def fetch_services():
    processed = process_services(resource_api=ORC_API_V1, label_selector=ORC_INSTANCE_LABEL)
    processed.extend(process_services(resource_api=ORC_API_V1, label_selector=ORC_APP_LABEL))
    processed.extend(process_services(resource_api=ORC_API_V1, label_selector=ORC_CONTROLLER_LABEL))
    return processed


def fetch_replicasets():
    processed = process_replicasets(resource_api=ORC_API_V1, label_selector=ORC_INSTANCE_LABEL)
    processed.extend(process_replicasets(resource_api=ORC_API_V1, label_selector=ORC_APP_LABEL))
    processed.extend(process_replicasets(resource_api=ORC_API_V1, label_selector=ORC_CONTROLLER_LABEL))
    return processed


support_runtime_elements = {
    "deployments": fetch_deployments,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    symphony_to_run = {}
    symphony_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    symphony_to_run.update(support_runtime_elements)

    return symphony_to_run
