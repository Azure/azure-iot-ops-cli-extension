# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import socket
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Union
from urllib.request import urlopen

from azure.cli.core.azclierror import ResourceNotFoundError
from knack.log import get_logger
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1APIResourceList, V1Pod, V1PodList
from packaging import version
from rich.console import NewLine, Pretty
from rich.json import JSON
from rich.padding import Padding

from azext_edge.e4k.common import (
    BRIDGE_RESOURCE,
    BROKER_RESOURCE,
    CheckTaskStatus,
    IotEdgeBrokerResource,
    ResourceState,
)

DEFAULT_NAMESPACE: str = "default"

logger = get_logger(__name__)


def load_config_context(context_name: Optional[str] = None):
    """
    Load default config using a specific context or 'current-context' if not specified.
    """
    config.load_kube_config(context=context_name)
    _, current_config = config.list_kube_config_contexts()
    global DEFAULT_NAMESPACE
    DEFAULT_NAMESPACE = current_config.get("namespace") or "default"


_namespaced_object_cache: dict = {}
_namespaced_service_cache: dict = {}


def get_namespaced_pods_by_prefix(
    prefix: str, namespace: str
) -> Tuple[Union[None, List[V1Pod]], Union[None, Exception]]:
    v1 = client.CoreV1Api()

    pods_list: V1PodList = v1.list_namespaced_pod(namespace)
    target_pods: List[V1Pod] = []
    for pod in pods_list.items:
        p: V1Pod = pod
        if p.metadata.name.startswith(prefix):
            target_pods.append(p)
    if not target_pods:
        # TODO
        return None, RuntimeError(
            f"Pods in namespace {namespace} with prefix {prefix} could not be found."
        )

    return target_pods, None


def get_namespaced_object(
    resource: IotEdgeBrokerResource, namespace: Optional[str] = None
) -> dict:
    target_resource_key = str(resource)
    if target_resource_key in _namespaced_object_cache:
        return _namespaced_object_cache[target_resource_key]

    if not namespace:
        namespace = DEFAULT_NAMESPACE

    custom_client = client.CustomObjectsApi()

    _namespaced_object_cache[
        target_resource_key
    ] = custom_client.list_namespaced_custom_object(
        resource.group, resource.version, namespace, resource.resource
    )

    return _namespaced_object_cache[target_resource_key]


class PodRequest:
    def __init__(self, namespace: str, pod_name: str, pod_port: str):
        self.namespace = namespace
        self.pod_name = pod_name
        self.pod_port = pod_port

    def get(self, resource_path: str):
        response = urlopen(self._build_url(resource_path=resource_path))
        return response.read().decode("utf-8")

    def _build_url(self, resource_path: str):
        return f"http://{self.pod_name}.{self.namespace}.kubernetes:{self.pod_port}{resource_path}"


@contextmanager
def portforward_http(
    namespace: str, pod_name: str, pod_port: str, **kwargs
) -> PodRequest:
    from kubernetes.stream import portforward, stream

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
        pod_request = PodRequest(
            namespace=namespace, pod_name=pod_name, pod_port=pod_port
        )
        yield pod_request
    finally:
        socket.create_connection = socket_create_connection


_cluster_resources_cache: dict = {}


def get_cluster_custom_resources(
    resource: IotEdgeBrokerResource, raise_on_404: bool = False
) -> Union[V1APIResourceList, None]:
    if resource in _cluster_resources_cache:
        return _cluster_resources_cache[resource]

    try:
        v1_api_resource_list: v1_api_resource_list = (
            client.CustomObjectsApi().get_api_resources(
                group=resource.group, version=resource.version
            )
        )
    except ApiException as ae:
        logger.debug(msg=str(ae))
        if int(ae.status) == 404 and raise_on_404:
            raise ResourceNotFoundError(
                f"{resource.group}/{resource.version} resources do not exist on the cluster."
            )
