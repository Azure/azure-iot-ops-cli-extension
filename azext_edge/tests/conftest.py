# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
import random
import sys
from typing import NamedTuple

import pytest
import responses

# Seed the global random module so that @pytest.mark.parametrize decorators
# that call random functions (randint, choice, etc.) produce identical test IDs
# across all pytest-xdist worker processes during collection.
random.seed(42)


class MarkerDefinition(NamedTuple):
    """Metadata for a pytest marker"""

    name: str
    description: str
    edge_exclude: bool  # If True, prevents auto-marking test as 'edge'


# Marker definitions with metadata
MARKERS = [
    MarkerDefinition("edge", "mark tests that run against edge / cluster (auto-applied to unmarked tests)", True),
    MarkerDefinition("e2e", "mark end-to-end containerized tests (support bundles, checks)", False),
    MarkerDefinition("rpsaas", "mark tests that are cloud-side", True),
    MarkerDefinition("upgrade", "mark tests that will run az iot ops upgrade", True),
    MarkerDefinition("mgmtactions", "mark tests that exercise az iot ops mgmt-actions end to end", True),
    MarkerDefinition("init_scenario_test", "mark tests that will run az iot ops init", True),
    MarkerDefinition("require_wlif_setup", "mark tests that require workload identity trust setup", True),
    MarkerDefinition("long_running", "mark tests that take a long time to run", False),
    MarkerDefinition("serial", "mark tests that must run serially (not parallelized by xdist)", False),
]


def pytest_configure(config):
    # Register custom markers
    for marker in MARKERS:
        config.addinivalue_line("markers", f"{marker.name}: {marker.description}")


def pytest_collection_modifyitems(items):
    """Auto-mark tests without specific marks as 'edge' tests"""
    # Get marks to be excluded from edge (default) mark
    exclude_marks = {m.name for m in MARKERS if m.edge_exclude}

    for item in items:
        # Get all marks on the test
        existing_marks = {mark.name for mark in item.iter_markers()}

        # Auto-mark as 'edge' if no exclude marks exist
        if not existing_marks.intersection(exclude_marks):
            item.add_marker(pytest.mark.edge)


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
    type(patched()).refresh_on = PropertyMock(return_value=sys.maxsize)
    yield patched


@pytest.fixture
def mocked_azcli_profile_get_raw_token(mocker):
    patched = mocker.patch(
        "azure.cli.core._profile.Profile.get_raw_token",
        autospec=True,
    )
    patched.return_value = (("Bearer", "token", None), None, None)
    yield patched


@pytest.fixture
def mocked_cmd(mocker, mocked_get_subscription_id, mocked_azcli_cred_get_token, mocked_azcli_profile_get_raw_token):
    class Stub:
        pass

    cloud = Stub()
    cloud.name = "AzureCloud"
    cloud.endpoints = Stub()
    cloud.endpoints.resource_manager = "https://management.azure.com/"
    cloud.endpoints.active_directory = "https://login.microsoftonline.com/"
    cloud.endpoints.active_directory_resource_id = "https://management.core.windows.net/"
    cloud.endpoints.microsoft_graph_resource_id = "https://graph.microsoft.com/"
    cloud.suffixes = Stub()
    cloud.suffixes.storage_endpoint = "core.windows.net"
    cloud.suffixes.keyvault_dns = ".vault.azure.net"
    cloud.suffixes.acr_login_server_endpoint = ".azurecr.io"

    az_cli_mock = mocker.patch("azure.cli.core.AzCli", autospec=True, **{"data": {"command": "az"}, "cloud": cloud})
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
    from .helpers import remove_file

    result = []
    yield result
    for file in result:
        remove_file(file)


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def mocked_confirm(mocker):
    mock = mocker.patch(
        "rich.prompt.Confirm",
    )
    mock.ask.return_value = True
    yield mock
