# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from subprocess import CompletedProcess


@pytest.fixture
def mocked_run_host_command(mocker, request):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.host.run_host_command", autospec=True)

    patched.expected_result = request.param["expected_result"]
    if patched.expected_result is not None:
        patched.return_value = CompletedProcess(
            args=None,
            returncode=request.param["returncode"],
            stdout=request.param["stdout"],
            stderr=request.param["stderr"],
        )
    else:
        patched.return_value = None

    yield patched
