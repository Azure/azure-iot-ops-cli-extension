# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from azure.cli.core.azclierror import ValidationError

import pytest
from azure.cli.core import get_default_cli

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


def test_check_latest_flow(mocker, spy_version_check_helpers):
    reset_version_config()
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
    mock_get_latest = mocker.patch("azext_edge.edge.util.version_check.get_latest_from_github")
    mock_get_latest.return_value = "999.999.999"
    with pytest.raises(
        ValidationError, match="Update available. Install with 'az extension --upgrade --name azure-iot-ops'."
    ):
        check_latest(cli_ctx=cli_ctx, force_refresh=True, throw_if_upgrade=True)


# Test command init


@pytest.fixture
def spy_version_check_helpers(mocker):
    from azext_edge.edge.util import version_check

    spies = {
        "get_latest_from_github": mocker.spy(version_check, "get_latest_from_github"),
        "check_connectivity": mocker.spy(version_check, "check_connectivity"),
    }

    yield spies
