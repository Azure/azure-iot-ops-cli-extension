# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from datetime import datetime
from pathlib import Path
from shlex import split
from unittest.mock import Mock
from requests.models import Response

import pytest
from azure.cli.core import get_default_cli
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.util.version_check import (
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

    check_latest(cli_ctx=cli_ctx)

    spy_check_conn: Mock = spy_version_check_helpers["check_connectivity"]
    spy_get_latest: Mock = spy_version_check_helpers["get_latest_from_github"]

    spy_check_conn.assert_called_once()
    spy_get_latest.assert_called_once()

    assert spy_check_conn.call_args.kwargs["url"] == GH_CLI_CONSTANTS_ENDPOINT
    assert spy_check_conn.call_args.kwargs["max_retries"] == 0

    assert spy_get_latest.call_args.kwargs["url"] == GH_CLI_CONSTANTS_ENDPOINT
    assert spy_get_latest.call_args.kwargs["timeout"] == 10

    last_fetched_inital = get_version_config_datetime()

    # Ensure subsequent check_latest call does not refresh config
    spy_check_conn.reset_mock()
    spy_get_latest.reset_mock()
    check_latest(cli_ctx=cli_ctx)

    spy_check_conn.assert_not_called()
    spy_get_latest.assert_not_called()

    last_fetched_next = get_version_config_datetime()
    assert last_fetched_inital == last_fetched_next

    # Force refresh before 24h window
    check_latest(cli_ctx=cli_ctx, force_refresh=True)
    spy_check_conn.assert_called_once()
    spy_get_latest.assert_called_once()

    last_fetched_refreshed = get_version_config_datetime()
    assert last_fetched_refreshed > last_fetched_inital

    # When using the relevant option, ensure exception is thrown if upgrade available
    mock_requests_get = mocker.patch("azext_edge.edge.util.version_check.requests.get")
    mock_response = Response()
    mock_response.status_code = 200
    mock_response.raw = MockResponseRaw(b'VERSION = "999.999.999"')
    mock_requests_get.return_value = mock_response

    with pytest.raises(
        ValidationError, match="Update available. Install with 'az extension --upgrade --name azure-iot-ops'."
    ):
        check_latest(cli_ctx=cli_ctx, force_refresh=True, throw_if_upgrade=True)

    # When check_latest is disabled via config, ensure no fetching takes place.
    spy_check_conn.reset_mock()
    spy_get_latest.reset_mock()
    config_set_result = cli_ctx.invoke(args=split("config set iotops.check_latest=false"))
    assert config_set_result == 0

    check_latest(cli_ctx=cli_ctx)
    spy_check_conn.assert_not_called()
    spy_get_latest.assert_not_called()


# TODO: Test command init


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
    }

    yield spies


@pytest.fixture
def reset_state():
    reset_version_config()
    yield
    cli_ctx.invoke(args=split("config unset iotops.check_latest"))
