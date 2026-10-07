# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial

from .base import (
    DAY_IN_SECONDS,
    process_config_maps,
    process_persistent_volume_claims,
    process_services,
    process_statefulset,
    process_v1_pods,
)
from .common import NAME_LABEL_FORMAT


EDGE_REGISTRY_NAME_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-registry")
EDGE_REGISTRY_DIRECTORY_PATH = "edgeregistry"


def fetch_stateful_sets():
    return process_statefulset(
        directory_path=EDGE_REGISTRY_DIRECTORY_PATH,
        label_selector=EDGE_REGISTRY_NAME_LABEL,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=EDGE_REGISTRY_DIRECTORY_PATH,
        label_selector=EDGE_REGISTRY_NAME_LABEL,
        since_seconds=since_seconds,
    )


def fetch_config_map():
    return process_config_maps(
        directory_path=EDGE_REGISTRY_DIRECTORY_PATH,
        label_selector=EDGE_REGISTRY_NAME_LABEL,
    )


def fetch_services():
    return process_services(
        directory_path=EDGE_REGISTRY_DIRECTORY_PATH,
        label_selector=EDGE_REGISTRY_NAME_LABEL,
    )


def fetch_persistent_volume_claims():
    return process_persistent_volume_claims(
        directory_path=EDGE_REGISTRY_DIRECTORY_PATH,
        label_selector=EDGE_REGISTRY_NAME_LABEL,
    )


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    return {
        "pods": partial(fetch_pods, since_seconds=log_age_seconds),
        "statefulsets": fetch_stateful_sets,
        "configmaps": fetch_config_map,
        "services": fetch_services,
        "persistentvolumeclaims": fetch_persistent_volume_claims,
    }
