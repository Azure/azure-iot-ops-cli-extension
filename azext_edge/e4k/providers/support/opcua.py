# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger
from kubernetes.client.models import V1ObjectMeta, V1PodList

from ..base import client
from .base import process_v1_pods, process_crd, process_deployments
from ...common import OPCUA_RESOURCE

logger = get_logger(__name__)
generic = client.ApiClient()


OPCUA_GENERAL_LABEL = "app in (opc-ua-connector,opcplc)"
OPCUA_SUPERVISOR_LABEL = "app in (edge-application-supervisor)"


def fetch_applications():
    return process_crd(OPCUA_RESOURCE, "applications")


def fetch_module_types():
    return process_crd(OPCUA_RESOURCE, "moduletypes", "module_type")


def fetch_modules():
    return process_crd(OPCUA_RESOURCE, "modules")


def fetch_asset_types():
    return process_crd(OPCUA_RESOURCE, "assettypes", "asset_type")


def fetch_assets():
    return process_crd(OPCUA_RESOURCE, "assets")


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    opcua_pods = process_v1_pods(OPCUA_RESOURCE, label_selector=OPCUA_GENERAL_LABEL, since_seconds=since_seconds)
    opcua_pods.extend(
        process_v1_pods(
            OPCUA_RESOURCE, label_selector=OPCUA_SUPERVISOR_LABEL, since_seconds=since_seconds, include_metrics=True
        )
    )
    return opcua_pods


def fetch_apollo_deployment():
    return process_deployments(resource=OPCUA_RESOURCE, label_selector="orchestrator=apollo")


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
