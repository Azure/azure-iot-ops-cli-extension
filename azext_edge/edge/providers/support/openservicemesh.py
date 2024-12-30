# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import OPENSERVICEMESH_CONFIG_API_V1, EdgeResourceApi
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    process_config_maps,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

OSM_DIRECTORY_PATH = OPENSERVICEMESH_CONFIG_API_V1.moniker
OSM_NAMESPACE = "arc-osm-system"


def fetch_deployments():
    return process_deployments(
        directory_path=OSM_DIRECTORY_PATH,
        namespace=OSM_NAMESPACE,
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=OSM_DIRECTORY_PATH,
        namespace=OSM_NAMESPACE,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=OSM_DIRECTORY_PATH,
        namespace=OSM_NAMESPACE,
        since_seconds=since_seconds,
    )


def fetch_services():
    return process_services(
        directory_path=OSM_DIRECTORY_PATH,
        namespace=OSM_NAMESPACE,
    )


def fetch_configmaps():
    return process_config_maps(
        directory_path=OSM_DIRECTORY_PATH,
        namespace=OSM_NAMESPACE,
    )


support_runtime_elements = {
    "configmaps": fetch_configmaps,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
) -> dict:
    osm_to_run = {}

    if apis:
        osm_to_run.update(assemble_crd_work(apis=apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    osm_to_run.update(support_runtime_elements)

    return osm_to_run
