# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.core.pipeline.policies import UserAgentPolicy
from ...constants import USER_AGENT

DEFAULT_AZURE_CREDENTIAL = DefaultAzureCredential()


def get_resource_client(subscription_id: str):
    return ResourceManagementClient(
        credential=DEFAULT_AZURE_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
    )
