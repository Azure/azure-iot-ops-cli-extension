# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import DATAFLOW_ACTIVE_API, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
    process_validating_webhook_configurations,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

DATAFLOW_NAME_LABEL = NAME_LABEL_FORMAT.format(label=DATAFLOW_ACTIVE_API.label)
DATAFLOW_DIRECTORY_PATH = DATAFLOW_ACTIVE_API.moniker
DATAFLOW_OPERATOR_PREFIX = "aio-dataflow-operator"
DATAFLOW_DEPLOYMENT_FIELD_SELECTOR = f"metadata.name={DATAFLOW_OPERATOR_PREFIX}"
DATAFLOW_PROFILE_POD_PREFIX = "aio-dataflow-"


def fetch_deployments():
    return process_deployments(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
    )


def fetch_services():
    return process_services(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
        since_seconds=since_seconds,
    )


def fetch_validating_webhook_configurations():
    return process_validating_webhook_configurations(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
    )


support_runtime_elements = {
    "deployments": fetch_deployments,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
    "validatingwebhooks": fetch_validating_webhook_configurations,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    dataflow_to_run = {}

    if apis:
        dataflow_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    dataflow_to_run.update(support_runtime_elements)

    return dataflow_to_run
