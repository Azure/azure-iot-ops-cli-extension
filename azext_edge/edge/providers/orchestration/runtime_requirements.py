# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Owner-supplied capability restrictions, independent of command Preview labels."""

from typing import Dict, Tuple

from ...util import parse_kvp_nargs
from .runtime import OperationRequirements, ParameterRequirement


# Register only communicated restrictions; a Preview help label alone is not a
# runtime restriction. Keys for component settings use their dotted --feature syntax.
COMMAND_REQUIREMENTS: Dict[str, OperationRequirements] = {}
PARAMETER_REQUIREMENTS: Dict[str, Tuple[ParameterRequirement, ...]] = {}


def get_runtime_requirements(command: str, cmd=None):
    metadata = vars(cmd) if cmd is not None else {}
    requirement = metadata.get("runtime_requirement") or COMMAND_REQUIREMENTS.get(command)
    parameters = tuple(PARAMETER_REQUIREMENTS.get(command, ())) + tuple(metadata.get("runtime_parameters", ()))
    return requirement, parameters


def requested_selections(arguments: dict) -> dict:
    selections = dict(arguments)
    selections.update(parse_kvp_nargs(arguments.get("instance_features")) or {})
    return selections


def validate_runtime_requirements(command: str, identity, arguments: dict, cmd=None) -> None:
    """Lifecycle check using explicit CLI selections, or supplied programmatic arguments.

    The invocation hook records selections on the per-target command copy. Reading
    that snapshot also avoids mistaking handler defaults/renamed arguments for user
    requests. Direct provider callers retain validation of their supplied arguments.
    """
    requirements, parameters = get_runtime_requirements(command, cmd)
    if requirements is not None:
        requirements.validate_identity(identity)
    arguments = vars(cmd).get("runtime_requested_arguments", arguments) if cmd is not None else arguments
    selections = requested_selections(arguments)
    for parameter in parameters:
        if parameter.applies(selections):
            parameter.requirements.validate_identity(identity)
