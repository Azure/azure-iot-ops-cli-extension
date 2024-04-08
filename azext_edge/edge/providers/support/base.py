# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from os import makedirs
from os.path import abspath, expanduser, isdir
from pathlib import PurePath
from typing import List, Dict, Optional, Iterable, Union
from functools import partial

from azext_edge.edge.common import BundleResourceKind
from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Container, V1ObjectMeta, V1PodSpec

from ..edge_api import EdgeResourceApi
from ..base import client, get_custom_objects
from ...util import get_timestamp_now_utc

logger = get_logger(__name__)
generic = client.ApiClient()

DAY_IN_SECONDS: int = 60 * 60 * 24


def process_crd(
    group: str,
    version: str,
    kind: str,
    plural: str,
    api_moniker: str,
    sub_group: Optional[str] = None,
    file_prefix: Optional[str] = None,
) -> List[dict]:
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
        zinfo = _process_zinfo(
            prefix=f"{namespace}/{api_moniker}",
            suffix=f"{file_prefix}.{version}.{name}.yaml",
            sub_group=sub_group,
        )
        processed.append({
            "data": r,
            "zinfo": zinfo,
        })

    return processed


def process_v1_pods(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    capture_previous_logs: bool = True,
    include_metrics: bool = False,
    since_seconds: int = DAY_IN_SECONDS,
    label_selector: Optional[str] = None,
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
        zinfo = _process_zinfo(
            prefix=f"{pod_namespace}/{resource_api.moniker}",
            suffix=f"pod.{pod_name}.yaml",
            sub_group=sub_group,
        )
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=p),
                "zinfo": zinfo,
            }
        )
        pod_spec: V1PodSpec = p.spec
        pod_containers: List[V1Container] = pod_spec.containers

        if pod_prefix_for_init_container_logs:
            # check if pod name starts with any prefix in pod_prefix_for_init_container_logs
            if any(pod_name.startswith(prefix) for prefix in pod_prefix_for_init_container_logs):
                init_pod_containers: List[V1Container] = pod_spec.init_containers
                pod_containers.extend(init_pod_containers)

        processed.extend(
            _capture_pod_container_logs(
                pod_containers=pod_containers,
                pod_name=pod_name,
                pod_namespace=pod_namespace,
                resource_api=resource_api,
                v1_api=v1_api,
                since_seconds=since_seconds,
                capture_previous_logs=capture_previous_logs,
                sub_group=sub_group,
            )
        )

        if include_metrics:
            try:
                logger.debug(f"Fetching runtime metrics for {pod_name}")
                metric: dict = custom_api.get_namespaced_custom_object(
                    "metrics.k8s.io", "v1beta1", pod_namespace, "pods", pod_name
                )
                if metric:
                    zinfo = _process_zinfo(
                        prefix=f"{pod_namespace}/{resource_api.moniker}",
                        suffix=f"pod.{pod_name}.metric.yaml",
                        sub_group=sub_group,
                    )
                    processed.append(
                        {
                            "data": metric,
                            "zinfo": zinfo,
                        }
                    )
            except ApiException as e:
                logger.debug(e.body)

    return processed


def process_deployments(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    return_namespaces: bool = False,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1DeploymentList

    v1_apps = client.AppsV1Api()
    deployments: V1DeploymentList = v1_apps.list_deployment_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )
    namespace_pods_work = {}

    processed = _process_kubernetes_resources(
        sub_group=sub_group,
        resources=deployments,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.deployment.value,
    )

    for deployment in deployments.items:
        deployment_namespace: str = deployment.metadata.namespace

        if deployment_namespace not in namespace_pods_work:
            namespace_pods_work[deployment_namespace] = True

    if return_namespaces:
        return processed, namespace_pods_work

    return processed


def process_statefulset(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
) -> List[dict]:
    from kubernetes.client.models import V1StatefulSetList

    v1_apps = client.AppsV1Api()
    statefulsets: V1StatefulSetList = v1_apps.list_stateful_set_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=statefulsets,
        resource_api=resource_api,
        kind=BundleResourceKind.statefulset.value,
    )


def process_services(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1ServiceList

    v1_api = client.CoreV1Api()
    services: V1ServiceList = v1_api.list_service_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=services,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.service.value,
    )


def process_replicasets(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1ReplicaSetList

    v1_apps = client.AppsV1Api()
    replicasets: V1ReplicaSetList = v1_apps.list_replica_set_for_all_namespaces(label_selector=label_selector)

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=replicasets,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.replicaset.value,
    )


def process_daemonsets(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1DaemonSetList

    v1_apps = client.AppsV1Api()
    daemonsets: V1DaemonSetList = v1_apps.list_daemon_set_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=daemonsets,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.daemonset.value,
    )


def process_nodes() -> Dict[str, Union[dict, str]]:
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


def process_events() -> List[dict]:
    event_content = []

    core_v1_api = client.CoreV1Api()
    event_content.append(
        {
            "data": generic.sanitize_for_serialization(obj=core_v1_api.list_event_for_all_namespaces()),
            "zinfo": "events.yaml",
        }
    )

    return event_content


def process_storage_classes() -> List[dict]:
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
    sub_group: Optional[str] = None,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1PersistentVolumeClaimList

    v1_api = client.CoreV1Api()
    pvcs: V1PersistentVolumeClaimList = v1_api.list_persistent_volume_claim_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=pvcs,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.pvc.value,
    )


def process_jobs(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1JobList

    batch_v1_api = client.BatchV1Api()
    jobs: V1JobList = batch_v1_api.list_job_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=jobs,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.job.value,
    )


def process_cron_jobs(
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    from kubernetes.client.models import V1CronJobList

    batch_v1_api = client.BatchV1Api()
    cron_jobs: V1CronJobList = batch_v1_api.list_cron_job_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        sub_group=sub_group,
        resources=cron_jobs,
        resource_api=resource_api,
        prefix_names=prefix_names,
        kind=BundleResourceKind.cronjob.value,
    )


def assemble_crd_work(
    apis: Iterable[EdgeResourceApi],
    sub_group: Optional[str] = None,
    file_prefix_map: Optional[Dict[str, str]] = None,
) -> dict:
    if not file_prefix_map:
        file_prefix_map = {}

    result = {}
    for api in apis:
        for kind in api.kinds:
            file_prefix = file_prefix_map.get(kind)
            result[f"{api.moniker} {api.version} {kind}"] = partial(
                process_crd,
                sub_group=sub_group,
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


def _capture_pod_container_logs(
    pod_containers: List[V1Container],
    pod_name: str,
    pod_namespace: str,
    resource_api: EdgeResourceApi,
    v1_api: client.CoreV1Api,
    capture_previous_logs: bool = True,
    since_seconds: int = DAY_IN_SECONDS,
    sub_group: Optional[str] = None,
) -> List[dict]:

    processed = []
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
                zinfo = _process_zinfo(
                    prefix=f"{pod_namespace}/{resource_api.moniker}",
                    suffix=f"pod.{pod_name}.{container.name}.{zinfo_previous_segment}log",
                    sub_group=sub_group,
                )
                processed.append(
                    {
                        "data": log,
                        "zinfo": zinfo,
                    }
                )
            except ApiException as e:
                logger.debug(e.body)

    return processed


def _process_kubernetes_resources(
    resources: object,
    resource_api: EdgeResourceApi,
    sub_group: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    kind: Optional[str] = None,
) -> List[dict]:
    processed = []

    if not prefix_names:
        prefix_names = []

    log = f"Detected {len(resources.items)} {kind}s." if kind else f"Detected {len(resources.items)} resources."
    logger.info(log)
    for resource in resources.items:
        r = resource
        r.api_version = resources.api_version
        r.kind = kind
        resource_metadata = r.metadata
        resource_namespace = resource_metadata.namespace
        resource_name = resource_metadata.name

        if prefix_names:
            matched_prefix = [resource_name.startswith(prefix) for prefix in prefix_names]
            if not any(matched_prefix):
                continue

        if len(kind) > 12:
            # get every first capital letter in the kind
            resource_type = "".join([c for c in kind if c.isupper()]).lower()
        else:
            resource_type = kind.lower()

        zinfo = _process_zinfo(
            prefix=f"{resource_namespace}/{resource_api.moniker}",
            suffix=f"{resource_type}.{resource_name}.yaml",
            sub_group=sub_group,
        )
        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=r),
                "zinfo": zinfo,
            }
        )

    return processed


def _process_zinfo(
    prefix: str,
    suffix: str,
    sub_group: Optional[str] = None,
) -> str:
    if not sub_group:
        sub_group = ""
    else:
        sub_group = f"{sub_group}/"

    return f"{prefix}/{sub_group}{suffix}"
