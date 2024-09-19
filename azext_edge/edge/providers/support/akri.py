# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger
from .base import (
    DAY_IN_SECONDS,
    process_deployments,
    process_v1_pods,
    process_replicasets,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

AKRI_NAME_LABEL_V2 = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-akri")
AKRI_DIRECTORY_PATH = "akri"


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=AKRI_DIRECTORY_PATH,
        label_selector=AKRI_NAME_LABEL_V2,
        since_seconds=since_seconds,
    )


def fetch_deployments():
    return process_deployments(
        directory_path=AKRI_DIRECTORY_PATH,
        label_selector=AKRI_NAME_LABEL_V2,
    )


def fetch_replicasets():
    return process_replicasets(directory_path=AKRI_DIRECTORY_PATH, label_selector=AKRI_NAME_LABEL_V2)


support_runtime_elements = {
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    akri_to_run = {}
    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    akri_to_run.update(support_runtime_elements)

    return akri_to_run
