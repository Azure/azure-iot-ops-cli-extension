# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azure.cli.core.azclierror import CLIInternalError
from ..helpers import run

logger = get_logger(__name__)


#  Unit testing
@pytest.fixture
def mocked_client(mocker):
    patched = mocker.patch("azext_edge.edge.providers.base.client", autospec=True)
    yield patched


@pytest.fixture
def mocked_config(request, mocker):
    patched = mocker.patch("azext_edge.edge.providers.base.config", autospec=True)
    current_context = getattr(request, "param", {})
    patched.list_kube_config_contexts.return_value = ([], current_context)
    yield {"param": current_context, "mock": patched}


@pytest.fixture
def mocked_urlopen(mocker):
    patched = mocker.patch("azext_edge.edge.providers.base.urlopen", autospec=True)
    yield patched


@pytest.fixture
def mocked_resource_management_client(request, mocker):
    import json

    request_results = getattr(request, "param", {})
    resource_mgmt_client = mocker.Mock()
    # Resource group
    rg_get = mocker.Mock()
    rg_get.as_dict.return_value = request_results.get("resource_groups.get")
    resource_mgmt_client.resource_groups.get.return_value = rg_get

    # Resources
    # Delete
    resource_mgmt_client.resources.begin_delete.return_value = None

    # Get + lazy way of ensuring original is present and result is a copy
    resource_get = mocker.Mock()
    get_result = request_results.get("resources.get")
    resource_get.original = get_result
    resource_get.as_dict.return_value = json.loads(json.dumps(get_result))
    resource_mgmt_client.resources.get.return_value = resource_get

    # Get by id + lazy way of ensuring original is present and result is a copy
    resource_get = mocker.Mock()
    get_result = request_results.get("resources.get_by_id")
    resource_get.original = get_result
    resource_get.as_dict.return_value = json.loads(json.dumps(get_result))
    resource_mgmt_client.resources.get_by_id.return_value = resource_get

    # Create
    poller = mocker.Mock()
    poller.wait.return_value = None
    poller.result.return_value = request_results.get("resources.begin_create_or_update_by_id")

    resource_mgmt_client.resources.begin_create_or_update_by_id.return_value = poller

    patched = mocker.patch("azext_edge.edge.util.az_client.get_resource_client", autospec=True)
    patched.return_value = resource_mgmt_client

    yield resource_mgmt_client


@pytest.fixture
def mocked_build_query(mocker, request):
    request_params = getattr(request, "param", {
        "path": "azext_edge.edge.util.common.client",
        "return_value": []
    })
    build_query_mock = mocker.patch(f"{request_params['path']}.build_query", autospec=True)
    if request_params.get("side_effect") is not None:
        build_query_mock.side_effect = request_params["side_effect"]
        # ensure original values are kept
        build_query_mock.side_effect_values = request_params["side_effect"]
    if request_params.get("return_value") is not None:
        build_query_mock.return_value = request_params["return_value"]
    yield build_query_mock


# Int testing
@pytest.fixture(scope="session")
def settings():
    from ..settings import DynamoSettings
    yield DynamoSettings()


@pytest.fixture(scope="session")
def tracked_resources():
    resources = []
    yield resources
    for res in resources:
        try:
            run(f"az resource delete --id {res} -v")
        except CLIInternalError:
            logger.warning(f"failed to delete {res}")


@pytest.fixture(scope="session")
def tracked_keyvault(request, tracked_resources, settings):
    # TODO: clean up env variables later
    from ..settings import convert_flag, EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.skip_init.value, conversion=convert_flag)
    if settings.env.azext_edge_skip_init:
        # kv only needed for init for now
        kv = None
    elif settings.env.azext_edge_kv:
        kv = run(f"az keyvault show -n {settings.env.azext_edge_kv} -g {settings.env.azext_edge_rg}")
    else:
        run_id = id(request.session)
        kv_name = f"opstestkv-{run_id}"
        kv = run(f"az keyvault create -n {kv_name} -g {settings.env.azext_edge_rg}")
        tracked_resources.append(kv["id"])
    yield kv


@pytest.fixture(scope="session")
def cluster_setup(settings):
    from kubernetes.client.rest import ApiException
    from ..settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.context_name.value)
    try:
        from azext_edge.edge.providers.base import load_config_context
        from kubernetes import client
        # Check for kube config file
        load_config_context(context_name=settings.env.azext_edge_context_name)
        # Check for cluster access
        client.VersionApi().get_code()
        yield
    except ApiException:
        raise NotImplementedError("Local cluster creation for testing not fully implemented yet.")
        # import os
        # os.environ["K3D_FIX_MOUNTS"] = "1"
        # run("kubectl cluster create -i ghcr.io/jlian/k3d-nfs:v1.25.3-k3s1")
        # yield
        # run("kubectl cluster delete")


@pytest.fixture()
def init_setup(request, cluster_setup, settings):
    from ..settings import convert_flag, EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.skip_init.value, conversion=convert_flag)
    if settings.env.azext_edge_skip_init:
        run("az iot ops verify-host -y")
        yield {}
        return

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.cluster.value)
    raise NotImplementedError("Connecting the cluster to Azure and init setup not implemented yet.")

    # cluster_resources = []
    # scenario = {}
    # if request and hasattr(request, "param"):
    #     scenario = request.param

    # run_id = id(request.session)
    # cluster_name = settings.env.azext_edge_cluster or f"az-iot-ops-test-cluster-{run_id}"
    # try:
    #     run(f"az connectedk8s connect --name {cluster_name} -g {settings.env.azext_edge_rg}")
    #     custom_locations_guid = run("az ad sp show --id bc313c14-388c-4e7d-a58e-70017303ee3b --query id -o tsv")
    #     run(
    #         f"az connectedk8s enable-features --name {cluster_name} -g {settings.env.azext_edge_rg}"
    #         f" --features custom-locations cluster-connect --custom-locations-oid {custom_locations_guid}"
    #     )
    # except CLIInternalError as e:
    #     logger.warning(e.error_msg)
    # result = run(f"az connectedk8s show --name {cluster_name} -g {settings.env.azext_edge_rg}")
    # resource_id_prefix = result["id"].split("Microsoft.Kubernetes")[0]
    # tracked_resources.append(result["id"])
    # cluster_resources.append(result["id"])

    # command = f"az iot ops init --cluster {cluster_name} -g {settings.env.azext_edge_rg} "\
    #     f"--kv-id {tracked_keyvault['id']} --no-progress --no-preflight"
    # for arg in scenario:
    #     command += f" {arg} {scenario[arg]}"
    # result = run(command)
    # # reverse the list so things can be deleted in the right order
    # converted_resources = []
    # for res in result["deploymentState"]["resources"][::-1]:
    #     if not res.startswith("Microsoft.Kubernetes"):
    #         converted_resources.append(resource_id_prefix + res)
    # tracked_resources.extend(converted_resources)
    # cluster_resources.extend(converted_resources)
    # assert result["clusterName"] == cluster_name
    # assert result["clusterNamespace"] == scenario.get("--cluster-namespace", "azure-iot-operations")
    # assert result["deploymentLink"]
    # assert result["deploymentName"]

    # dstate = result["deploymentState"]
    # assert dstate["correlationId"]
    # assert dstate["opsVersion"]

    # assert result["tls"]["aioTrustConfigMap"] == "aio-ca-trust-bundle-test-only"
    # assert result["tls"]["aioTrustSecretName"] == "aio-ca-key-pair-test-only"

    # # just incase
    # run("az iot ops verify-host -y")
    # yield result

    # for res in cluster_resources:
    #     try:
    #         run(f"az resource delete --id {res} -v")
    #         tracked_resources.remove(res)
    #     except CLIInternalError:
    #         logger.warning(f"failed to delete {res}")
