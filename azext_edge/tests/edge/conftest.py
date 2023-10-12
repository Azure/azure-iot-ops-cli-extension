# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

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
def mocked_get_subscription_id(mocker):
    from ..generators import get_zeroed_subscription

    patched = mocker.patch("azure.cli.core.commands.client_factory.get_subscription_id", autospec=True)
    patched.return_value = get_zeroed_subscription()
    yield patched


@pytest.fixture
def mocked_send_raw_request(request, mocker):
    request_result = mocker.Mock()
    raw_request_result = getattr(request, "param", {})
    request_result.content = raw_request_result
    request_result.json.return_value = {"value": raw_request_result}
    patched = mocker.patch("azure.cli.core.util.send_raw_request", autospec=True)
    patched.return_value = request_result
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

    # Create
    poller = mocker.Mock()
    poller.wait.return_value = None
    poller.result.return_value = request_results.get("resources.begin_create_or_update_by_id")

    resource_mgmt_client.resources.begin_create_or_update_by_id.return_value = poller

    patched = mocker.patch("azure.mgmt.resource.ResourceManagementClient", autospec=True)
    patched.return_value = resource_mgmt_client

    yield resource_mgmt_client


@pytest.fixture
def mocked_cmd(mocker, mocked_get_subscription_id):
    az_cli_mock = mocker.patch("azure.cli.core.AzCli", autospec=True)
    config = {"cli_ctx": az_cli_mock}
    patched = mocker.patch("azure.cli.core.commands.AzCliCommand", autospec=True, **config)
    yield patched
