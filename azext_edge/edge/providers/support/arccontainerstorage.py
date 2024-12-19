# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import ARCCONTAINERSTORAGE_API_V1, CONTAINERSTORAGE_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_config_maps,
    process_daemonsets,
    process_deployments,
    process_persistent_volume_claims,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

STORAGE_DIRECTORY_PATH = ARCCONTAINERSTORAGE_API_V1.moniker
ACSTOR_DIRECTORY_PATH = CONTAINERSTORAGE_API_V1.moniker
# TODO: Use common label once it is ready
STORAGE_NAMESPACE = "azure-arc-containerstorage"
ACSTOR_NAMESPACE = "azure-arc-acstor"


def fetch_deployments():
    processed = process_deployments(
        directory_path=STORAGE_DIRECTORY_PATH,
        namespace=STORAGE_NAMESPACE,
    )

    processed.extend(
        process_deployments(
            directory_path=ACSTOR_DIRECTORY_PATH,
            namespace=ACSTOR_NAMESPACE,
        )
    )

    return processed


def fetch_replicasets():
    processed = process_replicasets(
        directory_path=STORAGE_DIRECTORY_PATH,
        namespace=STORAGE_NAMESPACE,
    )

    processed.extend(
        process_replicasets(
            directory_path=ACSTOR_DIRECTORY_PATH,
            namespace=ACSTOR_NAMESPACE,
        )
    )

    return processed


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = process_v1_pods(
        directory_path=STORAGE_DIRECTORY_PATH,
        namespace=STORAGE_NAMESPACE,
        since_seconds=since_seconds,
    )

    processed.extend(
        process_v1_pods(
            directory_path=ACSTOR_DIRECTORY_PATH,
            namespace=ACSTOR_NAMESPACE,
            since_seconds=since_seconds,
        )
    )

    return processed


def fetch_daemonsets():
    processed = process_daemonsets(
        directory_path=STORAGE_DIRECTORY_PATH,
        namespace=STORAGE_NAMESPACE,
    )

    processed.extend(
        process_daemonsets(
            directory_path=ACSTOR_DIRECTORY_PATH,
            namespace=ACSTOR_NAMESPACE,
        )
    )

    return processed


def fetch_services():
    processed = process_services(
        directory_path=STORAGE_DIRECTORY_PATH,
        namespace=STORAGE_NAMESPACE,
    )

    processed.extend(
        process_services(
            directory_path=ACSTOR_DIRECTORY_PATH,
            namespace=ACSTOR_NAMESPACE,
        )
    )

    return processed


def fetch_peristent_volume_claims():
    return process_persistent_volume_claims(
        directory_path=STORAGE_DIRECTORY_PATH,
        namespace=STORAGE_NAMESPACE,
    )


def fetch_configmaps():
    return process_config_maps(
        directory_path=ACSTOR_DIRECTORY_PATH,
        namespace=ACSTOR_NAMESPACE,
    )


support_runtime_elements = {
    "configmaps": fetch_configmaps,
    "daemonsets": fetch_daemonsets,
    "deployments": fetch_deployments,
    "persistentvolumeclaims": fetch_peristent_volume_claims,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    acs_to_run = {}

    if apis:
        acs_to_run.update(assemble_crd_work(apis=apis, fallback_namespace=STORAGE_NAMESPACE))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    acs_to_run.update(support_runtime_elements)

    return acs_to_run
