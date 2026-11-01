# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Resolve the IoT Operations management API version an installed instance supports.

An instance resource is served by the resource provider, but its child resources (brokers, dataflows,
endpoints, ...) are served through the custom location, which only enables the API versions shipped
with the installed AIO version. Writing child resources with a newer CLI default API version fails
with ``MissingAzureKubernetesMapping``.
"""

from typing import Optional, Set, Tuple

from azure.core.exceptions import HttpResponseError
from knack.log import get_logger

from ...util.az_client import DEFAULT_IOTOPS_MGMT_API_VERSION, IoTOpsMgmtApiVersion, get_extloc_mgmt_client
from ...util.id_tools import parse_resource_id
from ...util.machinery import scoped_semver_import

logger = get_logger(__name__)

IOTOPS_RP = "Microsoft.IoTOperations"

# Newest API version each AIO minor line enables on its custom location, newest first. The first row
# whose minimum (major, minor) the instance meets wins. Instances newer than the first row reuse it,
# since a custom location keeps enabling the older API versions.
# Add a row when a new AIO line ships a new API version; a unit test ties the first row to the GA runtime.
INSTANCE_API_VERSIONS: Tuple[Tuple[Tuple[int, int], IoTOpsMgmtApiVersion], ...] = (
    ((1, 5), IoTOpsMgmtApiVersion.V20261001),
    ((1, 4), IoTOpsMgmtApiVersion.V20260701),
    ((1, 3), IoTOpsMgmtApiVersion.V20260301),
    ((1, 2), IoTOpsMgmtApiVersion.V20251001),
    ((1, 1), IoTOpsMgmtApiVersion.V20250401),
)
OLDEST_INSTANCE_API_VERSION = IoTOpsMgmtApiVersion.V20241101


def get_instance_iotops_api_version(instance_version: Optional[str]) -> str:
    """
    Get the IoT Operations management API version to use for an installed instance's child resources.

    Only the (major, minor) of the version is considered, so prerelease builds of a line
    (for example 1.5.0-preview.3) map with that line. A missing or unparseable version keeps the CLI default.
    """
    if not instance_version:
        return DEFAULT_IOTOPS_MGMT_API_VERSION.value

    try:
        parsed = scoped_semver_import().parse(instance_version)
    except (TypeError, ValueError):
        logger.debug("Unable to parse instance version %r. Using the default API version.", instance_version)
        return DEFAULT_IOTOPS_MGMT_API_VERSION.value

    for minimum, api_version in INSTANCE_API_VERSIONS:
        if (parsed.major, parsed.minor) >= minimum:
            return api_version.value
    return OLDEST_INSTANCE_API_VERSION.value


def get_enabled_iotops_api_versions(custom_location_id: str, **client_kwargs) -> Set[str]:
    """
    Get the API versions a custom location enables for Microsoft.IoTOperations resources.

    The client is created in the custom location's subscription; other kwargs (for example the
    cloud's ARM endpoint) are forwarded to the client factory.

    Best effort: returns an empty set when the custom location or its enabled resource types
    cannot be read, so callers should treat an empty result as unknown rather than unsupported.
    """
    parsed = parse_resource_id(custom_location_id) if custom_location_id else {}
    if not all(parsed.get(key) for key in ("subscription", "resource_group", "name")):
        return set()

    client_kwargs["subscription_id"] = parsed["subscription"]
    extloc_mgmt_client = get_extloc_mgmt_client(**client_kwargs)
    api_versions: Set[str] = set()
    try:
        for enabled_type in extloc_mgmt_client.custom_locations.list_enabled_resource_types(
            resource_group_name=parsed["resource_group"], resource_name=parsed["name"]
        ):
            for metadata in (enabled_type.get("properties") or {}).get("typesMetadata") or []:
                namespace = (metadata.get("resourceProviderNamespace") or "").lower()
                if namespace == IOTOPS_RP.lower() and metadata.get("apiVersion"):
                    api_versions.add(metadata["apiVersion"])
    except HttpResponseError as ex:
        logger.debug("Unable to read enabled resource types for custom location '%s': %s", custom_location_id, ex)
        return set()
    return api_versions
