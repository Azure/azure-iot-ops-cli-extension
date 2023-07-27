# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import OPCUA_API_V1, EdgeResourceApi, OpcuaResourceKinds
from .base import assemble_crd_work, process_deployments, process_v1_pods

logger = get_logger(__name__)


OPCUA_GENERAL_LABEL = "app in (opc-ua-connector,opcplc)"
OPCUA_SUPERVISOR_LABEL = "app in (edge-application-supervisor)"
OPCUA_ORCHESTRATOR_LABEL = "orchestrator=apollo"


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    opcua_pods = process_v1_pods(
        resource_api=OPCUA_API_V1,
        label_selector=OPCUA_GENERAL_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    opcua_pods.extend(
        process_v1_pods(
            resource_api=OPCUA_API_V1,
            label_selector=OPCUA_SUPERVISOR_LABEL,
            since_seconds=since_seconds,
            include_metrics=True,
            capture_previous_logs=True,
        )
    )
    return opcua_pods


def fetch_apollo_deployment():
    return process_deployments(resource_api=OPCUA_API_V1, label_selector=OPCUA_ORCHESTRATOR_LABEL)


support_runtime_elements = {"deployments": fetch_apollo_deployment}


def prepare_bundle(apis: Iterable[EdgeResourceApi], log_age_seconds: int = 60 * 60 * 24) -> dict:
    opcua_to_run = {}
    opcua_to_run.update(
        assemble_crd_work(
            apis,
            {OpcuaResourceKinds.MODULE_TYPE.value: "module_type", OpcuaResourceKinds.ASSET_TYPE.value: "asset_type"},
        )
    )

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    opcua_to_run.update(support_runtime_elements)

    return opcua_to_run
