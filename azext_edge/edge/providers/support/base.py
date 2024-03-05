# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from os import makedirs
from os.path import abspath, expanduser, isdir
from pathlib import PurePath
from typing import List, Dict, Optional, Iterable
from functools import partial

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Container, V1ObjectMeta, V1PodSpec

from ..edge_api import EdgeResourceApi
from ..base import client, get_custom_objects
from ...util import get_timestamp_now_utc

logger = get_logger(__name__)
generic = client.ApiClient()

DAY_IN_SECONDS: int = 60 * 60 * 24  # TODO: Use constant across services.


def process_crd(group: str, version: str, kind: str, plural: str, api_moniker: str, file_prefix: Optional[str] = None):
    result: dict = get_custom_objects(
        group=group,
        version=version,
        plural=plural,
        use_cache=False,
    )
    if not file_prefix:
        file_prefix = kind

    processed = []
    namespaces = []
    for r in result.get("items", []):
        namespace = r["metadata"]["namespace"]
        namespaces.append(namespace)
        name = r["metadata"]["name"]
        processed.append({"data": r, "zinfo": f"{namespace}/{api_moniker}/{file_prefix}.{version}.{name}.yaml"})

    return processed


def process_v1_pods(
    resource_api: EdgeResourceApi,
    label_selector=None,
    since_seconds: int = 60 * 60 * 24,
    include_metrics=False,
    capture_previous_logs=True,
    prefix_names: Optional[List[str]] = None,
    pod_prefix_for_init_container_logs: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1Pod, V1PodList

    v1_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    processed = []
    if not prefix_names:
        prefix_names = []

    pods: V1PodList = v1_api.list_pod_for_all_namespaces(label_selector=label_selector)
    pod_logger_info = f"Detected {len(pods.items)} pods"
    if label_selector:
        pod_logger_info = f"{pod_logger_info} with label '{label_selector}'."
    logger.info(pod_logger_info)
    for pod in pods.items:
        p: V1Pod = pod
        pod_metadata: V1ObjectMeta = p.metadata
        pod_namespace: str = pod_metadata.namespace
        pod_name: str = pod_metadata.name

        if prefix_names:
            matched_prefix = [pod_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue

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

        if pod_prefix_for_init_container_logs:
            # check if pod name start with any prefix in pod_prefix_for_init_container_logs
            if any(pod_name.startswith(prefix) for prefix in pod_prefix_for_init_container_logs):
                processed.extend(
                    _capture_init_container_logs(
                        pod_name=pod_name,
                        pod_namespace=pod_namespace,
                        pod_spec=pod_spec,
                        resource_api=resource_api,
                        since_seconds=since_seconds,
                        v1_api=v1_api,
                    )
                )

    return processed


def process_deployments(
    resource_api: EdgeResourceApi,
    label_selector: str = None,
    field_selector: str = None,
    return_namespaces: bool = False,
    prefix_names: List[str] = None,
):
    from kubernetes.client.models import V1Deployment, V1DeploymentList

    v1_apps = client.AppsV1Api()

    processed = []
    if not prefix_names:
        prefix_names = []

    deployments: V1DeploymentList = v1_apps.list_deployment_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )
    logger.info(f"Detected {len(deployments.items)} deployments.")
    namespace_pods_work = {}

    for deployment in deployments.items:
        d: V1Deployment = deployment
        # TODO: Workaround
        d.api_version = deployments.api_version
        d.kind = "Deployment"
        deployment_metadata: V1ObjectMeta = d.metadata
        deployment_namespace: str = deployment_metadata.namespace
        deployment_name: str = deployment_metadata.name

        if prefix_names:
            matched_prefix = [deployment_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue

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
    label_selector: str = None,
    field_selector: str = None,
):
    from kubernetes.client.models import V1StatefulSet, V1StatefulSetList

    v1_apps = client.AppsV1Api()

    processed = []

    statefulsets: V1StatefulSetList = v1_apps.list_stateful_set_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )
    logger.info(f"Detected {len(statefulsets.items)} statefulsets.")

    for statefulset in statefulsets.items:
        s: V1StatefulSet = statefulset
        # TODO: Workaround
        s.api_version = statefulsets.api_version
        s.kind = "Statefulset"
        statefulset_metadata: V1ObjectMeta = s.metadata
        statefulset_namespace: str = statefulset_metadata.namespace
        statefulset_name: str = statefulset_metadata.name
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=s),
                "zinfo": f"{statefulset_namespace}/{resource_api.moniker}/statefulset.{statefulset_name}.yaml",
            }
        )

    return processed


def process_services(
    resource_api: EdgeResourceApi,
    label_selector: str = None,
    field_selector: str = None,
    prefix_names: List[str] = None,
):
    from kubernetes.client.models import V1Service, V1ServiceList

    v1_api = client.CoreV1Api()

    processed = []
    if not prefix_names:
        prefix_names = []

    services: V1ServiceList = v1_api.list_service_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )
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
    label_selector: str = None,
    prefix_names: List[str] = None,
):
    from kubernetes.client.models import V1ReplicaSet, V1ReplicaSetList

    v1_apps = client.AppsV1Api()

    processed = []
    if not prefix_names:
        prefix_names = []

    replicasets: V1ReplicaSetList = v1_apps.list_replica_set_for_all_namespaces(label_selector=label_selector)
    logger.info(f"Detected {len(replicasets.items)} replicasets.")

    for replicaset in replicasets.items:
        r: V1ReplicaSet = replicaset
        # TODO: Workaround
        r.api_version = replicasets.api_version
        r.kind = "Replicaset"
        replicaset_metadata: V1ObjectMeta = r.metadata
        replicaset_namespace: str = replicaset_metadata.namespace
        replicaset_name: str = replicaset_metadata.name

        if prefix_names:
            matched_prefix = [replicaset_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue

        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=r),
                "zinfo": f"{replicaset_namespace}/{resource_api.moniker}/replicaset.{replicaset_name}.yaml",
            }
        )

    return processed


def process_daemonsets(
    resource_api: EdgeResourceApi,
    label_selector: str = None,
    field_selector: str = None,
    prefix_names: List[str] = None,
):
    from kubernetes.client.models import V1DaemonSet, V1DaemonSetList

    v1_apps = client.AppsV1Api()

    processed = []
    if not prefix_names:
        prefix_names = []

    daemonsets: V1DaemonSetList = v1_apps.list_daemon_set_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )
    logger.info(f"Detected {len(daemonsets.items)} daemonsets.")

    for daemonset in daemonsets.items:
        d: V1DaemonSet = daemonset
        d.api_version = daemonsets.api_version
        d.kind = "Daemonset"
        daemonset_metadata: V1ObjectMeta = d.metadata
        daemonset_namespace: str = daemonset_metadata.namespace
        daemonset_name: str = daemonset_metadata.name

        if prefix_names:
            matched_prefix = [daemonset_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue

        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=d),
                "zinfo": f"{daemonset_namespace}/{resource_api.moniker}/daemonset.{daemonset_name}.yaml",
            }
        )

    return processed


def process_nodes():
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_node()),
        "zinfo": "nodes.yaml",
    }


def get_mq_namespaces() -> List[str]:
    from ..edge_api import MQ_ACTIVE_API, MqResourceKinds

    namespaces = []
    cluster_brokers = MQ_ACTIVE_API.get_resources(MqResourceKinds.BROKER)
    if cluster_brokers and cluster_brokers["items"]:
        namespaces.extend([b["metadata"]["namespace"] for b in cluster_brokers["items"]])

    return namespaces


def process_events():
    event_content = []

    core_v1_api = client.CoreV1Api()
    event_content.append(
        {
            "data": generic.sanitize_for_serialization(obj=core_v1_api.list_event_for_all_namespaces()),
            "zinfo": "events.yaml",
        }
    )

    return event_content


def process_storage_classes():
    storage_class_content = []

    storage_v1_api = client.StorageV1Api()
    storage_class_content.append(
        {
            "data": generic.sanitize_for_serialization(obj=storage_v1_api.list_storage_class()),
            "zinfo": "storage_classes.yaml",
        }
    )

    return storage_class_content


def process_persistent_volume_claims(
    resource_api: EdgeResourceApi,
    label_selector: str = None,
    field_selector: str = None,
    prefix_names: List[str] = None,
):
    from kubernetes.client.models import V1PersistentVolumeClaim, V1PersistentVolumeClaimList

    v1_api = client.CoreV1Api()

    processed = []
    if not prefix_names:
        prefix_names = []

    pvcs: V1PersistentVolumeClaimList = v1_api.list_persistent_volume_claim_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )
    logger.info(f"Detected {len(pvcs.items)} persistent volumn claims.")

    for pvc in pvcs.items:
        d: V1PersistentVolumeClaim = pvc
        d.api_version = pvcs.api_version
        d.kind = "PersistentVolumeClaim"
        pvc_metadata: V1ObjectMeta = d.metadata
        pvc_namespace: str = pvc_metadata.namespace
        pvc_name: str = pvc_metadata.name

        if prefix_names:
            matched_prefix = [pvc_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue

        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=d),
                "zinfo": f"{pvc_namespace}/{resource_api.moniker}/pvc.{pvc_name}.yaml",
            }
        )

    return processed


def assemble_crd_work(apis: Iterable[EdgeResourceApi], file_prefix_map: Optional[Dict[str, str]] = None):
    if not file_prefix_map:
        file_prefix_map = {}

    result = {}
    for api in apis:
        for kind in api.kinds:
            file_prefix = file_prefix_map.get(kind)
            result[f"{api.moniker} {api.version} {kind}"] = partial(
                process_crd,
                group=api.group,
                version=api.version,
                kind=kind,
                plural=api._kinds[kind],  # TODO: optimize
                api_moniker=api.moniker,
                file_prefix=file_prefix,
            )

    return result


def get_bundle_path(bundle_dir: Optional[str] = None, system_name: str = "aio") -> PurePath:
    bundle_dir_pure_path = normalize_dir(bundle_dir)
    bundle_pure_path = bundle_dir_pure_path.joinpath(default_bundle_name(system_name))
    return bundle_pure_path


def normalize_dir(dir_path: Optional[str] = None) -> PurePath:
    if not dir_path:
        dir_path = "."
    if "~" in dir_path:
        dir_path = expanduser(dir_path)
    dir_path = abspath(dir_path)
    dir_pure_path = PurePath(dir_path)
    if not isdir(str(dir_pure_path)):
        makedirs(dir_pure_path, exist_ok=True)

    return dir_pure_path


def default_bundle_name(system_name: str) -> str:
    timestamp = get_timestamp_now_utc(format="%Y%m%dT%H%M%S")
    return f"support_bundle_{timestamp}_{system_name}.zip"


def _capture_init_container_logs(
    pod_name: str,
    pod_namespace: str,
    pod_spec: V1PodSpec,
    resource_api: EdgeResourceApi,
    v1_api: client.CoreV1Api,
    since_seconds: int = 60 * 60 * 24,
) -> List[dict]:

    processed = []
    pod_init_containers: List[V1Container] = pod_spec.init_containers or []

    for init_container in pod_init_containers:
        try:
            logger.debug(f"Reading init log from pod {pod_name} init container {init_container.name}")
            log: str = v1_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=pod_namespace,
                since_seconds=since_seconds,
                container=init_container.name,
                previous=False,
            )
            processed.append(
                {
                    "data": log,
                    "zinfo": (
                        f"{pod_namespace}/{resource_api.moniker}/pod.{pod_name}.{init_container.name}.init.log"
                    ),
                }
            )
        except ApiException as e:
            logger.debug(e.body)

    return processed
