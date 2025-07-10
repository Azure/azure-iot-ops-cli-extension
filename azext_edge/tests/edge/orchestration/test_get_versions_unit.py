# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

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
