# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
import os


# Sets current working directory to the directory of the executing file
@pytest.fixture
def set_cwd(request):
    os.chdir(os.path.dirname(os.path.abspath(str(request.fspath))))


@pytest.fixture
def embedded_cli_client(mocker, request):
    assert request and request.param
    assert "path" in request.param
    assert "as_json_result" in request.param
    patched_cli = mocker.patch(request.param["path"] + ".cli")
    # invoke raises the error
    # as_json returns the value - set 2 since side_effect becomes an iterator
    patched_cli.as_json.side_effect = [request.param["as_json_result"]] * 2

    # error handling to correct type - TODO future error handling
    # patched_handler = mocker.patch(request.param["path"] + "._service_exception")
    # patched_handler.side_effect = CLIError("error")

    yield patched_cli


@pytest.fixture
def mocked_get_subscription_id(mocker):
    from .generators import get_zeroed_subscription

    patched = mocker.patch("azure.cli.core.commands.client_factory.get_subscription_id", autospec=True)
    patched.return_value = get_zeroed_subscription()
    yield patched


@pytest.fixture
def mocked_cmd(mocker, mocked_get_subscription_id):
    az_cli_mock = mocker.patch("azure.cli.core.AzCli", autospec=True)
    config = {"cli_ctx": az_cli_mock}
    patched = mocker.patch("azure.cli.core.commands.AzCliCommand", autospec=True, **config)
    yield patched


@pytest.fixture
def mocked_send_raw_request(request, mocker):
    request_mock = mocker.Mock()
    raw_request_result = getattr(request, "param", {})
    request_mock.content = True
    if raw_request_result.get("side_effect"):
        request_mock.json.side_effect = raw_request_result["side_effect"]
        request_mock.json.side_effect_values = raw_request_result["side_effect"]
    if raw_request_result.get("return_value"):
        request_mock.json.return_value = raw_request_result["return_value"]
    patched = mocker.patch("azure.cli.core.util.send_raw_request", autospec=True)
    patched.return_value = request_mock
    yield patched
