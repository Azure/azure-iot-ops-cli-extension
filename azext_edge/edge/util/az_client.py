# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# this is a false positive in pylint 3.0.3 for python 3.13
from collections.abc import MutableMapping  # pylint: disable=import-error
from enum import Enum
from time import sleep
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Tuple, Union

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger

from ...constants import USER_AGENT
from .common import ensure_azure_namespace_path

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
    from azure.core.exceptions import HttpResponseError

    from ..vendor.clients.authzmgmt import AuthorizationManagementClient
    from ..vendor.clients.clusterconfigmgmt import KubernetesConfigurationClient
    from ..vendor.clients.connectedclustermgmt import ConnectedKubernetesClient
    from ..vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )
    from ..vendor.clients.extendedlocmgmt import CustomLocations
    from ..vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService
    from ..vendor.clients.keyvault import KeyVaultClient
    from ..vendor.clients.msimgmt import ManagedServiceIdentityClient
    from ..vendor.clients.resourcesmgmt import ResourceManagementClient
    from ..vendor.clients.resourcehealthmgmt import MicrosoftResourceHealth
    from ..vendor.clients.secretsyncmgmt import MicrosoftSecretSyncController
    from ..vendor.clients.storagemgmt import StorageManagementClient
    from ..vendor.clients.eventgridmgmt import EventGridManagementClient


# TODO @digimaun - simplify client init pattern. Consider multi-profile vs static API client.


def get_extloc_mgmt_client(subscription_id: str, **kwargs) -> "CustomLocations":
    from ..vendor.clients.extendedlocmgmt import CustomLocations

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return CustomLocations(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


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


class EventGridMgmtApiVersion(Enum):
    V20250215 = "2025-02-15"


DEFAULT_EVENTGRID_MGMT_API_VERSION = EventGridMgmtApiVersion.V20250215


def get_eventgrid_mgmt_client(
    subscription_id: str,
    api_version: Union[EventGridMgmtApiVersion, str] = DEFAULT_EVENTGRID_MGMT_API_VERSION,
    **kwargs,
) -> "EventGridManagementClient":
    from ..vendor.clients.eventgridmgmt import EventGridManagementClient

    if isinstance(api_version, EventGridMgmtApiVersion):
        api_version = api_version.value

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()
    kwargs["api_version"] = api_version

    return EventGridManagementClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


class DeviceRegistryMgmtApiVersion(Enum):
    V20260401 = "2026-04-01"
    V20260201_preview = "2026-02-01-preview"
    V20251001 = "2025-10-01"
    V20250701_preview = "2025-07-01-preview"
    V20241101 = "2024-11-01"
    V20240901_preview = "2024-09-01-preview"


DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION = DeviceRegistryMgmtApiVersion.V20260401


def get_registry_mgmt_client(
    subscription_id: str,
    api_version: Union[DeviceRegistryMgmtApiVersion, str] = DEFAULT_DEVICEREGISTRY_MGMT_API_VERSION,
    **kwargs,
) -> "MicrosoftDeviceRegistryManagementService":
    from ..vendor.clients.deviceregistrymgmt import (
        MicrosoftDeviceRegistryManagementService,
    )

    if isinstance(api_version, DeviceRegistryMgmtApiVersion):
        api_version = api_version.value

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()
    kwargs["api_version"] = api_version

    return MicrosoftDeviceRegistryManagementService(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


class IoTOpsMgmtApiVersion(Enum):
    V20260301 = "2026-03-01"
    V20251001 = "2025-10-01"
    V20250401 = "2025-04-01"
    V20241101 = "2024-11-01"


DEFAULT_IOTOPS_MGMT_API_VERSION = IoTOpsMgmtApiVersion.V20260301


def get_iotops_mgmt_client(
    subscription_id: str,
    api_version: Union[IoTOpsMgmtApiVersion, str] = DEFAULT_IOTOPS_MGMT_API_VERSION,
    **kwargs,
) -> "MicrosoftIoTOperationsManagementService":
    from ..vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService

    if isinstance(api_version, IoTOpsMgmtApiVersion):
        api_version = api_version.value

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()
    kwargs["api_version"] = api_version

    return MicrosoftIoTOperationsManagementService(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        **kwargs,
    )


def get_health_mgmt_client(
    subscription_id: str,
    **kwargs,
) -> "MicrosoftResourceHealth":
    from ..vendor.clients.resourcehealthmgmt import MicrosoftResourceHealth

    if "http_logging_policy" not in kwargs:
        kwargs["http_logging_policy"] = get_default_logging_policy()

    return MicrosoftResourceHealth(
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


def get_keyvault_client(subscription_id: str, keyvault_scope: Optional[str] = None, **kwargs) -> "KeyVaultClient":
    from ..vendor.clients.keyvault import KeyVaultClient

    client = KeyVaultClient(
        credential=AZURE_CLI_CREDENTIAL,
        subscription_id=subscription_id,
        user_agent_policy=UserAgentPolicy(user_agent=USER_AGENT),
        credential_scopes=[keyvault_scope or "https://vault.azure.net/.default"],
        **kwargs,
    )

    return client


def wait_for_terminal_state(poller: "LROPoller", wait_sec: int = POLL_WAIT_SEC, **_) -> JSON:
    # resource client does not handle sigint well
    counter = 0
    while counter < POLL_RETRIES:
        if poller.done():
            break
        sleep(wait_sec)
        counter = counter + 1
    return poller.result()


def wait_for_terminal_states(
    *pollers: "LROPoller", retries: int = POLL_RETRIES, wait_sec: int = POLL_WAIT_SEC, **_
) -> Tuple["LROPoller"]:
    counter = 0
    while counter < retries:
        batch_done = all(poller.done() for poller in pollers)
        if batch_done:
            break
        sleep(wait_sec)
        counter = counter + 1

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
            "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}"
            "/providers/Microsoft.Provider/{resourceType}/{resourceName}"
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


def get_api_error_str(exception: "HttpResponseError") -> str:
    if hasattr(exception, "message"):
        return exception.message
    return str(exception)
