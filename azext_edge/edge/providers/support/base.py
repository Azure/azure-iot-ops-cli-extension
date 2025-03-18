# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from pathlib import PurePath
from typing import List, Dict, Optional, Iterable, Tuple, TypeVar, Union
from functools import partial

from azext_edge.edge.common import BundleResourceKind, PodState
from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1Container,
    V1ObjectMeta,
    V1PodSpec,
    V1PodList,
    V1ServiceList,
    V1DeploymentList,
    V1StatefulSetList,
    V1ReplicaSetList,
    V1DaemonSetList,
    V1PersistentVolumeClaimList,
    V1JobList,
    V1CronJobList,
)

from ..edge_api import EdgeResourceApi
from ..base import client, get_custom_objects
from ...util import get_timestamp_now_utc

logger = get_logger(__name__)
generic = client.ApiClient()

DAY_IN_SECONDS: int = 60 * 60 * 24
POD_STATUS_FAILED_EVICTED: str = "evicted"

K8sRuntimeResources = TypeVar(
    "K8sRuntimeResources",
    V1ServiceList,
    V1PodList,
    V1DeploymentList,
    V1StatefulSetList,
    V1ReplicaSetList,
    V1DaemonSetList,
    V1PersistentVolumeClaimList,
    V1JobList,
    V1CronJobList,
)


def process_crd(
    group: str,
    version: str,
    kind: str,
    plural: str,
    directory_path: str,
    file_prefix: Optional[str] = None,
    fallback_namespace: Optional[str] = None,
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
    for r in result.get("items", []):
        # Try to get namespace from metadata, if not found, use fallback_namespace if provided
        try:
            namespace = r["metadata"]["namespace"]
        except KeyError:
            if fallback_namespace:
                namespace = fallback_namespace
            else:
                logger.debug("Namespace not found in CRD metadata and no fallback namespace provided.")
        name = r["metadata"]["name"]

        processed.append(
            {
                "data": r,
                "zinfo": f"{namespace}/{directory_path}/{file_prefix}.{version}.{name}.yaml",
            }
        )

    return processed


def process_v1_pods(
    directory_path: str,
    capture_previous_logs: bool = True,
    include_metrics: bool = False,
    since_seconds: int = DAY_IN_SECONDS,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    pod_prefix_for_init_container_logs: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    from kubernetes.client.models import V1Pod

    v1_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    processed = []
    if not prefix_names:
        prefix_names = []

    if namespace:
        pods: V1PodList = v1_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
    else:
        pods: V1PodList = v1_api.list_pod_for_all_namespaces(label_selector=label_selector)

    if exclude_prefixes:
        pods = exclude_resources_with_prefix(pods, exclude_prefixes)

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
                "zinfo": f"{pod_namespace}/{directory_path}/pod.{pod_name}.yaml",
            }
        )
        pod_spec: V1PodSpec = p.spec
        pod_containers: List[V1Container] = pod_spec.containers

        if pod_prefix_for_init_container_logs:
            # check if pod name starts with any prefix in pod_prefix_for_init_container_logs
            if any(pod_name.startswith(prefix) for prefix in pod_prefix_for_init_container_logs):
                init_pod_containers: List[V1Container] = pod_spec.init_containers
                pod_containers.extend(init_pod_containers)

        # exclude evicted pods from log capture since they are not accessible
        pod_status = pod.status
        if (
            pod_status
            and pod_status.phase == PodState.failed.value
            and str(pod_status.reason).lower() == POD_STATUS_FAILED_EVICTED
        ):
            logger.info(f"Pod {pod_name} in namespace {pod_namespace} is evicted. Skipping log capture.")
        else:
            processed.extend(
                _capture_pod_container_logs(
                    directory_path=directory_path,
                    pod_containers=pod_containers,
                    pod_name=pod_name,
                    pod_namespace=pod_namespace,
                    v1_api=v1_api,
                    since_seconds=since_seconds,
                    capture_previous_logs=capture_previous_logs,
                )
            )

        if include_metrics:
            try:
                logger.debug(f"Fetching runtime metrics for {pod_name}")
                metric: dict = custom_api.get_namespaced_custom_object(
                    "metrics.k8s.io", "v1", pod_namespace, "pods", pod_name
                )
                if metric:
                    processed.append(
                        {
                            "data": metric,
                            "zinfo": f"{pod_namespace}/{directory_path}/pod.{pod_name}.metric.yaml",
                        }
                    )
            except ApiException as e:
                logger.debug(e.body)

    return processed


def process_deployments(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    v1_apps = client.AppsV1Api()

    if namespace:
        deployments: V1DeploymentList = v1_apps.list_namespaced_deployment(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        deployments: V1DeploymentList = v1_apps.list_deployment_for_all_namespaces(
            label_selector=label_selector, field_selector=field_selector
        )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=deployments,
        prefix_names=prefix_names,
        kind=BundleResourceKind.deployment.value,
        exclude_prefixes=exclude_prefixes,
    )


def process_statefulset(
    directory_path: str,
    return_namespaces: bool = False,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> Union[Tuple[List[dict], dict], List[dict]]:
    v1_apps = client.AppsV1Api()

    if namespace:
        statefulsets: V1StatefulSetList = v1_apps.list_namespaced_stateful_set(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        statefulsets: V1StatefulSetList = v1_apps.list_stateful_set_for_all_namespaces(
            label_selector=label_selector, field_selector=field_selector
        )
    namespace_pods_work = {}

    processed = _process_kubernetes_resources(
        directory_path=directory_path,
        resources=statefulsets,
        kind=BundleResourceKind.statefulset.value,
        prefix_names=prefix_names,
    )

    for statefulset in statefulsets.items:
        statefulset_namespace: str = statefulset.metadata.namespace

        if statefulset_namespace not in namespace_pods_work:
            namespace_pods_work[statefulset_namespace] = True

    if return_namespaces:
        return processed, namespace_pods_work

    return processed


def process_services(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    v1_api = client.CoreV1Api()

    if namespace:
        services: V1ServiceList = v1_api.list_namespaced_service(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        services: V1ServiceList = v1_api.list_service_for_all_namespaces(
            label_selector=label_selector, field_selector=field_selector
        )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=services,
        prefix_names=prefix_names,
        kind=BundleResourceKind.service.value,
        exclude_prefixes=exclude_prefixes,
    )


def process_replicasets(
    directory_path: str,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    v1_apps = client.AppsV1Api()

    if namespace:
        replicasets: V1ReplicaSetList = v1_apps.list_namespaced_replica_set(
            namespace=namespace, label_selector=label_selector
        )
    else:
        replicasets: V1ReplicaSetList = v1_apps.list_replica_set_for_all_namespaces(label_selector=label_selector)

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=replicasets,
        prefix_names=prefix_names,
        kind=BundleResourceKind.replicaset.value,
        exclude_prefixes=exclude_prefixes,
    )


def process_daemonsets(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    v1_apps = client.AppsV1Api()

    if namespace:
        daemonsets: V1DaemonSetList = v1_apps.list_namespaced_daemon_set(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        daemonsets: V1DaemonSetList = v1_apps.list_daemon_set_for_all_namespaces(
            label_selector=label_selector, field_selector=field_selector
        )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=daemonsets,
        prefix_names=prefix_names,
        kind=BundleResourceKind.daemonset.value,
    )


def process_config_maps(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    v1_api = client.CoreV1Api()

    if namespace:
        config_maps = v1_api.list_namespaced_config_map(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        config_maps = v1_api.list_config_map_for_all_namespaces(
            label_selector=label_selector, field_selector=field_selector
        )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=config_maps,
        prefix_names=prefix_names,
        kind=BundleResourceKind.configmap.value,
    )


def process_cluster_roles(
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
) -> Dict[str, Union[dict, str]]:
    from kubernetes.client.models import V1ClusterRoleList
    from kubernetes.client import RbacAuthorizationV1Api

    processed = []
    rbac_api = RbacAuthorizationV1Api()

    cluster_roles: V1ClusterRoleList = rbac_api.list_cluster_role(label_selector=label_selector, field_selector=field_selector)
    for role in cluster_roles.items:
        namespace = role.metadata.annotations.get("meta.helm.sh/release-namespace") if role.metadata.annotations else None
        name = role.metadata.name
        resource_type = _get_resource_type_prefix(BundleResourceKind.clusterrole.value)

        if namespace:
            processed.append(
                {
                    "data": generic.sanitize_for_serialization(obj=role),
                    "zinfo": f"{namespace}/{directory_path}/{resource_type}.{name}.yaml",
                }
            )

    return processed


def process_cluster_role_bindings(
    directory_path: str,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
) -> Dict[str, Union[dict, str]]:
    from kubernetes.client.models import V1ClusterRoleBindingList
    from kubernetes.client import RbacAuthorizationV1Api

    processed = []
    rbac_api = RbacAuthorizationV1Api()

    cluster_role_bindings: V1ClusterRoleBindingList = rbac_api.list_cluster_role_binding(label_selector=label_selector, field_selector=field_selector)
    for binding in cluster_role_bindings.items:
        namespace = binding.metadata.annotations.get("meta.helm.sh/release-namespace") if binding.metadata.annotations else None
        name = binding.metadata.name
        resource_type = _get_resource_type_prefix(BundleResourceKind.clusterrolebinding.value)

        if namespace:
            processed.append(
                {
                    "data": generic.sanitize_for_serialization(obj=binding),
                    "zinfo": f"{namespace}/{directory_path}/{resource_type}.{name}.yaml",
                }
            )

    return processed


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
            "zinfo": "storage-classes.yaml",
        }
    )

    return storage_class_content


def process_persistent_volume_claims(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    namespace: Optional[str] = None,
) -> List[dict]:
    v1_api = client.CoreV1Api()

    if namespace:
        pvcs: V1PersistentVolumeClaimList = v1_api.list_namespaced_persistent_volume_claim(
            namespace=namespace, label_selector=label_selector, field_selector=field_selector
        )
    else:
        pvcs: V1PersistentVolumeClaimList = v1_api.list_persistent_volume_claim_for_all_namespaces(
            label_selector=label_selector, field_selector=field_selector
        )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=pvcs,
        prefix_names=prefix_names,
        kind=BundleResourceKind.pvc.value,
    )


def process_jobs(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
) -> List[dict]:
    batch_v1_api = client.BatchV1Api()
    jobs: V1JobList = batch_v1_api.list_job_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=jobs,
        prefix_names=prefix_names,
        kind=BundleResourceKind.job.value,
        exclude_prefixes=exclude_prefixes,
    )


def process_cron_jobs(
    directory_path: str,
    field_selector: Optional[str] = None,
    label_selector: Optional[str] = None,
    prefix_names: Optional[List[str]] = None,
) -> List[dict]:
    batch_v1_api = client.BatchV1Api()
    cron_jobs: V1CronJobList = batch_v1_api.list_cron_job_for_all_namespaces(
        label_selector=label_selector, field_selector=field_selector
    )

    return _process_kubernetes_resources(
        directory_path=directory_path,
        resources=cron_jobs,
        prefix_names=prefix_names,
        kind=BundleResourceKind.cronjob.value,
    )


def assemble_crd_work(
    apis: Iterable[EdgeResourceApi],
    file_prefix_map: Optional[Dict[str, str]] = None,
    directory_path: Optional[str] = None,
    fallback_namespace: Optional[str] = None,
) -> dict:
    if not file_prefix_map:
        file_prefix_map = {}

    result = {}
    for api in apis:
        path = directory_path or api.moniker
        for kind in api.kinds:
            file_prefix = file_prefix_map.get(kind)
            result[f"{api.moniker} {api.version} {kind}"] = partial(
                process_crd,
                group=api.group,
                version=api.version,
                kind=kind,
                plural=api._kinds[kind],  # TODO: optimize
                directory_path=path,
                file_prefix=file_prefix,
                fallback_namespace=fallback_namespace,
            )

    return result


def get_bundle_path(bundle_dir: Optional[str] = None, system_name: str = "aio") -> PurePath:
    from ...util import normalize_dir

    bundle_dir_pure_path = normalize_dir(bundle_dir)
    bundle_pure_path = bundle_dir_pure_path.joinpath(default_bundle_name(system_name))
    return bundle_pure_path


def default_bundle_name(system_name: str) -> str:
    timestamp = get_timestamp_now_utc(format="%Y%m%dT%H%M%S")
    return f"support_bundle_{timestamp}_{system_name}.zip"


def _capture_pod_container_logs(
    directory_path: str,
    pod_containers: List[V1Container],
    pod_name: str,
    pod_namespace: str,
    v1_api: client.CoreV1Api,
    capture_previous_logs: bool = True,
    since_seconds: int = DAY_IN_SECONDS,
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
                zinfo = f"{pod_namespace}/{directory_path}/pod.{pod_name}.{container.name}.{zinfo_previous_segment}log"
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
    directory_path: str,
    resources: K8sRuntimeResources,
    kind: str,
    prefix_names: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
) -> List[dict]:
    processed = []

    if not prefix_names:
        prefix_names = []

    if exclude_prefixes:
        resources = exclude_resources_with_prefix(resources, exclude_prefixes)

    logger.info(f"Detected {len(resources.items)} {kind}s.")
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

        resource_type = _get_resource_type_prefix(kind)

        processed.append(
            {
                "data": generic.sanitize_for_serialization(obj=r),
                "zinfo": f"{resource_namespace}/{directory_path}/{resource_type}.{resource_name}.yaml",
            }
        )

    return processed


def _get_resource_type_prefix(kind: str) -> str:
    if len(kind) > 12:
        # get every first capital letter in the kind
        resource_type = "".join([c for c in kind if c.isupper()]).lower()
    else:
        resource_type = kind.lower()

    return resource_type


def exclude_resources_with_prefix(resources: K8sRuntimeResources, exclude_prefixes: List[str]) -> K8sRuntimeResources:
    for prefix in exclude_prefixes:
        resources.items = [resource for resource in resources.items if not resource.metadata.name.startswith(prefix)]

    return resources
