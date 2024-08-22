# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from typing import Iterable, Optional
from uuid import uuid4

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger

from ...util.az_client import get_authz_client

logger = get_logger(__name__)

VALID_PERM_FORMS = frozenset(
    ["*", "*/write", "microsoft.authorization/roleassignments/write", "microsoft.authorization/*/write"]
)


# TODO: one-off for time, make generic
def verify_write_permission_against_rg(subscription_id: str, resource_group_name: str, **kwargs):
    for permission in get_principal_permissions_for_group(
        subscription_id=subscription_id, resource_group_name=resource_group_name
    ):
        permission_dict = permission.as_dict()
        action_result = False
        negate_action_result = False

        for action in permission_dict.get("actions", []):
            if action.lower() in VALID_PERM_FORMS:
                action_result = True
                break

        for not_action in permission_dict.get("not_actions", []):
            if not_action.lower() in VALID_PERM_FORMS:
                negate_action_result = True
                break

        if action_result and not negate_action_result:
            return

    raise ValidationError(
        "This IoT Operations deployment config includes resource sync rules which require the logged-in principal\n"
        "to have permission to write role assignments (Microsoft.Authorization/roleAssignments/write) "
        "against the resource group.\n\n"
        "Use --disable-rsync-rules to not include resource sync rules in the deployment.\n"
    )


def get_principal_permissions_for_group(subscription_id: str, resource_group_name: str) -> Iterable:
    authz_client = get_authz_client(subscription_id=subscription_id)
    return authz_client.permissions.list_for_resource_group(resource_group_name)


class PermissionState(Enum):
    ActionAllowed = 1
    ActionDenied = 2
    ActionUndefined = 3


class PermissionManager:
    def __init__(self, subscription_id: str):
        self.authz_client = get_authz_client(
            subscription_id=subscription_id,
        )

    def apply_role_assignment(self, scope: str, principal_id: str, role_def_id: str) -> Optional[dict]:
        role_assignments_iter = self.authz_client.role_assignments.list_for_scope(
            scope=scope, filter=f"principalId eq '{principal_id}'"
        )
        for role_assignment in role_assignments_iter:
            role_assignment_dict = role_assignment.as_dict()
            if role_assignment_dict["role_definition_id"] == role_def_id:
                return

        return self.authz_client.role_assignments.create(
            scope=scope,
            role_assignment_name=str(uuid4()),
            parameters={
                "role_definition_id": role_def_id,
                "principal_id": principal_id,
            },
        )

    def can_apply_role_assignment(
        self,
        resource_group_name: str,
        resource_provider_namespace: str,
        parent_resource_path: str,
        resource_type: str,
        resource_name: str,
    ) -> bool:
        permissions = self._get_principal_permissions_for_resource(
            resource_group_name=resource_group_name,
            resource_provider_namespace=resource_provider_namespace,
            parent_resource_path=parent_resource_path,
            resource_type=resource_type,
            resource_name=resource_name,
        )
        action_allowed = None
        for permission in permissions:
            permission_dict = permission.as_dict()
            action_result = self._calculate_action(permission_dict=permission_dict, valid_permissions=VALID_PERM_FORMS)

            if action_result == PermissionState.ActionAllowed and action_allowed is not False:
                action_allowed = True
            elif action_result == PermissionState.ActionDenied:
                action_allowed = False

        return bool(action_allowed)

    def _get_principal_permissions_for_resource(
        self,
        resource_group_name: str,
        resource_provider_namespace: str,
        parent_resource_path: str,
        resource_type: str,
        resource_name: str,
    ) -> Iterable:
        return self.authz_client.permissions.list_for_resource(
            resource_group_name=resource_group_name,
            resource_provider_namespace=resource_provider_namespace,
            parent_resource_path=parent_resource_path,
            resource_type=resource_type,
            resource_name=resource_name,
        )

    def _calculate_action(self, permission_dict: dict, valid_permissions: frozenset) -> PermissionState:
        action_result = False
        negate_action_result = False

        for action in permission_dict.get("actions", []):
            if action.lower() in valid_permissions:
                action_result = True
                break

        for not_action in permission_dict.get("not_actions", []):
            if not_action.lower() in valid_permissions:
                negate_action_result = True
                break

        if action_result and not negate_action_result:
            return PermissionState.ActionAllowed
        if negate_action_result:
            return PermissionState.ActionDenied
        return PermissionState.ActionUndefined
