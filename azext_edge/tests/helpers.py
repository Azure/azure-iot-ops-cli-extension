# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os
import shutil
from fnmatch import fnmatch
from knack.log import get_logger
from typing import Any, Dict, List, Optional, Union
from azure.cli.core.azclierror import CLIInternalError
import pytest

from azext_edge.edge.providers.edge_api.base import EdgeResourceApi

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
        if not any([
            # there is no valid resource match when looking for one
            resource_match and not fnmatch(name, resource_match),
            # or there is no valid prefix when looking for one
            prefixes and not any(name.startswith(prefix) for prefix in prefixes)
        ]):
            filtered[name] = item
    return filtered


def find_extra_or_missing_names(
    resource_type: str,
    result_names: List[str],
    expected_names: List[str],
    ignore_extras: bool = False,
    # TODO: remove once dynamic pods check logic is implemented
    ignore_missing: bool = False
):
    error_msg = []
    extra_names = [name for name in result_names if name not in expected_names]
    if extra_names:
        msg = f"Extra {resource_type} names: {', '.join(extra_names)}."
        if ignore_extras:
            logger.warning(msg)
        else:
            error_msg.append(msg)
    missing_names = [name for name in expected_names if name not in result_names]
    if missing_names:
        error_msg.append(f"Missing {resource_type} names: {', '.join(missing_names)}.")

    if error_msg:
        if ignore_missing:
            logger.warning('\n '.join(error_msg))
        else:
            raise AssertionError('\n '.join(error_msg))


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
    include_plural: bool = False
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
        resource_map[kind] = filter_resources(
            kubectl_items=cluster_resources,
            resource_match=resource_match
        )

        if plural_map.get(kind):
            resource_map[kind][PLURAL_KEY] = plural_map[kind]
    return resource_map


def get_kubectl_workload_items(
    prefixes: Union[str, List[str]],
    service_type: str,
    namespace: Optional[str] = None,
    resource_match: Optional[str] = None,
) -> Dict[str, Any]:
    """Gets workload kubectl items for a specific type (ex: pods)."""
    if service_type == "pvc":
        service_type = "persistentvolumeclaim"
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    namespace_param = f"-n {namespace}" if namespace else "-A"
    kubectl_items = run(f"kubectl get {service_type} {namespace_param} -o json")
    return filter_resources(
        kubectl_items=kubectl_items,
        prefixes=prefixes,
        resource_match=resource_match
    )


def remove_file_or_folder(file_path):
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.error(f"Failed to remove file: {file_path}. {e}")
    if os.path.isdir(file_path):
        try:
            shutil.rmtree(file_path)
        except OSError as e:
            logger.error(f"Failed to remove directory: {file_path}. {e}")


def run(command: str, shell_mode: bool = True, expect_failure: bool = False):
    """
    Wrapper function for run_host_command used for testing.
    Parameter `expect_failure` determines if an error will be raised for the command result.
    The output is converted to non-binary text and loaded as a json if possible.
    """
    import subprocess

    result = subprocess.run(
        command, check=False, shell=shell_mode, text=True, capture_output=True
    )
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
    kubectl_items: Dict[str, Any],
    include_all: bool = False
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
