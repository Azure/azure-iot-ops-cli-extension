# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from typing import Any, Dict, List, Optional, Tuple, Union
from os import path
from zipfile import ZipFile
from azure.cli.core.azclierror import CLIInternalError
import pytest
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from ....helpers import run


logger = get_logger(__name__)
BASE_ZIP_PATH = "__root__"
WORKLOAD_TYPES = [
    "cronjob", "daemonset", "deployment", "job", "pod", "podmetric", "pvc", "replicaset", "service", "statefulset"
]


def assert_file_names(files: List[str]):
    """Asserts file names."""
    for full_name in files:
        name = full_name.split(".")
        file_type = name.pop(0)
        extension = name.pop(-1)
        # trace files
        if extension == "pb":
            assert name[-1] == "otlp"
            continue
        if extension == "json":
            assert name[-1] == "tempo"
            continue

        assert extension in ["log", "txt", "yaml"]
        if file_type not in WORKLOAD_TYPES:
            if extension == "txt":
                continue
            assert name.pop(0).startswith("v")

        short_name = name.pop(0)
        if short_name == "aio-opc-opc":
            short_name += f".{name.pop(0)}"
        if "metric" in name and extension == "yaml":
            short_name += f".{name.pop(0)}"

        assert bool(name) == (extension != "yaml")


def convert_file_names(files: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """Maps deployment/pod/etc to list of dissembled file names"""
    file_name_objs = {}
    for full_name in files:
        name = full_name.split(".")
        file_type = name.pop(0)
        name_obj = {"extension": name.pop(-1), "full_name": full_name}

        if file_type == "pod" and name[-1] == "metric":
            file_type = "podmetric"

        if name_obj["extension"] in ["pb", "json"]:
            if "trace" not in file_name_objs:
                file_name_objs["trace"] = []
            # trace file
            # aio-mq-dmqtt-frontend-1.Publish.b9c3173d9c2b97b75edfb6cf7cb482f2.otlp.pb
            # aio-mq-dmqtt-frontend-1.Publish.b9c3173d9c2b97b75edfb6cf7cb482f2.tempo.json
            name_obj["name"] = file_type
            name_obj["action"] = name.pop(0).lower()
            name_obj["identifier"] = name.pop(0)
            file_name_objs["trace"].append(name_obj)
            continue

        if file_type not in file_name_objs:
            file_name_objs[file_type] = []

        assert name_obj["extension"] in ["log", "txt", "yaml"]

        # custom types should have a v
        if file_type not in WORKLOAD_TYPES:
            if name_obj["extension"] != "yaml":
                # check diagnositcs.txt later
                file_name_objs[file_type].append(name_obj)
                continue
            name_obj["version"] = name.pop(0)
            assert name_obj["version"].startswith("v")
        name_obj["name"] = name.pop(0)
        if name_obj["name"] == "aio-opc-opc":
            name_obj["name"] += f".{name.pop(0)}"

        # something like "msi-adapter", "init-runner"
        if name:
            name_obj["descriptor"] = name.pop(0)
        # something like "previous", "init"
        if name:
            name_obj["sub_descriptor"] = name.pop(0)

        file_name_objs[file_type].append(name_obj)

    return file_name_objs


def check_custom_resource_files(
    file_objs: Dict[str, List[Dict[str, str]]],
    resource_api: EdgeResourceApi,
    namespace: Optional[str] = None
):
    plural_map: Dict[str, str] = {}
    try:
        # prefer to use another tool to get resources
        api_table = run(f"kubectl api-resources --api-group={resource_api.group}")
        api_resources = [line.split() for line in api_table.split("\n")]
        api_resources = api_resources[1:-1]
        plural_map = {line[-1].lower(): line[0] for line in api_resources}
    except CLIInternalError:
        # fall back to python sdk if not possible
        pytest.skip("Cannot access resources via kubectl.")

    namespace = f"-n {namespace}" if namespace else "-A"
    for kind in resource_api.kinds:
        cluster_resources = {}
        if plural_map.get(kind):
            cluster_resources = run(
                f"kubectl get {plural_map[kind]}.{resource_api.version}.{resource_api.group} {namespace} -o json"
            )

        expected_names = [r["metadata"]["name"] for r in cluster_resources.get("items", [])]
        assert len(expected_names) == len(file_objs.get(kind, []))
        for resource in file_objs.get(kind, []):
            assert resource["name"] in expected_names
            assert resource["version"] == resource_api.version


def check_workload_resource_files(
    file_objs: Dict[str, List[Dict[str, str]]],
    expected_workload_types: List[str],
    prefixes: Union[str, List[str]]
):
    if "pod" in expected_workload_types:
        expected_workload_types.remove("pod")
    # pod
    file_pods = {}
    for file in file_objs.get("pod", []):
        if file["name"] not in file_pods:
            file_pods[file["name"]] = {"yaml": False}
        converted_file = file_pods[file["name"]]

        # for all of these files, make sure that it was not seen before
        # in the end, there should be one yaml
        # if sub_descriptor file present, descriptor file should be there too (has exceptions)
        if file["extension"] == "yaml":
            # only one yaml per pod
            assert not converted_file["yaml"]
            converted_file["yaml"] = True
        elif file.get("sub_descriptor") in ["init", None]:
            assert f"{file['descriptor']}.{file.get('sub_descriptor')}" not in converted_file
            converted_file[file["descriptor"]] = True
        else:
            assert file["sub_descriptor"] == "previous"
            sub_key = f"{file['descriptor']}.{file['sub_descriptor']}"
            assert sub_key not in converted_file
            converted_file[sub_key] = True
            # if msi-adapter.previous present, msi-adapter must present too
            # for some reason does not apply to xxx.init
            if file["descriptor"] not in converted_file:
                converted_file[file["descriptor"]] = False

    expected_pods = get_kubectl_items(prefixes, service_type="pod")
    expected_pod_names = [item["metadata"]["name"] for item in expected_pods]
    find_extra_or_missing_files("pod", file_pods.keys(), expected_pod_names)

    for name, files in file_pods.items():
        for extension, value in files.items():
            assert value, f"Pod {name} is missing {extension}."

    # other
    for key in expected_workload_types:
        expected_items = get_kubectl_items(prefixes, service_type=key)
        expected_item_names = [item["metadata"]["name"] for item in expected_items]
        for file in file_objs.get(key, []):
            assert file["extension"] == "yaml"
        present_names = [file["name"] for file in file_objs.get(key, [])]
        find_extra_or_missing_files(key, present_names, expected_item_names)


def find_extra_or_missing_files(
    resource_type: str, bundle_names: List[str], expected_names: List[str], ignore_extras: bool = False
):
    error_msg = []
    extra_names = [name for name in bundle_names if name not in expected_names]
    if extra_names:
        msg = f"Extra {resource_type} files: {', '.join(extra_names)}."
        if ignore_extras:
            logger.warning(msg)
        else:
            error_msg.append(msg)
    missing_files = [name for name in expected_names if name not in bundle_names]
    if missing_files:
        error_msg.append(f"Missing {resource_type} files: {', '.join(missing_files)}.")

    if error_msg:
        raise AssertionError('\n '.join(error_msg))


def get_kubectl_items(prefixes: Union[str, List[str]], service_type: str) -> Dict[str, Any]:
    if service_type == "pvc":
        service_type = "persistentvolumeclaim"
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    kubectl_items = run(f"kubectl get {service_type}s -A -o json")
    filtered = []
    for item in kubectl_items["items"]:
        for prefix in prefixes:
            if item["metadata"]["name"].startswith(prefix):
                filtered.append(item)
    return filtered


def get_file_map(
    walk_result: Dict[str, Dict[str, List[str]]],
    ops_service: str,
    mq_traces: bool = False
) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
    # Remove all files that will not be checked
    namespace, c_namespace, lnm_namespace = process_top_levels(walk_result, ops_service)
    walk_result.pop(path.join(BASE_ZIP_PATH, namespace))

    # Level 2 and 3 - bottom
    if ops_service == OpsServiceType.dataprocessor.value and not walk_result:
        return

    ops_path = path.join(BASE_ZIP_PATH, namespace, ops_service)
    # separate namespaces
    file_map = {"__namespaces__": {}}
    if mq_traces and path.join(ops_path, "traces") in walk_result:
        # still possible for no traces if cluster is too new
        assert len(walk_result) == 2
        assert walk_result[ops_path]["folders"]
        assert not walk_result[path.join(ops_path, "traces")]["folders"]
        file_map["traces"] = convert_file_names(walk_result[path.join(ops_path, "traces")]["files"])
    elif ops_service == "billing":
        assert len(walk_result) == 2
        ops_path = path.join(BASE_ZIP_PATH, namespace, "clusterconfig", ops_service)
        c_path = path.join(BASE_ZIP_PATH, c_namespace, "clusterconfig", ops_service)
        file_map["usage"] = convert_file_names(walk_result[c_path]["files"])
        file_map["__namespaces__"]["usage"] = c_namespace
    elif ops_service == "lnm":
        assert len(walk_result) >= 1
        ops_path = path.join(BASE_ZIP_PATH, namespace, ops_service)
        lnm_path = path.join(BASE_ZIP_PATH, lnm_namespace, ops_service)
        file_map["lnm"] = convert_file_names(walk_result[lnm_path]["files"])
        file_map["__namespaces__"]["lnm"] = lnm_namespace
    elif ops_service != "otel":
        assert len(walk_result) == 1
        assert not walk_result[ops_path]["folders"]
    file_map["aio"] = convert_file_names(walk_result[ops_path]["files"])
    file_map["__namespaces__"]["aio"] = namespace
    return file_map


# def get_lnm_file_map(
#     walk_result: Dict[str, Dict[str, List[str]]],
# ) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
#     # get all instances names
#     instances = []
#     kubectl_lnmz = run(f"kubectl get lnmz -A -o json")
#     for item in kubectl_lnmz["items"]:
#         instances.append(item["metadata"]["name"])

#     for instance in instances:
#         # the main namespace is the one which deployment file that contains the instance name
#         namespace = None


#     ops_path = path.join(BASE_ZIP_PATH, namespace, ops_service)
#     # separate namespaces
#     file_map = {"__namespaces__": {}}
#     if mq_traces and path.join(ops_path, "traces") in walk_result:
#         # still possible for no traces if cluster is too new
#         assert len(walk_result) == 2
#         assert walk_result[ops_path]["folders"]
#         assert not walk_result[path.join(ops_path, "traces")]["folders"]
#         file_map["traces"] = convert_file_names(walk_result[path.join(ops_path, "traces")]["files"])
#     elif ops_service == "billing":
#         assert len(walk_result) == 2
#         ops_path = path.join(BASE_ZIP_PATH, namespace, "clusterconfig", ops_service)
#         c_path = path.join(BASE_ZIP_PATH, c_namespace, "clusterconfig", ops_service)
#         file_map["usage"] = convert_file_names(walk_result[c_path]["files"])
#         file_map["__namespaces__"]["usage"] = c_namespace
#     elif ops_service != "otel":
#         assert len(walk_result) == 1
#         assert not walk_result[ops_path]["folders"]
#     file_map["aio"] = convert_file_names(walk_result[ops_path]["files"])
#     file_map["__namespaces__"]["aio"] = namespace
#     return file_map


def process_top_levels(
    walk_result: Dict[str, Dict[str, List[str]]], ops_service: str
) -> Tuple[str, str, str]:
    level_0 = walk_result.pop(BASE_ZIP_PATH)
    for file in ["events.yaml", "nodes.yaml", "storage_classes.yaml"]:
        assert file in level_0["files"]
    if not level_0["folders"]:
        pytest.skip(f"No bundles created for {ops_service}.")
    namespaces = level_0["folders"]
    namespace = namespaces[0]
    clusterconfig_namespace = None
    lnm_namespace = None
    for name in namespaces:
        # determine which namespace belongs to aio vs billing
        level_1 = walk_result.get(path.join(BASE_ZIP_PATH, name, "clusterconfig", "billing"), {})
        files = [f for f in level_1.get("files", []) if f.startswith("deployment")]
        lnm_files = [f for f in level_1.get("files", []) if ops_service == "lnm" and f.startswith("daemonset")]
        if files:
            # if there is a deployment, should be azure-extensions-usage-system
            clusterconfig_namespace = name
        elif lnm_files:
            lnm_namespace = name
        else:
            namespace = name

    if clusterconfig_namespace:
        logger.debug("Determined the following namespaces:")
        logger.debug(f"AIO namespace: {namespace}")
        logger.debug(f"Usage system namespace: {clusterconfig_namespace}")
        # remove empty billing related folders
        level_1 = walk_result.pop(path.join(BASE_ZIP_PATH, clusterconfig_namespace))
        assert level_1["folders"] == ["clusterconfig"]
        assert not level_1["files"]
        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, namespace, "clusterconfig"))
        assert level_2["folders"] == ["billing"]
        assert not level_2["files"]
        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, clusterconfig_namespace, "clusterconfig"))
        assert level_2["folders"] == ["billing"]
        assert not level_2["files"]

    return namespace, clusterconfig_namespace, lnm_namespace


def run_bundle_command(
    command: str,
    tracked_files: List[str],
) -> Dict[str, Dict[str, List[str]]]:
    result = run(command)
    assert result["bundlePath"]
    tracked_files.append(result["bundlePath"])
    # transform this into a walk result of an extracted zip file
    walk_result = {}
    with ZipFile(result["bundlePath"], 'r') as zip:
        file_names = zip.namelist()
        for name in file_names:
            name = path.join(BASE_ZIP_PATH, name)
            directory, file_name = path.split(name)

            # decompose incase seperator from zipfile is different from os sep. Example:
            # windows sep is \\
            # zipfile returns azure-extensions-usage-system/clusterconfig/billing
            decomposed_folders = []
            while path.split(directory)[0]:
                directory, sub = path.split(directory)
                decomposed_folders.append(sub)
            decomposed_folders.append(directory)

            built_path = ""
            while decomposed_folders:
                folder = decomposed_folders.pop(-1)
                # make sure to add in directory to parent folder if it exists
                if built_path and folder not in walk_result[built_path]["folders"]:
                    walk_result[built_path]["folders"].append(folder)

                built_path = path.join(built_path, folder)
                # add in the current built directory in
                if built_path not in walk_result:
                    walk_result[built_path] = {"folders": [], "files": []}

            # lastly add in the file (with the correct seperators)
            walk_result[built_path]["files"].append(file_name)

    return walk_result
