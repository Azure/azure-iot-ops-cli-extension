# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from knack.log import get_logger

from ...util.az_client import get_resource_client

logger = get_logger(__name__)


ADR_PROVIDER = "Microsoft.DeviceRegistry"
RP_NAMESPACE_SET = frozenset(
    [
        "Microsoft.IoTOperations",
        "Microsoft.SecretSyncController",
        ADR_PROVIDER
    ]
)


def register_providers(subscription_id: str, resource_provider: Optional[str] = None):
    resource_client = get_resource_client(subscription_id=subscription_id)
    providers_list = resource_client.providers.list()
    required_providers = [resource_provider] if resource_provider else RP_NAMESPACE_SET
    for provider in providers_list:
        if "namespace" in provider and provider["namespace"] in required_providers:
            if provider["registrationState"] == "Registered":
                logger.debug("RP %s is already registered.", provider["namespace"])
                continue
            logger.debug("Registering RP %s.", provider["namespace"])
            resource_client.providers.register(provider["namespace"])
