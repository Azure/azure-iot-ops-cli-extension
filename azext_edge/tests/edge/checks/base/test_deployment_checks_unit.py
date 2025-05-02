# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import ValidationError
from kubernetes.client.models import V1ObjectMeta, V1StorageClass, V1StorageClassList, VersionInfo

from azext_edge.edge.providers.check.common import MIN_K8S_VERSION

# Stub to prevent validation of k8s objects
local_vars_configuration = Mock(client_side_validation=False)


@pytest.mark.parametrize(
    "k8s_version, expected_status",
    [
        (MIN_K8S_VERSION, "success"),
        ("1.30", "success"),
        ("1.20", "error"),
    ],
)
def test_check_k8s_version(mocked_version_client, k8s_version, expected_status):
    from azext_edge.edge.providers.check.base.deployment import _check_k8s_version

    major, minor = k8s_version.split(".")
    mocked_version_client.return_value.get_code.return_value = VersionInfo(
        local_vars_configuration=local_vars_configuration, major=major, minor=minor
    )

    result = _check_k8s_version(as_list=True)

    assert result["name"] == "evalK8sVers"
    assert result["targets"]["k8s"]["_all_"]["evaluations"][0]["status"] == expected_status
    assert result["targets"]["k8s"]["_all_"]["evaluations"][0]["value"] == k8s_version


@pytest.mark.parametrize(
    "storage_classes, expected_classes, expected_status",
    [
        (["default", "local-path"], "default,local-path", "success"),
        (["default", "local-path"], "non-default", "error"),
        ([], "default,test", "error"),
        ([], "", "error"),
    ],
)
def test_check_storage_classes(mocked_storage_client, storage_classes, expected_classes, expected_status):
    from azext_edge.edge.providers.check.base.deployment import _check_storage_classes

    mocked_storage_client.return_value.list_storage_class.return_value = V1StorageClassList(
        items=[
            V1StorageClass(metadata=V1ObjectMeta(name=sc), local_vars_configuration=local_vars_configuration)
            for sc in storage_classes
        ]
    )

    acs_config = {"feature.diskStorageClass": expected_classes}

    # if no storage classes are provided, should raise a validation error
    if expected_classes == "":
        with pytest.raises(
            ValidationError, match=r"^Provided ACS config does not contain a 'feature.diskStorageClass' value"
        ):
            _check_storage_classes(acs_config=acs_config, as_list=True)
        return

    result = _check_storage_classes(acs_config=acs_config, as_list=True)

    assert result["name"] == "evalStorageClasses"
    assert result["targets"]["cluster/storage-classes"]["_all_"]["evaluations"][-1]["status"] == expected_status
    assert result["targets"]["cluster/storage-classes"]["_all_"]["evaluations"][0]["value"] == (
        {"len(cluster/storage-classes)": len(storage_classes)} if storage_classes else "No storage classes available"
    )

    assert result["targets"]["cluster/storage-classes"]["_all_"]["evaluations"][-1]["value"] == (
        ",".join(storage_classes) if storage_classes else "No storage classes available"
    )
    assert result["targets"]["cluster/storage-classes"]["_all_"]["status"] == expected_status
    assert result["targets"]["cluster/storage-classes"]["_all_"]["conditions"] == [
        "len(cluster/storage-classes)>=1",
        f"contains(cluster/storage-classes, any({expected_classes}))",
    ]


@pytest.mark.parametrize(
    "pre_check_results, error",
    [
        (
            [
                {
                    "description": "Evaluate Kubernetes server",
                    "name": "evalK8sVers",
                    "status": "success",
                    "targets": {
                        "k8s": {
                            "_all_": {
                                "conditions": ["(k8s version)>=1.29"],
                                "evaluations": [{"status": "success", "value": "1.31"}],
                                "status": "success",
                            }
                        }
                    },
                },
                {
                    "description": "Evaluate cluster nodes",
                    "name": "evalClusterNodes",
                    "status": "success",
                    "targets": {
                        "cluster/nodes": {
                            "_all_": {
                                "conditions": ["len(cluster/nodes)>=1"],
                                "evaluations": [{"status": "success", "value": {"len(cluster/nodes)": 1}}],
                                "status": "success",
                            }
                        },
                        "cluster/nodes/k3d-k3s-default-server-0": {
                            "_all_": {
                                "conditions": [
                                    "info.architecture in (amd64)",
                                    "allocatable.cpu>=4",
                                    "allocatable.memory>=16G",
                                ],
                                "evaluations": [
                                    {"status": "success", "value": {"info.architecture": "amd64"}},
                                    {"status": "success", "value": {"allocatable.cpu": 4}},
                                    {"status": "success", "value": {"allocatable.memory": "16G"}},
                                ],
                                "status": "success",
                            }
                        },
                    },
                },
            ],
            False,
        ),
        (
            [
                {
                    "description": "Evaluate Kubernetes server",
                    "name": "evalK8sVers",
                    "status": "success",
                    "targets": {
                        "k8s": {
                            "_all_": {
                                "conditions": ["(k8s version)>=1.29"],
                                "evaluations": [{"status": "error", "value": "1.1"}],  # invalid version
                                "status": "success",
                            }
                        }
                    },
                },
                {
                    "description": "Evaluate cluster nodes",
                    "name": "evalClusterNodes",
                    "status": "success",
                    "targets": {
                        "cluster/nodes": {
                            "_all_": {
                                "conditions": ["len(cluster/nodes)>=1"],
                                "evaluations": [{"status": "success", "value": {"len(cluster/nodes)": 1}}],
                                "status": "success",
                            }
                        },
                        "cluster/nodes/k3d-k3s-default-server-0": {
                            "_all_": {
                                "conditions": [
                                    "info.architecture in (amd64)",
                                    "allocatable.cpu>=4",
                                    "allocatable.memory>=16G",
                                ],
                                "evaluations": [
                                    {
                                        "status": "error",
                                        "value": {"info.architecture": "invalid_arch"},
                                    },  # invalid architecture
                                    {"status": "error", "value": {"allocatable.cpu": 1}},  # invalid cpu count
                                    {"status": "success", "value": {"allocatable.memory": "12G"}},  # invalid memory
                                ],
                                "status": "success",
                            }
                        },
                    },
                },
            ],
            True,
        ),
    ],
    ids=["all_success", "errors"],
)
@pytest.mark.parametrize(
    "acs_config",
    [
        {"feature.diskStorageClass": "default,local-path"},
        {"feature.diskStorageClass": "singleclass"},
        {"feature.diskStorageClass": ""},
        None,
    ],
    ids=["default", "singleclass", "noclass", "no_config"],
)
@pytest.mark.parametrize(
    "storage_space_check",
    [
        True,
        False,
    ],
    ids=["storage", "no_storage"],
)
def test_validate_cluster_prechecks(mocker, pre_check_results, error, acs_config, storage_space_check):
    from azext_edge.edge.providers.check.base.deployment import validate_cluster_prechecks

    kwargs = {"acs_config": acs_config}
    kwargs.update({"storage_space_check": storage_space_check})

    mocked_precheck = mocker.patch(
        "azext_edge.edge.providers.check.base.deployment.check_pre_deployment", return_value=pre_check_results
    )
    if error:
        with pytest.raises(Exception, match=r"^Cluster readiness pre-checks failed") as ex:
            validate_cluster_prechecks(**kwargs)
        assert "Cluster readiness pre-checks failed" in str(ex.value)
        assert isinstance(ex.value, ValidationError)
        assert_cluster_precheck_errors(str(ex.value), pre_check_results)

    else:
        validate_cluster_prechecks(**kwargs)

    mocked_precheck.assert_called_once_with(acs_config=acs_config, storage_space_check=storage_space_check)


def assert_cluster_precheck_errors(error_str: str, pre_check_results: List[dict]):
    failed_targets = []
    failed_conditions = []
    failed_evals = []
    for check in pre_check_results:
        for target in check["targets"]:
            for namespace in check["targets"][target]:
                for idx, check_eval in enumerate(check["targets"][target][namespace]["evaluations"]):
                    if check_eval["status"] not in ["success", "skipped"]:
                        expected_condition = check["targets"][target][namespace]["conditions"][idx]
                        failed_targets.append(target)
                        failed_conditions.append(expected_condition)
                        failed_evals.append(check_eval["value"])
    assert all(target in error_str for target in failed_targets)
    assert all(condition in error_str for condition in failed_conditions)
    assert all(str(eval) in error_str for eval in failed_evals)


@pytest.mark.parametrize(
    "acs_config",
    [
        {"feature.diskStorageClass": "default,local-path"},
        {"feature.diskStorageClass": "singleclass"},
        {"feature.diskStorageClass": ""},
        None,
    ],
    ids=["default", "singleclass", "noclass", "no_config"],
)
@pytest.mark.parametrize(
    "storage_space_check",
    [
        True,
        False,
    ],
    ids=["storage", "no_storage"],
)
def test_check_pre_deployment(mocker, acs_config, storage_space_check):
    from azext_edge.edge.providers.check.base.deployment import check_pre_deployment

    mocker.patch(
        "azext_edge.edge.providers.check.base.deployment._check_k8s_version",
        return_value={"name": "evalK8sVers", "status": "success"},
    )
    mocker.patch(
        "azext_edge.edge.providers.check.base.deployment.check_nodes",
        return_value={"name": "evalClusterNodes", "status": "success"},
    )
    mocker.patch(
        "azext_edge.edge.providers.check.base.deployment._check_storage_classes",
        return_value={"name": "evalStorageClasses", "status": "success"},
    )

    kwargs = {}
    kwargs.update(acs_config=acs_config, storage_space_check=storage_space_check)
    result = check_pre_deployment(as_list=True, **kwargs)

    expected_checks = ["evalK8sVers", "evalClusterNodes"]
    if acs_config:
        expected_checks.append("evalStorageClasses")

    # ensure correct checks are present
    for idx, check in enumerate(expected_checks):
        assert result[idx]["name"] == check
        assert result[idx]["status"] == "success"
