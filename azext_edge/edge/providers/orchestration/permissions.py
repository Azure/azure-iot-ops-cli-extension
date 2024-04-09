# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

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


def get_principal_permissions_for_group(subscription_id: str, resource_group_name: str):
    authz_client = get_authz_client(subscription_id=subscription_id)
    return authz_client.permissions.list_for_resource_group(resource_group_name)
