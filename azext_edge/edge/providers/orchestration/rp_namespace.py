# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger

from ...util.az_client import get_resource_client

logger = get_logger(__name__)


RP_NAMESPACE_SET = frozenset(
    [
        "Microsoft.IoTOperationsOrchestrator",
        "Microsoft.IoTOperations",
        "Microsoft.DeviceRegistry",
        "Microsoft.SecretSyncController",
    ]
)


def register_providers(subscription_id: str):
    resource_client = get_resource_client(subscription_id=subscription_id)
    providers_list = resource_client.providers.list()
    for provider in providers_list:
        if "namespace" in provider and provider["namespace"] in RP_NAMESPACE_SET:
            if provider["registrationState"] == "Registered":
                logger.debug("RP %s is already registered.", provider["namespace"])
                continue
            logger.debug("Registering RP %s.", provider["namespace"])
            resource_client.providers.register(provider["namespace"])
