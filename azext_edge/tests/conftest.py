# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import os
import sys
import responses


# Sets current working directory to the directory of the executing file
@pytest.fixture
def set_cwd(request):
    os.chdir(os.path.dirname(os.path.abspath(str(request.fspath))))


@pytest.fixture
def mocked_get_subscription_id(mocker):
    from .generators import get_zeroed_subscription

    patched = mocker.patch("azure.cli.core.commands.client_factory.get_subscription_id", autospec=True)
    patched.return_value = get_zeroed_subscription()
    yield patched


@pytest.fixture
def mocked_azcli_cred_get_token(mocker):
    from unittest.mock import PropertyMock
    patched = mocker.patch(
        "azure.identity._credentials.azure_cli.AzureCliCredential.get_token",
    )
    type(patched()).expires_on = PropertyMock(return_value=sys.maxsize)
    yield patched


@pytest.fixture
def mocked_cmd(mocker, mocked_get_subscription_id, mocked_azcli_cred_get_token):
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


# Int test fixtures
@pytest.fixture(scope="module")
def tracked_files():
    from .helpers import remove_file_or_folder

    result = []
    yield result
    for file in result:
        remove_file_or_folder(file)


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps
