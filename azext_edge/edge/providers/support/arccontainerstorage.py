# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import ARCCONTAINERSTORAGE_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_daemonsets,
    process_deployments,
    process_persistent_volume_claims,
    process_replicasets,
    process_services,
    process_v1_pods,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

STORAGE_DIRECTORY_PATH = ARCCONTAINERSTORAGE_API_V1.moniker
STORAGE_INSTANCE_FIELD_SELECTOR = "metadata.name=azurefile"
STORAGE_NAMESPACE = "azure-arc-containerstorage"
STORAGE_NAME_LABEL = NAME_LABEL_FORMAT.format(label="arccontainerstorage")
STORAGE_SCHEMA_REGISTRY_LABEL = NAME_LABEL_FORMAT.format(label="w-adr-schema-registry-cache-claim")
APP_LABELS = ["edgevolume-mounthelper", "config-operator", "csi-wyvern-controller", "csi-wyvern-node"]
STORAGE_APP_LABEL = "app in ({})".format(",".join(APP_LABELS))


def fetch_deployments():
    processed = []

    for label in [STORAGE_NAME_LABEL, STORAGE_SCHEMA_REGISTRY_LABEL, STORAGE_APP_LABEL]:
        processed.extend(
            process_deployments(
                directory_path=STORAGE_DIRECTORY_PATH,
                label_selector=label,
                namespace=STORAGE_NAMESPACE,
            )
        )

    return processed


def fetch_replicasets():
    processed = []

    for label in [STORAGE_NAME_LABEL, STORAGE_SCHEMA_REGISTRY_LABEL, STORAGE_APP_LABEL]:
        processed.extend(
            process_replicasets(
                directory_path=STORAGE_DIRECTORY_PATH,
                label_selector=label,
                namespace=STORAGE_NAMESPACE,
            )
        )

    return processed


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = []

    for label in [STORAGE_NAME_LABEL, STORAGE_SCHEMA_REGISTRY_LABEL, STORAGE_APP_LABEL]:
        processed.extend(
            process_v1_pods(
                directory_path=STORAGE_DIRECTORY_PATH,
                label_selector=label,
                namespace=STORAGE_NAMESPACE,
                since_seconds=since_seconds,
            )
        )

    return processed


def fetch_daemonsets():
    processed = []

    for label in [STORAGE_NAME_LABEL, STORAGE_APP_LABEL]:
        processed.extend(
            process_daemonsets(
                directory_path=STORAGE_DIRECTORY_PATH,
                label_selector=label,
                namespace=STORAGE_NAMESPACE,
            )
        )

    return processed


def fetch_services():
    return process_services(
        directory_path=STORAGE_DIRECTORY_PATH,
        label_selector=STORAGE_SCHEMA_REGISTRY_LABEL,
        namespace=STORAGE_NAMESPACE,
    )


def fetch_peristent_volume_claims():
    return process_persistent_volume_claims(
        directory_path=STORAGE_DIRECTORY_PATH,
        prefix_names=["adr-schema-registry"],
        namespace=STORAGE_NAMESPACE,
    )


support_runtime_elements = {
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
    esa_to_run = {}

    if apis:
        esa_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    esa_to_run.update(support_runtime_elements)

    return esa_to_run
