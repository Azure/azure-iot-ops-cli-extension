# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable, Optional
from zipfile import ZipInfo

from knack.log import get_logger

from ..edge_api import MQ_ACTIVE_API, EdgeResourceApi
from ..stats import get_stats, get_traces
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    get_mq_namespaces,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)
from .shared import NAME_LABEL_FORMAT

logger = get_logger(__name__)

MQ_K8S_LABEL = "k8s-app in (aio-mq-fluent-bit)"

MQ_NAME_LABEL = NAME_LABEL_FORMAT.format(label=MQ_ACTIVE_API.label)
MQ_DIRECTORY_PATH = MQ_ACTIVE_API.moniker


def fetch_diagnostic_metrics(namespace: str):
    # @digimaun - TODO dynamically determine pod:port
    try:
        stats_raw = get_stats(namespace=namespace, raw_response=True)
        return {
            "data": stats_raw,
            "zinfo": f"{namespace}/{MQ_DIRECTORY_PATH}/diagnostic_metrics.txt",
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
                    zinfo = ZipInfo(
                        filename=f"{namespace}/{MQ_DIRECTORY_PATH}/traces/{trace[0].filename}",
                        date_time=trace[0].date_time,
                    )
                    # Fixed in Py 3.9 https://github.com/python/cpython/issues/70373
                    zinfo.file_size = 0
                    zinfo.compress_size = 0
                    result.append(
                        {
                            "data": trace[1],
                            "zinfo": zinfo,
                        }
                    )

        except Exception:
            logger.debug(f"Unable to process diagnostics pod traces against namespace {namespace}.")

    return result


def fetch_statefulsets():
    processed, namespaces = process_statefulset(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
        return_namespaces=True,
    )

    for namespace in namespaces:
        metrics = fetch_diagnostic_metrics(namespace)
        if metrics:
            processed.append(metrics)

    return processed


def fetch_services():
    processed = process_services(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )

    return processed


def fetch_replicasets():
    processed = process_replicasets(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )

    return processed


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    processed = process_v1_pods(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
        since_seconds=since_seconds,
    )

    # TODO: @jiacju - will remove once label decision is finalized
    processed.extend(
        process_v1_pods(
            directory_path=MQ_DIRECTORY_PATH,
            label_selector=MQ_K8S_LABEL,
            since_seconds=since_seconds,
        )
    )

    return processed


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    apis: Iterable[EdgeResourceApi], log_age_seconds: int = DAY_IN_SECONDS, include_mq_traces: Optional[bool] = None
) -> dict:
    mq_to_run = {}
    mq_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    if include_mq_traces:
        support_runtime_elements["traces"] = fetch_diagnostic_traces

    mq_to_run.update(support_runtime_elements)

    return mq_to_run
