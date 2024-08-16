# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import DATAFLOW_API_V1B1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_v1_pods,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

DATAFLOW_NAME_LABEL = NAME_LABEL_FORMAT.format(label=DATAFLOW_API_V1B1.label)
DATAFLOW_DIRECTORY_PATH = DATAFLOW_API_V1B1.moniker


def fetch_deployments():
    processed = process_deployments(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
    )

    # TODO: remove this once dataflow deployment label is fixed
    processed.extend(
        process_deployments(
            directory_path=DATAFLOW_DIRECTORY_PATH,
            label_selector=DATAFLOW_NAME_LABEL,
        )
    )

    return processed


def fetch_replicasets():
    return process_replicasets(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=DATAFLOW_DIRECTORY_PATH,
        label_selector=DATAFLOW_NAME_LABEL,
        since_seconds=since_seconds,
    )


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
}


def prepare_bundle(
    apis: Iterable[EdgeResourceApi], log_age_seconds: int = DAY_IN_SECONDS
) -> dict:
    dataflow_to_run = {}
    dataflow_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    dataflow_to_run.update(support_runtime_elements)

    return dataflow_to_run
