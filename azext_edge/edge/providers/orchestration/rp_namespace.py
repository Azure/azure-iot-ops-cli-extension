# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Optional, Set

from knack.log import get_logger

from ...util.az_client import get_resource_client

if TYPE_CHECKING:
    from ...util.az_client import ResourceManagementClient


logger = get_logger(__name__)


ADR_PROVIDER = "Microsoft.DeviceRegistry"
HEALTH_PROVIDER = "Microsoft.ResourceHealth"

# Required RPs - registration failure will block deployment
RP_NAMESPACE_SET = frozenset(
    [
        "Microsoft.IoTOperations",
        "Microsoft.SecretSyncController",
        ADR_PROVIDER,
    ]
)

# Optional RPs - registration failure is logged but won't block deployment
RP_NAMESPACE_OPTIONAL_SET = frozenset(
    [
        HEALTH_PROVIDER,
    ]
)


def _needs_registration(state: str) -> bool:
    return state.lower() not in ("registered", "registering")


def _try_register(resource_client: "ResourceManagementClient", namespace: str, optional: bool) -> bool:
    """
    Attempt to register a single RP.

    Returns:
        True if successful, False if optional and failed.
    """
    try:
        logger.debug("Registering RP %s.", namespace)
        resource_client.providers.register(namespace)
        return True
    except Exception as e:
        if optional:
            logger.debug("Optional RP %s registration failed: %s. Continuing.", namespace, e)
            return False
        raise


def register_providers(subscription_id: str, resource_provider: Optional[str] = None) -> Set[str]:
    """
    Register resource providers for IoT Operations.

    Args:
        subscription_id: Azure subscription ID.
        resource_provider: Specific RP to register. If None, registers all default RPs.

    Returns:
        Set of optional RPs that failed to register.
    """
    resource_client = get_resource_client(subscription_id=subscription_id)
    providers = {p["namespace"]: p.get("registrationState", "") for p in resource_client.providers.list()}

    if resource_provider:
        if _needs_registration(providers.get(resource_provider, "")):
            _try_register(resource_client, resource_provider, optional=False)
        return set()

    for rp in RP_NAMESPACE_SET:
        if _needs_registration(providers.get(rp, "")):
            _try_register(resource_client, rp, optional=False)

    failed_optional: Set[str] = set()
    for rp in RP_NAMESPACE_OPTIONAL_SET:
        if _needs_registration(providers.get(rp, "")):
            if not _try_register(resource_client, rp, optional=True):
                failed_optional.add(rp)

    return failed_optional
