# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Runtime release inputs, independent of the CLI package version and interface maturity.

Release-specific inputs are supplied by the profile catalog after generation and review.
An integration train is never implicitly treated as Public Preview.
"""

import re
from dataclasses import InitVar, dataclass, field
from enum import Enum
from typing import Iterable, Optional

from azure.cli.core.azclierror import ValidationError

from ...util.machinery import scoped_semver_import
from .common import EXTENSION_MONIKER_OPS
from .runtime_dependencies import DependencyRequirement
from .template import TemplateBlueprint


class RuntimeChannel(str, Enum):
    STABLE = "stable"
    PREVIEW = "preview"


def parse_runtime_version(version: str):
    try:
        return scoped_semver_import().parse(version)
    except (TypeError, ValueError) as ex:
        raise ValidationError(f"Unable to validate AIO runtime version {version!r}.") from ex


@dataclass(frozen=True)
class RuntimeIdentity:
    channel: RuntimeChannel
    version: str
    train: str

    def __post_init__(self):
        object.__setattr__(self, "channel", RuntimeChannel(self.channel))
        if not isinstance(self.train, str) or not self.train:
            raise ValidationError("Unable to determine AIO release train.")
        object.__setattr__(self, "train", self.train.lower())
        if self.train not in (self.channel.value, "integration"):
            raise ValidationError(f"Train {self.train!r} conflicts with the {self.channel.value} runtime profile.")
        version = parse_runtime_version(self.version)
        if self.channel == RuntimeChannel.STABLE:
            valid = version.prerelease is None
        else:
            valid = version.patch == 0 and re.fullmatch(r"preview\.[1-9][0-9]*", version.prerelease or "")
        if not valid:
            raise ValidationError(f"Version {self.version!r} conflicts with the {self.channel.value} runtime profile.")


@dataclass(frozen=True)
class RuntimeProfile:
    channel: RuntimeChannel
    release: str
    source_ref: str
    source_commit: str
    instance_blueprint: InitVar[TemplateBlueprint]
    preview_notice: Optional[str] = None
    preview_agreement_url: Optional[str] = None
    opcua_connector_version: Optional[str] = None
    identity: RuntimeIdentity = field(init=False)
    _instance_blueprint: TemplateBlueprint = field(init=False, repr=False, compare=False)

    def __post_init__(self, instance_blueprint: TemplateBlueprint):
        object.__setattr__(self, "channel", RuntimeChannel(self.channel))
        if not all(isinstance(value, str) and value for value in (self.release, self.source_ref, self.source_commit)):
            raise ValidationError("Runtime profiles require a release, source ref and resolved source commit.")
        blueprint = instance_blueprint.copy()
        variables = blueprint.content.get("variables", {})
        identity = RuntimeIdentity(
            channel=self.channel,
            version=variables.get("VERSIONS", {}).get(EXTENSION_MONIKER_OPS),
            train=variables.get("TRAINS", {}).get(EXTENSION_MONIKER_OPS),
        )
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "_instance_blueprint", blueprint)

    def copy_instance_blueprint(self) -> TemplateBlueprint:
        """Return a private working copy for both validation and deployment preparation."""
        return self._instance_blueprint.copy()

    def require_opcua_connector_version(self) -> str:
        if not self.opcua_connector_version:
            raise ValidationError(
                f"The {self.channel.value} profile has no reviewed OPC UA connector backfill version."
            )
        return self.opcua_connector_version

    def validate_overrides(self, version: Optional[str] = None, train: Optional[str] = None) -> RuntimeIdentity:
        target = RuntimeIdentity(self.channel, version or self.identity.version, train or self.identity.train)
        if target.train != self.identity.train:
            raise ValidationError("AIO train overrides cannot change the selected runtime profile's deployment train.")
        # Integration identities require an explicit, reviewed version/profile association.
        if target.train == "integration" and target.version != self.identity.version:
            raise ValidationError("An integration version override requires matching reviewed profile inputs.")
        return target


class RuntimeProfileCatalog:
    """One create/upgrade target per channel; not a list of every supported source runtime."""

    def __init__(
        self, profiles: Iterable[RuntimeProfile], qualification_identities: Iterable[RuntimeIdentity] = (),
        dependency_requirements: Iterable[DependencyRequirement] = (),
    ):
        self._profiles = {}
        for profile in profiles:
            if profile.channel in self._profiles:
                raise ValidationError(f"Multiple target profiles registered for {profile.channel.value}.")
            self._profiles[profile.channel] = profile
        self.qualification_identities = tuple(qualification_identities) + tuple(
            profile.identity for profile in self._profiles.values() if profile.identity.train == "integration"
        )
        self.dependency_requirements = tuple(dependency_requirements)
        types = [requirement.extension_type for requirement in self.dependency_requirements]
        if len(set(types)) != len(types):
            raise ValidationError("Duplicate shared foundation compatibility requirements.")

    def get(self, channel: RuntimeChannel) -> RuntimeProfile:
        channel = RuntimeChannel(channel)
        if channel not in self._profiles:
            raise ValidationError(f"No reviewed {channel.value} runtime profile is bundled in this CLI.")
        return self._profiles[channel]

    def for_create(self, use_preview: bool = False) -> RuntimeProfile:
        return self.get(RuntimeChannel.PREVIEW if use_preview else RuntimeChannel.STABLE)

    def for_upgrade(self, installed: RuntimeIdentity) -> RuntimeProfile:
        return self.get(installed.channel)

    def describe_profiles(self) -> dict:
        """Report bundled targets, not installed runtimes or qualified upgrade paths."""
        return {
            channel.value: {
                "release": profile.release,
                "version": profile.identity.version,
                "train": profile.identity.train,
                "sourceRef": profile.source_ref,
                "sourceCommit": profile.source_commit,
                "opcuaConnectorVersion": profile.opcua_connector_version,
            }
            for channel in RuntimeChannel
            if (profile := self._profiles.get(channel)) is not None
        }


def resolve_runtime_identity(
    version: str, train: str, qualification_identities: Iterable[RuntimeIdentity] = ()
) -> RuntimeIdentity:
    """Resolve public trains directly; integration requires an exact internal qualification mapping.

    A version suffix alone is not proof that a runtime is an approved Public Preview.
    Historical integration baselines can be supplied independently of the target catalog.
    """
    if not isinstance(train, str) or not train:
        raise ValidationError("Unable to determine AIO release train.")
    normalized_train = train.lower()
    if normalized_train in (RuntimeChannel.STABLE.value, RuntimeChannel.PREVIEW.value):
        return RuntimeIdentity(RuntimeChannel(normalized_train), version, normalized_train)
    if normalized_train == "integration":
        matches = {
            identity for identity in qualification_identities
            if identity.train == normalized_train and identity.version == version
        }
        if len(matches) == 1:
            return matches.pop()
    raise ValidationError(f"AIO runtime {version!r} on train {train!r} has no supported runtime profile mapping.")


def validate_upgrade_boundary(installed: RuntimeIdentity, target: RuntimeIdentity) -> None:
    """Mandatory boundary only; passing does NOT qualify a source/target migration path.

    This deliberately has no force/preflight override. Path-specific upgrade policies
    must run separately after this check and before any mutations.
    """
    if installed.channel != target.channel or installed.train != target.train:
        raise ValidationError(
            f"Cannot upgrade AIO from {installed.channel.value}/{installed.train} "
            f"to {target.channel.value}/{target.train}. "
            "GA clusters must remain GA; preview clusters must remain preview."
        )
    if parse_runtime_version(target.version) < parse_runtime_version(installed.version):
        raise ValidationError(f"AIO downgrade from {installed.version} to {target.version} is not supported.")
