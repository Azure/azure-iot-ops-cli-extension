# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from pathlib import Path

import pytest

from ...generators import generate_random_string

MOCK_BROKER_CONFIG_PATH = Path(__file__).parent.joinpath("./broker_config.json")


# Not used
@pytest.fixture
def mocked_verify_write_permission_against_rg(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.permissions.verify_write_permission_against_rg", autospec=True
    )
    yield patched


@pytest.fixture
def mocked_permission_manager(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.PermissionManager", autospec=True)
    yield patched


@pytest.fixture
def mocked_verify_custom_locations_enabled(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.base.verify_custom_locations_enabled", autospec=True
    )
    yield patched


##


@pytest.fixture
def mocked_resource_graph(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.connected_cluster.ResourceGraph", autospec=True)
    yield patched


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.get_resource_client", autospec=True)
    yield patched


@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.wait_for_terminal_state", autospec=True)
    yield patched


@pytest.fixture
def mocked_register_providers(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.rp_namespace.register_providers", autospec=True)
    yield patched


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.IoTOperationsResourceMap")
    yield patched


@pytest.fixture(scope="module")
def mock_broker_config():
    custom_config = {generate_random_string(): generate_random_string()}
    MOCK_BROKER_CONFIG_PATH.write_text(json.dumps(custom_config), encoding="utf-8")
    yield custom_config
    MOCK_BROKER_CONFIG_PATH.unlink()


@pytest.fixture
def mocked_sleep(mocker):
    patched = {
        "az_client.sleep": mocker.patch("azext_edge.edge.util.az_client.sleep", autospec=True),
        "work.sleep": mocker.patch("azext_edge.edge.providers.orchestration.work.sleep", autospec=True)
    }
    yield patched


@pytest.fixture
def spy_work_displays(mocker):
    from azext_edge.edge.providers.orchestration.work import WorkManager

    yield {
        "render_display": mocker.spy(WorkManager, "_render_display"),
        "complete_step": mocker.spy(WorkManager, "_complete_step"),
    }


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.work.logger", autospec=True)
    yield patched
