# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from ...constants import USER_AGENT
from .common import ensure_azure_namespace_path

ensure_azure_namespace_path()

from azure.core.pipeline.policies import UserAgentPolicy
from azure.identity import AzureCliCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.resource import ResourceManagementClient

AZURE_CLI_CREDENTIAL = AzureCliCredential()


def get_resource_client(subscription_id: str) -> ResourceManagementClient:
    return ResourceManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
    )


def get_authz_client(subscription_id: str):
    return AuthorizationManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
    )