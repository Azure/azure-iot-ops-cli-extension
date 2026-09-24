# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Tuple
from unittest.mock import MagicMock

import pytest

from azext_edge.edge.commands_edge import get_versions
from azext_edge.edge.common import GET_VERSIONS_URL


def _setup_mocks(mocker, browser_success: bool = True) -> Tuple[MagicMock, MagicMock, MagicMock]:
    """Helper function to set up common mocks for get_versions tests.

    Args:
        mocker: pytest-mock's mocker fixture
        browser_success: Whether webbrowser.open should return True or False

    Returns:
        Tuple of (mock_webbrowser_open, mock_console, mock_console_class)
    """
    mock_webbrowser_open = mocker.patch("webbrowser.open", return_value=browser_success)
    mock_console = mocker.MagicMock()
    mock_console_class = mocker.patch("rich.console.Console", return_value=mock_console)

    return mock_webbrowser_open, mock_console, mock_console_class


def _assert_common_calls(
    mock_webbrowser_open: MagicMock, mock_console: MagicMock, mock_console_class: MagicMock
) -> None:
    """Helper function to assert common calls that should happen in all scenarios.

    Args:
        mock_webbrowser_open: Mock for webbrowser.open
        mock_console: Mock console instance
        mock_console_class: Mock Console class
    """
    # Verify webbrowser.open was called with correct parameters
    mock_webbrowser_open.assert_called_once_with(GET_VERSIONS_URL, new=1)

    # Verify Console was created with stderr=True
    mock_console_class.assert_called_once_with(stderr=True)

    # Verify console.status was used
    mock_console.status.assert_called_once_with("Working...")


@pytest.mark.parametrize(
    "browser_success,should_log_error",
    [
        (True, False),  # Browser opens successfully
        (False, True),  # Browser fails to open
    ],
)
def test_get_versions(mocker, browser_success: bool, should_log_error: bool):
    """Test get_versions with different browser open outcomes.

    Args:
        mocker: pytest-mock's mocker fixture
        browser_success: Whether the browser should open successfully
        should_log_error: Whether an error message should be logged
    """
    # Setup mocks
    mock_webbrowser_open, mock_console, mock_console_class = _setup_mocks(mocker, browser_success)

    # Call the function
    get_versions()

    # Assert common behavior
    _assert_common_calls(mock_webbrowser_open, mock_console, mock_console_class)

    # Assert specific behavior based on browser success
    if should_log_error:
        expected_message = (
            f"Failed to open browser. Please visit {GET_VERSIONS_URL} to "
            "view the Azure IoT Operations version reference."
        )
        mock_console.log.assert_called_once_with(expected_message)
    else:
        mock_console.log.assert_not_called()


def test_get_versions_target_link_constant():
    """Test that the target link constant has the expected value."""
    from azext_edge.edge.common import GET_VERSIONS_URL

    assert GET_VERSIONS_URL == "https://aka.ms/aio-versions"


def test_inline_versions_preserve_legacy_fields_and_actual_train(mocker):
    from azext_edge.constants import AIO_RELEASE, VERSION
    from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
    from azext_edge.edge.providers.orchestration.targets import InitTargets
    from azext_edge.edge.providers.orchestration.template import TEMPLATE_BLUEPRINT_INSTANCE

    browser = mocker.patch("webbrowser.open", side_effect=AssertionError("browser"))
    mocker.patch("azure.cli.core.commands.client_factory.get_subscription_id", side_effect=AssertionError("auth"))
    mocker.patch("azure.cli.core._profile.Profile.get_raw_token", side_effect=AssertionError("auth"))
    mocker.patch("requests.sessions.Session.request", side_effect=AssertionError("network"))
    legacy = InitTargets("", "")
    result = get_versions(inline=True)
    assert result["cliVersion"] == VERSION
    assert result["iotOpsRelease"] == AIO_RELEASE
    assert result["extensions"] == {**legacy.get_extension_versions(), **legacy.get_extension_versions(False)}
    assert result["defaultRuntimeChannel"] == "stable"
    assert set(result["runtimeProfiles"]) == {"stable", "preview"}
    stable = result["runtimeProfiles"]["stable"]
    assert stable["version"] == result["extensions"]["iotOperations"]["version"]
    assert stable["train"] == TEMPLATE_BLUEPRINT_INSTANCE.content["variables"]["TRAINS"]["iotOperations"]
    assert stable["sourceCommit"] == TEMPLATE_BLUEPRINT_INSTANCE.commit_id
    preview = result["runtimeProfiles"]["preview"]
    preview_profile = get_runtime_catalog().for_create(use_preview=True)
    assert preview == {
        "release": preview_profile.release,
        "version": preview_profile.identity.version,
        "train": preview_profile.identity.train,
        "sourceRef": preview_profile.source_ref,
        "sourceCommit": preview_profile.source_commit,
        "opcuaConnectorVersion": preview_profile.opcua_connector_version,
    }
    assert json.loads(json.dumps(result)) == result
    browser.assert_not_called()


@pytest.mark.parametrize("train", [None, "integration"])
def test_inline_reports_both_bundled_profiles_without_relabeling_trains(mocker, train):
    from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, RuntimeProfileCatalog
    from azext_edge.edge.providers.orchestration.targets import InitTargets
    from .test_runtime_profiles_unit import make_profile

    stable = make_profile(RuntimeChannel.STABLE, "1.5.7", train, opcua_connector_version="test-stable-tag")
    preview = make_profile(RuntimeChannel.PREVIEW, "1.6.0-preview.4", train,
                           opcua_connector_version="test-preview-tag")
    catalog = RuntimeProfileCatalog([preview, stable])
    mocker.patch("azext_edge.edge.providers.orchestration.runtime_catalog.get_runtime_catalog", return_value=catalog)
    mocker.patch("requests.sessions.Session.request", side_effect=AssertionError("network"))
    result = get_versions(inline=True)
    assert result["extensions"]["iotOperations"] == {"version": "1.5.7", "train": train or "stable"}
    shared = InitTargets("", "").get_extension_versions()
    assert all(result["extensions"][name] == value for name, value in shared.items())
    assert list(result["runtimeProfiles"]) == ["stable", "preview"]
    for profile in (stable, preview):
        assert result["runtimeProfiles"][profile.channel.value] == {
            "release": profile.release,
            "version": profile.identity.version,
            "train": train or profile.channel.value,
            "sourceRef": "test-ref",
            "sourceCommit": "test-commit",
            "opcuaConnectorVersion": profile.opcua_connector_version,
        }
    result["runtimeProfiles"]["preview"]["train"] = "changed"
    assert catalog.describe_profiles()["preview"]["train"] == (train or "preview")


def test_browser_versions_does_not_construct_runtime_catalog(mocker):
    _setup_mocks(mocker)
    mocker.patch("azext_edge.edge.providers.orchestration.runtime_catalog.get_runtime_catalog",
                 side_effect=AssertionError("runtime catalog"))
    get_versions()
