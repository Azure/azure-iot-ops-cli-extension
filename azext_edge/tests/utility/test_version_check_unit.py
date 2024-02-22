# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from datetime import datetime
from pathlib import Path
from shlex import split
from typing import Union
from unittest.mock import Mock

import pytest
from azure.cli.core import get_default_cli
from azure.cli.core.azclierror import ValidationError
from requests.exceptions import ConnectionError, RequestException, Timeout
from requests.models import Response

from azext_edge.edge.util.version_check import (
    CURRENT_CLI_VERSION,
    FORMAT_VERSION_V1_VALUE,
    GH_CLI_CONSTANTS_ENDPOINT,
    SESSION_FILE_NAME,
    SESSION_KEY_FORMAT_VERSION,
    SESSION_KEY_LAST_FETCHED,
)

cli_ctx = get_default_cli()


def get_version_config_path() -> Path:
    base_path = Path(cli_ctx.config.config_dir)
    return base_path.joinpath(SESSION_FILE_NAME)


def get_version_config() -> dict:
    config_path = get_version_config_path()
    assert config_path.exists()
    config_content = config_path.read_text(encoding="utf8")
    config_content = json.loads(config_content)
    assert config_content[SESSION_KEY_FORMAT_VERSION] == FORMAT_VERSION_V1_VALUE
    assert config_content[SESSION_KEY_LAST_FETCHED]

    return config_content


def get_version_config_datetime() -> datetime:
    config_content = get_version_config()

    return datetime.strptime(config_content["lastFetched"], "%Y-%m-%d %H:%M:%S.%f")


def reset_version_config():
    config_path = get_version_config_path()
    config_path.unlink(missing_ok=True)


def test_check_latest_flow(mocker, spy_version_check_helpers, reset_state):
    from azext_edge.edge.util.version_check import check_latest

    spy_check_conn: Mock = spy_version_check_helpers["check_connectivity"]
    spy_get_latest: Mock = spy_version_check_helpers["get_latest_from_github"]
    spy_logger: Mock = spy_version_check_helpers["logger"]
    spy_console: Mock = spy_version_check_helpers["console"]

    patch_requests_session(mocker)
    patch_requests_get(mocker, CURRENT_CLI_VERSION)
    check_latest(cli_ctx=cli_ctx)

    spy_check_conn.assert_called_once()
    spy_get_latest.assert_called_once()

    assert spy_check_conn.call_args.kwargs["url"] == GH_CLI_CONSTANTS_ENDPOINT
    assert spy_check_conn.call_args.kwargs["max_retries"] == 0

    assert spy_get_latest.call_args.kwargs["url"] == GH_CLI_CONSTANTS_ENDPOINT
    assert spy_get_latest.call_args.kwargs["timeout"] == 10

    # console is used to indicate update availability
    spy_console.print.assert_not_called()
    last_fetched_inital = get_version_config_datetime()

    # Ensure subsequent check_latest call does not refresh config
    spy_check_conn.reset_mock()
    spy_get_latest.reset_mock()
    spy_console.reset_mock()

    check_latest(cli_ctx=cli_ctx)

    spy_check_conn.assert_not_called()
    spy_get_latest.assert_not_called()
    spy_console.print.assert_not_called()

    last_fetched_next = get_version_config_datetime()
    assert last_fetched_inital == last_fetched_next

    # Force refresh before 24h window and use older fetched semver
    patch_requests_get(mocker, "0.1.0b1")
    check_latest(cli_ctx=cli_ctx, force_refresh=True)
    spy_check_conn.assert_called_once()
    spy_get_latest.assert_called_once()
    spy_console.print.assert_not_called()

    last_fetched_refreshed = get_version_config_datetime()
    assert last_fetched_refreshed > last_fetched_inital

    # If upgrade is available, user is notified
    spy_check_conn.reset_mock()
    spy_get_latest.reset_mock()
    patch_requests_get(mocker, "999.999.999")
    expected_base_text = "Update available. Install with 'az extension --upgrade --name azure-iot-ops'."
    expected_decorated_text = (
        ":dim_button: [italic][yellow]Update available[/yellow]. "
        "Install with '[green]az extension --upgrade --name azure-iot-ops[/green]'."
    )
    reset_version_config()
    check_latest(cli_ctx=cli_ctx)
    spy_check_conn.assert_called_once()
    spy_get_latest.assert_called_once()
    spy_console.print.assert_called_once()
    spy_console.print.call_args.args[0] == expected_decorated_text

    # When using the relevant option, ensure exception is thrown if upgrade available
    with pytest.raises(ValidationError, match=expected_base_text):
        check_latest(cli_ctx=cli_ctx, force_refresh=True, throw_if_upgrade=True)
    assert spy_logger.debug.call_args.args[0] == expected_base_text

    # When check_latest is disabled via config, ensure no fetching takes place.
    spy_check_conn.reset_mock()
    spy_get_latest.reset_mock()
    spy_logger.reset_mock()
    spy_console.reset_mock()

    reset_version_config()
    config_set_result = cli_ctx.invoke(args=split("config set iotops.check_latest=false"))
    assert config_set_result == 0

    check_latest(cli_ctx=cli_ctx)
    spy_check_conn.assert_not_called()
    spy_get_latest.assert_not_called()
    spy_logger.assert_not_called()
    spy_console.assert_not_called()


# TODO: if not --only-show-errors
# TODO: Test command init


def patch_requests_get(mocker, version: str, status_code: int = 200) -> Mock:
    # When using the relevant option, ensure exception is thrown if upgrade available
    mock_requests_get = mocker.patch("azext_edge.edge.util.version_check.requests.get")
    mock_response = Response()
    mock_response.status_code = status_code
    mock_response.raw = MockResponseRaw(f'VERSION = "{version}"'.encode("utf-8"))
    mock_requests_get.return_value = mock_response

    return mock_requests_get


def patch_requests_session(mocker, status_code: Union[int, RequestException] = 200) -> Mock:
    # When using the relevant option, ensure exception is thrown if upgrade available
    mock_requests_session = mocker.patch("azext_edge.edge.util.version_check.requests.Session.head")

    if not isinstance(status_code, int):
        if issubclass(status_code, RequestException):
            mock_requests_session.side_effect = status_code
            return mock_requests_session

    mock_response = Response()
    mock_response.status_code = status_code
    mock_requests_session.return_value = mock_response

    return mock_requests_session


class MockResponseRaw:
    def __init__(self, content: bytes):
        self.read_calls = 0
        self.content = content

    def read(self, chunk_size: int) -> bytes:
        _ = chunk_size
        if not self.read_calls:
            self.read_calls += 1
            return self.content
        return b""


@pytest.fixture
def spy_version_check_helpers(mocker):
    from azext_edge.edge.util import version_check

    spies = {
        "get_latest_from_github": mocker.spy(version_check, "get_latest_from_github"),
        "check_connectivity": mocker.spy(version_check, "check_connectivity"),
        "logger": mocker.spy(version_check, "logger"),
        "console": mocker.spy(version_check, "console"),
    }

    yield spies


@pytest.fixture
def reset_state():
    reset_version_config()
    yield
    cli_ctx.invoke(args=split("config unset iotops.check_latest"))


def test_version_check_handler(mocker):
    from argparse import Namespace

    from azext_edge import version_check_handler

    mocked_check_latest: Mock = mocker.patch("azext_edge.edge.util.version_check.check_latest")

    kwargs = {"command": "iot ops check", "args": Namespace(ensure_latest=True)}

    cli_ctx = Namespace(cli_ctx="cli_ctx")
    version_check_handler(cli_ctx, **kwargs)
    assert mocked_check_latest.call_args.args[0] == cli_ctx

    mocked_check_latest.reset_mock()
    kwargs["command"] = "iot ops init"
    version_check_handler(cli_ctx, **kwargs)
    assert mocked_check_latest.call_args.kwargs == {
        "cli_ctx": cli_ctx,
        "force_refresh": True,
        "throw_if_upgrade": True,
    }

    mocked_check_latest.reset_mock()
    kwargs["command"] = "iot ops init"
    kwargs["args"] = Namespace(ensure_latest=None)
    version_check_handler(cli_ctx, **kwargs)
    assert mocked_check_latest.call_args.kwargs == {
        "cli_ctx": cli_ctx,
        "force_refresh": None,
        "throw_if_upgrade": None,
    }

    mocked_check_latest.reset_mock()
    kwargs["command"] = "storage create"
    version_check_handler(cli_ctx, **kwargs)
    mocked_check_latest.assert_not_called()


@pytest.mark.parametrize("status_code", [401, 404, 500, ConnectionError, Timeout])
def test_non_success_on_get(mocker, status_code, spy_version_check_helpers, reset_state):
    from azext_edge.edge.util.version_check import check_latest

    spy_check_conn: Mock = spy_version_check_helpers["check_connectivity"]
    spy_get_latest: Mock = spy_version_check_helpers["get_latest_from_github"]
    spy_logger: Mock = spy_version_check_helpers["logger"]
    spy_console: Mock = spy_version_check_helpers["console"]

    patch_requests_session(mocker, status_code=status_code)
    patch_requests_get(mocker, CURRENT_CLI_VERSION, status_code=status_code)

    check_latest(cli_ctx=cli_ctx)

    spy_check_conn.assert_called_once()
    spy_console.assert_not_called()

    if not isinstance(status_code, int):
        if issubclass(status_code, RequestException):
            spy_get_latest.assert_not_called()
            spy_logger.info.assert_called_with("Connectivity problem detected.")
            assert spy_logger.debug.call_count > 0

            return

    spy_get_latest.assert_called_once()

    assert spy_logger.debug.call_args.args == (
        "Failed to fetch the latest version from '%s' with status code '%s' and reason '%s'",
        GH_CLI_CONSTANTS_ENDPOINT,
        status_code,
        None,
    )
