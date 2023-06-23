# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from ...common import BROKER_RESOURCE
from ..base import client, get_namespaced_pods_by_prefix
from .base import process_crd, process_deployments, process_replicasets, process_services, process_statefulset

logger = get_logger(__name__)
generic = client.ApiClient()


def fetch_events(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_namespaced_event(namespace)),
        "zinfo": f"{namespace}/events.json",
    }


# for previous in [False, True]:
#     try:
#         log: str = v1_api.read_namespaced_pod_log(
#             name=pod_name,
#             namespace=namespace,
#             container=c.name,
#             previous=previous,
#         )
#         result.append(
#             {
#                 "data": log,
#                 "zinfo": f"{namespace}/{pod_name}/{c.name}{'-previous' if previous else ''}.log",
#             }
#         )
#     except ApiException as e:
#         logger.debug(e.body)


# TODO
# {MqttBridgeTopicMap}
# {MqttBridgeConnector}


def fetch_brokers():
    return process_crd(BROKER_RESOURCE, "brokers")


def fetch_broker_listeners():
    return process_crd(BROKER_RESOURCE, "brokerlisteners")


def fetch_broker_diagnostics():
    return process_crd(BROKER_RESOURCE, "brokerdiagnostics")


def fetch_broker_authentication():
    return process_crd(BROKER_RESOURCE, "brokerauthentications")


def fetch_broker_authorization():
    return process_crd(BROKER_RESOURCE, "brokerauthorizations")


def fetch_diagnostic_service():
    return process_crd(BROKER_RESOURCE, "diagnosticservices")


support_crd_elements = {
    "brokers": fetch_brokers,
    "listeners": fetch_broker_listeners,
    "diagnostics": fetch_broker_diagnostics,
    "authN": fetch_broker_authentication,
    "authZ": fetch_broker_authorization,
    "services": fetch_diagnostic_service,
}


def fetch_diagnostic_metrics(namespace: str):
    from ...common import AZEDGE_DIAGNOSTICS_POD_PREFIX
    from ..stats import get_stats_pods

    target_pods, _ = get_namespaced_pods_by_prefix(prefix=AZEDGE_DIAGNOSTICS_POD_PREFIX, namespace=namespace)
    if not target_pods:
        logger.debug(f"Skipping metrics fetch for namespace {namespace}.")
        return

    stats_raw = get_stats_pods(namespace=namespace, raw_response=True)
    return {
        "data": stats_raw,
        "zinfo": f"{namespace}/diagnostics_metrics.log",
    }


def fetch_broker_deployments(since_seconds: int = 60 * 60 * 24):
    return process_deployments(
        resource=BROKER_RESOURCE,
        label_selector="app in (azedge-e4k-operator,broker,diagnostics,azedge-selftest)",
        since_seconds=since_seconds,
    )


def fetch_statefulsets():
    return process_statefulset(
        resource=BROKER_RESOURCE,
        label_selector="app in (azedge-e4k-operator,broker,diagnostics,azedge-selftest,health-manager)",
    )


def fetch_services():
    return process_services(
        resource=BROKER_RESOURCE,
        label_selector="app in (azedge-e4k-operator,broker,diagnostics,azedge-selftest,health-manager)",
    )


def fetch_replicasets():
    return process_replicasets(
        resource=BROKER_RESOURCE,
        label_selector="app in (azedge-e4k-operator,broker,diagnostics,azedge-selftest,health-manager)",
    )


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
}


def prepare_bundle(log_age_seconds: int = 60 * 60 * 24) -> dict:
    e4k_to_run = {}

    support_runtime_elements["deployments"] = partial(fetch_broker_deployments, since_seconds=log_age_seconds)

    e4k_to_run = {}
    e4k_to_run.update(support_crd_elements)
    e4k_to_run.update(support_runtime_elements)

    return e4k_to_run
