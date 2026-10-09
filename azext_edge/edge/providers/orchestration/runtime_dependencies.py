# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Explicit shared foundation compatibility, not inferred from AIO's channel or version."""

from dataclasses import dataclass
from typing import Tuple

from azure.cli.core.azclierror import ValidationError

from ...util.machinery import scoped_semver_import
from .common import OPS_EXTENSION_DEPS


def _version(value):
    try:
        return scoped_semver_import().parse(value)
    except (TypeError, ValueError) as ex:
        raise ValidationError(f"Unable to validate foundation extension version {value!r}.") from ex


@dataclass(frozen=True)
class DependencyIdentity:
    version: str
    train: str

    def __post_init__(self):
        _version(self.version)
        if not isinstance(self.train, str) or not self.train:
            raise ValidationError("Foundation compatibility requires an explicit release train.")
        object.__setattr__(self, "train", self.train.lower())


@dataclass(frozen=True)
class DependencyRequirement:
    extension_type: str
    identities: Tuple[DependencyIdentity, ...]
    required_configuration: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self):
        if not isinstance(self.extension_type, str) or self.extension_type.lower() not in OPS_EXTENSION_DEPS:
            raise ValidationError("Compatibility requirements must identify a shared foundation extension type.")
        object.__setattr__(self, "extension_type", self.extension_type.lower())
        object.__setattr__(self, "identities", tuple(self.identities))
        object.__setattr__(self, "required_configuration", tuple(tuple(item) for item in self.required_configuration))
        if not self.identities:
            raise ValidationError("Foundation compatibility requires at least one reviewed version/train pair.")
        if not all(isinstance(identity, DependencyIdentity) for identity in self.identities):
            raise ValidationError("Foundation compatibility requires reviewed version/train identities.")
        if any(len(item) != 2 or not all(isinstance(value, str) for value in item)
               for item in self.required_configuration):
            raise ValidationError("Foundation compatibility configuration must contain string key/value pairs.")
        keys = [key for key, _ in self.required_configuration]
        if len(set(keys)) != len(keys):
            raise ValidationError("Duplicate required foundation configuration keys.")

    def validate_identity(self, version: str, train: str, configuration: dict) -> None:
        identity = DependencyIdentity(version, train)
        if identity not in self.identities:
            supported = ", ".join(f"{item.version}/{item.train}" for item in self.identities)
            raise ValidationError(
                f"Foundation extension {self.extension_type} uses {version}/{train}; "
                f"the bundled compatibility policy supports: {supported}. "
                "Use compatible foundation inputs before continuing."
            )
        if not isinstance(configuration, dict):
            raise ValidationError(f"Foundation extension {self.extension_type} reports invalid configuration.")
        for key, value in self.required_configuration:
            if configuration.get(key) != value:
                raise ValidationError(
                    f"Foundation extension {self.extension_type} requires configuration {key}={value}."
                )

    def validate_installed(self, extension: dict) -> None:
        self.validate_observed(extension)
        properties = extension.get("properties") or {}
        self.validate_identity(
            properties.get("currentVersion"), properties.get("releaseTrain"),
            properties.get("configurationSettings", {}),
        )

    def validate_observed(self, extension: dict, allow_repair: bool = False) -> None:
        """Validate observed evidence separately from a planned target's compatibility."""
        properties = extension.get("properties") or {}
        version = properties.get("currentVersion")
        if not version:
            raise ValidationError(
                f"Unable to determine installed {self.extension_type} version: currentVersion missing."
            )
        if str(properties.get("extensionType", "")).lower() != self.extension_type:
            raise ValidationError("Foundation compatibility record does not match the required extension type.")
        DependencyIdentity(version, properties.get("releaseTrain"))
        state = str(properties.get("provisioningState") or "").lower()
        repairing = allow_repair and state in {"failed", "canceled"}
        if state != "succeeded" and not repairing:
            raise ValidationError(f"Foundation extension {self.extension_type} is not ready.")
        statuses = properties.get("statuses", [])
        if not isinstance(statuses, list) or any(not isinstance(item, dict) for item in statuses):
            raise ValidationError(f"Foundation extension {self.extension_type} reports invalid or failed status.")
        if not repairing and (
            any(str(item.get("level", "")).lower() == "error" for item in statuses) or properties.get("errorInfo")
        ):
            raise ValidationError(f"Foundation extension {self.extension_type} reports invalid or failed status.")
        requested = properties.get("version")
        if requested is not None and _version(requested) != _version(version) and not repairing:
            raise ValidationError(
                f"Foundation extension {self.extension_type} requested and installed versions differ."
            )
