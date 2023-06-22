# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import List, Optional

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Container, V1ObjectMeta, V1Pod, V1PodList, V1PodSpec
from ..base import client
from ...common import IotEdgeBrokerResource

logger = get_logger(__name__)
generic = client.ApiClient()


def process_crd(resource: IotEdgeBrokerResource, plural: str, file_prefix: Optional[str] = None):
    result: dict = client.CustomObjectsApi().list_cluster_custom_object(
        group=resource.group,
        version=resource.version,
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


def process_v1_pods(pods: V1PodList, since_seconds: int = 60 * 60 * 24, include_metrics=False):
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


def process_events(resource: IotEdgeBrokerResource, plural: str, file_prefix: Optional[str] = None):
    client.
    result: dict = client.CustomObjectsApi().list_cluster_custom_object(
        group=resource.group,
        version=resource.version,
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