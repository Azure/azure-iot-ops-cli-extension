# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger
from kubernetes.client.models import V1ObjectMeta, V1PodList

from ..base import client
from .base import process_v1_pods, process_crd
from ...common import OPCUA_RESOURCE

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


def fetch_deployments(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.AppsV1Api().list_namespaced_deployment(namespace)),
        "zinfo": f"{namespace}/deployments.json",
    }


def fetch_replica_sets(
    namespace: str,
):
    return {
        "data": generic.sanitize_for_serialization(obj=client.AppsV1Api().list_namespaced_deployment(namespace)),
        "zinfo": f"{namespace}/replicasets.json",
    }


def fetch_pods(
    namespace: str,
):
    from kubernetes.client.exceptions import ApiException
    from kubernetes.client.models import V1Container, V1Pod, V1PodList, V1PodSpec

    result = []
    v1_api = client.CoreV1Api()
    pods_data: V1PodList = v1_api.list_namespaced_pod(namespace)
    result.append({"data": generic.sanitize_for_serialization(obj=pods_data), "zinfo": f"{namespace}/pods.json"})

    for p in pods_data.items:
        pod: V1Pod = p
        pod_name = pod.metadata.name
        pod_spec: V1PodSpec = pod.spec
        pod_containers: List[V1Container] = pod_spec.containers
        for c in pod_containers:
            for previous in [False, True]:
                try:
                    log: str = v1_api.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace,
                        container=c.name,
                        previous=previous,
                    )
                    result.append(
                        {
                            "data": log,
                            "zinfo": f"{namespace}/{pod_name}/{c.name}{'-previous' if previous else ''}.log",
                        }
                    )
                except ApiException as e:
                    logger.debug(e.body)

    return result


def fetch_custom_brokers(namespace: str):
    from ..common import BROKER_RESOURCE

    return {
        "data": client.CustomObjectsApi().list_namespaced_custom_object(
            group=BROKER_RESOURCE.group,
            version=BROKER_RESOURCE.version,
            namespace=namespace,
            plural=BROKER_RESOURCE.resource,
        ),
        "zinfo": f"{namespace}/custombrokers.json",
    }


def fetch_diagnostic_metrics(namespace: str):
    from ..common import AZEDGE_DIAGNOSTICS_POD_PREFIX
    from .stats import get_stats_pods

    target_pods, _ = get_namespaced_pods_by_prefix(prefix=AZEDGE_DIAGNOSTICS_POD_PREFIX, namespace=namespace)
    if not target_pods:
        logger.debug(f"Skipping metrics fetch for namespace {namespace}.")
        return

    stats_raw = get_stats_pods(namespace=namespace, raw_response=True)
    return {
        "data": stats_raw,
        "zinfo": f"{namespace}/diagnostics_metrics.log",
    }


def fetch_nodes(**kwargs):
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_node()),
        "zinfo": "nodes.json",
    }


support_namespace_elements = {
    "events": fetch_events,
    "replication controllers": fetch_replication_controllers,
    "services": fetch_services,
    "daemon sets": fetch_daemon_sets,
    "deployments": fetch_deployments,
    "pods": fetch_pods,
    "custom brokers": fetch_custom_brokers,
    "diagnostic metrics": fetch_diagnostic_metrics,
}


def prepare_bundle(log_age_seconds: int = 60 * 60 * 24) -> dict:
    applicable_namespaces = []
    support_runtime_elements["supervisorPods"] = partial(fetch_supervisor_pods, since_seconds=log_age_seconds)
    support_runtime_elements["deployments"] = partial(fetch_deployments, since_seconds=log_age_seconds)

    opcua_to_run = {}
    opcua_to_run.update(support_crd_elements)
    opcua_to_run.update(support_runtime_elements)
