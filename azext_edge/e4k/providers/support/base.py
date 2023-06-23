# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from os import makedirs
from os.path import abspath, expanduser, isdir
from pathlib import PurePath
from typing import List, Optional

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Container, V1ObjectMeta, V1Pod, V1PodList, V1PodSpec

from ...common import IotEdgeBrokerResource
from ..base import client

logger = get_logger(__name__)
generic = client.ApiClient()


def process_crd(
    resource: IotEdgeBrokerResource, plural: str, file_prefix: Optional[str] = None, include_namespaces: bool = False
):
    result: dict = client.CustomObjectsApi().list_cluster_custom_object(
        group=resource.group,
        version=resource.version,
        plural=plural,
    )
    if not file_prefix:
        file_prefix = plural[:-1]

    if resource.group.startswith("e4i"):
        edge_service = "opcua"
    else:
        edge_service = "e4k"

    processed = []
    namespaces = []
    for r in result.get("items", []):
        namespace = r["metadata"]["namespace"]
        namespaces.append(namespace)
        name = r["metadata"]["name"]
        processed.append({"data": r, "zinfo": f"{edge_service}/{namespace}/{file_prefix}.{name}.yaml"})

    if include_namespaces:
        processed, namespaces
    return processed


def process_v1_pods(
    edge_service: str, pods: V1PodList, since_seconds: int = 60 * 60 * 24, include_metrics=False, previous_logs=False
) -> List[dict]:
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
                "zinfo": f"{edge_service}/{pod_namespace}/pod.{pod_name}.yaml",
            }
        )
        pod_spec: V1PodSpec = p.spec
        pod_containers: List[V1Container] = pod_spec.containers
        for container in pod_containers:
            try:
                # previous_log_runs = [False]
                # if previous_logs:
                #     previous_log_runs.append(True)
                logger.debug(f"Reading log from pod {pod_name} container {container.name}")
                log: str = v1_api.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=pod_namespace,
                    since_seconds=since_seconds,
                    container=container.name,
                )
                processed.append(
                    {
                        "data": log,
                        "zinfo": f"{edge_service}/{pod_namespace}/pod.{pod_name}.{container.name}.log",
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
                            "zinfo": f"{edge_service}/{pod_namespace}/pod.{pod_name}.metric.yaml",
                        }
                    )
            except ApiException as e:
                logger.debug(e.body)

    return processed


def process_events(resource: IotEdgeBrokerResource, plural: str, file_prefix: Optional[str] = None):
    result: dict = client.CustomObjectsApi().list_cluster_custom_object(
        group=resource.group,
        version=resource.version,
        plural=plural,
    )
    if not file_prefix:
        file_prefix = plural[:-1]

    if resource.group.startswith("e4i"):
        edge_service = "opcua"
    else:
        edge_service = "e4k"

    processed = []
    for r in result.get("items", []):
        namespace = r["metadata"]["namespace"]
        name = r["metadata"]["name"]
        processed.append({"data": r, "zinfo": f"{edge_service}/{namespace}/{file_prefix}.{name}.yaml"})

    return processed


def process_deployments(
    resource: IotEdgeBrokerResource,
    label_selector: str,
    since_seconds: int = 60 * 60 * 24,
):
    from kubernetes.client.models import V1Deployment, V1DeploymentList

    v1_api = client.CoreV1Api()
    v1_apps = client.AppsV1Api()

    processed = []
    if resource.group.startswith("e4i"):
        edge_service = "opcua"
    else:
        edge_service = "e4k"

    deployments: V1DeploymentList = v1_apps.list_deployment_for_all_namespaces(label_selector=label_selector)
    logger.info(f"Detected {len(deployments.items)} deployments.")

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
                "zinfo": f"{edge_service}/{deployment_namespace}/deployment.{deployment_name}.yaml",
            }
        )
        deployment_pods = v1_api.list_namespaced_pod(deployment_namespace)
        processed.extend(
            process_v1_pods(edge_service=edge_service, pods=deployment_pods, since_seconds=since_seconds)
        )

    return processed


def get_bundle_path(bundle_dir: Optional[str] = None, system_name: str = "pas") -> PurePath:
    if not bundle_dir:
        bundle_dir = "."
    bundle_dir = abspath(bundle_dir)
    if "~" in bundle_dir:
        bundle_dir = expanduser(bundle_dir)
    bundle_dir_pure_path = PurePath(bundle_dir)
    if not isdir(str(bundle_dir_pure_path)):
        makedirs(bundle_dir_pure_path, exist_ok=True)
    bundle_pure_path = bundle_dir_pure_path.joinpath(default_bundle_name(system_name))
    return bundle_pure_path


def default_bundle_name(system_name: str) -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    timestamp = timestamp.replace(":", "-")
    return f"support_bundle_{timestamp}_{system_name}.zip"
