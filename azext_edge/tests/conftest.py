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
def build_query_fixture(mocker, request):
    assert request and request.param
    assert "path" in request.param
    assert "result" in request.param
    patched_build_query = mocker.patch(request.param["path"] + ".build_query")
    patched_build_query.return_value = request.param["result"]

    yield patched_build_query
