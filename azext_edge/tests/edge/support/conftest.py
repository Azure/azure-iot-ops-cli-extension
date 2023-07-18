# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import List
from ...generators import generate_generic_id

import pytest


@pytest.fixture
def mocked_client(mocker, mocked_client):
    patched = mocker.patch("azext_edge.edge.providers.support.base.client", autospec=True)
    yield patched


@pytest.fixture
def mocked_os_makedirs(mocker):
    patched = mocker.patch("azext_edge.edge.providers.support.base.makedirs", autospec=True)
    yield patched


@pytest.fixture
def mocked_zipfile(mocker):
    patched = mocker.patch("azext_edge.edge.providers.support_bundle.ZipFile", autospec=True)
    yield patched


# TODO - @digimaun make this more useful / flexible configuration.
@pytest.fixture
def mocked_list_pods(mocked_client):
    from kubernetes.client.models import V1PodList, V1Pod, V1PodSpec, V1ObjectMeta, V1Container

    result = {}
    pod_names = [generate_generic_id(), generate_generic_id()]
    pods = []
    for n in pod_names:
        container_name = generate_generic_id()
        namespace_name = generate_generic_id()
        spec = V1PodSpec(containers=[V1Container(name=container_name)])
        pod = V1Pod(metadata=V1ObjectMeta(namespace=namespace_name, name=n), spec=spec)
        pods.append(pod)
        result[namespace_name] = {n: {container_name: {}}}

    pods_list = V1PodList(items=pods)
    mocked_client.CoreV1Api().list_pod_for_all_namespaces.return_value = pods_list

    yield result


@pytest.fixture(scope="function")
def mocked_cluster_resources(request, mocker):
    from azure.cli.core.azclierror import ResourceNotFoundError
    from kubernetes.client.models import V1APIResource, V1APIResourceList

    from ....edge.common import EdgeResourceApi, E4K_API_V1A2, OPCUA_API_V1

    requested_resource_apis = getattr(request, "param", {})
    resource_map = {}

    def _get_api_resource(kind: str):
        return V1APIResource(name=f"{kind.lower()}s", kind=kind, namespaced=True, singular_name=kind.lower(), verbs=[])

    for resource_api in requested_resource_apis:
        r: EdgeResourceApi = resource_api
        v1_resources: List[V1APIResource] = []

        if r == E4K_API_V1A2:
            v1_resources.append(_get_api_resource("Broker"))
            v1_resources.append(_get_api_resource("BrokerListener"))
            v1_resources.append(_get_api_resource("BrokerDiagnostic"))
            v1_resources.append(_get_api_resource("DiagnosticService"))
            v1_resources.append(_get_api_resource("BrokerAuthentication"))
            v1_resources.append(_get_api_resource("BrokerAuthorization"))
            v1_resources.append(_get_api_resource("MqttBridgeTopicMap"))
            v1_resources.append(_get_api_resource("MqttBridgeConnector"))

        if r == OPCUA_API_V1:
            v1_resources.append(_get_api_resource("Application"))
            v1_resources.append(_get_api_resource("ModuleType"))
            v1_resources.append(_get_api_resource("Module"))
            v1_resources.append(_get_api_resource("AssetType"))
            v1_resources.append(_get_api_resource("Asset"))

        resource_map[r] = V1APIResourceList(resources=v1_resources, group_version=r.version)

    def _handle_resource_call(*args, **kwargs):
        resource_map = kwargs["context"]
        if kwargs["resource_api"] in resource_map:
            return resource_map[kwargs["resource_api"]]

        if "raise_on_404" in kwargs and kwargs["raise_on_404"]:
            raise ResourceNotFoundError(f"{kwargs['resource_api'].as_str()} resources do not exist on the cluster.")

    patched = mocker.patch("azext_edge.edge.providers.support_bundle.get_cluster_custom_api", autospec=True)
    _handle_call = partial(_handle_resource_call, context=resource_map)
    patched.side_effect = _handle_call

    yield {"param": requested_resource_apis, "mock": patched, "resources": resource_map}
