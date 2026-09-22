# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Opt-in runtime eligibility for extension commands, independent of CLI maturity.

Command registrations accept runtime_requirement=OperationRequirements(...),
runtime_parameters=(ParameterRequirement(...), ...), and optionally
runtime_target=RuntimeTarget(instance_name="other_name", resource_group_name="other_rg").
Parameter rules use handler argument destinations, or dotted --feature keys. A rule
with values restricts only those explicitly selected values, not the whole option.
No handler changes or is_preview tag are needed. The central requirement registries
are also supported. An unusual resource hierarchy can supply a runtime_target callable
(cmd, namespace) returning a RuntimeContext, instead of an argument mapping.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Optional

from azure.cli.core.azclierror import ValidationError
from azure.cli.core.commands import AzCommandGroup

from .runtime_requirements import get_runtime_requirements, requested_selections


# These entry points already discover their runtime (or select a create profile)
# and enforce requirements before writes. Keep their repair/readiness semantics.
LIFECYCLE_COMMANDS = frozenset({"iot ops create", "iot ops update", "iot ops upgrade"})


@dataclass(frozen=True)
class RuntimeTarget:
    """Argument destinations for an instance target; subscription defaults to the CLI job context."""

    instance_name: str = "instance_name"
    resource_group_name: str = "resource_group_name"
    subscription_id: Optional[str] = None

    def __call__(self, cmd, namespace):
        from .resources.instances import Instances
        from .runtime_catalog import get_runtime_catalog

        name = getattr(namespace, self.instance_name, None)
        resource_group = getattr(namespace, self.resource_group_name, None)
        subscription = getattr(namespace, self.subscription_id, None) if self.subscription_id else None
        if not name or not resource_group or (self.subscription_id and not subscription):
            raise ValidationError(
                f"Cannot resolve the AIO runtime for '{cmd.name}'. Supply the instance target arguments "
                "or register a runtime_target mapping/resolver."
            )
        instances = Instances(cmd, subscription_id=subscription)
        instance = instances.show(name=name, resource_group_name=resource_group)
        return instances.get_runtime_context(instance, get_runtime_catalog().qualification_identities)


class RuntimeCommandGroup(AzCommandGroup):
    """Consume extension metadata without passing unsupported keywords to Azure CLI."""

    def _command(self, name, method_name, custom_command=False, **kwargs):
        requirement = kwargs.pop("runtime_requirement", None)
        parameters = tuple(kwargs.pop("runtime_parameters", ()))
        target = kwargs.pop("runtime_target", RuntimeTarget())
        command_name = super()._command(name, method_name, custom_command=custom_command, **kwargs)
        command = self.command_loader.command_table.get(command_name)
        if command is not None:
            command.runtime_requirement = requirement
            command.runtime_parameters = parameters
            command.runtime_target = target
        return command_name


def runtime_validation_handler(cli_ctx, **kwargs):
    """Capture selections after parsing; defer discovery until after --ids expansion.

    Azure CLI validates every expanded job before executing any handlers. Chaining
    its existing validator here preserves argument validation and per-job subscription
    context. Help exits before this event; unmarked commands never discover a runtime.
    """
    namespace = kwargs.get("args")
    command_name = kwargs.get("command")
    if namespace is None or not command_name:
        return
    command = namespace.func
    # Events are global: do not change commands supplied by another extension/loader.
    if "runtime_target" not in vars(command):
        return
    requirement, parameters = get_runtime_requirements(command_name, command)
    lifecycle = command_name in LIFECYCLE_COMMANDS
    if requirement is None and not parameters and not lifecycle:
        return

    invoker = cli_ctx.invocation
    parser = invoker.parser.subparser_map[command_name]
    specified = frozenset(parser.specified_arguments)
    original_validator = getattr(namespace, "_command_validator", None)

    def validate(cmd, namespace):
        # Capture the expanded, explicit values before validators inject defaults or
        # rewrite aliases. This state belongs to this job, never the shared command.
        selections = deepcopy({key: value for key, value in vars(namespace).items() if key in specified})
        cmd.runtime_requested_arguments = selections
        if original_validator:
            invoker._validate_cmd_level(namespace, original_validator)  # pylint: disable=protected-access
        else:
            invoker._validate_arg_level(namespace)  # pylint: disable=protected-access
        if lifecycle:
            return
        requested = requested_selections(selections)
        active = [rule.requirements for rule in parameters if rule.applies(requested)]
        if requirement is not None:
            active.insert(0, requirement)
        if not active:
            return
        runtime = command.runtime_target(cmd, namespace)
        runtime.require_ready()
        for rule in active:
            rule.validate_identity(runtime.identity)

    namespace._command_validator = validate  # pylint: disable=protected-access
