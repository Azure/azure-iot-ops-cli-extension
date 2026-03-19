# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import ArgumentUsageError
from azext_edge.edge.providers.check.common import CoreServiceResourceKinds, ResourceOutputDetailLevel
from azext_edge.edge.providers.check.opcua import evaluate_core_service_runtime

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_pod_stub
)
from ...generators import generate_random_string


@pytest.mark.parametrize(
    "resource_kinds",
    [None, [], ["test"]],
)
@pytest.mark.parametrize('ops_service', ['opcua'])
def test_check_opcua_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE.value:
            "azext_edge.edge.providers.check.opcua.evaluate_core_service_runtime",
    }

    try:
        assert_check_by_resource_types(ops_service, mocker, resource_kinds, eval_lookup)
    except ArgumentUsageError as e:
        assert "Resource filtering is not supported for service opcua." in str(e)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "opcua-broker-1", "opcua*", "*broker*"])
@pytest.mark.parametrize(
    "pods, namespace_conditions, namespace_evaluations",
    [
        (
            # pods
            [
                generate_pod_stub(
                    name="opcua-broker-1",
                    phase="Running",
                )
            ],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/status.phase", "Running"),
                ],
            ]
        ),
        (
            # pods
            [
                generate_pod_stub(
                    name="opcua-broker-1",
                    phase="Failed",
                )
            ],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "error")
                ],
            ]
        ),
    ]
)
def test_evaluate_core_service_runtime(
    mocker,
    pods,
    namespace_conditions,
    namespace_evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.opcua.get_namespaced_pods_by_prefix",
        return_value=pods,
    )

    namespace = generate_random_string()
    for pod in pods:
        pod.metadata.namespace = namespace
    result = evaluate_core_service_runtime(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalCoreServiceRuntime"
    assert result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

    for namespace in target:
        assert namespace in result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)


def test_evaluate_core_service_runtime_no_pods(mocker):
    """When OPC UA is enabled but no pods are found, the check should return an error."""
    mocker.patch(
        "azext_edge.edge.providers.check.opcua.get_namespaced_pods_by_prefix",
        return_value=[],
    )
    mocker.patch(
        "azext_edge.edge.providers.check.opcua.get_resources_by_name",
        return_value=[],
    )
    result = evaluate_core_service_runtime()

    assert result["name"] == "evalCoreServiceRuntime"
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    assert "_all_" in target
    assert target["_all_"]["status"] == "error"
    assert any(
        "No OPC UA broker pods detected." in str(e.get("value", ""))
        for e in target["_all_"]["evaluations"]
    )


def test_evaluate_core_service_runtime_disabled(mocker):
    """When OPC UA feature is disabled in the instance spec, the check should return skipped."""
    mocker.patch(
        "azext_edge.edge.providers.check.opcua.get_namespaced_pods_by_prefix",
        return_value=[],
    )
    mocker.patch(
        "azext_edge.edge.providers.check.opcua.get_resources_by_name",
        return_value=[{"spec": {"features": {"opcua": {"mode": "Disabled"}}}}],
    )
    result = evaluate_core_service_runtime()

    assert result["name"] == "evalCoreServiceRuntime"
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    assert "_all_" in target
    assert target["_all_"]["status"] == "skipped"
    assert any(
        "disabled" in str(e.get("value", "")).lower()
        for e in target["_all_"]["evaluations"]
    )
