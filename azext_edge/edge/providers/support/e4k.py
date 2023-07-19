# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from ...common import (
    E4K_BROKER,
    E4K_BROKER_DIAGNOSTIC,
    E4K_BROKER_LISTENER,
    E4K_DIAGNOSTIC_SERVICE,
    E4K_BROKER_AUTHENTICATION,
    E4K_BROKER_AUTHORIZATION,
    E4K_MQTT_BRIDGE_TOPIC_MAP,
    E4K_MQTT_BRIDGE_CONNECTOR,
)
from ..base import client, get_namespaced_pods_by_prefix
from .base import (
    process_crd,
    process_deployments,
    process_replicasets,
    process_services,
    process_statefulset,
    process_v1_pods,
)


logger = get_logger(__name__)
generic = client.ApiClient()

E4K_LABEL = "app in (azedge-e4k-operator,broker,diagnostics,azedge-selftest,health-manager)"


# TODO: @digimaun
# def fetch_events():
#     return {
#         "data": generic.sanitize_for_serialization(
#             obj=client.CoreV1Api().list_event_for_all_namespaces(label_selector=E4K_LABEL)
#         ),
#         "zinfo": f"e4k/events.json",
#     }


def fetch_brokers():
    return process_crd(E4K_BROKER)


def fetch_broker_listeners():
    return process_crd(E4K_BROKER_LISTENER)


def fetch_broker_diagnostics():
    return process_crd(E4K_BROKER_DIAGNOSTIC)


def fetch_broker_authentications():
    return process_crd(E4K_BROKER_AUTHENTICATION)


def fetch_broker_authorizations():
    return process_crd(E4K_BROKER_AUTHORIZATION)


def fetch_diagnostic_services():
    return process_crd(E4K_DIAGNOSTIC_SERVICE)


def fetch_mqtt_bridge_topic_maps():
    return process_crd(E4K_MQTT_BRIDGE_TOPIC_MAP)


def fetch_mqtt_bridge_connectors():
    return process_crd(E4K_MQTT_BRIDGE_CONNECTOR)


support_crd_elements = {
    "brokers": fetch_brokers,
    "listeners": fetch_broker_listeners,
    "brokerdiagnostics": fetch_broker_diagnostics,
    "authN": fetch_broker_authentications,
    "authZ": fetch_broker_authorizations,
    "diagnosticservices": fetch_diagnostic_services,
    "bridgetopicmaps": fetch_mqtt_bridge_topic_maps,
    "bridgeconnectors": fetch_mqtt_bridge_connectors,
}


def fetch_diagnostic_metrics(namespace: str):
    from ...common import AZEDGE_DIAGNOSTICS_SERVICE
    from ..stats import get_stats_pods

    target_pods = get_namespaced_pods_by_prefix(prefix=AZEDGE_DIAGNOSTICS_SERVICE, namespace=namespace)
    if not target_pods:
        logger.debug(f"Skipping metrics fetch for namespace {namespace}.")
        return

    try:
        stats_raw = get_stats_pods(namespace=namespace, raw_response=True)
        return {
            "data": stats_raw,
            "zinfo": f"e4k/{namespace}/diagnostics_metrics.txt",
        }
    except Exception:
        logger.debug(f"Unable to call stats pod metrics against namespace {namespace}.")


def fetch_broker_deployments():
    processed, namespaces = process_deployments(resource=E4K_BROKER, label_selector=E4K_LABEL, return_namespaces=True)
    for namespace in namespaces:
        metrics: dict = fetch_diagnostic_metrics(namespace)
        if metrics:
            processed.append(metrics)

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
        resource=E4K_BROKER,
        label_selector=E4K_LABEL,
    )


def fetch_services():
    return process_services(
        resource=E4K_BROKER,
        label_selector=E4K_LABEL,
    )


def fetch_replicasets():
    return process_replicasets(
        resource=E4K_BROKER,
        label_selector=E4K_LABEL,
    )


def fetch_pods(since_seconds: int = 60 * 60 * 24):
    return process_v1_pods(
        resource=E4K_BROKER, label_selector=E4K_LABEL, since_seconds=since_seconds, capture_previous_logs=True
    )


support_runtime_elements = {
    "statefulsets": fetch_statefulsets,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
    "deployments": fetch_broker_deployments,
}


def prepare_bundle(log_age_seconds: int = 60 * 60 * 24) -> dict:
    e4k_to_run = {}

    support_runtime_elements["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)

    e4k_to_run = {}
    e4k_to_run.update(support_crd_elements)
    e4k_to_run.update(support_runtime_elements)

    return e4k_to_run
