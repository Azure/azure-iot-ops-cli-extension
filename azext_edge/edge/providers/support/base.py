# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from os import makedirs
from os.path import abspath, expanduser, isdir
from pathlib import PurePath
from typing import List, Dict, Optional, Iterable
from functools import partial

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Container, V1ObjectMeta

from ..edge_api import EdgeResource, EdgeResourceApi
from ..base import client

logger = get_logger(__name__)
generic = client.ApiClient()


def process_crd(resource: EdgeResource, file_prefix: Optional[str] = None):
    result: dict = client.CustomObjectsApi().list_cluster_custom_object(
        group=resource.api.group,
        version=resource.api.version,
        plural=resource.plural,
    )
    if not file_prefix:
        file_prefix = resource.kind

    processed = []
    namespaces = []
    for r in result.get("items", []):
        namespace = r["metadata"]["namespace"]
        namespaces.append(namespace)
        name = r["metadata"]["name"]
        processed.append(
            {"data": r, "zinfo": f"{namespace}/{resource.api.moniker}/{file_prefix}.{resource.api.version}.{name}.yaml"}
        )

    return processed


def process_v1_pods(
    resource_api: EdgeResourceApi,
    label_selector=None,
    since_seconds: int = 60 * 60 * 24,
    include_metrics=False,
    capture_previous_logs=False,
) -> List[dict]:
    from kubernetes.client.models import V1Pod, V1PodList, V1PodSpec

    v1_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    processed = []

    pods: V1PodList = v1_api.list_pod_for_all_namespaces(label_selector=label_selector)
    pod_logger_info = f"Detected {len(pods.items)} pods."
    if label_selector:
        pod_logger_info = f"{pod_logger_info} with label {pod_logger_info}."
    logger.info(pod_logger_info)
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
                "zinfo": f"{pod_namespace}/{resource_api.moniker}/pod.{pod_name}.yaml",
            }
        )
        pod_spec: V1PodSpec = p.spec
        pod_containers: List[V1Container] = pod_spec.containers
        capture_previous_log_runs = [False]
        if capture_previous_logs:
            capture_previous_log_runs.append(True)
        for container in pod_containers:
            for capture_previous in capture_previous_log_runs:
                try:
                    logger_debug_previous = "previous run " if capture_previous else ""
                    logger.debug(f"Reading {logger_debug_previous}log from pod {pod_name} container {container.name}")
                    log: str = v1_api.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=pod_namespace,
                        since_seconds=since_seconds,
                        container=container.name,
                        previous=capture_previous,
                    )
                    zinfo_previous_segment = "previous." if capture_previous else ""
                    processed.append(
                        {
                            "data": log,
                            "zinfo": (
                                f"{pod_namespace}/{resource_api.moniker}"
                                f"/pod.{pod_name}.{container.name}.{zinfo_previous_segment}log"
                            ),
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
                            "zinfo": f"{pod_namespace}/{resource_api.moniker}/pod.{pod_name}.metric.yaml",
                        }
                    )
            except ApiException as e:
                logger.debug(e.body)

    return processed


def process_deployments(
    resource_api: EdgeResourceApi,
    label_selector: str = None,
    return_namespaces: bool = False,
):
    from kubernetes.client.models import V1Deployment, V1DeploymentList

    v1_apps = client.AppsV1Api()

    processed = []

    deployments: V1DeploymentList = v1_apps.list_deployment_for_all_namespaces(label_selector=label_selector)
    logger.info(f"Detected {len(deployments.items)} deployments.")
    namespace_pods_work = {}

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
                "zinfo": f"{deployment_namespace}/{resource_api.moniker}/deployment.{deployment_name}.yaml",
            }
        )
        if deployment_namespace not in namespace_pods_work:
            namespace_pods_work[deployment_namespace] = True

    if return_namespaces:
        return processed, namespace_pods_work

    return processed


def process_statefulset(
    resource_api: EdgeResourceApi,
    label_selector: str,
):
    from kubernetes.client.models import V1StatefulSet, V1StatefulSetList

    v1_apps = client.AppsV1Api()

    processed = []

    statefulsets: V1StatefulSetList = v1_apps.list_stateful_set_for_all_namespaces(label_selector=label_selector)
    logger.info(f"Detected {len(statefulsets.items)} statefulsets.")

    for statefulset in statefulsets.items:
        s: V1StatefulSet = statefulset
        # TODO: Workaround
        s.api_version = statefulsets.api_version
        s.kind = "Statefulset"
        statefulset_metadata: V1ObjectMeta = s.metadata
        statefulset_namespace = statefulset_metadata.namespace
        statefulset_name = statefulset_metadata.name
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=s),
                "zinfo": f"{statefulset_namespace}/{resource_api.moniker}/statefulset.{statefulset_name}.yaml",
            }
        )

    return processed


def process_services(resource_api: EdgeResourceApi, label_selector: str, prefix_names: List[str] = None):
    from kubernetes.client.models import V1Service, V1ServiceList

    v1_api = client.CoreV1Api()

    processed = []
    if not prefix_names:
        prefix_names = []

    services: V1ServiceList = v1_api.list_service_for_all_namespaces(label_selector=label_selector)
    logger.info(f"Detected {len(services.items)} services.")

    for service in services.items:
        s: V1Service = service
        # TODO: Workaround
        s.api_version = services.api_version
        s.kind = "Service"
        service_metadata: V1ObjectMeta = s.metadata
        service_namespace: str = service_metadata.namespace
        service_name: str = service_metadata.name
        if prefix_names:
            matched_prefix = [service_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=s),
                "zinfo": f"{service_namespace}/{resource_api.moniker}/service.{service_name}.yaml",
            }
        )

    return processed


def process_replicasets(
    resource_api: EdgeResourceApi,
    label_selector: str,
):
    from kubernetes.client.models import V1ReplicaSet, V1ReplicaSetList

    v1_apps = client.AppsV1Api()

    processed = []

    replicasets: V1ReplicaSetList = v1_apps.list_replica_set_for_all_namespaces(label_selector=label_selector)
    logger.info(f"Detected {len(replicasets.items)} replicasets.")

    for replicaset in replicasets.items:
        r: V1ReplicaSet = replicaset
        # TODO: Workaround
        r.api_version = replicasets.api_version
        r.kind = "Replicaset"
        statefulset_metadata: V1ObjectMeta = r.metadata
        statefulset_namespace = statefulset_metadata.namespace
        statefulset_name = statefulset_metadata.name
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=r),
                "zinfo": f"{statefulset_namespace}/{resource_api.moniker}/replicaset.{statefulset_name}.yaml",
            }
        )

    return processed


def process_nodes():
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_node()),
        "zinfo": "nodes.yaml",
    }


def assemble_crd_work(apis: Iterable[EdgeResourceApi], file_prefix_map: Optional[Dict[str, str]] = None):
    if not file_prefix_map:
        file_prefix_map = {}

    result = {}
    for api in apis:
        for kind in api.kinds:
            resource = api.get_resource(kind)
            file_prefix = file_prefix_map.get(kind)
            if resource:
                result[f"{resource.api.moniker} {resource.api.version} {resource.plural}"] = partial(
                    process_crd, resource=resource, file_prefix=file_prefix
                )

    return result


def get_bundle_path(bundle_dir: Optional[str] = None, system_name: str = "pas") -> PurePath:
    if not bundle_dir:
        bundle_dir = "."
    if "~" in bundle_dir:
        bundle_dir = expanduser(bundle_dir)
    bundle_dir = abspath(bundle_dir)
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
