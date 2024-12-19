# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from typing import Dict, List, Optional, Tuple, Union
from os import path
from zipfile import ZipFile
import pytest
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api.base import EdgeResourceApi
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from ....helpers import (
    PLURAL_KEY,
    find_extra_or_missing_names,
    get_kubectl_custom_items,
    get_kubectl_workload_items,
    run,
)


logger = get_logger(__name__)
BASE_ZIP_PATH = "__root__"
WORKLOAD_TYPES = [
    "configmap",
    "cronjob",
    "daemonset",
    "deployment",
    "job",
    "pod",
    "podmetric",
    "pvc",
    "replicaset",
    "service",
    "statefulset",
]


def assert_file_names(files: List[str]):
    """Asserts file names."""
    for full_name in files:
        name = split_name(full_name)
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
        name = split_name(full_name)
        file_type = name.pop(0)
        name_obj = {"extension": name.pop(-1), "full_name": full_name}

        if file_type == "pod" and name[-1] == "metric":
            file_type = "podmetric"

        if name_obj["extension"] in ["pb", "json"]:
            if "trace" not in file_name_objs:
                file_name_objs["trace"] = []
            # trace file
            # aio-broker-dmqtt-frontend-1.Publish.b9c3173d9c2b97b75edfb6cf7cb482f2.otlp.pb
            # aio-broker-dmqtt-frontend-1.Publish.b9c3173d9c2b97b75edfb6cf7cb482f2.tempo.json
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
    namespace: Optional[str] = None,
):
    # skip validation if resource is not deployed
    if not resource_api.is_deployed():
        return

    resource_map = get_kubectl_custom_items(resource_api=resource_api, namespace=namespace, include_plural=True)
    for kind in resource_api.kinds:
        cluster_resources = resource_map[kind]
        # subresources like scale will not have a plural
        if cluster_resources.get(PLURAL_KEY):
            assert len(cluster_resources.keys()) - 1 == len(file_objs.get(kind, []))
            for resource in file_objs.get(kind, []):
                assert resource["name"] in cluster_resources.keys()
                assert resource["version"] == resource_api.version


def check_workload_resource_files(
    file_objs: Dict[str, List[Dict[str, str]]],
    expected_workload_types: List[str],
    prefixes: Union[str, List[str]],
    bundle_path: str,
    expected_label: Optional[str] = None,
    optional_workload_types: Optional[List[str]] = None,
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
            assert file["sub_descriptor"] == "previous", f"Full file name: {file['full_name']}, file_obj {file}"
            sub_key = f"{file['descriptor']}.{file['sub_descriptor']}"
            assert sub_key not in converted_file, f"Full file name: {file['full_name']}, file_obj {file}"
            converted_file[sub_key] = True
            # if msi-adapter.previous present, msi-adapter must present too
            # for some reason does not apply to xxx.init
            if file["descriptor"] not in converted_file:
                converted_file[file["descriptor"]] = False

    expected_pods = get_kubectl_workload_items(prefixes, service_type="pod", label_match=expected_label)
    check_log_for_evicted_pods(bundle_path, file_objs.get("pod", []))
    find_extra_or_missing_names(
        resource_type="pod",
        result_names=file_pods.keys(),
        expected_names=expected_pods.keys(),
        ignore_extras=True,
        ignore_missing=True,
    )

    for name, files in file_pods.items():
        for extension, value in files.items():
            assert value, f"Pod {name} is missing {extension}."

    # other
    def _check_non_pod_files(workload_types: List[str], required: bool = False, expected_label: Optional[str] = None):
        for key in workload_types:
            try:
                expected_items = get_kubectl_workload_items(prefixes, service_type=key, label_match=expected_label)
                for file in file_objs.get(key, []):
                    assert file["extension"] == "yaml"
                present_names = [file["name"] for file in file_objs.get(key, [])]
                find_extra_or_missing_names(key, present_names, expected_items.keys())
            except CLIInternalError as e:
                if required:
                    raise e

    _check_non_pod_files(expected_workload_types, expected_label=expected_label)
    if optional_workload_types:
        _check_non_pod_files(optional_workload_types, required=False, expected_label=expected_label)


def check_log_for_evicted_pods(bundle_dir: str, file_pods: List[Dict[str, str]]):
    # open the file using bundle_dir and check for evicted pods
    name_extension_pair = list(set([(file["name"], file["extension"]) for file in file_pods]))
    # TODO: upcoming fix will get file content earlier
    with ZipFile(bundle_dir, "r") as zip:
        file_names = zip.namelist()
        for name, extension in name_extension_pair:
            if extension == "log":
                # find file path in file_names that has name and extension
                file_path = next((file for file in file_names if file.endswith(name + ".yaml")), None)
                if not file_path:
                    continue
                with zip.open(file_path) as pod_content:
                    log_content = pod_content.read().decode("utf-8")
                    assert "Evicted" not in log_content, f"Evicted pod {name} log found in bundle."


def get_file_map(
    walk_result: Dict[str, Dict[str, List[str]]],
    ops_service: str,
    mq_traces: bool = False,
) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
    # Remove all files that will not be checked
    namespaces = process_top_levels(walk_result, ops_service)
    arc_namespace = namespaces.get("arc")
    aio_namespace = namespaces.get("aio")
    acs_namespace = namespaces.get("acs")
    acstor_namespace = namespaces.get("acstor")
    ssc_namespace = namespaces.get("ssc")
    c_namespace = namespaces.get("usage_system")

    if aio_namespace:
        walk_result.pop(path.join(BASE_ZIP_PATH, aio_namespace))
        ops_path = path.join(BASE_ZIP_PATH, aio_namespace, ops_service)

    # separate namespaces
    file_map = {"__namespaces__": {}}
    # default walk result meta and arcagents
    expected_default_walk_result = 1 + len(ARC_AGENTS)

    if arc_namespace:
        file_map["arc"] = {}
        file_map["__namespaces__"]["arc"] = arc_namespace
        for agent, _ in ARC_AGENTS:
            agent_path = path.join(BASE_ZIP_PATH, arc_namespace, "arcagents", agent)
            file_map["arc"][agent] = convert_file_names(walk_result[agent_path]["files"])

    if mq_traces and path.join(ops_path, "traces") in walk_result:
        # still possible for no traces if cluster is too new
        assert len(walk_result) == 2 + expected_default_walk_result
        assert walk_result[ops_path]["folders"]
        assert not walk_result[path.join(ops_path, "traces")]["folders"]
        file_map["traces"] = convert_file_names(walk_result[path.join(ops_path, "traces")]["files"])
    elif ops_service == "billing":
        assert len(walk_result) == 2 + expected_default_walk_result
        ops_path = path.join(BASE_ZIP_PATH, aio_namespace, ops_service)
        c_path = path.join(BASE_ZIP_PATH, c_namespace, "clusterconfig", ops_service)
        file_map["usage"] = convert_file_names(walk_result[c_path]["files"])
        file_map["__namespaces__"]["usage"] = c_namespace
    elif ops_service == "acs":
        if acstor_namespace:
            # resources in both acstor_namespace and acs_namespace
            assert len(walk_result) == 2 + expected_default_walk_result
            acstor_path = path.join(BASE_ZIP_PATH, acstor_namespace, "containerstorage")
            file_map["acstor"] = convert_file_names(walk_result[acstor_path]["files"])
            file_map["__namespaces__"]["acstor"] = acstor_namespace
        else:
            # resources only in acs_namespace
            assert len(walk_result) == 1 + expected_default_walk_result
        acs_path = path.join(BASE_ZIP_PATH, acs_namespace, "arccontainerstorage")
        file_map["acs"] = convert_file_names(walk_result[acs_path]["files"])
        file_map["__namespaces__"]["acs"] = acs_namespace

        # no files for aio, skip the rest assertions
        return file_map
    elif ops_service == OpsServiceType.secretstore.value:
        ops_path = path.join(BASE_ZIP_PATH, aio_namespace, OpsServiceType.secretstore.value)
        ssc_path = path.join(BASE_ZIP_PATH, ssc_namespace, OpsServiceType.secretstore.value)
        if ops_path not in walk_result:
            # no CR created in aio namespace
            # since CR is the only resource type under aio, skip the rest assertions
            assert len(walk_result) == 1 + expected_default_walk_result
            pytest.skip(f"No bundles created for {ops_service}.")
        else:
            assert len(walk_result) == 2 + expected_default_walk_result
        file_map[OpsServiceType.secretstore.value] = convert_file_names(walk_result[ssc_path]["files"])
        file_map["__namespaces__"][OpsServiceType.secretstore.value] = ssc_namespace
    elif ops_service == OpsServiceType.azuremonitor.value:
        monitor_path = path.join(BASE_ZIP_PATH, arc_namespace, OpsServiceType.azuremonitor.value)
        assert len(walk_result) == 1 + expected_default_walk_result
        file_map[OpsServiceType.azuremonitor.value] = convert_file_names(walk_result[monitor_path]["files"])
        file_map["__namespaces__"][OpsServiceType.azuremonitor.value] = arc_namespace

        # no files for aio, skip the rest assertions
        return file_map
    elif ops_service == "deviceregistry":
        if ops_path not in walk_result:
            assert len(walk_result) == expected_default_walk_result
            pytest.skip(f"No bundles created for {ops_service}.")
        else:
            assert len(walk_result) == 1 + expected_default_walk_result
    # remove ops_service that are not selectable by --svc
    elif ops_service not in ["otel", "meta"]:
        assert len(walk_result) == 1 + expected_default_walk_result
        assert not walk_result[ops_path]["folders"]
    file_map["aio"] = convert_file_names(walk_result[ops_path]["files"])
    file_map["__namespaces__"]["aio"] = aio_namespace
    return file_map


def process_top_levels(
    walk_result: Dict[str, Dict[str, List[str]]],
    ops_service: str,
) -> Dict[str, Union[str, None]]:
    level_0 = walk_result.pop(BASE_ZIP_PATH)
    for file in ["events.yaml", "nodes.yaml", "storage-classes.yaml", "azure-clusterconfig.yaml"]:
        assert file in level_0["files"]
    if not level_0["folders"]:
        pytest.skip(f"No bundles created for {ops_service}.")
    namespaces = level_0["folders"]
    namespace = None
    clusterconfig_namespace = None
    arc_namespace = None
    acs_namespace = None
    acstor_namespace = None
    ssc_namespace = None

    def _get_namespace_determinating_files(name: str, folder: str, file_prefix: str) -> List[str]:
        level1 = walk_result.get(path.join(BASE_ZIP_PATH, name, folder), {})
        return [f for f in level1.get("files", []) if f.startswith(file_prefix)]

    for name in namespaces:
        # determine which namespace belongs to aio vs billing
        if _get_namespace_determinating_files(
            name=name, folder=path.join("clusterconfig", "billing"), file_prefix="deployment"
        ):
            # if there is a deployment, should be azure-extensions-usage-system
            clusterconfig_namespace = name
        elif _get_namespace_determinating_files(
            name=name, folder=path.join("arcagents", ARC_AGENTS[0][0]), file_prefix="pod"
        ):
            arc_namespace = name
        elif _get_namespace_determinating_files(name=name, folder=path.join("arccontainerstorage"), file_prefix="pvc"):
            acs_namespace = name
        elif _get_namespace_determinating_files(
            name=name, folder=path.join("containerstorage"), file_prefix="configmap"
        ):
            acstor_namespace = name
        elif _get_namespace_determinating_files(
            name=name, folder=OpsServiceType.secretstore.value, file_prefix="deployment"
        ):
            ssc_namespace = name
        else:
            namespace = name

    monitor_path = path.join(BASE_ZIP_PATH, arc_namespace, OpsServiceType.azuremonitor.value)
    for namespace_folder, services in [
        (clusterconfig_namespace, ["clusterconfig"]),
        (arc_namespace, ["arcagents"]),
        (acs_namespace, ["arccontainerstorage"]),
        (acstor_namespace, ["containerstorage"]),
        (ssc_namespace, [OpsServiceType.secretstore.value]),
    ]:
        if namespace_folder:
            # remove empty folders in level 1
            level_1 = walk_result.pop(path.join(BASE_ZIP_PATH, namespace_folder))

            if namespace_folder == arc_namespace and monitor_path in walk_result:
                services.append(OpsServiceType.azuremonitor.value)
            assert set(level_1["folders"]) == set(services)
            assert not level_1["files"]

    # remove empty folders in level 2
    if clusterconfig_namespace:
        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, clusterconfig_namespace, "clusterconfig"))
        assert level_2["folders"] == ["billing"]
        assert not level_2["files"]
    if arc_namespace:
        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, arc_namespace, "arcagents"))
        assert level_2["folders"] == [agent[0] for agent in ARC_AGENTS]
        assert not level_2["files"]

    logger.debug("Determined the following namespaces:")
    logger.debug(f"AIO namespace: {namespace}")
    logger.debug(f"Usage system namespace: {clusterconfig_namespace}")
    logger.debug(f"ARC namespace: {arc_namespace}")
    logger.debug(f"ACS namespace: {acs_namespace}")
    logger.debug(f"ACSTOR namespace: {acstor_namespace}")
    logger.debug(f"SSC namespace: {ssc_namespace}")

    return {
        "arc": arc_namespace,
        "aio": namespace,
        "acs": acs_namespace,
        "acstor": acstor_namespace,
        "ssc": ssc_namespace,
        "usage_system": clusterconfig_namespace,
    }


def run_bundle_command(
    command: str,
    tracked_files: List[str],
) -> Tuple[Dict[str, Dict[str, List[str]]], str]:
    result = run(command)
    if not result:
        pytest.skip("No bundle was created.")
    assert result["bundlePath"]
    tracked_files.append(result["bundlePath"])
    # transform this into a walk result of an extracted zip file
    walk_result = {}
    with ZipFile(result["bundlePath"], "r") as zip:
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

    return walk_result, result["bundlePath"]


def split_name(name: str) -> List[str]:
    first_pass = name.split(".")
    second_pass = []
    for i in range(len(first_pass)):
        # we should not need to worry about trying to access too early
        # since the first part should be the workload type (ex: pod)
        if first_pass[i].isnumeric() or first_pass[i - 1].isnumeric():
            second_pass[-1] = f"{second_pass[-1]}.{first_pass[i]}"
        else:
            second_pass.append(first_pass[i])

    return second_pass
