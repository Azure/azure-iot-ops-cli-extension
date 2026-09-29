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


# Point to the supplied terms rather than reproducing or adding legal terms here.
PREVIEW_AGREEMENT_URL = "https://azure.microsoft.com/en-us/support/legal/preview-supplemental-terms/"
PREVIEW_NOTICE = (
    "You are creating an Azure IoT Operations preview instance. "
    "Use of the preview is subject to the Supplemental Terms of Use for Microsoft Azure Previews "
    "at the following URL."
)

# Keep the existing GA-bound blueprint and its actual train unchanged. In an alpha
# build this may still deploy from integration; it is not silently promoted to stable.
# Register the preview source as supplied, including its actual integration train.
# Registration selects release inputs; it is not a claim of live qualification.
PREVIEW_PROFILE: Optional[RuntimeProfile] = RuntimeProfile(
    channel=RuntimeChannel.PREVIEW,
    release="prev2610",
    source_ref="preview/v1.6.x/2610",
    source_commit="6e1521ebb4893f2db20b4d97187c5ff9c211326f",
    instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW,
    preview_notice=PREVIEW_NOTICE,
    preview_agreement_url=PREVIEW_AGREEMENT_URL,
    opcua_connector_version="1.4.0-alpha.164",
    iotops_api_version=IoTOpsMgmtApiVersion.V20260901_preview.value,
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
        source_ref=TEMPLATE_BLUEPRINT_INSTANCE.commit_id,
        source_commit=TEMPLATE_BLUEPRINT_INSTANCE.commit_id,
        instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE,
        opcua_connector_version=OPCUA_CONNECTOR_VERSION,
    )
    profiles = [stable]
    if PREVIEW_PROFILE is not None:
        profiles.append(PREVIEW_PROFILE)
    return RuntimeProfileCatalog(profiles, QUALIFICATION_IDENTITIES, SHARED_DEPENDENCY_REQUIREMENTS)
