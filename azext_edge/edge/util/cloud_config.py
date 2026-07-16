# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Centralized cloud configuration.

Single source of truth for cloud-specific endpoints, suffixes, and token scopes.
Values that the Azure CLI cloud framework provides (ARM, Microsoft Graph, Key Vault,
Storage, ACR) are read at runtime from ``cmd.cli_ctx.cloud``. Values the framework does
not provide (Service Bus suffix, Event Grid token audience) are maintained here as
explicit cloud-name -> value mappings.

When adding new cloud-dependent functionality, resolve values through ``CloudConfig``
rather than hardcoding public-cloud URLs.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.cli.core.commands import AzCliCommand

# Known cloud names as reported by ``cmd.cli_ctx.cloud.name``.
CLOUD_AZURE_PUBLIC = "AzureCloud"
CLOUD_AZURE_US_GOVERNMENT = "AzureUSGovernment"
# NOTE: Azure China (Mooncake) is NOT functional today — the Azure IoT Operations service
# does not have server-side support in Mooncake, so end-to-end flows cannot be validated
# there yet. The China endpoint/suffix mappings below are intentionally retained so that
# support is already in place if/when Mooncake gains server-side support in the future.
# Until then, treat AzureChinaCloud as best-effort / untested.
CLOUD_AZURE_CHINA = "AzureChinaCloud"

# Service Bus FQDN suffix per cloud. Not provided by the Azure CLI cloud framework.
SERVICEBUS_SUFFIX_MAP = {
    CLOUD_AZURE_PUBLIC: "servicebus.windows.net",
    CLOUD_AZURE_US_GOVERNMENT: "servicebus.usgovcloudapi.net",
    CLOUD_AZURE_CHINA: "servicebus.chinacloudapi.cn",
}

# Event Grid token audience per cloud. Not provided by the Azure CLI cloud framework.
EVENTGRID_AUDIENCE_MAP = {
    CLOUD_AZURE_PUBLIC: "https://eventgrid.azure.net",
    CLOUD_AZURE_US_GOVERNMENT: "https://eventgrid.azure.us",
    CLOUD_AZURE_CHINA: "https://eventgrid.azure.cn",
}

# Clouds where Microsoft Fabric OneLake is available.
FABRIC_ONELAKE_SUPPORTED_CLOUDS = frozenset({CLOUD_AZURE_PUBLIC})

# Clouds where Event Grid Namespaces with MQTT (used by management actions) is available.
EVENTGRID_MQTT_SUPPORTED_CLOUDS = frozenset({CLOUD_AZURE_PUBLIC, CLOUD_AZURE_US_GOVERNMENT})


class CloudConfig:
    """Resolves cloud-specific values for the user's active Azure CLI cloud context."""

    def __init__(self, cmd: "AzCliCommand"):
        self._cloud = cmd.cli_ctx.cloud

    @property
    def name(self) -> str:
        return self._cloud.name

    # --- Values provided by the Azure CLI cloud framework ---

    @property
    def arm_endpoint(self) -> str:
        """Azure Resource Manager endpoint (e.g. https://management.azure.com/)."""
        return self._cloud.endpoints.resource_manager

    @property
    def arm_endpoint_scope(self) -> str:
        """ARM resource manager endpoint token scope (e.g. https://management.azure.com/.default).

        Derived from the ARM endpoint itself. Required by flows such as ACR's oauth2/exchange that
        expect a token for the resource manager audience (``https://management.<cloud>/``).
        """
        return f"{self._cloud.endpoints.resource_manager.rstrip('/')}/.default"

    @property
    def graph_endpoint(self) -> str:
        """Microsoft Graph endpoint with trailing slash (e.g. https://graph.microsoft.com/)."""
        endpoint = self._cloud.endpoints.microsoft_graph_resource_id
        return endpoint if endpoint.endswith("/") else f"{endpoint}/"

    @property
    def graph_token_resource(self) -> str:
        """Microsoft Graph token resource (no trailing slash)."""
        return self._cloud.endpoints.microsoft_graph_resource_id.rstrip("/")

    @property
    def storage_suffix(self) -> str:
        """Storage endpoint suffix (e.g. core.windows.net)."""
        return self._cloud.suffixes.storage_endpoint

    @property
    def keyvault_dns_suffix(self) -> str:
        """Key Vault DNS suffix (e.g. .vault.azure.net)."""
        return self._cloud.suffixes.keyvault_dns

    @property
    def keyvault_scope(self) -> str:
        """Key Vault data-plane token scope (e.g. https://vault.azure.net/.default)."""
        return f"https://{self._cloud.suffixes.keyvault_dns.lstrip('.')}/.default"

    @property
    def acr_suffix(self) -> str:
        """Azure Container Registry login server suffix (e.g. .azurecr.io)."""
        return self._cloud.suffixes.acr_login_server_endpoint

    # --- Values maintained here (not provided by the framework) ---

    @property
    def servicebus_suffix(self) -> str:
        """Service Bus FQDN suffix (e.g. servicebus.windows.net)."""
        return SERVICEBUS_SUFFIX_MAP.get(self.name, SERVICEBUS_SUFFIX_MAP[CLOUD_AZURE_PUBLIC])

    @property
    def eventgrid_audience(self) -> str:
        """Event Grid token audience (e.g. https://eventgrid.azure.net)."""
        return EVENTGRID_AUDIENCE_MAP.get(self.name, EVENTGRID_AUDIENCE_MAP[CLOUD_AZURE_PUBLIC])

    # --- Feature availability ---

    @property
    def supports_fabric_onelake(self) -> bool:
        return self.name in FABRIC_ONELAKE_SUPPORTED_CLOUDS

    @property
    def supports_eventgrid_mqtt(self) -> bool:
        return self.name in EVENTGRID_MQTT_SUPPORTED_CLOUDS
