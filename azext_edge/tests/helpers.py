# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os
from fnmatch import fnmatch
from knack.log import get_logger
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from azure.cli.core.azclierror import CLIInternalError
import pytest

from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from azext_edge.edge.providers.orchestration.resource_map import IoTOperationsResource
from azext_edge.tests.generators import generate_random_string

logger = get_logger(__name__)

PLURAL_KEY = "_plural_"


def filter_resources(
    kubectl_items: List[Dict[str, Any]],
    prefixes: Optional[Union[str, List[str]]] = None,
    resource_match: Optional[str] = None,
) -> Dict[str, Any]:
    filtered = {}
    for item in kubectl_items.get("items", []):
        name = item["metadata"]["name"]
        # resources should not be added if
        if not any(
            [
                # there is no valid resource match when looking for one
                resource_match and not fnmatch(name, resource_match),
                # or there is no valid prefix when looking for one
                prefixes and not any(name.startswith(prefix) for prefix in prefixes),
            ]
        ):
            filtered[name] = item
    return filtered


def find_extra_or_missing_names(
    resource_type: str,
    result_names: List[str],
    pre_expected_names: List[str],
    post_expected_names: List[str],
    ignore_extras: bool = False,
    ignore_missing: bool = False,
):
    """
    Checks the result to find missing or extra names.
    First checks the result name against the names in the kubectl results from before the result was fetched.
    If anything is missing/extra, checks against the kubectl results from after the result was fetched.
    """
    error_msg = []
    # names may contain descriptors after the initial '.', just comparing first prefix
    # vilit double check if ^ is still needed

    extra_names = [name for name in result_names if name not in pre_expected_names]
    extra_names = [name for name in extra_names if name not in post_expected_names]
    if extra_names:
        msg = f"Extra {resource_type} names: {', '.join(extra_names)}"
        if ignore_extras:
            logger.warning(msg)
        else:
            error_msg.append(msg)

    missing_names = [name for name in pre_expected_names if name not in result_names]
    missing_names = [name for name in missing_names if name in post_expected_names]
    if missing_names:
        error_msg.append(f"Missing {resource_type} names: {', '.join(missing_names)}")

    if error_msg:
        if ignore_missing:
            logger.warning("\n ".join(error_msg))
        else:
            raise AssertionError("\n ".join(error_msg))


def get_plural_map(
    api_group: str,
) -> Dict[str, str]:
    """Returns a mapping of resource type to it's plural value."""
    plural_map: Dict[str, str] = {}
    try:
        api_table = run(f"kubectl api-resources --api-group={api_group} --no-headers=true")
        api_resources = [line.split() for line in api_table.strip().split("\n")]
        plural_map = {line[-1].lower(): line[0] for line in api_resources}
    except CLIInternalError:
        pytest.skip("Cannot access resources via kubectl.")
    return plural_map


def get_kubectl_custom_items(
    resource_api: EdgeResourceApi,
    namespace: Optional[str] = None,
    resource_match: Optional[str] = None,
    include_plural: bool = False,
) -> Dict[str, Any]:
    """
    Gets all kubectl custom items for a resource api and sorts it by type.
    Dictionary keys are resource api kinds and the values are the unchanged items.
    """
    plural_map = {}
    if include_plural:
        plural_map = get_plural_map(resource_api.group)

    namespace = f"-n {namespace}" if namespace else "-A"
    resource_map = {}
    for kind in resource_api.kinds:
        cluster_resources = {}
        try:
            cluster_resources = run(
                f"kubectl get {kind}.{resource_api.version}.{resource_api.group} {namespace} -o json"
            )
        except CLIInternalError:
            # sub resource like lnm scales
            pass
        resource_map[kind] = filter_resources(kubectl_items=cluster_resources, resource_match=resource_match)

        if plural_map.get(kind):
            resource_map[kind][PLURAL_KEY] = plural_map[kind]
    return resource_map


def get_kubectl_workload_items(
    prefixes: Union[str, List[str]],
    service_type: str,
    namespace: Optional[str] = None,
    resource_match: Optional[str] = None,
    label_match: Optional[Tuple[str, str]] = None,
) -> Dict[str, Any]:
    """Gets workload kubectl items for a specific type (ex: pods)."""
    if service_type == "pvc":
        service_type = "persistentvolumeclaim"
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    namespace_param = f"-n {namespace}" if namespace else "-A"
    label_param = f"--selector {label_match[0]}={label_match[1]}" if label_match else ""
    kubectl_items = run(f"kubectl get {service_type} {namespace_param} {label_param} -o json")
    return filter_resources(kubectl_items=kubectl_items, prefixes=prefixes, resource_match=resource_match)


def get_multi_kubectl_workload_items(
    expected_workload_types: Union[str, List[str]],
    prefixes: Union[str, List[str]],
    expected_label: Optional[Tuple[str, str]] = None
) -> Dict[str, Iterable[str]]:
    """
    Fetch a list of the workload resources via kubectl.
    Returns a mapping of workload type to another mapping of name to resource.
    """
    result = {}
    if not isinstance(expected_workload_types, list):
        expected_workload_types = [expected_workload_types]
    for key in expected_workload_types:
        items = get_kubectl_workload_items(prefixes, service_type=key, label_match=expected_label)
        result[key] = items
    return result


def create_file(
    file_name: str, module_file: str, tracked_files: List[str], content: str, encoding: str = "utf-8"
) -> str:
    """
    Creates a file in the module directory and return the full file path.

    module_file must be __file__ to put the created file in the right directory
    """
    from pathlib import PurePath
    file_path = PurePath(PurePath(module_file).parent, file_name)
    with open(file_path, "w", encoding=encoding) as f:
        f.write(content)
    tracked_files.append(file_path)
    return file_path


def remove_file(file_path):
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.error(f"Failed to remove file: {file_path}. {e}")


def run(command: str, shell_mode: bool = True, expect_failure: bool = False):
    """
    Wrapper function for run_host_command used for testing.
    Parameter `expect_failure` determines if an error will be raised for the command result.
    The output is converted to non-binary text and loaded as a json if possible.
    Raises CLIInternalError if there is an unexpected error or an unexpected success.
    """
    import subprocess

    result = subprocess.run(command, check=False, shell=shell_mode, text=True, capture_output=True, encoding="utf-8")
    if expect_failure and result.returncode == 0:
        raise CLIInternalError(f"Command `{command}` did not fail as expected.")
    elif not expect_failure and result.returncode != 0:
        # logger since pytest can cut off long commands
        logger.error(f"Command `{command}` failed.")
        raise CLIInternalError(result.stderr)

    if result.stdout:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout


def sort_kubectl_items_by_namespace(
    kubectl_items: Dict[str, Any], include_all: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Transforms a list of kubectl items into a dictionary for easier access.
    The keys are the names and the values are the unchanged items.
    """
    sorted_items = {}
    if include_all:
        sorted_items["_all_"] = {}
    for name, item in kubectl_items.items():
        if name == PLURAL_KEY:
            continue
        namespace = item["metadata"]["namespace"]
        if namespace not in sorted_items:
            sorted_items[namespace] = {}
        sorted_items[namespace][name] = item
        if include_all:
            sorted_items["_all_"][name] = item
    return sorted_items


def process_additional_args(additional_args: str) -> Dict[str, Union[str, bool]]:
    """
    Process additional args for init, create, upgrade into dictionaries that can be passed in as kwargs.

    This will transform the args into variable friendly keys (- into _).
    Flag arguments will be converted to have the boolean value.

    Examples:
    --simulate-plc -> {"simulate_plc": True}
    --desc "potato cluster" -> {"desc": "potato cluster"}
    """
    arg_dict = {}
    if not additional_args:
        return arg_dict
    for arg in additional_args.split("--")[1:]:
        arg = arg.strip().split(" ", maxsplit=1)
        # --simulate-plc vs --desc "potato cluster"
        arg[0] = arg[0].replace("-", "_")
        if len(arg) == 1 or arg[1].lower() == "true":
            arg_dict[arg[0]] = True
        elif arg[1].lower() == "false":
            arg_dict[arg[0]] = False
        else:
            arg_dict[arg[0]] = arg[1]
    return arg_dict


def strip_quotes(argument: Optional[str]) -> Optional[str]:
    """Get rid of extra quotes when dealing with pipeline inputs."""
    if not argument:
        return argument
    if argument[0] == argument[-1] and argument[0] in ("'", '"'):
        argument = argument[1:-1]
    return argument


def generate_ops_resource(segments: int = 1) -> IoTOperationsResource:
    resource_id = ""
    for _ in range(segments):
        resource_id = f"{resource_id}/{generate_random_string()}"

    resource = IoTOperationsResource(
        resource_id=resource_id,
        display_name=resource_id.split("/")[-1],
        api_version=generate_random_string(),
    )

    return resource
