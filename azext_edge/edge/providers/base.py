# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import socket
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Union
from urllib.request import urlopen

from azure.cli.core.azclierror import ResourceNotFoundError
from knack.log import get_logger
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1APIResourceList,
    V1ObjectMeta,
    V1Pod,
    V1PodList,
    V1Service,
)

from ..common import K8sSecretType

DEFAULT_NAMESPACE: str = "azure-iot-operations"

logger = get_logger(__name__)
generic = client.ApiClient()


def load_config_context(context_name: Optional[str] = None):
    """
    Load default config using a specific context or 'current-context' if not specified.
    """
    from ..util import set_log_level

    # This will ensure --debug works with http(s) k8s interactions
    set_log_level("urllib3.connectionpool")

    config.load_kube_config(context=context_name)
    _, current_config = config.list_kube_config_contexts()
    global DEFAULT_NAMESPACE
    DEFAULT_NAMESPACE = current_config.get("namespace") or "default"


_namespaced_service_cache: dict = {}


def get_namespaced_service(name: str, namespace: str, as_dict: bool = False) -> Union[V1Service, dict, None]:
    def retrieve_namespaced_service_from_cache(key: tuple):
        result = _namespaced_service_cache[key]
        if as_dict:
            return generic.sanitize_for_serialization(obj=result)
        return result

    target_service_key = (name, namespace)
    if target_service_key in _namespaced_service_cache:
        return retrieve_namespaced_service_from_cache(target_service_key)

    try:
        v1 = client.CoreV1Api()
        v1_service: V1Service = v1.read_namespaced_service(name=name, namespace=namespace)
        _namespaced_service_cache[target_service_key] = v1_service
    except ApiException as ae:
        logger.debug(str(ae))
    else:
        return retrieve_namespaced_service_from_cache(target_service_key)


_namespaced_pods_cache: dict = {}


def get_namespaced_pods_by_prefix(
    prefix: str,
    namespace: str,
    label_selector: str = None,
    as_dict: bool = False,
) -> Union[List[V1Pod], List[dict], None]:
    def filter_pods_by_prefix(pods: List[V1Pod], prefix: str) -> List[V1Pod]:
        return [pod for pod in pods if pod.metadata.name.startswith(prefix)]

    def filter_pods_from_cache(key: tuple):
        cached_pods = _namespaced_pods_cache[key]
        result = filter_pods_by_prefix(pods=cached_pods, prefix=prefix)
        if as_dict:
            return generic.sanitize_for_serialization(obj=result)
        return result

    target_pods_key = (namespace, label_selector)
    if target_pods_key in _namespaced_pods_cache:
        return filter_pods_from_cache(target_pods_key)
    try:
        v1 = client.CoreV1Api()
        if namespace:
            pods_list: V1PodList = v1.list_namespaced_pod(namespace, label_selector=label_selector)
        else:
            pods_list: V1PodList = v1.list_pod_for_all_namespaces(label_selector=label_selector)
        _namespaced_pods_cache[target_pods_key] = pods_list.items
    except ApiException as ae:
        logger.debug(str(ae))
    else:
        return filter_pods_from_cache(target_pods_key)


_custom_object_cache: dict = {}


def get_custom_objects(
    group: str, version: str, plural: str, namespace: Optional[str] = None, use_cache: bool = True
) -> Union[List[dict], None]:
    target_resource_key = (group, version, plural, namespace)
    if use_cache:
        if target_resource_key in _custom_object_cache:
            return _custom_object_cache[target_resource_key]

    try:
        custom_client = client.CustomObjectsApi()
        kwargs = {"group": group, "version": version, "plural": plural}
        if namespace:
            kwargs["namespace"] = namespace
            f = custom_client.list_namespaced_custom_object
        else:
            f = custom_client.list_cluster_custom_object
        _custom_object_cache[target_resource_key] = f(**kwargs)
    except ApiException as ae:
        logger.debug(str(ae))
    else:
        return _custom_object_cache[target_resource_key]


_cluster_resource_api_cache: dict = {}


def get_cluster_custom_api(group: str, version: str, raise_on_404: bool = False) -> Union[V1APIResourceList, None]:
    target_resource_api_key = (group, version)
    if target_resource_api_key in _cluster_resource_api_cache:
        return _cluster_resource_api_cache[target_resource_api_key]

    try:
        custom_client = client.CustomObjectsApi()
        _cluster_resource_api_cache[target_resource_api_key] = custom_client.get_api_resources(
            group=group, version=version
        )
    except ApiException as ae:
        logger.debug(msg=str(ae))
        if int(ae.status) == 404 and raise_on_404:
            raise ResourceNotFoundError(f"{group}/{version} resource API is not detected on the cluster.")
    else:
        return _cluster_resource_api_cache[target_resource_api_key]


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
def portforward_http(namespace: str, pod_name: str, pod_port: str, **kwargs) -> Iterator[PodRequest]:
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


@contextmanager
def portforward_socket(namespace: str, pod_name: str, pod_port: str) -> Iterator[socket.socket]:
    from kubernetes.stream import portforward

    api = client.CoreV1Api()
    pf = portforward(
        api.connect_get_namespaced_pod_portforward,
        pod_name,
        namespace,
        ports=str(pod_port),
    )

    target_socket: socket.socket = pf.socket(int(pod_port))._socket
    target_socket.settimeout(10.0)
    yield target_socket
    target_socket.shutdown(socket.SHUT_RDWR)
    target_socket.close()


def create_namespaced_secret(
    secret_name: str,
    namespace: str,
    data: Dict[str, str],
    labels: Optional[Dict[str, str]] = None,
    secret_type: K8sSecretType = K8sSecretType.opaque,
    delete_first: bool = False,
):
    if delete_first:
        delete_namespaced_secret(namespace=namespace, secret_name=secret_name)

    data_kw = {}
    if secret_type == K8sSecretType.opaque:
        data_kw = {"string_data": data}
    elif secret_type == K8sSecretType.tls:
        data_kw = {"data": data}
    else:
        raise RuntimeError(f"{secret_type} not supported.")

    v1_secret = client.V1Secret(
        metadata=V1ObjectMeta(name=secret_name, labels=labels), type=secret_type.value, **data_kw
    )

    try:
        v1_api = client.CoreV1Api()
        return v1_api.create_namespaced_secret(namespace=namespace, body=v1_secret)
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        raise RuntimeError(error_msg)


def get_namespaced_secret(namespace: str, secret_name: str) -> dict:
    result = None
    try:
        v1_api = client.CoreV1Api()
        result = v1_api.read_namespaced_secret(namespace=namespace, name=secret_name)
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
    else:
        if result:
            return generic.sanitize_for_serialization(obj=result)


def delete_namespaced_secret(namespace: str, secret_name: str, raise_on_404: bool = False):
    try:
        v1_api = client.CoreV1Api()
        v1_api.delete_namespaced_secret(namespace=namespace, name=secret_name)
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        if int(ae.status) == 404 and not raise_on_404:
            return
        raise RuntimeError(error_msg)


def create_cluster_namespace(namespace: str) -> dict:
    result = None
    try:
        v1_api = client.CoreV1Api()
        result = v1_api.create_namespace(body=client.V1Namespace(metadata=V1ObjectMeta(name=namespace)))
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        raise RuntimeError(error_msg)
    else:
        if result:
            return generic.sanitize_for_serialization(obj=result)


def get_cluster_namespace(namespace: str) -> dict:
    result = None
    try:
        v1_api = client.CoreV1Api()
        result = v1_api.read_namespace(name=namespace)
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
    else:
        if result:
            return generic.sanitize_for_serialization(obj=result)


def create_namespaced_custom_objects(
    group: str, version: str, namespace: str, plural: str, yaml_objects: List[dict], delete_first: bool = False
) -> List[dict]:
    if not yaml_objects:
        yaml_objects = []
    result = []
    try:
        custom_client = client.CustomObjectsApi()
        for data in yaml_objects:
            if delete_first:
                delete_namespaced_custom_object(
                    group=group, version=version, namespace=namespace, plural=plural, name=data["metadata"]["name"]
                )
            result.append(
                custom_client.create_namespaced_custom_object(
                    group=group, version=version, namespace=namespace, plural=plural, body=data
                )
            )
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        raise RuntimeError(error_msg)
    else:
        return result


def delete_namespaced_custom_object(
    group: str, version: str, namespace: str, plural: str, name: str, raise_on_404: bool = False
):
    try:
        custom_client = client.CustomObjectsApi()
        custom_client.delete_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=name,
        )
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        if raise_on_404:
            if int(ae.status) == 404 and not raise_on_404:
                return
            raise RuntimeError(error_msg)


def create_namespaced_configmap(namespace: str, cm_name: str, data: Dict[str, str], delete_first: bool = False) -> dict:
    result = None
    try:
        v1_api = client.CoreV1Api()
        if delete_first:
            delete_namespaced_configmap(namespace=namespace, cm_name=cm_name)
        result = v1_api.create_namespaced_config_map(
            namespace=namespace, body=client.V1ConfigMap(data=data, metadata=V1ObjectMeta(name=cm_name))
        )
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        raise RuntimeError(error_msg)
    else:
        if result:
            return generic.sanitize_for_serialization(obj=result)


def delete_namespaced_configmap(namespace: str, cm_name: str, raise_on_404: bool = False) -> dict:
    try:
        v1_api = client.CoreV1Api()
        v1_api.delete_namespaced_config_map(namespace=namespace, name=cm_name)
    except ApiException as ae:
        error_msg = str(ae)
        logger.debug(msg=error_msg)
        if raise_on_404:
            if int(ae.status) == 404 and not raise_on_404:
                return
            raise RuntimeError(error_msg)
