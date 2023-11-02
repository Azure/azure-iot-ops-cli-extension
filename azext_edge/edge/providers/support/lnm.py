# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Iterable, List

from functools import partial
from ..edge_api import LNM_API_V1B1, EdgeResourceApi, LnmResourceKinds
from .base import (
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_v1_pods,
    process_daemonsets,
)

LNM_APP_LABELS = [
    'aio-lnm-operator'
]
LNM_APP_LABEL_TYPE = 'app'
LNM_LABEL_PREFIX = "aio-lnm"


def fetch_replicasets():
    lnm_labels = _generate_lnm_labels(prefix=LNM_LABEL_PREFIX, label_type=LNM_APP_LABEL_TYPE)

    return process_replicasets(
        resource_api=LNM_API_V1B1,
        label_selector=lnm_labels,
    )


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    lnm_labels = _generate_lnm_labels(prefix=LNM_LABEL_PREFIX, label_type=LNM_APP_LABEL_TYPE)

    return process_v1_pods(
        resource_api=LNM_API_V1B1, label_selector=lnm_labels, since_seconds=since_seconds, capture_previous_logs=True
    )


def fetch_services():
    lnm_labels = _generate_lnm_labels(prefix=LNM_LABEL_PREFIX, label_type=LNM_APP_LABEL_TYPE)

    return process_services(resource_api=LNM_API_V1B1, label_selector=lnm_labels)


def fetch_lnm_deployments():
    deployment_prefixes = [f"{LNM_LABEL_PREFIX}-{name}" for name in _fetch_lnm_instance_names()]
    deployment_prefixes.extend(LNM_APP_LABELS)

    return process_deployments(resource_api=LNM_API_V1B1, label_selector=None, prefix_names=deployment_prefixes)


def fetch_daemonsets():
    daemonset_prefixes = [f"svclb-{LNM_LABEL_PREFIX}-{name}" for name in _fetch_lnm_instance_names()]
    if not daemonset_prefixes:
        daemonset_prefixes.append(f"svclb-{LNM_LABEL_PREFIX}")
    return process_daemonsets(resource_api=LNM_API_V1B1, label_selector=None, prefix_names=daemonset_prefixes)


support_runtime_elements = {
    "daemonsets": fetch_daemonsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_lnm_deployments,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    lnm_to_run = {}
    lnm_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    lnm_to_run.update(support_runtime_elements)

    return lnm_to_run


# fetch all lnm instance names, so it can be used to generate app labels
def _fetch_lnm_instance_names() -> List[str]:
    lnm_instances = LNM_API_V1B1.get_resources(LnmResourceKinds.LNM)
    return [instance["metadata"]["name"] for instance in lnm_instances["items"]]


def _generate_lnm_labels(prefix: str, label_type: str) -> str:
    lnm_names = _fetch_lnm_instance_names()
    # add prefix to instance names
    lnm_names = [f"{prefix}-{name}" for name in lnm_names]
    # add lnm_names to LNM_APP_LABELS
    lnm_labels = LNM_APP_LABELS + lnm_names
    return f"{label_type} in ({','.join(lnm_labels)})"
