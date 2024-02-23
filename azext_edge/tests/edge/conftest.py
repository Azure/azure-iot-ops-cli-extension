# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
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
    try:
        yield DynamoSettings()
    except RuntimeError:
        pytest.skip("Test requires resource group.")


@pytest.fixture(scope="session")
def tracked_resources() -> List[str]:
    resources = []
    yield resources
    for res in resources:
        try:
            run(f"az resource delete --id {res} -v")
        except CLIInternalError:
            logger.warning(f"failed to delete {res}")


@pytest.fixture(scope="session")
def tracked_keyvault(request, tracked_resources, settings):
    from ..settings import EnvironmentVariables, convert_flag
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.skip_init.value, conversion=convert_flag)
    if settings.env.azext_edge_skip_init:
        # kv only needed for init for now
        kv = None
    elif settings.env.azext_edge_kv:
        kv = run(f"az keyvault show -n {settings.env.azext_edge_kv} -g {settings.env.azext_edge_testrg}")
    else:
        run_id = id(request)
        kv_name = f"opstestkv-{run_id}"
        kv = run(f"az keyvault create -n {kv_name} -g {settings.env.azext_edge_testrg}")
        tracked_resources.append(kv["id"])
    yield kv


@pytest.fixture()
def init_setup(request, tracked_resources, tracked_keyvault, settings):
    from ..settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.cluster.value)
    try:
        run("kubectl api-resources")
    except CLIInternalError:
        raise CLIInternalError("Failed to access cluster. Required for testing.")
    if settings.env.azext_edge_skip_init:
        if not settings.env.azext_edge_cluster:
            raise CLIInternalError("Cluster name required if not running init.")
        yield {
            "clusterName": settings.env.azext_edge_cluster,
            "resourceGroup": settings.env.azext_edge_testrg
        }
        return

    scenario = {}
    if request and hasattr(request, "param"):
        scenario = request.param

    run_id = id(request)
    cluster_name = settings.env.azext_edge_cluster or f"az-iot-ops-test-cluster-{run_id}"
    try:
        run(f"az connectedk8s connect --name {cluster_name} -g {settings.env.azext_edge_testrg}")
    except CLIInternalError:
        raise CLIInternalError("Failed to connect cluster. Required for testing.")
    custom_locations_guid = run("az ad sp show --id bc313c14-388c-4e7d-a58e-70017303ee3b --query id -o tsv")
    run(
        f"az connectedk8s enable-features --name {cluster_name} -g {settings.env.azext_edge_testrg}"
        f" --features custom-locations cluster-connect --custom-locations-oid {custom_locations_guid}"
    )
    result = run(f"az connectedk8s show --name {cluster_name} -g {settings.env.azext_edge_testrg}")
    tracked_resources.append(result["id"])

    command = f"az iot ops init --cluster {cluster_name} -g {settings.env.azext_edge_testrg} "\
        f"--kv-id {tracked_keyvault['id']} --no-progress"
    for arg in scenario:
        command += f" {arg} {scenario[arg]}"
    # import pdb; pdb.set_trace()

    result = run(command)
    # reverse the list so things can be deleted in the right order
    tracked_resources.extend(result["resources"][::-1])
    assert result["clusterName"] == cluster_name
    assert result["clusterNamespace"] == scenario.get("--cluster-namespace", "azure-iot-operations")
    assert result["deploymentLink"]
    assert result["deploymentName"]

    dstate = result["deploymentState"]
    assert dstate["correlationId"]
    assert dstate["opsVersion"]["adr"] == "0.1.0-preview"
    assert dstate["opsVersion"]["aio"] == "0.3.0-preview"
    assert dstate["opsVersion"]["akri"] == "0.1.0-preview"
    assert dstate["opsVersion"]["layeredNetworking"] == "0.1.0-preview"
    assert dstate["opsVersion"]["mq"] == "0.2.0-preview"
    assert dstate["opsVersion"]["observability"] == "0.1.0-preview"
    assert dstate["opsVersion"]["opcUaBroker"] == "0.2.0-preview"
    assert dstate["opsVersion"]["processor"] == "0.1.2-preview"

    assert result["tls"]["aioTrustConfigMap"] == "aio-ca-trust-bundle-test-only"
    assert result["tls"]["aioTrustSecretName"] == "aio-ca-key-pair-test-only"

    # just incase
    run("az iot ops verify-host -y")
    yield result
