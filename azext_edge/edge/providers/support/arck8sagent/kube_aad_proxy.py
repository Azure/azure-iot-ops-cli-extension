# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..base import (
    DAY_IN_SECONDS,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

MONIKER = "kubeaadproxy"
COMPONENT_LABEL = "app.kubernetes.io/component in (kube-aad-proxy)"


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    dataprocessor_pods = process_v1_pods(
        moniker=MONIKER,
        label_selector=COMPONENT_LABEL,
        since_seconds=since_seconds,
    )

    return dataprocessor_pods


def fetch_deployments():
    processed = process_deployments(moniker=MONIKER, label_selector=COMPONENT_LABEL)

    return processed


def fetch_replicasets():
    processed = process_replicasets(moniker=MONIKER, label_selector=COMPONENT_LABEL)

    return processed


def fetch_services():
    return  process_services(moniker=MONIKER, label_selector=COMPONENT_LABEL)


support_runtime_elements = {
    "replicasets": fetch_replicasets,
    "deployments": fetch_deployments,
    "services": fetch_services,
}


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    agent_to_run = {}

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    agent_to_run.update(support_runtime_elements)

    return agent_to_run
