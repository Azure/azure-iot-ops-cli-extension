# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Read-only runtime discovery and capability checks. Never called while constructing help."""

from dataclasses import dataclass
from typing import Any, FrozenSet, Iterable, Mapping, Optional, Tuple

from azure.cli.core.azclierror import ValidationError

from ...util.id_tools import is_valid_resource_id, parse_resource_id
from .common import EXTENSION_TYPE_OPS
from .runtime_profiles import RuntimeChannel, RuntimeIdentity, parse_runtime_version, resolve_runtime_identity


def _lower(value) -> str:
    return value.lower() if isinstance(value, str) else ""


def _resource_id(value: str, namespace: str, resource_type: str) -> str:
    if not isinstance(value, str) or not is_valid_resource_id(value):
        raise ValidationError(f"Unable to resolve runtime: invalid {resource_type} resource ID.")
    parsed = parse_resource_id(value)
    if (
        parsed.get("namespace", "").lower() != namespace.lower()
        or parsed.get("type", "").lower() != resource_type.lower()
        or parsed.get("last_child_num")
        or not parsed.get("resource_group")
    ):
        raise ValidationError(f"Unable to resolve runtime: expected a {namespace}/{resource_type} resource ID.")
    return value


def get_runtime_cluster_id(instance: dict, custom_location: dict) -> str:
    """Validate the association before using its cluster ID to construct subscription-scoped clients."""
    _resource_id(instance.get("id"), "Microsoft.IoTOperations", "instances")
    location_id = _resource_id(
        (instance.get("extendedLocation") or {}).get("name"), "Microsoft.ExtendedLocation", "customLocations"
    )
    returned_id = _resource_id(custom_location.get("id"), "Microsoft.ExtendedLocation", "customLocations")
    if location_id.lower() != returned_id.lower():
        raise ValidationError("The custom location does not match the instance's extended location.")
    return _resource_id(
        (custom_location.get("properties") or {}).get("hostResourceId"), "Microsoft.Kubernetes", "connectedClusters"
    )


@dataclass(frozen=True)
class RuntimeContext:
    instance_id: str
    custom_location_id: str
    cluster_id: str
    extension_id: str
    identity: RuntimeIdentity
    requested_version: Optional[str]
    provisioning_state: Optional[str]
    readiness_issues: Tuple[str, ...] = ()

    def require_ready(self) -> None:
        if self.readiness_issues:
            raise ValidationError("AIO runtime is not ready: " + "; ".join(self.readiness_issues))

    def require_upgradeable(self) -> None:
        # A known failed extension can be reconciled, but not while another operation
        # is in flight. Missing identity/association information has already failed discovery.
        if _lower(self.provisioning_state) not in {"failed", "canceled"}:
            self.require_ready()
            return
        blockers = [
            issue for issue in self.readiness_issues
            if not issue.startswith(("extension provisioning state", "extension reports", "requested version"))
        ]
        if blockers:
            raise ValidationError("AIO runtime cannot be upgraded: " + "; ".join(blockers))


def resolve_runtime(
    instance: dict,
    custom_location: dict,
    cluster: dict,
    extensions: Iterable[dict],
    qualification_identities: Iterable[RuntimeIdentity] = (),
) -> RuntimeContext:
    """Validate live ARM records without guessing an installed version from the requested pin."""
    cluster_id = get_runtime_cluster_id(instance, custom_location)
    returned_id = _resource_id(cluster.get("id"), "Microsoft.Kubernetes", "connectedClusters")
    if cluster_id.lower() != returned_id.lower():
        raise ValidationError("The connected cluster does not match the custom location's host.")
    matches = [
        extension for extension in extensions
        if _lower((extension.get("properties") or {}).get("extensionType")) == EXTENSION_TYPE_OPS
    ]
    if len(matches) != 1:
        raise ValidationError("Expected exactly one AIO extension on the associated connected cluster.")
    extension = matches[0]
    extension_id = extension.get("id")
    prefix = cluster_id.lower() + "/providers/microsoft.kubernetesconfiguration/extensions/"
    if (
        not isinstance(extension_id, str)
        or not is_valid_resource_id(extension_id)
        or not extension_id.lower().startswith(prefix)
        or not extension_id[len(prefix):]
        or "/" in extension_id[len(prefix):]
    ):
        raise ValidationError("The AIO extension does not belong to the associated connected cluster.")
    associated_ids = (custom_location.get("properties") or {}).get("clusterExtensionIds")
    if not isinstance(associated_ids, list) or extension_id.lower() not in {
        value.lower() for value in associated_ids if isinstance(value, str)
    }:
        raise ValidationError("The custom location is not associated with the AIO extension.")

    properties = extension.get("properties") or {}
    installed_version = properties.get("currentVersion")
    if not installed_version:
        raise ValidationError("Unable to determine installed AIO version: extension currentVersion is missing.")
    identity = resolve_runtime_identity(installed_version, properties.get("releaseTrain"), qualification_identities)
    issues = []
    for name, record in (("instance", instance), ("custom location", custom_location), ("extension", extension)):
        state = (record.get("properties") or {}).get("provisioningState")
        if not isinstance(state, str) or state.lower() != "succeeded":
            issues.append(f"{name} provisioning state is {state or 'unknown'}")
    if _lower((cluster.get("properties") or {}).get("connectivityStatus")) != "connected":
        issues.append("connected cluster is disconnected or its connectivity is unknown")
    statuses = properties.get("statuses", [])
    if not isinstance(statuses, list) or any(not isinstance(status, dict) for status in statuses):
        issues.append("extension status information is invalid")
    elif any(_lower(status.get("level")) == "error" for status in statuses):
        issues.append("extension reports an error")
    if properties.get("errorInfo"):
        issues.append("extension reports an error")
    requested_version = properties.get("version")
    if requested_version is not None:
        requested = parse_runtime_version(requested_version)
        if requested != parse_runtime_version(installed_version):
            issues.append(f"requested version {requested_version} differs from installed version {installed_version}")
    return RuntimeContext(
        instance_id=instance["id"],
        custom_location_id=custom_location["id"],
        cluster_id=cluster_id,
        extension_id=extension_id,
        identity=identity,
        requested_version=requested_version,
        provisioning_state=properties.get("provisioningState"),
        readiness_issues=tuple(issues),
    )


@dataclass(frozen=True)
class OperationRequirements:
    """Execution eligibility, not the command's CLI Preview label."""

    name: str
    channels: FrozenSet[RuntimeChannel] = frozenset(RuntimeChannel)
    minimum_version: Optional[str] = None
    maximum_version_exclusive: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "channels", frozenset(RuntimeChannel(channel) for channel in self.channels))
        minimum = parse_runtime_version(self.minimum_version) if self.minimum_version else None
        maximum = parse_runtime_version(self.maximum_version_exclusive) if self.maximum_version_exclusive else None
        if minimum is not None and maximum is not None and minimum >= maximum:
            raise ValidationError(f"Invalid runtime version range for {self.name}.")

    def validate(self, runtime: RuntimeContext) -> None:
        runtime.require_ready()
        self.validate_identity(runtime.identity)

    def validate_identity(self, identity: RuntimeIdentity) -> None:
        """Also usable before create, when a target identity exists but no instance does."""
        if identity.channel not in self.channels:
            allowed = ", ".join(sorted(channel.value for channel in self.channels))
            raise ValidationError(
                f"{self.name} requires a {allowed} runtime; the target uses {identity.channel.value}."
            )
        version = parse_runtime_version(identity.version)
        if self.minimum_version and version < parse_runtime_version(self.minimum_version):
            raise ValidationError(f"{self.name} requires AIO version {self.minimum_version} or newer.")
        if self.maximum_version_exclusive and version >= parse_runtime_version(self.maximum_version_exclusive):
            raise ValidationError(f"{self.name} requires AIO version older than {self.maximum_version_exclusive}.")


@dataclass(frozen=True)
class ParameterRequirement:
    parameter: str
    requirements: OperationRequirements
    values: Optional[FrozenSet[Any]] = None

    def __post_init__(self):
        if self.values is not None:
            object.__setattr__(self, "values", frozenset(self.values))

    def applies(self, requested_arguments: Mapping[str, Any]) -> bool:
        if self.parameter not in requested_arguments:
            return False
        value = requested_arguments[self.parameter]
        if value is None:
            return False
        if self.values is None:
            return True
        values = value if isinstance(value, (list, tuple, set, frozenset)) else (value,)
        return any(value in self.values for value in values)


def validate_operation(
    runtime: RuntimeContext,
    requirements: OperationRequirements,
    requested_arguments: Optional[Mapping[str, Any]] = None,
    parameter_requirements: Iterable[ParameterRequirement] = (),
) -> None:
    """Check a command and its requested selections before any writer/feature invocation.

    Callers supply requested selections, not parser defaults. In particular, an explicit
    False/0 is not the same as an omitted argument. Shared commands stay shared even if
    an individual option or value requires preview.
    """
    requirements.validate(runtime)
    for parameter in parameter_requirements:
        if parameter.applies(requested_arguments or {}):
            parameter.requirements.validate(runtime)
