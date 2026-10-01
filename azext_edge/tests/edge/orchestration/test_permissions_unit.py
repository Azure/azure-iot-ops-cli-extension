# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.providers.orchestration.permissions import (
    PermissionManager,
    verify_write_permission_against_rg,
)
from azure.cli.core.azclierror import ValidationError

from ...generators import get_zeroed_subscription, generate_random_string

MOCK_SUBSCRIPTION_ID = get_zeroed_subscription()
MOCK_RG = f"rg_{generate_random_string()}"


@pytest.fixture
def mocked_get_principal_permissions_for_group(mocker, request):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.permissions.get_principal_permissions_for_group",
        return_value=request.param["permissions"],
    )
    setattr(patched, "expected_success", request.param.get("expected_success", True))
    yield patched


@pytest.mark.parametrize(
    "mocked_get_principal_permissions_for_group",
    [
        {
            "permissions": [
                {"actions": [], "notActions": []},
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {"actions": ["*"], "notActions": ["*/write"]},
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {"actions": ["*"], "notActions": ["Microsoft.Authorization/*/write"]},
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {
                    "actions": ["Microsoft.Authorization/*/write"],
                    "notActions": ["Microsoft.Authorization/roleAssignments/write"],
                },
            ],
            "expected_success": False,
        },
        {
            "permissions": [
                {"actions": ["*"], "notActions": []},
            ],
        },
        {
            "permissions": [
                {"actions": ["*"], "notActions": ["Microsoft.Authorization/*/write"]},
                {"actions": ["*"], "notActions": []},
            ],
        },
        {
            "permissions": [
                {"actions": [], "notActions": []},
                {"actions": ["*/write"], "notActions": ["Microsoft.Test/subject/action"]},
            ],
        },
        {
            "permissions": [
                {
                    "actions": ["Microsoft.Authorization/roleAssignments/write", "Microsoft.Test/subject/action"],
                    "notActions": [],
                },
            ],
        },
        {
            "permissions": [
                {"actions": [], "notActions": []},
                {"actions": ["Microsoft.Authorization/*/write"], "notActions": []},
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


class TestEnsureRoleAssignment:
    def test_returns_existing_assignment(self, mocker):
        existing = {
            "id": "/existing",
            "properties": {"roleDefinitionId": "/roles/reader"},
        }
        manager = PermissionManager.__new__(PermissionManager)
        manager.authz_client = mocker.MagicMock()
        manager.authz_client.role_assignments.list_for_scope.return_value = [existing]

        result, created = manager.ensure_role_assignment(
            scope="/scope",
            principal_id="principal",
            role_def_id="/roles/reader",
            principal_type="User",
        )

        assert result == existing
        assert created is False
        manager.authz_client.role_assignments.create.assert_not_called()

    def test_returns_created_assignment(self, mocker):
        created_assignment = {
            "id": "/created",
            "properties": {"roleDefinitionId": "/roles/reader"},
        }
        manager = PermissionManager.__new__(PermissionManager)
        manager.authz_client = mocker.MagicMock()
        manager.authz_client.role_assignments.list_for_scope.return_value = []
        manager.authz_client.role_assignments.create.return_value = created_assignment

        result, created = manager.ensure_role_assignment(
            scope="/scope",
            principal_id="principal",
            role_def_id="/roles/reader",
            principal_type="User",
        )

        assert result == created_assignment
        assert created is True
        parameters = manager.authz_client.role_assignments.create.call_args.kwargs["parameters"]
        assert parameters["properties"]["principalType"] == "User"

    def test_apply_preserves_existing_return_contract(self, mocker):
        manager = PermissionManager.__new__(PermissionManager)
        manager.ensure_role_assignment = mocker.MagicMock(
            return_value=({"id": "/existing"}, False)
        )

        result = manager.apply_role_assignment(
            scope="/scope",
            principal_id="principal",
            role_def_id="/roles/reader",
        )

        assert result is None

    def test_apply_returns_created_assignment(self, mocker):
        created_assignment = {"id": "/created"}
        manager = PermissionManager.__new__(PermissionManager)
        manager.ensure_role_assignment = mocker.MagicMock(
            return_value=(created_assignment, True)
        )

        result = manager.apply_role_assignment(
            scope="/scope",
            principal_id="principal",
            role_def_id="/roles/reader",
        )

        assert result == created_assignment

    def test_delete_role_assignment_by_id(self, mocker):
        manager = PermissionManager.__new__(PermissionManager)
        manager.authz_client = mocker.MagicMock()

        manager.delete_role_assignment("/assignments/created")

        manager.authz_client.role_assignments.delete_by_id.assert_called_once_with(
            role_assignment_id="/assignments/created"
        )
