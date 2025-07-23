# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import META_API_V1, EdgeResourceApi, MesoResourceKinds
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_deployments,
    process_jobs,
    process_mutating_webhook_configurations,
    process_replicasets,
    process_services,
    process_v1_pods,
    process_validating_webhook_configurations,
)
from .billing import AIO_USAGE_PREFIX, BILLING_RESOURCE_KIND
from .common import NAME_LABEL_FORMAT
from .meso import MESO_DIRECTORY_PATH

logger = get_logger(__name__)

META_NAME_LABEL = NAME_LABEL_FORMAT.format(label=META_API_V1.label)
META_DIRECTORY_PATH = META_API_V1.moniker
META_PREFIX_NAMES = "aio-operator"


def fetch_deployments():
    return process_deployments(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        exclude_prefixes=[AIO_USAGE_PREFIX, BILLING_RESOURCE_KIND],
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        exclude_prefixes=[AIO_USAGE_PREFIX, BILLING_RESOURCE_KIND],
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        since_seconds=since_seconds,
        exclude_prefixes=[AIO_USAGE_PREFIX, BILLING_RESOURCE_KIND],
    )


def fetch_services():
    return process_services(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        prefix_names=[META_PREFIX_NAMES],
        exclude_prefixes=[AIO_USAGE_PREFIX, BILLING_RESOURCE_KIND],
    )


def fetch_jobs():
    return process_jobs(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
        exclude_prefixes=[AIO_USAGE_PREFIX, BILLING_RESOURCE_KIND],
    )


def fetch_mutating_webhook_configurations():
    return process_mutating_webhook_configurations(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
    )


def fetch_validating_webhook_configurations():
    return process_validating_webhook_configurations(
        directory_path=META_DIRECTORY_PATH,
        label_selector=META_NAME_LABEL,
    )


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "jobs": fetch_jobs,
    "mutatingwebhooks": fetch_mutating_webhook_configurations,
    "validatingwebhooks": fetch_validating_webhook_configurations,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS, apis: Optional[Iterable[EdgeResourceApi]] = None) -> dict:
    meta_to_run = {}

    if apis:
        meta_to_run.update(
            assemble_crd_work(apis, kind_to_dir={MesoResourceKinds.OBSERVABILITY.value: MESO_DIRECTORY_PATH})
        )

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    meta_to_run.update(support_runtime_elements)

    return meta_to_run
