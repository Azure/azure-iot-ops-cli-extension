# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.providers.check.common import CoreServiceResourceKinds, ResourceOutputDetailLevel
from azext_edge.edge.providers.check.opcua import evaluate_asset_types, evaluate_core_service_runtime
from azext_edge.edge.providers.edge_api.opcua import OpcuaResourceKinds

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_pod_stub
)
from ...generators import generate_random_string


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [OpcuaResourceKinds.ASSET_TYPE.value],
    ],
)
@pytest.mark.parametrize('ops_service', ['opcua'])
def test_check_opcua_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE.value:
            "azext_edge.edge.providers.check.opcua.evaluate_core_service_runtime",
        OpcuaResourceKinds.ASSET_TYPE.value: "azext_edge.edge.providers.check.opcua.evaluate_asset_types",
    }

    assert_check_by_resource_types(ops_service, mocker, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "boiler-1", "boiler*"])
@pytest.mark.parametrize(
    "asset_types, namespace_conditions, namespace_evaluations",
    [
        (
            # asset_types
            [
                {
                    "metadata": {
                        "name": "boiler-1",
                    },
                    "spec": {
                        "description": "",
                        "labels": [],
                        "name": "boiler_1",
                        "schema": '''{"@context":"dtmi:dtdl:context;3","@type":"Interface",
                        "@id":"dtmi:microsoft:opcuabroker:Boiler__2;1","contents":[]}'''
                    }
                },
                {
                    "metadata": {
                        "name": "boiler-2",
                    },
                    "spec": {
                        "description": "",
                        "labels": [],
                        "name": "boiler_2",
                        "schema": '''{"@context":"dtmi:dtdl:context;3","@type":"Interface",
                        "@id":"dtmi:microsoft:opcuabroker:Boiler__2;1","contents":[]}'''
                    }
                },
            ],
            # namespace conditions str
            ["len(asset_types)>=0"],
            # namespace evaluations str
            [
                [],
            ]
        ),
        (
            # asset_types
            [],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "skipped"),
                    ("value/asset_types", "Unable to fetch OPC UA broker asset types in any namespaces.")
                ],
            ]
        ),
    ]
)
def test_asset_types_checks(
    mocker,
    asset_types,
    namespace_conditions,
    namespace_evaluations,
    mock_generate_opcua_target_resources,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": asset_types}],
    )

    namespace = generate_random_string()
    for asset_type in asset_types:
        asset_type['metadata']['namespace'] = namespace
    result = evaluate_asset_types(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalAssetTypes"
    assert result["targets"]["assettypes.opcuabroker.iotoperations.azure.com"]
    target = result["targets"]["assettypes.opcuabroker.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["assettypes.opcuabroker.iotoperations.azure.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)


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
    mock_generate_opcua_target_resources,
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
