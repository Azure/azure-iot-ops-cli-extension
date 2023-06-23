# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import List, Tuple

from knack.log import get_logger

from ..base import client, get_namespaced_pods_by_prefix
from .base import process_crd, process_deployments
from ...common import BROKER_RESOURCE

logger = get_logger(__name__)
generic = client.ApiClient()


def fetch_events(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_namespaced_event(namespace)),
        "zinfo": f"{namespace}/events.json",
    }


def fetch_replication_controllers(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(
            obj=client.CoreV1Api().list_namespaced_replication_controller(namespace)
        ),
        "zinfo": f"{namespace}/replicationcontrollers.json",
    }


def fetch_services(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_namespaced_service(namespace)),
        "zinfo": f"{namespace}/services.json",
    }


def fetch_daemon_sets(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.AppsV1Api().list_namespaced_daemon_set(namespace)),
        "zinfo": f"{namespace}/daemonsets.json",
    }


def fetch_replica_sets(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.AppsV1Api().list_stateful_set_for_all_namespaces(namespace)),
        "zinfo": f"{namespace}/replicasets.json",
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


# support_namespace_elements = {
#     "events": fetch_events,
#     "replication controllers": fetch_replication_controllers,
#     "services": fetch_services,
#     "daemon sets": fetch_daemon_sets,
#     "deployments": fetch_deployments,
#     "pods": fetch_pods,
#     "custom brokers": fetch_custom_brokers,
#     "diagnostic metrics": fetch_diagnostic_metrics,
# }


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


def fetch_broker_deployments(since_seconds: int = 60 * 60 * 24):
    return process_deployments(
        resource=BROKER_RESOURCE,
        field_selectors=["app=azedge-e4k-operator", "app=broker", "app=diagnostics"],
        since_seconds=since_seconds,
    )


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


support_runtime_elements = {}


def prepare_bundle(log_age_seconds: int = 60 * 60 * 24) -> dict:
    e4k_to_run = {}

    # support_runtime_elements["supervisorPods"] = partial(fetch_supervisor_pods, since_seconds=log_age_seconds)
    support_runtime_elements["deployments"] = partial(fetch_broker_deployments, since_seconds=log_age_seconds)

    e4k_to_run = {}
    e4k_to_run.update(support_crd_elements)
    e4k_to_run.update(support_runtime_elements)

    return e4k_to_run
