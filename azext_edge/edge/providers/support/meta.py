# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import META_API_V1B1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)
from .shared import NAME_LABEL_FORMAT

logger = get_logger(__name__)

META_NAME_LABEL = NAME_LABEL_FORMAT.format(label=META_API_V1B1.label)
META_DIRECTORY_PATH = META_API_V1B1.moniker
META_PREFIX_NAMES = "aio-operator"


def fetch_deployments():
    return process_deployments(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        prefix_names=[META_PREFIX_NAMES],
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        prefix_names=[META_PREFIX_NAMES],
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        since_seconds=since_seconds,
        prefix_names=[META_PREFIX_NAMES],
    )


def fetch_services():
    return process_services(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        prefix_names=[META_PREFIX_NAMES],
    )


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    apis: Iterable[EdgeResourceApi], log_age_seconds: int = DAY_IN_SECONDS
) -> dict:
    meta_to_run = {}
    meta_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    meta_to_run.update(support_runtime_elements)

    return meta_to_run
