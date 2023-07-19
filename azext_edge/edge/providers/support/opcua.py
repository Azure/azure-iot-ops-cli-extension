# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from ...common import OPCUA_APPLICATION, OPCUA_ASSET, OPCUA_ASSET_TYPE, OPCUA_MODULE, OPCUA_MODULE_TYPE
from .base import process_crd, process_deployments, process_v1_pods

logger = get_logger(__name__)


OPCUA_GENERAL_LABEL = "app in (opc-ua-connector,opcplc)"
OPCUA_SUPERVISOR_LABEL = "app in (edge-application-supervisor)"
OPCUA_ORCHESTRATOR_LABEL = "orchestrator=apollo"


def fetch_applications():
    return process_crd(OPCUA_APPLICATION)


def fetch_module_types():
    return process_crd(OPCUA_MODULE_TYPE, "module_type")


def fetch_modules():
    return process_crd(OPCUA_MODULE)


def fetch_asset_types():
    return process_crd(OPCUA_ASSET_TYPE, "asset_type")


def fetch_assets():
    return process_crd(OPCUA_ASSET)


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    opcua_pods = process_v1_pods(
        resource=OPCUA_APPLICATION,
        label_selector=OPCUA_GENERAL_LABEL,
        since_seconds=since_seconds,
        capture_previous_logs=True,
    )
    opcua_pods.extend(
        process_v1_pods(
            resource=OPCUA_APPLICATION,
            label_selector=OPCUA_SUPERVISOR_LABEL,
            since_seconds=since_seconds,
            include_metrics=True,
            capture_previous_logs=True,
        )
    )
    return opcua_pods


def fetch_apollo_deployment():
    return process_deployments(resource=OPCUA_APPLICATION, label_selector=OPCUA_ORCHESTRATOR_LABEL)


support_crd_elements = {
    "applications": fetch_applications,
    "moduleTypes": fetch_module_types,
    "modules": fetch_modules,
    "assettypes": fetch_asset_types,
    "assets": fetch_assets,
}

support_runtime_elements = {"deployments": fetch_apollo_deployment}


def prepare_bundle(log_age_seconds: int = 60 * 60 * 24) -> dict:
    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)

    opcua_to_run = {}
    opcua_to_run.update(support_crd_elements)
    opcua_to_run.update(support_runtime_elements)

    return opcua_to_run
