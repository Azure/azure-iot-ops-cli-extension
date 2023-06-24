# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from ...common import BROKER_RESOURCE
from ..base import client, get_namespaced_pods_by_prefix
from .base import (
    process_crd,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)
from ..checks import run_checks


logger = get_logger(__name__)
generic = client.ApiClient()

E4K_LABEL = "app in (azedge-e4k-operator,broker,diagnostics,azedge-selftest,health-manager)"


def fetch_events(
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_event_for_all_namespaces(label_selector=E4K_LABEL)),
        "zinfo": f"e4k/events.json",
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


def fetch_broker_authentications():
    return process_crd(BROKER_RESOURCE, "brokerauthentications")


def fetch_broker_authorizations():
    return process_crd(BROKER_RESOURCE, "brokerauthorizations")


def fetch_diagnostic_services():
    return process_crd(BROKER_RESOURCE, "diagnosticservices")


def fetch_mqtt_bridge_topic_maps():
    return process_crd(BROKER_RESOURCE, "mqttbridgetopicmaps")


def fetch_mqtt_bridge_connectors():
    return process_crd(BROKER_RESOURCE, "mqttbridgeconnectors")


support_crd_elements = {
    "brokers": fetch_brokers,
    "listeners": fetch_broker_listeners,
    "diagnostics": fetch_broker_diagnostics,
    "authN": fetch_broker_authentications,
    "authZ": fetch_broker_authorizations,
    "services": fetch_diagnostic_services,
    "bridgetopicmaps": fetch_mqtt_bridge_topic_maps,
    "bridgeconnectors": fetch_mqtt_bridge_connectors,
}


def fetch_diagnostic_metrics(namespace: str):
    from ...common import AZEDGE_DIAGNOSTICS_POD_PREFIX
    from ..stats import get_stats_pods

    target_pods, _ = get_namespaced_pods_by_prefix(prefix=AZEDGE_DIAGNOSTICS_POD_PREFIX, namespace=namespace)
    if not target_pods:
        logger.debug(f"Skipping metrics fetch for namespace {namespace}.")
        return

    try:
        stats_raw = get_stats_pods(namespace=namespace, raw_response=True)
        return {
            "data": stats_raw,
            "zinfo": f"e4k/{namespace}/diagnostics_metrics.out",
        }
    except Exception:
        logger.debug(f"Unable to call stats pod metrics against namespace {namespace}.")


def fetch_broker_deployments():
    processed, namespaces = process_deployments(
        resource=BROKER_RESOURCE, label_selector=E4K_LABEL, return_namespaces=True
    )
    for namespace in namespaces:
        metrics: dict = fetch_diagnostic_metrics(namespace)
        if metrics:
            processed.append(metrics)

        metrics: dict = fetch_diagnostic_metrics(namespace)
        if metrics:
            processed.append(metrics)

        # TODO: @digimaun
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
        resource=BROKER_RESOURCE,
        label_selector=E4K_LABEL,
    )


def fetch_services():
    return process_services(
        resource=BROKER_RESOURCE,
        label_selector=E4K_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        resource=BROKER_RESOURCE,
        label_selector=E4K_LABEL,
    )


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    return process_v1_pods(resource=BROKER_RESOURCE, label_selector=E4K_LABEL, since_seconds=since_seconds)


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "services": fetch_services,
    "replicasets": fetch_replicasets,
    "deployments": fetch_broker_deployments,
}


def prepare_bundle(log_age_seconds: int = 60 * 60 * 24) -> dict:
    e4k_to_run = {}

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)

    e4k_to_run = {}
    e4k_to_run.update(support_crd_elements)
    e4k_to_run.update(support_runtime_elements)

    return e4k_to_run
