# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest


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
    # deployments
    deploy_what_if = mocker.Mock()
    deploy_what_if.as_dict.return_value = request_results.get("deployments.begin_what_if")
    resource_mgmt_client.deployments.begin_what_if.return_value = deploy_what_if
    deploy_begin_create = mocker.Mock()
    deploy_begin_create.as_dict.return_value = request_results.get("deployments.begin_create_or_update")
    resource_mgmt_client.deployments.begin_create_or_update.return_value = deploy_begin_create

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

    client_path = request_results.get("client_path", "azext_edge.edge.util.az_client")
    patched = mocker.patch(f"{client_path}.get_resource_client", autospec=True)
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
