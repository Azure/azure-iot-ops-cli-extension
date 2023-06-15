# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import json
from datetime import datetime
from typing import Dict, List
from zipfile import ZipFile

from knack.log import get_logger

from .base import DEFAULT_NAMESPACE, get_namespaced_pods_by_prefix, client

logger = get_logger(__name__)


def fetch_events(
    namespace: str,
):
    return {
        "data": client.CoreV1Api().list_namespaced_event(namespace).to_dict(),
        "zinfo": f"{namespace}/events.json",
    }


def fetch_replication_controllers(
    namespace: str,
):
    return {
        "data": client.CoreV1Api()
        .list_namespaced_replication_controller(namespace)
        .to_dict(),
        "zinfo": f"{namespace}/replicationcontrollers.json",
    }


def fetch_services(
    namespace: str,
):
    return {
        "data": client.CoreV1Api().list_namespaced_service(namespace).to_dict(),
        "zinfo": f"{namespace}/services.json",
    }


def fetch_daemon_sets(
    namespace: str,
):
    return {
        "data": client.AppsV1Api().list_namespaced_daemon_set(namespace).to_dict(),
        "zinfo": f"{namespace}/daemonsets.json",
    }


def fetch_deployments(
    namespace: str,
):
    return {
        "data": client.AppsV1Api().list_namespaced_deployment(namespace).to_dict(),
        "zinfo": f"{namespace}/deployments.json",
    }


def fetch_replica_sets(
    namespace: str,
):
    return {
        "data": client.AppsV1Api().list_namespaced_deployment(namespace).to_dict(),
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
    result.append({"data": pods_data.to_dict(), "zinfo": f"{namespace}/pods.json"})
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
                    log = _add_log_header(
                        log=log,
                        namespace=namespace,
                        container_name=c.name,
                        pod_name=pod_name,
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

    target_pods, exception = get_namespaced_pods_by_prefix(
        prefix=AZEDGE_DIAGNOSTICS_POD_PREFIX, namespace=namespace
    )
    if not target_pods:
        logger.debug(f"Skipping metrics fetch for namespace {namespace}.")
        return

    stats_raw = get_stats_pods(namespace=namespace, raw_response=True)
    return {
        "data": stats_raw,
        "zinfo": f"{namespace}/diagnostics_metrics.txt",
    }


def fetch_nodes(**kwargs):
    return {
        "data": client.CoreV1Api().list_node().to_dict(),
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

support_global_elements = {"nodes": fetch_nodes}


def _add_log_header(log: str, container_name: str, namespace: str, pod_name: str):
    return (
        f"==== START logs for container {container_name} of pod {namespace}/{pod_name} ====\n"
        f"{log}\n"
        f"==== END logs for container {container_name} of pod {namespace}/{pod_name} ====\n"
    )


def build_bundle(bundle_path: str, namespaces: List[str] = None):
    from rich.console import Console, NewLine
    from rich.live import Live
    from rich.table import Table
    from rich.progress import Progress

    console = Console(width=120)
    grid = Table.grid(expand=False)
    grid = Table.grid(expand=False)
    grid.add_column()

    collects = []
    collects.extend(list(support_namespace_elements.keys()))

    if not namespaces:
        namespaces = [DEFAULT_NAMESPACE]

    if "kube-system" not in namespaces:
        namespaces.append("kube-system")

    bundle = {}
    with Live(grid, console=console, transient=True) as live:
        uber_progress = Progress()
        uber_task = uber_progress.add_task(
            "[green]Building support bundle", total=(len(collects) * len(namespaces))
        )
        for namespace in namespaces:
            namespace_task = uber_progress.add_task(
                f"[cyan]Processing {namespace}", total=len(collects)
            )
            bundle[namespace] = {}
            for element in support_namespace_elements:
                header = f"Fetching [medium_purple4]{element}[/medium_purple4] data..."
                grid = Table.grid(expand=False)
                grid.add_column()

                grid.add_row(NewLine(1))
                grid.add_row(header)
                grid.add_row(NewLine(1))
                grid.add_row(uber_progress)
                live.update(grid, refresh=True)

                bundle[namespace][element] = support_namespace_elements[element](
                    namespace
                )

                if not uber_progress.finished:
                    uber_progress.update(namespace_task, advance=1)
                    uber_progress.update(uber_task, advance=1)

            bundle["global"] = {}
            for element in support_global_elements:
                bundle["global"][element] = support_global_elements[element]()

    write_zip(file_path=bundle_path, bundle=bundle)
    return {"bundlePath": bundle_path, "namespaces": namespaces, "errors": None}


def write_zip(bundle: dict, file_path: str):
    with ZipFile(file=file_path, mode="w") as myzip:
        todo: List[dict] = []
        global_elements = bundle.pop("global", None)
        if global_elements:
            for element in global_elements:
                todo.append(global_elements[element])

        for namespace in bundle:
            for element in bundle[namespace]:
                if isinstance(bundle[namespace][element], list):
                    todo.extend(bundle[namespace][element])
                else:
                    todo.append(bundle[namespace][element])

        for t in todo:
            if t:
                data = t.get("data")
                if data:
                    if isinstance(data, dict):
                        data = json.dumps(t["data"], indent=2, cls=SafeEncoder)
                    myzip.writestr(zinfo_or_arcname=f"{t['zinfo']}", data=data)


class SafeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%dT%H:%M:%SZ")

        return json.JSONEncoder.default(self, o)
