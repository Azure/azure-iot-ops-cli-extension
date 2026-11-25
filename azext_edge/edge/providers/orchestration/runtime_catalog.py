# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bundled release inputs, separate from runtime selection and validation machinery."""

from typing import Optional, Tuple

from azext_edge.constants import AIO_RELEASE

from ...util.az_client import IoTOpsMgmtApiVersion
from ...util.cloud_config import CLOUD_AZURE_PUBLIC, CLOUD_AZURE_US_GOVERNMENT
from .common import OPCUA_CONNECTOR_VERSION
from .runtime_dependencies import DependencyRequirement
from .runtime_profiles import RuntimeChannel, RuntimeIdentity, RuntimeProfile, RuntimeProfileCatalog
from .template import TEMPLATE_BLUEPRINT_INSTANCE
from .template_preview import TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW


PREVIEW_PROFILE: Optional[RuntimeProfile] = RuntimeProfile(
    channel=RuntimeChannel.PREVIEW,
    release="prev2612",
    source_ref="preview/v1.6.x/2612",
    source_commit="94ad9f812b962343275bd3610d744b494defa2ef",
    instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW,
    opcua_connector_version="1.6.1-preview.4",
    iotops_api_version=IoTOpsMgmtApiVersion.V20261101_preview.value,
)
QUALIFICATION_IDENTITIES: Tuple[RuntimeIdentity, ...] = ()
# Keep the last separately bundled Fairfax runtime upgradeable without --force.
FAIRFAX_QUALIFICATION_IDENTITIES: Tuple[RuntimeIdentity, ...] = (
    RuntimeIdentity(RuntimeChannel.STABLE, "1.5.46", "stable", CLOUD_AZURE_US_GOVERNMENT),
)
# GA and preview share the same init dependency versions and trains.
# No additional dependency compatibility constraints are specified for this release.
# An empty policy leaves the existing shared foundation checks unchanged.
SHARED_DEPENDENCY_REQUIREMENTS: Tuple[DependencyRequirement, ...] = ()


def get_runtime_catalog(cloud_name: str = CLOUD_AZURE_PUBLIC) -> RuntimeProfileCatalog:
    if cloud_name == CLOUD_AZURE_US_GOVERNMENT:
        blueprint = TEMPLATE_BLUEPRINT_INSTANCE
        return RuntimeProfileCatalog(
            [
                RuntimeProfile(
                    channel=RuntimeChannel.STABLE,
                    release=str(AIO_RELEASE),
                    source_ref="releases/v1.5.x/2612",
                    source_commit=blueprint.commit_id,
                    instance_blueprint=blueprint,
                    opcua_connector_version=blueprint.content["variables"]["VERSIONS"]["connectors"],
                    cloud_name=cloud_name,
                    versions_variable="FAIRFAX_VERSIONS",
                    trains_variable="FAIRFAX_TRAINS",
                )
            ],
            FAIRFAX_QUALIFICATION_IDENTITIES,
        )
    stable = RuntimeProfile(
        channel=RuntimeChannel.STABLE,
        release=str(AIO_RELEASE),
        source_ref="releases/v1.5.x/2612",
        source_commit="3542da1961157e38ccac600f88cbd2ca127c4faa",
        instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE,
        opcua_connector_version=OPCUA_CONNECTOR_VERSION,
    )
    profiles = [stable]
    if PREVIEW_PROFILE is not None:
        profiles.append(PREVIEW_PROFILE)
    return RuntimeProfileCatalog(profiles, QUALIFICATION_IDENTITIES, SHARED_DEPENDENCY_REQUIREMENTS)
