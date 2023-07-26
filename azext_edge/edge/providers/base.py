# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import socket
from contextlib import contextmanager
from typing import List, Optional, Union
from urllib.request import urlopen

from azure.cli.core.azclierror import ResourceNotFoundError
from knack.log import get_logger
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1APIResourceList, V1Pod, V1PodList, V1Service

from .edge_api import EdgeResourceApi, EdgeResource

DEFAULT_NAMESPACE: str = "default"

logger = get_logger(__name__)
generic = client.ApiClient()


def load_config_context(context_name: Optional[str] = None):
    """
    Load default config using a specific context or 'current-context' if not specified.
    """
    config.load_kube_config(context=context_name)
    _, current_config = config.list_kube_config_contexts()
    global DEFAULT_NAMESPACE
    DEFAULT_NAMESPACE = current_config.get("namespace") or "default"


_namespaced_service_cache: dict = {}


def get_namespaced_service(name: str, namespace: str, as_dict: bool = False) -> Union[V1Service, dict, None]:
    target_service_key = (name, namespace)
    if target_service_key in _namespaced_service_cache:
        return _namespaced_service_cache[target_service_key]

    try:
        v1 = client.CoreV1Api()
        v1_service: V1Service = v1.read_namespaced_service(name=name, namespace=namespace)
        _namespaced_service_cache[target_service_key] = v1_service
    except ApiException as ae:
        logger.debug(str(ae))
    else:
        result = _namespaced_service_cache[target_service_key]
        if as_dict:
            return generic.sanitize_for_serialization(obj=result)
        return result


_namespaced_pods_cache: dict = {}


def get_namespaced_pods_by_prefix(
    prefix: str,
    namespace: str,
    label_selector: str = None,
    as_dict: bool = False,
) -> Union[List[V1Pod], List[dict], None]:
    target_pods_key = (prefix, namespace, label_selector)
    if target_pods_key in _namespaced_pods_cache:
        return _namespaced_pods_cache[target_pods_key]

    try:
        v1 = client.CoreV1Api()
        pods_list: V1PodList = v1.list_namespaced_pod(namespace, label_selector=label_selector)
        matched_pods: List[V1Pod] = []
        for pod in pods_list.items:
            p: V1Pod = pod
            if p.metadata.name.startswith(prefix):
                matched_pods.append(p)
        _namespaced_pods_cache[target_pods_key] = matched_pods
    except ApiException as ae:
        logger.debug(str(ae))
    else:
        result = _namespaced_pods_cache[target_pods_key]
        if as_dict:
            return generic.sanitize_for_serialization(obj=result)
        return result


_namespaced_object_cache: dict = {}


def get_namespaced_custom_objects(resource: EdgeResource, namespace: str) -> Union[List[dict], None]:
    target_resource_key = (resource, resource.plural)
    if target_resource_key in _namespaced_object_cache:
        return _namespaced_object_cache[target_resource_key]

    try:
        custom_client = client.CustomObjectsApi()
        _namespaced_object_cache[target_resource_key] = custom_client.list_namespaced_custom_object(
            group=resource.api.group,
            version=resource.api.version,
            namespace=namespace,
            plural=resource.plural,
        )
    except ApiException as ae:
        logger.debug(str(ae))
    else:
        return _namespaced_object_cache[target_resource_key]


_cluster_resource_api_cache: dict = {}


def get_cluster_custom_api(resource_api: EdgeResourceApi, raise_on_404: bool = False) -> Union[V1APIResourceList, None]:
    if resource_api in _cluster_resource_api_cache:
        return _cluster_resource_api_cache[resource_api]

    try:
        custom_client = client.CustomObjectsApi()
        _cluster_resource_api_cache[resource_api] = custom_client.get_api_resources(
            group=resource_api.group, version=resource_api.version
        )
    except ApiException as ae:
        logger.debug(msg=str(ae))
        if int(ae.status) == 404 and raise_on_404:
            raise ResourceNotFoundError(f"{resource_api.as_str()} resource API is not detected on the cluster.")
    else:
        return _cluster_resource_api_cache[resource_api]


class PodRequest:
    def __init__(self, namespace: str, pod_name: str, pod_port: str):
        self.namespace = namespace
        self.pod_name = pod_name
        self.pod_port = pod_port

    def get(self, resource_path: str):
        with urlopen(self._build_url(resource_path=resource_path)) as response:
            return response.read().decode("utf-8")

    def _build_url(self, resource_path: str):
        return f"http://{self.pod_name}.{self.namespace}.kubernetes:{self.pod_port}{resource_path}"


@contextmanager
def portforward_http(namespace: str, pod_name: str, pod_port: str, **kwargs) -> PodRequest:
    from kubernetes.stream import portforward

    api = client.CoreV1Api()

    def kubernetes_create_connection(address, *args, **kwargs):
        dns_name = address[0]
        if isinstance(dns_name, bytes):
            dns_name = dns_name.decode()
        dns_name = dns_name.split(".")
        if len(dns_name) != 3 or dns_name[2] != "kubernetes":
            return socket_create_connection(address, *args, **kwargs)
        pf = portforward(
            api.connect_get_namespaced_pod_portforward,
            dns_name[0],
            dns_name[1],
            ports=str(address[1]),
        )
        return pf.socket(address[1])

    socket_create_connection = socket.create_connection
    try:
        socket.create_connection = kubernetes_create_connection
        pod_request = PodRequest(namespace=namespace, pod_name=pod_name, pod_port=pod_port)
        yield pod_request
    finally:
        socket.create_connection = socket_create_connection
