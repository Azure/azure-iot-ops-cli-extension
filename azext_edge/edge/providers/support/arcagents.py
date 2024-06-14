# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from azext_edge.edge.providers.support.shared import COMPONENT_LABEL_FORMAT

from .base import (
    DAY_IN_SECONDS,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

MONIKER = "arcagents"
ARC_AGENTS_SERVICE_LABEL = "app.kubernetes.io/managed-by in (Helm)"
ARC_AGENTS = [
    ("cluster-identity-operator", False),  # (component, has_services)
    ("clusterconnect-agent", False),
    ("config-agent", False),
    ("extension-events-collector", True),
    ("extension-manager", True),
    ("kube-aad-proxy", True),
    ("cluster-metadata-operator", False),
    ("metrics-agent", False),
    ("resource-sync-agent", False),
]


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = fetch_resources(
        func=process_v1_pods,
        since_seconds=since_seconds
    )
    return processed


def fetch_deployments():
    processed = fetch_resources(
        func=process_deployments
    )
    return processed


def fetch_replicasets():
    processed = fetch_resources(
        func=process_replicasets
    )
    return processed


def fetch_services():
    processed = fetch_resources(
        func=process_services,
    )
    return processed


def fetch_resources(func: callable, since_seconds: int = None) -> list:
    resources = []
    for component, has_service in ARC_AGENTS:
        kwargs: dict = {
            'directory_path': f"{MONIKER}/{component}",
            'label_selector': COMPONENT_LABEL_FORMAT.format(label=component),
        }
        if since_seconds:
            kwargs['since_seconds'] = since_seconds
        if func == process_services:
            if not has_service:
                continue
            kwargs['label_selector'] = ARC_AGENTS_SERVICE_LABEL
            kwargs['prefix_names'] = [component]

        resources.extend(func(**kwargs))
    return resources


def prepare_bundle(log_age_seconds: int = DAY_IN_SECONDS) -> dict:
    agents_to_run = {}

    agents_to_run = {
        "pods": partial(fetch_pods, since_seconds=log_age_seconds),
        "replicasets": fetch_replicasets,
        "deployments": fetch_deployments,
        "services": fetch_services,
    }

    return agents_to_run
