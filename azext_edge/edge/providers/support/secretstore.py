# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

SSC_DIRECTORY_PATH = "secretstore"
# TODO: Use common label once it is ready
SSC_NAMESPACE = "azure-secret-store"


def fetch_deployments():
    return process_deployments(
        directory_path=SSC_DIRECTORY_PATH,
        namespace=SSC_NAMESPACE,
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=SSC_DIRECTORY_PATH,
        namespace=SSC_NAMESPACE,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=SSC_DIRECTORY_PATH,
        since_seconds=since_seconds,
        namespace=SSC_NAMESPACE,
    )


def fetch_services():
    return process_services(
        directory_path=SSC_DIRECTORY_PATH,
        namespace=SSC_NAMESPACE,
    )


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    ssc_to_run = {}

    if apis:
        ssc_to_run.update(assemble_crd_work(apis=apis, directory_path=SSC_DIRECTORY_PATH))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    ssc_to_run.update(support_runtime_elements)

    return ssc_to_run
