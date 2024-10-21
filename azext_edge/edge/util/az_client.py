# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import sys
from time import sleep
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Tuple

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger

from ...constants import USER_AGENT
from .common import ensure_azure_namespace_path

if sys.version_info >= (3, 9):
    from collections.abc import MutableMapping
else:
    from typing import MutableMapping
JSON = MutableMapping[str, Any]  # pylint: disable=unsubscriptable-object

ensure_azure_namespace_path()

from azure.core.pipeline.policies import HttpLoggingPolicy, UserAgentPolicy
from azure.identity import AzureCliCredential

AZURE_CLI_CREDENTIAL = AzureCliCredential()

POLL_RETRIES = 240
POLL_WAIT_SEC = 15

logger = get_logger(__name__)


if TYPE_CHECKING:
    from azure.core.polling import LROPoller
    from azure.keyvault.secrets import SecretClient

    from ..vendor.clients.authzmgmt import AuthorizationManagementClient
    from ..vendor.clients.clusterconfigmgmt import KubernetesConfigurationClient
    from ..vendor.clients.connectedclustermgmt import ConnectedKubernetesClient
    from ..vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )
    from ..vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService
    from ..vendor.clients.resourcesmgmt import ResourceManagementClient
    from ..vendor.clients.storagemgmt import StorageManagementClient
    from ..vendor.clients.msimgmt import ManagedServiceIdentityClient
    from ..vendor.clients.secretsyncmgmt import MicrosoftSecretSyncController


# TODO @digimaun - simplify client init pattern. Consider multi-profile vs static API client.


def get_ssc_mgmt_client(subscription_id: str, **kwargs) -> "MicrosoftSecretSyncController":
    from ..vendor.clients.secretsyncmgmt import MicrosoftSecretSyncController

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return MicrosoftSecretSyncController(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_msi_mgmt_client(subscription_id: str, **kwargs) -> "ManagedServiceIdentityClient":
    from ..vendor.clients.msimgmt import ManagedServiceIdentityClient

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return ManagedServiceIdentityClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_clusterconfig_mgmt_client(subscription_id: str, **kwargs) -> "KubernetesConfigurationClient":
    from ..vendor.clients.clusterconfigmgmt import KubernetesConfigurationClient

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return KubernetesConfigurationClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_connectedk8s_mgmt_client(subscription_id: str, **kwargs) -> "ConnectedKubernetesClient":
    from ..vendor.clients.connectedclustermgmt import ConnectedKubernetesClient

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return ConnectedKubernetesClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_storage_mgmt_client(subscription_id: str, **kwargs) -> "StorageManagementClient":
    from ..vendor.clients.storagemgmt import StorageManagementClient

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return StorageManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


REGISTRY_API_VERSION = "2024-09-01-preview"


def get_registry_mgmt_client(subscription_id: str, **kwargs) -> "MicrosoftDeviceRegistryManagementService":
    from ..vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return MicrosoftDeviceRegistryManagementService(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_iotops_mgmt_client(subscription_id: str, **kwargs) -> "MicrosoftIoTOperationsManagementService":
    from ..vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return MicrosoftIoTOperationsManagementService(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_resource_client(subscription_id: str, **kwargs) -> "ResourceManagementClient":
    from ..vendor.clients.resourcesmgmt import ResourceManagementClient

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return ResourceManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_authz_client(subscription_id: str, **kwargs) -> "AuthorizationManagementClient":
    from ..vendor.clients.authzmgmt import AuthorizationManagementClient

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return AuthorizationManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_keyvault_client(subscription_id: str, keyvault_name: str, **kwargs) -> "SecretClient":
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        vault_url=f"https://{keyvault_name}.vault.azure.net",
        **kwargs,
    )

    # wait to set the access token
    sleep(5)

    return client


def wait_for_terminal_state(poller: "LROPoller", wait_sec: int = POLL_WAIT_SEC, **_) -> JSON:
    # resource client does not handle sigint well
    counter = 0
    while counter < POLL_RETRIES:
        sleep(wait_sec)
        counter = counter + 1
        if poller.done():
            break
    return poller.result()


def wait_for_terminal_states(
    *pollers: "LROPoller", retries: int = POLL_RETRIES, wait_sec: int = POLL_WAIT_SEC, **_
) -> Tuple["LROPoller"]:
    counter = 0
    while counter < retries:
        sleep(wait_sec)
        counter = counter + 1
        batch_done = all(poller.done() for poller in pollers)
        if batch_done:
            break

    return pollers


def get_tenant_id() -> str:
    from azure.cli.core._profile import Profile

    profile = Profile()
    sub = profile.get_subscription()
    return sub["tenantId"]


def get_default_logging_policy() -> HttpLoggingPolicy:
    http_logging_policy = HttpLoggingPolicy(logger=logger)
    http_logging_policy.allowed_query_params.add("api-version")
    http_logging_policy.allowed_query_params.add("$filter")
    http_logging_policy.allowed_query_params.add("$expand")
    http_logging_policy.allowed_header_names.add("x-ms-correlation-request-id")

    return http_logging_policy


class ResourceIdContainer(NamedTuple):
    subscription_id: str
    resource_group_name: str
    resource_name: str
    resource_id: str


def parse_resource_id(resource_id: str) -> Optional[ResourceIdContainer]:
    if not resource_id:
        return resource_id

    # TODO - cheap.
    parts = resource_id.split("/")
    if len(parts) < 9:
        raise ValidationError(
            f"Malformed resource Id '{resource_id}'. An Azure resource Id has the form:\n"
            "/subscription/{subscriptionId}/resourceGroups/{resourceGroup}"
            "/providers/Microsoft.Provider/{resourcePath}/{resourceName}"
        )

    # Extract the subscription, resource group, and resource name
    subscription_id = parts[2]
    resource_group_name = parts[4]
    resource_name = parts[-1]

    return ResourceIdContainer(
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        resource_name=resource_name,
        resource_id=resource_id,
    )
