# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import ORC_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_v1_pods,
    process_services,
    process_replicasets,
)

logger = get_logger(__name__)


ORC_APP_LABEL = "app in (aio-orc-api, cert-manager, cainjector, webhook)"
ORC_CONTROLLER_LABEL = "control-plane in (aio-plat-controller-manager)"
ORC_DIRECTORY_PATH = ORC_API_V1.moniker

# TODO: @jiacju - this label will be used near future for consistency
# META_AIO_NAME_LABEL = "app.kubernetes.io/name in (microsoft-iotoperations)"


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = []
    for label in [ORC_APP_LABEL, ORC_CONTROLLER_LABEL]:
        processed.extend(
            process_v1_pods(
                directory_path=ORC_DIRECTORY_PATH,
                label_selector=label,
                since_seconds=since_seconds,
            )
        )

    return processed


def fetch_deployments():
    processed = []
    for label in [ORC_APP_LABEL, ORC_CONTROLLER_LABEL]:
        processed.extend(process_deployments(directory_path=ORC_DIRECTORY_PATH, label_selector=label))

    return processed


def fetch_services():
    processed = []
    for label in [ORC_APP_LABEL, ORC_CONTROLLER_LABEL]:
        processed.extend(process_services(directory_path=ORC_DIRECTORY_PATH, label_selector=label))

    return processed


def fetch_replicasets():
    processed = []
    for label in [ORC_APP_LABEL, ORC_CONTROLLER_LABEL]:
        processed.extend(process_replicasets(directory_path=ORC_DIRECTORY_PATH, label_selector=label))

    return processed


support_runtime_elements = {
    "deployments": fetch_deployments,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    symphony_to_run = {}

    if apis:
        symphony_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    symphony_to_run.update(support_runtime_elements)

    return symphony_to_run
