# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azure.core.exceptions import HttpResponseError

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


def _get_http_response_error(mocker, payload, status_code=200, text=""):
    response = mocker.Mock()
    response.status_code = status_code
    response.reason = "OK"
    response.headers = {}
    response.json.return_value = payload
    response.text.return_value = text
    return HttpResponseError(response=response)


def test_wait_for_terminal_state_formats_failed_lro(mocker):
    error = _get_http_response_error(
        mocker,
        {
            "status": "Failed",
            "error": {
                "code": "ResourceOperationFailure",
                "message": "The resource operation failed.",
                "details": [
                    {"code": "ReconcileFailed", "message": "A child resource could not be removed."},
                    "Retry the operation.",
                ],
            },
        },
    )
    error.response.headers = {"x-ms-request-id": "request-id"}
    poller = mocker.Mock()
    poller.done.return_value = True
    poller.result.side_effect = error

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    with pytest.raises(HttpResponseError) as exc_info:
        wait_for_terminal_state(poller)

    assert exc_info.value is error
    assert error.message == (
        "Long-running operation failed with status 'Failed'.\n"
        "Code: ResourceOperationFailure\n"
        "Message: The resource operation failed.\n"
        "Details:\n"
        "  - ReconcileFailed: A child resource could not be removed.\n"
        "  - Retry the operation.\n"
        "Request ID: request-id"
    )
    assert str(error) == error.message


@pytest.mark.parametrize("service_error", [None, {}])
def test_wait_for_terminal_state_formats_canceled_lro_without_error(mocker, service_error):
    error = _get_http_response_error(mocker, {"status": "Canceled", "error": service_error})
    poller = mocker.Mock()
    poller.done.return_value = True
    poller.result.side_effect = error

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    with pytest.raises(HttpResponseError):
        wait_for_terminal_state(poller)

    assert error.message == (
        "Long-running operation failed with status 'Canceled'.\n"
        "The service returned no error details."
    )


def test_wait_for_terminal_state_formats_nonstandard_lro_error(mocker):
    error = _get_http_response_error(mocker, {"status": "Failed", "error": "Reconciliation failed."})
    poller = mocker.Mock()
    poller.done.return_value = True
    poller.result.side_effect = error

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    with pytest.raises(HttpResponseError):
        wait_for_terminal_state(poller)

    assert error.message == (
        "Long-running operation failed with status 'Failed'.\n"
        "Error: Reconciliation failed."
    )


@pytest.mark.parametrize(
    "payload,status_code",
    [
        ({"status": "Succeeded"}, 200),
        ({"status": "Failed"}, 500),
        (["Failed"], 200),
    ],
)
def test_wait_for_terminal_state_preserves_nonmatching_error(mocker, payload, status_code):
    error = _get_http_response_error(mocker, payload, status_code=status_code)
    original_message = error.message
    poller = mocker.Mock()
    poller.done.return_value = True
    poller.result.side_effect = error

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    with pytest.raises(HttpResponseError):
        wait_for_terminal_state(poller)

    assert error.message == original_message


def test_wait_for_terminal_state_preserves_standard_arm_error(mocker):
    error = _get_http_response_error(
        mocker,
        {"status": "Failed"},
        text='{"error":{"code":"Conflict","message":"A dependency exists."}}',
    )
    original_message = error.message
    poller = mocker.Mock()
    poller.done.return_value = True
    poller.result.side_effect = error

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    with pytest.raises(HttpResponseError):
        wait_for_terminal_state(poller)

    assert error.message == original_message


def test_wait_for_terminal_state_preserves_unreadable_response(mocker):
    error = _get_http_response_error(mocker, {"status": "Failed"})
    error.response.json.side_effect = ValueError("Invalid JSON")
    original_message = error.message
    poller = mocker.Mock()
    poller.done.return_value = True
    poller.result.side_effect = error

    from azext_edge.edge.util.az_client import wait_for_terminal_state

    with pytest.raises(HttpResponseError):
        wait_for_terminal_state(poller)

    assert error.message == original_message


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
