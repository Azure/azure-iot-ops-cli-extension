# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
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

    result = _check_storage_classes(acs_config=acs_config, as_list=True)

    assert result["name"] == "evalStorageClasses"
    assert result["targets"]["cluster/storage-classes"]["_all_"]["evaluations"][-1]["status"] == expected_status


def test_validate_cluster_prechecks(mocker):
    from azext_edge.edge.providers.check.base.deployment import validate_cluster_prechecks

    mocker.patch(
        "azext_edge.edge.providers.check.base.deployment.check_pre_deployment",
        return_value=[
            {
                "status": "error",
                "targets": {
                    "cluster/nodes": {
                        "_all_": {
                            "evaluations": [{"status": "error", "value": "No nodes detected."}],
                            "conditions": ["len(cluster/nodes)>=1"],
                        }
                    }
                },
            }
        ],
    )

    with pytest.raises(Exception) as exc_info:
        validate_cluster_prechecks()

    assert "Cluster readiness pre-checks failed" in str(exc_info.value)


@pytest.mark.parametrize(
    "acs_config",
    [
        {"feature.diskStorageClass": "default,local-path"},
        None,
    ],
)
def test_check_pre_deployment(mocker, acs_config):
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
    if acs_config:
        kwargs.update({"acs_config": acs_config})
    result = check_pre_deployment(as_list=True, **kwargs)

    assert len(result) == 3 if acs_config else 2
    assert result[0]["name"] == "evalK8sVers"
    assert result[1]["name"] == "evalClusterNodes"

    if acs_config:
        assert result[2]["name"] == "evalStorageClasses"
