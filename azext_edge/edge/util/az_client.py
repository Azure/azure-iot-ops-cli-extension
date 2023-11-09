# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azure.identity import AzureCliCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.core.pipeline.policies import UserAgentPolicy
from ...constants import USER_AGENT

AZURE_CLI_CREDENTIAL = AzureCliCredential()


def get_resource_client(subscription_id: str):
    return ResourceManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
    )
