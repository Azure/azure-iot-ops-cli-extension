# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.arguments import CaseInsensitiveList
from knack.log import get_logger
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    AkriResourceKinds,
    DataProcessorResourceKinds,
    LnmResourceKinds,
    MqResourceKinds,
    OpcuaResourceKinds,
)

logger = get_logger(__name__)

@pytest.fixture(scope="session")
def command_runner():
    from ...helpers import CommandRunner
    runner = CommandRunner()
    yield runner
    runner.close_stdin()



@pytest.fixture(scope="session")
def settings():
    from ...settings import DynamoSettings
    try:
        yield DynamoSettings()
    except RuntimeError:
        pytest.skip("Test requires resource group.")


@pytest.fixture(scope="session")
def tracked_resources(command_runner):
    resources = []
    yield resources
    for res in resources:
        command = f"az resource delete --ids {res['id']}"
        if res.get("api_version"):
            command += f" --api-version {res['api_version']}"
        try:
            command_runner.run(command)
        except CLIInternalError:
            logger.warning(f"failed to delete {res['id']}")


@pytest.fixture(scope="session")
def tracked_keyvault(request, command_runner, tracked_resources, settings):
    from ...settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.kv.value)
    if settings.env.azext_edge_kv:
        kv = command_runner.run(f"az keyvault show -n {settings.env.azext_edge_kv} -g {settings.env.azext_edge_testrg}")
    else:
        run_id = request.node.callspec.id
        kv_name = f"opstestkv-{run_id}"
        kv = command_runner.run(f"az keyvault create -n {kv_name} -g {settings.env.azext_edge_testrg}")
        tracked_resources.append(kv)
    yield kv


@pytest.fixture(scope="session")
def init_setup(request, tracked_resources, command_runner, tracked_keyvault, settings):
    from ...settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.cluster.value)
    settings.add_to_config(EnvironmentVariables.skip_init.value)
    # try:
    #     command_runner.run("kubectl api-resources")
    # except CLIInternalError:
    #     raise CLIInternalError("Failed to access cluster. Required for testing.")
    if settings.env.azext_edge_skip_init:
        yield {
            "clusterName": settings.env.azext_edge_cluster,
            "resourceGroup": settings.env.azext_edge_testrg
        }
        return

    scenario = {}
    if request and hasattr(request, "param"):
        scenario = request.param

    run_id = request.node.callspec.id
    cluster_name = settings.env.azext_edge_cluster or f"az-iot-ops-test-cluster-{run_id}"

    command = f"az iot ops init --cluster {cluster_name} -g {settings.env.azext_edge_testrg} --kv-id {tracked_keyvault['id']} --no-progress"
    for arg in scenario:
        command += f" {arg} {scenario[arg]}"

    result = command_runner.run(command)
    assert result["clusterName"] == cluster_name
    assert result["clusterNamespace"] == scenario.get()
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

    cresources = result["resources"]

    assert result["tls"]["aioTrustConfigMap"] == "aio-ca-trust-bundle-test-only"
    assert result["tls"]["aioTrustSecretName"] == "aio-ca-key-pair-test-only"

    command_runner.run("az iot ops verify-host -y")

    yield result


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("services_map", [
    ("akri", AkriResourceKinds.list()),
    ("dataprocessor", DataProcessorResourceKinds.list()),
    ("lnm", LnmResourceKinds.list()),
    ("mq", [
        MqResourceKinds.BROKER.value,
        MqResourceKinds.BROKER_LISTENER.value,
        MqResourceKinds.DIAGNOSTIC_SERVICE.value,
        MqResourceKinds.KAFKA_CONNECTOR.value,
    ]),
    ("opcua", OpcuaResourceKinds.list())
])
@pytest.mark.parametrize("post", [False, True])
@pytest.mark.parametrize("pre", [False, True])
def test_check(init_setup, command_runner, detail_level, services_map, post, pre):
    ops_service, resources = services_map
    resources = " ".join(resources)
    command = f"az iot ops check --as-object --detail-level {detail_level} --ops-service {ops_service} --post {post} "\
        f"--pre {pre} --resources {resources}"
    result = command_runner.run(command)

    expected_title = "Evaluation for {[bright_blue]" + ops_service + "[/bright_blue]} service deployment"
    assert result["title"] == expected_title

    if not post and not pre:
        post = pre = True

    assert bool(result.get("postDeployment")) == post
    assert bool(result.get("preDeployment")) == pre

    # TODO: see how specific to get - for now keep it simple


# @pytest.mark.parametrize("bundle_dir", [None, "support_bundles"])
# @pytest.mark.parametrize("services_map", [
#     ("akri", AkriResourceKinds.list()),
#     ("dataprocessor", DataProcessorResourceKinds.list()),
#     ("lnm", LnmResourceKinds.list()),
#     ("mq", MqResourceKinds.list()),
#     ("opcua", OpcuaResourceKinds.list())
# ])
# @pytest.mark.parametrize("mq_traces", [False, True])
# def test_create_bundle(init_setup, bundle_dir, mq_traces, ops_service, tracked_files):

#     command = f"az iot ops support create-bundle --mq-traces {mq_traces} --ops-service {ops_service}"
#     if bundle_dir:
#         command += f" --bundle-dir {bundle_dir}"
#         command_runner.run(f"mkdir {bundle_dir}")
#     result = command_runner.run(command)
#     assert result["bundlePath"]
#     tracked_files.append(result["bundlePath"])

#     if bundle_dir:
#         command_runner.run(f"rm -r {bundle_dir}")
