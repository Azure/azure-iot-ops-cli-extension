# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import MQ_API_V1A2, EdgeResourceApi
from ..stats import get_stats
from .base import (
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)

logger = get_logger(__name__)

MQ_APP_LABELS = [
    'azedge-e4k-operator',
    'broker',
    'diagnostics',
    'azedge-selftest',
    'health-manager',
    'azedge-mqttbridge',
    'azedge-datalake',
    'azedge-kafka-connector',
    'azedge-iothub-connector'
]

MQ_LABEL = f"app in ({','.join(MQ_APP_LABELS)})"


# TODO: @digimaun
# def fetch_events():
#     return {
#         "data": generic.sanitize_for_serialization(
#             obj=client.CoreV1Api().list_event_for_all_namespaces(label_selector=E4K_LABEL)
#         ),
#         "zinfo": f"e4k/events.json",
#     }


def fetch_diagnostic_metrics(namespace: str):
    # @digimaun - TODO dynamically determine pod:port
    try:
        stats_raw = get_stats(namespace=namespace, raw_response=True)
        return {
            "data": stats_raw,
            "zinfo": f"{namespace}/e4k/diagnostic_metrics.txt",
        }
    except Exception:
        logger.debug(f"Unable to call stats pod metrics against namespace {namespace}.")


def fetch_broker_deployments():
    processed, namespaces = process_deployments(
        resource_api=MQ_API_V1A2, label_selector=MQ_LABEL, return_namespaces=True
    )
    for namespace in namespaces:
        metrics: dict = fetch_diagnostic_metrics(namespace)
        if metrics:
            processed.append(metrics)

        # TODO: @digimaun - enable after support for disabling check polling UX.
        # try:
        #     checks = run_checks(namespace=namespace)
        #     checks_data = {
        #         "data": checks,
        #         "zinfo": f"e4k/{namespace}/checks.yaml",
        #     }
        #     processed.append(checks_data)
        # except Exception:
        #     logger.debug(f"Unable to run checks against namespace {namespace}.")

    return processed


def fetch_statefulsets():
    return process_statefulset(
        resource_api=MQ_API_V1A2,
        label_selector=MQ_LABEL,
    )


def fetch_services():
    return process_services(
        resource_api=MQ_API_V1A2,
        label_selector=MQ_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        resource_api=MQ_API_V1A2,
        label_selector=MQ_LABEL,
    )


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    return process_v1_pods(
        resource_api=MQ_API_V1A2, label_selector=MQ_LABEL, since_seconds=since_seconds, capture_previous_logs=True
    )


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_broker_deployments,
}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    mq_to_run = {}
    mq_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    mq_to_run.update(support_runtime_elements)

    return mq_to_run
