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
from ..stats import get_traces
from .base import (
    DAY_IN_SECONDS,
    assemble_crd_work,
    get_mq_namespaces,
    process_config_maps,
    process_daemonsets,
    process_jobs,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

MQ_NAME_LABEL = NAME_LABEL_FORMAT.format(label=MQ_ACTIVE_API.label)
MQ_DIRECTORY_PATH = MQ_ACTIVE_API.moniker


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
    return process_statefulset(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )


def fetch_daemonsets():
    return process_daemonsets(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )


def fetch_services():
    return process_services(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )


def fetch_jobs():
    return process_jobs(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )


def fetch_configmaps():
    return process_config_maps(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
    )


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    return process_v1_pods(
        directory_path=MQ_DIRECTORY_PATH,
        label_selector=MQ_NAME_LABEL,
        since_seconds=since_seconds,
    )


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "configmaps": fetch_configmaps,
    "jobs": fetch_jobs,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "daemonsets": fetch_daemonsets,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
    apis: Optional[Iterable[EdgeResourceApi]] = None,
    include_mq_traces: Optional[bool] = None,
) -> dict:
    mq_to_run = {}

    # when apis not found, still try to fetch other resources
    if apis:
        mq_to_run.update(assemble_crd_work(apis))

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    if include_mq_traces:
        support_runtime_elements["traces"] = fetch_diagnostic_traces

    mq_to_run.update(support_runtime_elements)

    return mq_to_run
