# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bundled release inputs, separate from runtime selection and validation machinery."""

from typing import Optional, Tuple

from azext_edge.constants import AIO_RELEASE

from ...util.az_client import IoTOpsMgmtApiVersion
from .common import OPCUA_CONNECTOR_VERSION
from .runtime_dependencies import DependencyRequirement
from .runtime_profiles import RuntimeChannel, RuntimeIdentity, RuntimeProfile, RuntimeProfileCatalog
from .template import TEMPLATE_BLUEPRINT_INSTANCE
from .template_preview import TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW


PREVIEW_PROFILE: Optional[RuntimeProfile] = RuntimeProfile(
    channel=RuntimeChannel.PREVIEW,
    release="prev2610",
    source_ref="preview/v1.6.x/2610",
    source_commit="f306f5abaf891dddf7a1f9db00b13a8a742d5ad8",
    instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW,
    opcua_connector_version="1.5.19",
    iotops_api_version=IoTOpsMgmtApiVersion.V20261101_preview.value,
)
QUALIFICATION_IDENTITIES: Tuple[RuntimeIdentity, ...] = ()
# GA and preview share the same init dependency versions and trains.
# No additional dependency compatibility constraints are specified for this release.
# An empty policy leaves the existing shared foundation checks unchanged.
SHARED_DEPENDENCY_REQUIREMENTS: Tuple[DependencyRequirement, ...] = ()


def get_runtime_catalog() -> RuntimeProfileCatalog:
    stable = RuntimeProfile(
        channel=RuntimeChannel.STABLE,
        release=str(AIO_RELEASE),
        source_ref="releases/v1.5.x/2610",
        source_commit="7b3394800282382ca61654842fc466e6a0be33dd",
        instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE,
        opcua_connector_version=OPCUA_CONNECTOR_VERSION,
    )
    profiles = [stable]
    if PREVIEW_PROFILE is not None:
        profiles.append(PREVIEW_PROFILE)
    return RuntimeProfileCatalog(profiles, QUALIFICATION_IDENTITIES, SHARED_DEPENDENCY_REQUIREMENTS)
