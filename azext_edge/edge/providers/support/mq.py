# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional

from knack.log import get_logger

from azext_edge.edge.common import AIO_MQ_OPERATOR

from ..edge_api import MQ_ACTIVE_API, EdgeResourceApi
from ..stats import get_stats, get_traces
from .base import (
    assemble_crd_work,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
    get_mq_namespaces,
)

logger = get_logger(__name__)

MQ_APP_LABELS = [
    "broker",  # aio-mq-dmqtt-frontend, aio-mq-dmqtt-backend, aio-mq-dmqtt-authentication
    "diagnostics",  # aio-mq-diagnostics-service
    "health-manager",  # aio-mq-dmqtt-health-manager
    "aio-mq-operator",
    "aio-mq-mqttbridge",
    "aio-mq-datalake",
    "aio-mq-kafka-connector",
    "aio-mq-iothub-connector",
]

MQ_LABEL = f"app in ({','.join(MQ_APP_LABELS)})"


def fetch_diagnostic_metrics(namespace: str):
    # @digimaun - TODO dynamically determine pod:port
    try:
        stats_raw = get_stats(namespace=namespace, raw_response=True)
        return {
            "data": stats_raw,
            "zinfo": f"{namespace}/{MQ_ACTIVE_API.moniker}/diagnostic_metrics.txt",
        }
    except Exception:
        logger.debug(f"Unable to process diagnostics pod metrics against namespace {namespace}.")


def fetch_diagnostic_traces():
    namespaces = get_mq_namespaces()
    result = []
    for namespace in namespaces:
        try:
            traces = get_traces(namespace=namespace, trace_ids=["!support_bundle!"])
            if traces:
                for trace in traces:
                    result.append(
                        {
                            "data": trace[1],
                            "zinfo": f"{namespace}/{MQ_ACTIVE_API.moniker}/traces/{trace[0]}",
                        }
                    )

        except Exception as e:
            import pdb

            pdb.set_trace()
            logger.debug(f"Unable to process diagnostics pod traces against namespace {namespace}.")

    return result


def fetch_deployments():
    processed, namespaces = process_deployments(
        resource_api=MQ_ACTIVE_API, label_selector=MQ_LABEL, return_namespaces=True
    )
    # aio-mq-operator deployment has no app label
    operators, operator_namespaces = process_deployments(
        resource_api=MQ_ACTIVE_API, field_selector=f"metadata.name={AIO_MQ_OPERATOR}", return_namespaces=True
    )
    processed.extend(operators)

    for namespace in {**namespaces, **operator_namespaces}:
        metrics: dict = fetch_diagnostic_metrics(namespace)
        if metrics:
            processed.append(metrics)

        # TODO: @digimaun - enable after support for disabling check polling UX.
        # try:
        #     checks = run_checks(namespace=namespace)
        #     checks_data = {
        #         "data": checks,
        #         "zinfo": f"{MQ_ACTIVE_API.moniker}/{namespace}/checks.yaml",
        #     }
        #     processed.append(checks_data)
        # except Exception:
        #     logger.debug(f"Unable to run checks against namespace {namespace}.")

    return processed


def fetch_statefulsets():
    return process_statefulset(
        resource_api=MQ_ACTIVE_API,
        label_selector=MQ_LABEL,
    )


def fetch_services():
    return process_services(
        resource_api=MQ_ACTIVE_API,
        label_selector=MQ_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        resource_api=MQ_ACTIVE_API,
        label_selector=MQ_LABEL,
    )


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    return process_v1_pods(
        resource_api=MQ_ACTIVE_API, label_selector=MQ_LABEL, since_seconds=since_seconds, capture_previous_logs=True
    )


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_deployments,
}


def prepare_bundle(
    apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24, include_mq_traces: Optional[bool] = None
) -> dict:
    mq_to_run = {}
    mq_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    if include_mq_traces:
        support_runtime_elements["traces"] = fetch_diagnostic_traces

    mq_to_run.update(support_runtime_elements)

    return mq_to_run
