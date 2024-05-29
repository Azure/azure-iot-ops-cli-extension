# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from .base import (
    DAY_IN_SECONDS,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
)

logger = get_logger(__name__)

MONIKER = "arcagents"
ARC_AGENTS = [
    ("clusteridentityoperator", "cluster-identity-operator", False), # (sub_group, component_label, has_services)
    ("clusterconnectagent", "clusterconnect-agent", False),
    ("configagent", "config-agent", False),
    ("controllermanager", "controller-manager", False),
    ("extensioneventscollector", "extension-events-collector", True),
    ("extensionmanager", "extension-manager", True),
    ("kubeaadproxy", "kube-aad-proxy",  True),
    ("clustermetadataoperator", "cluster-metadata-operator", False),
    ("metricsagent", "metrics-agent", False),
    ("resourcesyncagent", "resource-sync-agent", False),
]


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = fetch_resources(
        func=process_v1_pods,
        exclude_evicted_pod_log=True,
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


def fetch_resources(func: callable, since_seconds: int = None, exclude_evicted_pod_log: bool = None) -> list:
    resources = []
    for agent_name, component_label, has_service in ARC_AGENTS:
        kwargs: dict = {
            'moniker': MONIKER,
            'sub_group': agent_name,
            'label_selector': f"app.kubernetes.io/component in ({component_label})"
        }
        if since_seconds and exclude_evicted_pod_log:
            kwargs['exclude_evicted_pod_log'] = exclude_evicted_pod_log
            kwargs['since_seconds'] = since_seconds
        if has_service and func==process_services:
            kwargs['label_selector'] = "app.kubernetes.io/managed-by in (Helm)"
            kwargs['prefix_names'] = [component_label]

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
