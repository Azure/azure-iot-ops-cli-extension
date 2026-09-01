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
