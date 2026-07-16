# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os
from fnmatch import fnmatch
from time import sleep
from knack.log import get_logger
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union
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
    result_names: List[str],
    pre_expected_names: List[str],
    post_expected_names: List[str],
) -> Tuple[List[str], List[str]]:
    """
    Checks the result to find missing or extra names and returns lists of names.
    First checks the result name against the names in the kubectl results from before the result was fetched.
    If anything is missing/extra, checks against the kubectl results from after the result was fetched.
    """
    extra_names = [name for name in result_names if name not in pre_expected_names]
    extra_names = [name for name in extra_names if name not in post_expected_names]

    missing_names = [name for name in pre_expected_names if name not in result_names]
    missing_names = [name for name in missing_names if name in post_expected_names]

    return extra_names, missing_names


def assert_extra_or_missing_names(
    resource_type: str,
    result_names: List[str],
    pre_expected_names: List[str],
    post_expected_names: List[str],
    ignore_extras: bool = False,
    ignore_missing: bool = False,
):
    """
    Checks the result to find missing or extra names and raises if there are any extra or missing names.
    """
    extra_names, missing_names = find_extra_or_missing_names(
        result_names=result_names,
        pre_expected_names=pre_expected_names,
        post_expected_names=post_expected_names
    )
    error_msg = []

    if extra_names:
        msg = f"Extra {resource_type} names: {', '.join(extra_names)}"
        if ignore_extras:
            logger.warning(msg)
        else:
            error_msg.append(msg)

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
    # map for shorthand names to full names (something kubectl understands)
    key_to_full_map = {
        "pvc": "persistentvolumeclaim",
        "vwc": "validatingwebhookconfiguration",
        "mwc": "mutatingwebhookconfiguration",
    }

    # if the service type is in the map, use the full name
    service_type = key_to_full_map.get(service_type, service_type)

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


def get_role_assignment_ids(scope: str, assignee: str) -> List[str]:
    """Return the role definition GUIDs assigned to `assignee` at `scope` (empty if none/propagating)."""
    command = (
        f"az role assignment list --scope {scope} "
        f"--assignee {assignee} --query \"[].roleDefinitionId\" -o tsv"
    )
    output = run(command) or ""
    return [ra.rsplit("/", maxsplit=1)[-1] for ra in str(output).splitlines() if ra.strip()]


def assert_role_assignment(
    scope: str,
    assignee: str,
    expected_role_ids: Union[str, List[str]],
    disallowed_role_ids: Optional[Union[str, List[str]]] = None,
    max_retries: int = 6,
    retry_interval: int = 10,
):
    """Poll for RBAC propagation, then assert expected roles are present (and optionally others absent)."""
    expected = [expected_role_ids] if isinstance(expected_role_ids, str) else list(expected_role_ids)
    disallowed = (
        [disallowed_role_ids] if isinstance(disallowed_role_ids, str) else list(disallowed_role_ids or [])
    )

    assigned: List[str] = []
    last_cli_error: Optional[str] = None
    for attempt in range(max_retries):
        try:
            assigned = get_role_assignment_ids(scope=scope, assignee=assignee)
            last_cli_error = None
        except CLIInternalError as e:
            last_cli_error = str(e)
            assigned = []
        if not last_cli_error and all(role_id in assigned for role_id in expected):
            break
        if attempt < max_retries - 1:
            sleep(retry_interval)

    missing = [role_id for role_id in expected if role_id not in assigned]
    cli_err_suffix = f"; last az error: {last_cli_error}" if last_cli_error else ""
    assert not missing, (
        f"Missing role(s) {missing} for {assignee} on {scope}; found: {assigned}{cli_err_suffix}"
    )

    present_disallowed = [role_id for role_id in disallowed if role_id in assigned]
    assert not present_disallowed, (
        f"Disallowed role(s) {present_disallowed} for {assignee} on {scope}; found: {assigned}{cli_err_suffix}"
    )


def run(
    command: str,
    shell_mode: bool = True,
    expect_failure: bool = False,
    timeout: Optional[int] = None,
) -> Union[Dict[str, Any], str, None]:
    """
    Wrapper function for run_host_command used for testing.
    Parameter `expect_failure` determines if an error will be raised for the command result.
    The output is converted to non-binary text and loaded as a json if possible.
    Raises CLIInternalError if there is an unexpected error or an unexpected success.
    """
    import subprocess

    result = subprocess.run(
        command, check=False, shell=shell_mode, text=True, capture_output=True,
        encoding="utf-8", timeout=timeout,
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
    return None


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


def wait_for_expected_count(
    list_cmd: str,
    expected_count: int,
    expected_names: Optional[List[str]] = None,
    max_retries: int = 8,
    initial_interval: int = 3,
    max_interval: int = 20,
    backoff_factor: float = 1.5,
    reissue_cmds: Optional[Dict[str, str]] = None,
    reissue_on_missing: bool = True,
    run_fn: Optional[Callable[..., Any]] = None,
) -> list:
    """Poll a list command until the expected count (and optionally names) are reached.

    Handles Azure API eventual consistency by retrying with exponential backoff.
    Default schedule: 3 → 4.5 → 6.75 → 10 → 15 → 20 → 20 → 20s.

    Args:
        list_cmd: CLI command that returns a JSON list.
        expected_count: The item count to wait for.
        expected_names: If given, also verify these names appear (or are absent).
        max_retries: Maximum number of retry attempts.
        initial_interval: Seconds to wait before the first retry.
        max_interval: Cap on the retry interval.
        backoff_factor: Multiplier applied to the interval after each retry.
        reissue_cmds: ``{name: command}`` map.  On each retry, commands are
            re-issued for names that are missing (``reissue_on_missing=True``,
            the default — use for adds) or still present
            (``reissue_on_missing=False`` — use for removes).
        reissue_on_missing: Direction flag for *reissue_cmds*.
        run_fn: Callable to execute commands; defaults to ``run()``.

    Returns the final list result on success; raises AssertionError on exhaustion.
    """
    _run = run_fn or run
    interval = initial_interval

    for attempt in range(max_retries + 1):
        result = _run(list_cmd)
        result = result if result else []

        names_ok = True
        if expected_names:
            actual_names = {item.get("name") for item in result if isinstance(item, dict)}
            if reissue_on_missing:
                names_ok = all(n in actual_names for n in expected_names)
            else:
                names_ok = not any(n in actual_names for n in expected_names)

        if len(result) == expected_count and names_ok:
            return result

        if attempt < max_retries:
            logger.info(
                "Expected %d items but got %d (attempt %d/%d), retrying in %ds...",
                expected_count, len(result), attempt + 1, max_retries, interval,
            )
            sleep(interval)
            interval = min(interval * backoff_factor, max_interval)

            if reissue_cmds:
                actual_names = {item.get("name") for item in result if isinstance(item, dict)}
                for name, cmd in reissue_cmds.items():
                    should_reissue = (
                        (reissue_on_missing and name not in actual_names)
                        or (not reissue_on_missing and name in actual_names)
                    )
                    if should_reissue:
                        _run(cmd)

    assert len(result) == expected_count and names_ok, (
        f"Expected {expected_count} items but got {len(result)} after {max_retries} retries"
    )
    return result


# Representative endpoint/suffix values per cloud, matching what the Azure CLI
# cloud framework exposes at runtime. Used to build mock cmd objects for
# government-cloud (Fairfax) and China-cloud readiness tests.
CLOUD_CONFIG_FIXTURES = {
    "AzureCloud": {
        "resource_manager": "https://management.azure.com/",
        "microsoft_graph_resource_id": "https://graph.microsoft.com/",
        "storage_endpoint": "core.windows.net",
        "keyvault_dns": ".vault.azure.net",
        "acr_login_server_endpoint": ".azurecr.io",
    },
    "AzureUSGovernment": {
        "resource_manager": "https://management.usgovcloudapi.net/",
        "microsoft_graph_resource_id": "https://graph.microsoft.us/",
        "storage_endpoint": "core.usgovcloudapi.net",
        "keyvault_dns": ".vault.usgovcloudapi.net",
        "acr_login_server_endpoint": ".azurecr.us",
    },
    "AzureChinaCloud": {
        "resource_manager": "https://management.chinacloudapi.cn",
        "microsoft_graph_resource_id": "https://microsoftgraph.chinacloudapi.cn",
        "storage_endpoint": "core.chinacloudapi.cn",
        "keyvault_dns": ".vault.azure.cn",
        "acr_login_server_endpoint": ".azurecr.cn",
    },
}


def build_mock_cmd_for_cloud(cloud_name: str):
    """Build a mock cmd whose cli_ctx.cloud reflects the given cloud's endpoints/suffixes."""
    from unittest.mock import Mock

    fixture = CLOUD_CONFIG_FIXTURES[cloud_name]

    class _Stub:
        pass

    cloud = _Stub()
    cloud.name = cloud_name
    cloud.endpoints = _Stub()
    cloud.endpoints.resource_manager = fixture["resource_manager"]
    cloud.endpoints.microsoft_graph_resource_id = fixture["microsoft_graph_resource_id"]
    cloud.suffixes = _Stub()
    cloud.suffixes.storage_endpoint = fixture["storage_endpoint"]
    cloud.suffixes.keyvault_dns = fixture["keyvault_dns"]
    cloud.suffixes.acr_login_server_endpoint = fixture["acr_login_server_endpoint"]

    cmd = Mock()
    cmd.cli_ctx.cloud = cloud
    return cmd
