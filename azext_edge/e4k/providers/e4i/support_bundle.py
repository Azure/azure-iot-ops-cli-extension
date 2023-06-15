# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import List, Optional
from zipfile import ZipFile

import yaml
from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1Container,
    V1ObjectMeta,
    V1Pod,
    V1PodList,
    V1PodSpec,
)

from ..base import client

logger = get_logger(__name__)
generic = client.ApiClient()


def fetch_applications():
    return process_opcua_crd("applications")


def fetch_module_types():
    return process_opcua_crd("moduletypes", "module_type")


def fetch_modules():
    return process_opcua_crd("modules")


def fetch_asset_types():
    return process_opcua_crd("assettypes", "asset_type")


def fetch_assets():
    return process_opcua_crd("assets")


def process_opcua_crd(plural: str, file_prefix: Optional[str] = None):
    from ...common import OPCUA_RESOURCE

    result: dict = client.CustomObjectsApi().list_cluster_custom_object(
        group=OPCUA_RESOURCE.group,
        version=OPCUA_RESOURCE.version,
        plural=plural,
    )
    if not file_prefix:
        file_prefix = plural[:-1]

    processed = []
    for r in result.get("items", []):
        namespace = r["metadata"]["namespace"]
        name = r["metadata"]["name"]
        processed.append({"data": r, "zinfo": f"{namespace}/{file_prefix}.{name}.yaml"})

    return processed


def fetch_supervisor_pods(since_seconds: int = 60 * 60 * 24):
    v1_api = client.CoreV1Api()

    pods: V1PodList = v1_api.list_pod_for_all_namespaces(
        label_selector="app=edge-application-supervisor"
    )
    logger.info(f"Detected {len(pods.items)} edge-application-supervisor pods.")
    return _process_v1_pods(
        pods=pods, since_seconds=since_seconds, include_metrics=True
    )


def fetch_deployments(since_seconds: int = 60 * 60 * 24):
    from kubernetes.client.models import V1Deployment, V1DeploymentList

    v1_api = client.CoreV1Api()
    v1_apps = client.AppsV1Api()

    deployments: V1DeploymentList = v1_apps.list_deployment_for_all_namespaces(
        label_selector="orchestrator=apollo"
    )
    logger.info(f"Detected {len(deployments.items)} deployments.")

    processed = []
    for deployment in deployments.items:
        d: V1Deployment = deployment
        # TODO: Workaround
        d.api_version = deployments.api_version
        d.kind = "Deployment"
        deployment_metadata: V1ObjectMeta = d.metadata
        deployment_namespace = deployment_metadata.namespace
        deployment_name = deployment_metadata.name
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=d),
                "zinfo": f"{deployment_namespace}/deployment.{deployment_name}.yaml",
            }
        )
        deployment_pods = v1_api.list_namespaced_pod(deployment_namespace)
        processed.extend(
            _process_v1_pods(pods=deployment_pods, since_seconds=since_seconds)
        )

    return processed


def _process_v1_pods(
    pods: V1PodList, since_seconds: int = 60 * 60 * 24, include_metrics=False
):
    v1_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    processed = []
    for pod in pods.items:
        p: V1Pod = pod
        pod_metadata: V1ObjectMeta = p.metadata
        pod_namespace = pod_metadata.namespace
        pod_name = pod_metadata.name
        # TODO: Workaround
        p.api_version = pods.api_version
        p.kind = "Pod"
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=p),
                "zinfo": f"{pod_namespace}/pod.{pod_name}.yaml",
            }
        )
        pod_spec: V1PodSpec = p.spec
        pod_containers: List[V1Container] = pod_spec.containers
        for container in pod_containers:
            try:
                logger.debug(
                    f"Reading log from pod {pod_name} container {container.name}"
                )
                log: str = v1_api.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=pod_namespace,
                    since_seconds=since_seconds,
                    container=container.name,
                )
                processed.append(
                    {
                        "data": log,
                        "zinfo": f"{pod_namespace}/pod.{pod_name}.{container.name}.log",
                    }
                )
            except ApiException as e:
                logger.debug(e.body)

        if include_metrics:
            try:
                logger.debug(f"Fetching runtime metrics for {pod_name}")
                metric: dict = custom_api.get_namespaced_custom_object(
                    "metrics.k8s.io", "v1beta1", pod_namespace, "pods", pod_name
                )
                if metric:
                    processed.append(
                        {
                            "data": metric,
                            "zinfo": f"{pod_namespace}/pod.{pod_name}.metric.yaml",
                        }
                    )
            except ApiException as e:
                logger.debug(e.body)

    return processed


support_crd_elements = {
    "applications": fetch_applications,
    "moduleTypes": fetch_module_types,
    "modules": fetch_modules,
    "assettypes": fetch_asset_types,
    "assets": fetch_assets,
}

support_runtime_elements = {}


def build_bundle(bundle_path: str, log_age_seconds: Optional[int] = None):
    from functools import partial

    from rich.console import Console, NewLine
    from rich.live import Live
    from rich.progress import Progress
    from rich.table import Table

    support_runtime_elements["supervisorPods"] = partial(
        fetch_supervisor_pods, since_seconds=log_age_seconds
    )
    support_runtime_elements["deployments"] = partial(
        fetch_deployments, since_seconds=log_age_seconds
    )

    bundle = {}
    console = Console(width=120)
    grid = Table.grid(expand=False)
    with Live(grid, console=console, transient=True) as live:
        uber_progress = Progress()
        uber_task = uber_progress.add_task(
            "[green]Building support bundle",
            total=(len(support_crd_elements) + len(support_runtime_elements)),
        )

        def visually_process(description: str, support_segment: dict):
            namespace_task = uber_progress.add_task(
                f"[cyan]{description}", total=len(support_segment)
            )
            for element in support_segment:
                header = f"Fetching [medium_purple4]{element}[/medium_purple4] data..."
                grid = Table.grid(expand=False)
                grid.add_column()

                grid.add_row(NewLine(1))
                grid.add_row(header)
                grid.add_row(NewLine(1))
                grid.add_row(uber_progress)
                live.update(grid, refresh=True)

                bundle[element] = support_segment[element]()

                if not uber_progress.finished:
                    uber_progress.update(namespace_task, advance=1)
                    uber_progress.update(uber_task, advance=1)

        visually_process(
            description="Processing custom resources",
            support_segment=support_crd_elements,
        )
        visually_process(
            description="Processing runtime resources",
            support_segment=support_runtime_elements,
        )

    write_zip(file_path=bundle_path, bundle=bundle)
    return {"bundlePath": bundle_path}


def write_zip(bundle: dict, file_path: str):
    with ZipFile(file=file_path, mode="w") as myzip:
        todo: List[dict] = []
        for element in bundle:
            if isinstance(bundle[element], list):
                todo.extend(bundle[element])
            else:
                todo.append(bundle[element])

        for t in todo:
            if t:
                data = t.get("data")
                if data:
                    if isinstance(data, dict):
                        data = yaml.safe_dump(t["data"], indent=2)
                    myzip.writestr(zinfo_or_arcname=f"{t['zinfo']}", data=data)


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.representer.SafeRepresenter.add_representer(str, str_presenter)
