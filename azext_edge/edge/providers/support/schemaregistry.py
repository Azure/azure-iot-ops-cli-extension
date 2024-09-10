# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from knack.log import get_logger

from .base import (
    DAY_IN_SECONDS,
    process_config_maps,
    process_services,
    process_statefulset,
    process_v1_pods,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

SCHEMAS_NAME_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-schemas")
SCHEMAS_DIRECTORY_PATH = "schemaregistry"


def fetch_stateful_sets():
    return process_statefulset(
        directory_path=SCHEMAS_DIRECTORY_PATH,
        label_selector=SCHEMAS_NAME_LABEL,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=SCHEMAS_DIRECTORY_PATH,
        label_selector=SCHEMAS_NAME_LABEL,
        since_seconds=since_seconds,
    )


def fetch_config_map():
    return process_config_maps(
        directory_path=SCHEMAS_DIRECTORY_PATH,
        label_selector=SCHEMAS_NAME_LABEL,
    )


def fetch_services():
    return process_services(
        directory_path=SCHEMAS_DIRECTORY_PATH,
        label_selector=SCHEMAS_NAME_LABEL,
    )


support_runtime_elements = {
    "statefulsets": fetch_stateful_sets,
    "configmaps": fetch_config_map,
    "services": fetch_services,
    # TODO: @jiacju - capture pvc once service is ready
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    schemas_to_run = {}

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    schemas_to_run.update(support_runtime_elements)

    return schemas_to_run
