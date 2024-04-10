# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Union
from os import mkdir, path, walk
from shutil import rmtree, unpack_archive
from azure.cli.core.azclierror import CLIInternalError
import pytest
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from ....helpers import run


EXTRACTED_PATH = "unpacked"
AUTO_EXTRACTED_PATH = f"auto_{EXTRACTED_PATH}"
WORKLOAD_TYPES = ["daemonset", "deployment", "pod", "pvc", "replicaset", "service", "statefulset"]


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
        if file_type not in [
            "daemonset", "deployment", "pod", "podmetric", "pvc", "replicaset", "service", "statefulset"
        ]:
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
    resource_kinds: List[str]
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

    for kind in resource_kinds:
        cluster_resources = {}
        if plural_map.get(kind):
            cluster_resources = run(
                f"kubectl get {plural_map[kind]}.{resource_api.version}.{resource_api.group} -A -o json"
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
        expected_workload_types.pop("pod")
    # pod
    file_pods = {}
    for file in file_objs["pod"]:
        if file["name"] not in file_pods:
            file_pods[file["name"]] = {"yaml_present": False}
        converted_file = file_pods[file["name"]]

        # for all of these files, make sure that it was not seen before
        # in the end, there should be one yaml
        # if sub_descriptor file present, descriptor file should be there too (has exceptions)
        if file["extension"] == "yaml":
            # only one yaml per pod
            assert not converted_file["yaml_present"]
            converted_file["yaml_present"] = True
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
    assert len(file_pods) == len(expected_pods)

    for name, files in file_pods.items():
        assert name in expected_pod_names
        for value in files.values():
            assert value

    # other
    for key in expected_workload_types:
        expected_items = get_kubectl_items(prefixes, service_type=key)
        expected_item_names = [item["metadata"]["name"] for item in expected_items]
        for file in file_objs[key]:
            assert file["extension"] == "yaml"
            assert file["name"] in expected_item_names
        assert len(file_objs[key]) == len(expected_item_names)


def ensure_clean_dir(dir_path: str, tracked_files: List[str]):
    try:
        mkdir(dir_path)
        tracked_files.append(dir_path)
    except FileExistsError:
        rmtree(dir_path)
        mkdir(dir_path)


def filter_duplicate_file_names(files):
    return [name for name in files if not name.endswith(".metric")]
    # for name in files:
    #     # make sure multiple mq backend/frontend pods/statefulsets aren't counted more
    #     # than once
    #     repeated = False
    #     for repeatable in ["aio-mq-dmqtt-backend", "aio-mq-dmqtt-frontend", "aio-mq-operator", "aio-orc-api"]:
    #         if name.startswith(repeatable):
    #             repeated = True
    #             if repeatable not in filtered_files:
    #                 filtered_files.append(repeatable)
    #             break
    #     name = name.split(".")[0]
    #     if name not in filtered_files and not repeated:
    #         filtered_files.append(name)
    # return filtered_files


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
    walk_result,
    ops_service: str,
    mq_traces: bool = False
) -> Dict[str, List[Dict[str, str]]]:
    # Remove all files that will not be checked
    level_0 = walk_result.pop(EXTRACTED_PATH)
    namespace = level_0["folders"][0]
    walk_result.pop(path.join(EXTRACTED_PATH, namespace))

    # Level 2 and 3 - bottom
    if ops_service == OpsServiceType.dataprocessor.value and not walk_result:
        return

    ops_path = path.join(EXTRACTED_PATH, namespace, ops_service)
    file_map = {}
    if mq_traces and path.join(ops_path, "traces") in walk_result:
        # still possible for no traces if cluster is too new
        assert len(walk_result) == 2
        assert walk_result[ops_path]["folders"]
        assert not walk_result[path.join(ops_path, "traces")]["folders"]
        file_map["traces"] = convert_file_names(walk_result[path.join(ops_path, "traces")]["files"])
    elif ops_service != "otel":
        assert len(walk_result) == 1
        assert not walk_result[ops_path]["folders"]

    file_map.update(convert_file_names(walk_result[ops_path]["files"]))
    return file_map


def run_bundle_command(
    command: str,
    tracked_files: List[str],
    extracted_path: str = EXTRACTED_PATH,
) -> Dict[str, Dict[str, List[str]]]:
    ensure_clean_dir(extracted_path, tracked_files)
    result = run(command)
    assert result["bundlePath"]
    tracked_files.append(result["bundlePath"])
    unpack_archive(result["bundlePath"], extract_dir=extracted_path)
    return {
        directory: {
            "folders": folders, "files": files
        } for directory, folders, files in walk(extracted_path)
    }
