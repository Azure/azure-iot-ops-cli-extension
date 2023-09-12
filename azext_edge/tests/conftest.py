# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
import os

from azure.cli.core.commands import AzCliCommand
from azure.cli.core.mock import DummyCli


# Sets current working directory to the directory of the executing file
@pytest.fixture
def set_cwd(request):
    os.chdir(os.path.dirname(os.path.abspath(str(request.fspath))))


# Fixtures for unit tests
@pytest.fixture()
def fixture_cmd(mocker):
    cli = DummyCli()
    cli.loader = mocker.MagicMock()
    cli.loader.cli_ctx = cli
    cli.data['subscription_id'] = "mySub1"

    def test_handler1():
        pass

    return AzCliCommand(cli.loader, "iot-extension command", test_handler1)


@pytest.fixture
def embedded_cli_client(mocker, request):
    assert request and request.param
    assert "path" in request.param
    assert "as_json_result" in request.param
    patched_cli = mocker.patch(request.param["path"])
    # invoke raises the error
    # as_json returns the value - set 2 since side_effect becomes an iterator
    patched_cli.as_json.side_effect = [request.param["as_json_result"]] * 2

    # patched_handler = mocker.patch("azext_iot.devices.commands_group.handle_service_exception")
    # patched_handler.side_effect = CLIError("error")

    yield patched_cli

