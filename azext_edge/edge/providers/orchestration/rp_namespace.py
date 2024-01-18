# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict

from knack.log import get_logger

from ...util.az_client import get_resource_client

logger = get_logger(__name__)


RP_NAMESPACE_SET = frozenset(
    [
        "Microsoft.IoTOperationsOrchestrator",
        "Microsoft.IoTOperationsMQ",
        "Microsoft.IoTOperationsDataProcessor",
        "Microsoft.DeviceRegistry",
    ]
)


def register_providers(subscription_id: str, **kwargs) -> Dict[str, bool]:
    resource_client = get_resource_client(subscription_id=subscription_id)
    providers_list = resource_client.providers.list()
    for provider in providers_list:
        provider_dict = provider.as_dict()
        if "namespace" in provider_dict and provider_dict["namespace"] in RP_NAMESPACE_SET:
            if provider_dict["registration_state"] == "Registered":
                logger.debug("RP %s is already registered.", provider_dict["namespace"])
                continue
            logger.debug("Registering RP %s.", provider_dict["namespace"])
            resource_client.providers.register(provider_dict["namespace"])
