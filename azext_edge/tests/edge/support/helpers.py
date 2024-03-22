# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List
from os import mkdir
from shutil import rmtree


def convert_file_names(files: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """Maps deployment/pod/etc to list of dissembled file names"""
    file_name_objs = {}
    for full_name in files:
        name = full_name.split(".")
        file_type = name.pop(0)
        if file_type not in file_name_objs:
            file_name_objs[file_type] = []

        name_obj = {"extension": name.pop(-1), "full_name": full_name}
        assert name_obj["extension"] in ["log", "txt", "yaml"]

        # custom types should have a v
        if file_type not in ["daemonset", "deployment", "pod", "pvc", "replicaset", "service", "statefulset"]:
            name_obj["version"] = name.pop(0)
            assert name_obj["version"].startswith("v")
        name_obj["name"] = name.pop(0)

        # only logs should still have something in the name
        assert bool(name) == (name_obj["extension"] != "yaml")

        # something like "msi-adapter", "init-runner"
        if name:
            name_obj["descriptor"] = name.pop(0)
        # something like "previous", "init"
        if name:
            name_obj["sub_descriptor"] = name.pop(0)
            assert name_obj["sub_descriptor"] in ["init", "previous"]

        file_name_objs[file_type].append(name_obj)

    return file_name_objs


def check_non_custom_file_objs(
    file_objs: Dict[str, List[Dict[str, str]]],
    expected: Dict[str, List[str]]
):
    assert len(file_objs) > len(expected)
    # pod
    expected_pods = expected.pop("pod")
    file_pods = {}
    for file in file_objs["pod"]:
        if file["name"] not in file_pods:
            file_pods[file["name"]] = {"yaml_present": False}
        converted_file = file_pods[file["name"]]

        if file["extension"] == "yaml":
            # only one yaml per pod
            assert not converted_file["yaml_present"]
            converted_file["yaml_present"] = True
        elif file.get("sub_descriptor") in ["init", None]:
            assert file.get("sub_descriptor") not in converted_file
            converted_file[file["descriptor"]] = True
        else:
            assert file["sub_descriptor"] == "previous"
            assert file["sub_descriptor"] not in converted_file
            converted_file[file["sub_descriptor"]] = True
            # if msi-adapter.previous present, msi-adapter must present too
            # for some reason does not apply to xxx.init
            if file["descriptor"] not in converted_file:
                converted_file[file["descriptor"]] = False

    assert len(file_pods) == len(expected_pods)
    for name, files in file_pods.items():
        assert any([
            name in expected_pods,
            name.rsplit("-", 1)[0] in expected_pods,
            name.rsplit("-", 2)[0] in expected_pods
        ])
        for value in files.values():
            assert value

    # other
    for key in expected:
        assert len(file_objs[key]) == len(expected[key])
        for file in file_objs[key]:
            assert file["extension"] == "yaml"
            # make sure we can check names like aio-dp-operator-5c74655f8b-zr5xm
            assert (
                (file["name"] in expected[key])
                or (file["name"].rsplit("-", 1)[0] in expected[key])
                or (file["name"].rsplit("-", 2)[0] in expected[key])
            )


def ensure_clean_dir(path: str, tracked_files: List[str]):
    try:
        mkdir(path)
        tracked_files.append(path)
    except FileExistsError:
        rmtree(path)
        mkdir(path)
