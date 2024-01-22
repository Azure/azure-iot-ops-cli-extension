# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.providers.orchestration.host import is_package_installed


@pytest.mark.parametrize(
    "mocked_run_host_command",
    [{"returncode": 0, "stdout": b"install ok installed", "stderr": b"", "expected_result": True}],
    indirect=True,
)
def test_is_package_installed(mocked_run_host_command):
    pkg_name = "nfs-common"
    package_installed = is_package_installed(pkg_name)
    assert package_installed == mocked_run_host_command.expected_result
    call_arg = mocked_run_host_command.call_args.args[0]
    assert call_arg == f"dpkg-query --show -f='${{Status}}' {pkg_name}"
