# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from ..generators import generate_random_string

AZ_CLIENT_PATH = "azext_edge.edge.util.az_client"


@pytest.mark.parametrize("done", [True, False])
def test_wait_for_terminal_state(mocker, done):
    # could be fixture with param
    sleep_patch = mocker.patch(f"{AZ_CLIENT_PATH}.sleep")
    poll_num = 10
    mocker.patch(f"{AZ_CLIENT_PATH}.POLL_RETRIES", poll_num)

    poller = mocker.Mock()
    poller.done.return_value = done
    poller.result.return_value = generate_random_string()

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    result = wait_for_terminal_state(poller)
    assert result == poller.result.return_value
    assert sleep_patch.call_count == (0 if done else poll_num)


def test_get_tenant_id(mocker):
    tenant_id = generate_random_string()
    profile_patch = mocker.patch("azure.cli.core._profile.Profile", autospec=True)
    profile_patch.return_value.get_subscription.return_value = {"tenantId": tenant_id}

    from azext_edge.edge.util.az_client import get_tenant_id

    result = get_tenant_id()
    assert result == tenant_id
    profile_patch.assert_called_once()


@pytest.mark.parametrize(
    "error, expected",
    [
        # Transient network / token-acquisition failures.
        (ConnectionResetError("Connection reset by peer"), True),
        (TimeoutError("timed out"), True),
        (Exception("Failed to establish a new connection"), True),
        (Exception("Temporary failure in name resolution"), True),
        # Non-transient failures must not be retried.
        (Exception("Please run 'az login' to setup account"), False),
        (ValueError("invalid instance name"), False),
    ],
)
def test_is_transient_error_message_markers(error, expected):
    from azext_edge.edge.util.az_client import is_transient_error

    assert is_transient_error(error) is expected


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504, 400, 404])
def test_is_transient_error_http_status_not_retried_here(status_code):
    # HTTP status errors are handled by the azure-core transport retry policy, so
    # this helper must NOT treat them as transient (avoids double-retrying).
    from azure.core.exceptions import HttpResponseError

    from azext_edge.edge.util.az_client import is_transient_error

    error = HttpResponseError(message="service error")
    error.status_code = status_code
    assert is_transient_error(error) is False


def test_is_transient_error_service_request(mocker):
    from azure.core.exceptions import ServiceRequestError, ServiceResponseError

    from azext_edge.edge.util.az_client import is_transient_error

    assert is_transient_error(ServiceRequestError(message="send failed")) is True
    assert is_transient_error(ServiceResponseError(message="no response")) is True


def test_retry_on_transient_error_succeeds_after_retries(mocker):
    sleep_patch = mocker.patch(f"{AZ_CLIENT_PATH}.sleep")
    expected = generate_random_string()

    func = mocker.Mock(
        side_effect=[
            ConnectionResetError("Connection reset by peer"),
            ConnectionResetError("Connection reset by peer"),
            expected,
        ]
    )

    from azext_edge.edge.util.az_client import retry_on_transient_error

    result = retry_on_transient_error(func, max_attempts=3, initial_backoff_sec=1, context="unit test")
    assert result == expected
    assert func.call_count == 3
    # Linear backoff: 1 * attempt for each of the two failed attempts.
    assert sleep_patch.call_count == 2
    sleep_patch.assert_has_calls([mocker.call(1), mocker.call(2)])


def test_retry_on_transient_error_non_transient_fails_fast(mocker):
    sleep_patch = mocker.patch(f"{AZ_CLIENT_PATH}.sleep")
    func = mocker.Mock(side_effect=ValueError("bad request"))

    from azext_edge.edge.util.az_client import retry_on_transient_error

    with pytest.raises(ValueError):
        retry_on_transient_error(func, max_attempts=3, initial_backoff_sec=1)
    # No retry for a non-transient error.
    assert func.call_count == 1
    assert sleep_patch.call_count == 0


def test_retry_on_transient_error_exhausts_attempts(mocker):
    sleep_patch = mocker.patch(f"{AZ_CLIENT_PATH}.sleep")
    func = mocker.Mock(side_effect=ConnectionResetError("Connection reset by peer"))

    from azext_edge.edge.util.az_client import retry_on_transient_error

    with pytest.raises(ConnectionResetError):
        retry_on_transient_error(func, max_attempts=3, initial_backoff_sec=1)
    assert func.call_count == 3
    # Sleeps between attempts only (attempts - 1).
    assert sleep_patch.call_count == 2
