# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from time import sleep
from typing import TYPE_CHECKING

from ...constants import USER_AGENT
from .common import ensure_azure_namespace_path

ensure_azure_namespace_path()

from azure.core.pipeline.policies import UserAgentPolicy
from azure.identity import AzureCliCredential, ClientSecretCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.resource import ResourceManagementClient

AZURE_CLI_CREDENTIAL = AzureCliCredential()

POLL_RETRIES = 240
POLL_WAIT_SEC = 15

if TYPE_CHECKING:
    from azure.core.polling import LROPoller
    from azure.mgmt.resource.resources.models import GenericResource


def get_resource_client(subscription_id: str) -> ResourceManagementClient:
    return ResourceManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
    )


def get_authz_client(subscription_id: str) -> AuthorizationManagementClient:
    return AuthorizationManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
    )


def get_token_from_sp_credential(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    client_secret_cred = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
    return client_secret_cred.get_token(scope).token


def wait_for_terminal_state(poller: "LROPoller") -> "GenericResource":
    # resource client does not handle sigint well
    counter = 0
    while counter < POLL_RETRIES:
        sleep(POLL_WAIT_SEC)
        counter = counter + 1
        if poller.done():
            break
    return poller.result()


def wait_for_terminal_states(*pollers: "LROPoller"):
    pass


def get_tenant_id() -> str:
    from azure.cli.core._profile import Profile

    profile = Profile()
    sub = profile.get_subscription()
    return sub["tenantId"]
