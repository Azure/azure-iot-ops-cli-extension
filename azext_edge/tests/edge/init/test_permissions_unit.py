# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.providers.orchestration.permissions import verify_write_permission_against_rg
from azure.cli.core.azclierror import ValidationError

from ...generators import get_zeroed_subscription, generate_random_string

MOCK_SUBSCRIPTION_ID = get_zeroed_subscription()
MOCK_RG = f"rg_{generate_random_string()}"


class IntermObj:
    def __init__(self, return_dict: dict):
        self._return_dict = return_dict

    def as_dict(self):
        return self._return_dict


@pytest.fixture
def mocked_get_principal_permissions_for_group(mocker, request):
    return_payload = []
    for p in request.param["permissions"]:
        return_payload.append(IntermObj(p))

    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.permissions.get_principal_permissions_for_group",
        return_value=return_payload,
    )
    setattr(patched, "expected_success", request.param.get("expected_success", True))
    yield patched


@pytest.mark.parametrize(
    "mocked_get_principal_permissions_for_group",
    [
        {
            "permissions": [
                {"actions": [], "not_actions": []},
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {"actions": ["*"], "not_actions": ["*/write"]},
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {"actions": ["*"], "not_actions": ["Microsoft.Authorization/*/write"]},
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {
                    "actions": ["Microsoft.Authorization/*/write"],
                    "not_actions": ["Microsoft.Authorization/roleAssignments/write"],
                },
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {"actions": ["*"], "not_actions": []},
            ],
        },
        {
            "permissions": [
                {"actions": ["*"], "not_actions": ["Microsoft.Authorization/*/write"]},
                {"actions": ["*"], "not_actions": []},
            ],
        },
        {
            "permissions": [
                {"actions": [], "not_actions": []},
                {"actions": ["*/write"], "not_actions": ["Microsoft.Test/subject/action"]},
            ],
        },
        {
            "permissions": [
                {
                    "actions": ["Microsoft.Authorization/roleAssignments/write", "Microsoft.Test/subject/action"],
                    "not_actions": [],
                },
            ],
        },
        {
            "permissions": [
                {"actions": [], "not_actions": []},
                {"actions": ["Microsoft.Authorization/*/write"], "not_actions": []},
            ],
        },
    ],
    indirect=True,
)
def test_verify_write_permission_against_rg(mocked_get_principal_permissions_for_group):
    if not mocked_get_principal_permissions_for_group.expected_success:
        with pytest.raises(ValidationError):
            verify_write_permission_against_rg(subscription_id=MOCK_SUBSCRIPTION_ID, resource_group_name=MOCK_RG)
        return

    verify_write_permission_against_rg(subscription_id=MOCK_SUBSCRIPTION_ID, resource_group_name=MOCK_RG)
    call_kwargs = mocked_get_principal_permissions_for_group.call_args.kwargs
    assert call_kwargs["subscription_id"] == MOCK_SUBSCRIPTION_ID
    assert call_kwargs["resource_group_name"] == MOCK_RG
