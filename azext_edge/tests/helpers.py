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


def filter_resources(
    kubectl_items: List[Dict[str, Any]],
    prefixes: Optional[Union[str, List[str]]] = None,
    resource_match: Optional[str] = None,
) -> Dict[str, Any]:
    def pass_conditions(item: Dict[str, Any]) -> bool:
        name = item["metadata"]["name"]
        if resource_match and not fnmatch(name, resource_match):
            return False
        if prefixes and not any([name.startswith(prefix) for prefix in prefixes]):
            return False
        return True

    filtered = {}
    for item in kubectl_items["items"]:
        if pass_conditions(item):
            filtered[item["metadata"]["name"]] = item
    return filtered


def find_extra_or_missing_names(
    resource_type: str, result_names: List[str], expected_names: List[str], ignore_extras: bool = False
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
        raise AssertionError('\n '.join(error_msg))


def get_kubectl_workload_items(
    prefixes: Union[str, List[str]],
    service_type: str,
    namespace: Optional[str] = None,
    resource_match: Optional[str] = None,
) -> Dict[str, Any]:
    if service_type == "pvc":
        service_type = "persistentvolumeclaim"
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    namespace_param = f"-n {namespace}" if namespace else "-A"
    kubectl_items = run(f"kubectl get {service_type}s {namespace_param} -o json")
    return filter_resources(
        kubectl_items=kubectl_items,
        prefixes=prefixes,
        resource_match=resource_match
    )


def get_custom_resource_kind_items(
    resource_api: EdgeResourceApi,
    namespace: Optional[str] = None,
    resource_match: Optional[str] = None,
):
    plural_map: Dict[str, str] = {}
    try:
        # prefer to use another tool to get resources
        api_table = run(f"kubectl api-resources --api-group={resource_api.group}")
        api_resources = [line.split() for line in api_table.split("\n")]
        api_resources = api_resources[1:-1]
        plural_map = {line[-1].lower(): line[0] for line in api_resources}
    except CLIInternalError:
        pytest.skip("Cannot access resources via kubectl.")

    namespace = f"-n {namespace}" if namespace else "-A"
    resource_map = {}
    for kind in resource_api.kinds:
        cluster_resources = {}
        if plural_map.get(kind):
            cluster_resources = run(
                f"kubectl get {plural_map[kind]}.{resource_api.version}.{resource_api.group} {namespace} -o json"
            )
        resource_map[kind] = filter_resources(
            kubectl_items=cluster_resources,
            resource_match=resource_match
        )
    return resource_map


def parse_rest_command(rest_command: str) -> Dict[str, str]:
    """Simple az rest command parsing."""
    assert rest_command.startswith("rest")
    rest_list = rest_command.split("--")[1:]
    result = {}
    for rest_input in rest_list:
        key, value = rest_input.split(maxsplit=1)
        result[key] = value.strip()
    return result


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
        command, check=False, shell=shell_mode, text=True, capture_output=True, encoding="utf-8", errors="replace"
    )
    if expect_failure and result.returncode == 0:
        raise CLIInternalError(f"Command `{command}` did not fail as expected.")
    elif not expect_failure and result.returncode != 0:
        raise CLIInternalError(result.stderr)

    if result.stdout:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout
