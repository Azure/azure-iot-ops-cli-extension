# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Cloud-specific deployment inputs, independent of the selected runtime channel."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError

from ...util.cloud_config import CLOUD_AZURE_US_GOVERNMENT, CloudConfig
from .common import EXTENSION_MONIKER_CM, EXTENSION_MONIKER_SSC
from .runtime_profiles import RuntimeChannel
from .template import TEMPLATE_BLUEPRINT_ENABLEMENT, TEMPLATE_BLUEPRINT_INSTANCE, TemplateBlueprint

# Fairfax deployments are currently supported only in US Gov Virginia.
FAIRFAX_ALLOWED_LOCATIONS = ("usgovvirginia",)


@dataclass(frozen=True)
class DeploymentPolicy:
    cloud_name: str

    @property
    def is_fairfax(self) -> bool:
        return self.cloud_name == CLOUD_AZURE_US_GOVERNMENT

    def copy_enablement_blueprint(self) -> TemplateBlueprint:
        return TEMPLATE_BLUEPRINT_ENABLEMENT.copy()

    @property
    def foundation_targets(self) -> Dict[str, Dict[str, str]]:
        if not self.is_fairfax:
            return {}
        variables = TEMPLATE_BLUEPRINT_ENABLEMENT.content["variables"]
        return {
            moniker: {"version": variables["VERSIONS"][moniker], "train": variables["TRAINS"][moniker]}
            for moniker in (EXTENSION_MONIKER_CM, EXTENSION_MONIKER_SSC)
        }

    @property
    def aio_configuration(self) -> Dict[str, str]:
        if not self.is_fairfax:
            return {}
        return dict(TEMPLATE_BLUEPRINT_INSTANCE.content["variables"]["FAIRFAX_AIO_CONFIGURATION_SETTINGS"])

    @property
    def allowed_locations(self) -> Tuple[str, ...]:
        if not self.is_fairfax:
            return ()
        return FAIRFAX_ALLOWED_LOCATIONS

    def validate_runtime(self, channel: RuntimeChannel) -> None:
        if self.is_fairfax and channel == RuntimeChannel.PREVIEW:
            raise ValidationError(
                "The AIO preview runtime is not supported in AzureUSGovernment. "
                "Use the GA runtime without --use-preview."
            )

    def validate_location(self, location: Optional[str]) -> Optional[str]:
        if self.is_fairfax and location is not None:
            for value in self.allowed_locations:
                if location.replace(" ", "").lower() == value.replace(" ", "").lower():
                    return value
            raise InvalidArgumentValueError(
                "AIO GA deployment in AzureUSGovernment is supported only in "
                f"{', '.join(self.allowed_locations)}."
            )
        return location

    def merge_aio_configuration(self, overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        overrides = overrides or {}
        required = self.aio_configuration
        for key, value in required.items():
            if key in overrides and overrides[key] != value:
                raise InvalidArgumentValueError(
                    f"AIO configuration '{key}' must be '{value}' in AzureUSGovernment."
                )
        return {**required, **overrides}


def get_deployment_policy(cmd) -> DeploymentPolicy:
    return DeploymentPolicy(CloudConfig(cmd).name)
