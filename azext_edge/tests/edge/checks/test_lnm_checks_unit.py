# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.providers.check.common import CoreServiceResourceKinds, ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api.lnm import LnmResourceKinds
from azext_edge.edge.providers.check.lnm import evaluate_core_service_runtime, evaluate_lnms

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_pod_stub,
    generate_resource_stub
)
from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [LnmResourceKinds.LNM.value],
    ],
)
@pytest.mark.parametrize('ops_service', ['lnm'])
def test_check_lnm_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE.value:
            "azext_edge.edge.providers.check.lnm.evaluate_core_service_runtime",
        LnmResourceKinds.LNM.value: "azext_edge.edge.providers.check.lnm.evaluate_lnms",
    }

    assert_check_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "lnms, namespace_conditions, namespace_evaluations",
    [
        (
            # lnms
            [
                generate_resource_stub(
                    metadata={
                        "name": "test-lnm",
                    },
                    spec={
                        "allowList": {
                            "domains": [
                                {
                                    "destinationType": "internal",
                                    "destinationUrl": "microsoft.com"
                                },
                                {
                                    "destinationType": "external",
                                    "destinationUrl": "microsoftonline.com"
                                }
                            ],
                            "enableArcDomains": True,
                            "sourceIpRange": ""
                        },
                        "image": {
                            "pullPolicy": "IfNotPresent",
                            "pullSecrets": [
                                {
                                    "name": "regcred"
                                }
                            ],
                            "repository": "mcr.microsoft.com/azureiotedge-lnm",
                            "tag": "1.0.0"
                        },
                        "endpointType": "mqtt",
                        "level": "debug",
                        "logLevel": "debug",
                        "nodeTolerations": [
                            {
                                "effect": "NoSchedule",
                                "key": "node-role.kubernetes.io/master"
                            }
                        ],
                        "openTelemetryMetricsCollectorAddr": "",
                        "parentIpAddr": "",
                        "parentPort": 0,
                        "port": 0,
                        "replicas": 0
                    },
                    status={
                        "configStatusLevel": "ok"
                    }
                ),
                generate_resource_stub(
                    metadata={
                        "name": "test-lnm2",
                    },
                    spec={
                        "allowList": {
                            "domains": [
                                {
                                    "destinationType": "internal",
                                    "destinationUrl": "microsoft.com"
                                },
                            ],
                            "enableArcDomains": True,
                            "sourceIpRange": ""
                        },
                        "image": {
                            "pullPolicy": "IfNotPresent",
                            "pullSecrets": [
                                {
                                    "name": "regcred"
                                }
                            ],
                            "repository": "mcr.microsoft.com/azureiotedge-lnm",
                            "tag": "1.0.0"
                        },
                        "endpointType": "mqtt",
                        "level": "debug",
                        "logLevel": "debug",
                        "nodeTolerations": [
                            {
                                "effect": "NoSchedule",
                                "key": "node-role.kubernetes.io/master"
                            }
                        ],
                        "openTelemetryMetricsCollectorAddr": "",
                        "parentIpAddr": "",
                        "parentPort": 0,
                        "port": 0,
                        "replicas": 0
                    },
                    status={
                        "configStatusLevel": "ok",
                    }
                )
            ],
            # namespace conditions str
            ["len(lnms)>=1", "status.configStatusLevel", "spec.allowList", "spec.image"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/status.configStatusLevel", "ok"),
                ],
            ]
        ),
        (
            # lnms
            [
                {
                    "metadata": {
                        "name": "test-lnm2",
                    },
                    "status": {
                        "configStatusLevel": "warn",
                        "configStatusDescription": "test warning"
                    },
                    "spec": {
                        "allowList": {
                            "domains": [
                                {
                                    "destinationType": "internal",
                                    "destinationUrl": "microsoft.com"
                                },
                                {
                                    "destinationType": "external",
                                    "destinationUrl": "microsoftonline.com"
                                }
                            ],
                            "enableArcDomains": True,
                            "sourceIpRange": ""
                        }
                    }
                }
            ],
            # namespace conditions str
            ["len(lnms)>=1", "status.configStatusLevel", "spec.allowList", "spec.image"],
            # namespace evaluations str
            [
                [
                    ("status", "warning"),
                    ("value/status.configStatusLevel", "warn"),
                ],
            ]
        ),
        (
            # lnms
            [],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "skipped")
                ],
            ]
        ),
    ]
)
def test_lnm_checks(
    mocker,
    mock_get_namespaced_pods_by_prefix,
    mock_generate_lnm_target_resources,
    lnms,
    namespace_conditions,
    namespace_evaluations,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": lnms}],
    )

    namespace = generate_generic_id()
    for lnm in lnms:
        lnm['metadata']['namespace'] = namespace
    result = evaluate_lnms(detail_level=detail_level)

    assert result["name"] == "evalLnms"
    assert result["targets"]["lnmz.layerednetworkmgmt.iotoperations.azure.com"]
    target = result["targets"]["lnmz.layerednetworkmgmt.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["lnmz.layerednetworkmgmt.iotoperations.azure.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "pods, namespace_conditions, namespace_evaluations",
    [
        (
            # pods
            [
                generate_pod_stub(
                    name="lnm-operator-1",
                    phase="Running",
                    conditions=[
                        {
                            "type": "Ready",
                            "status": "True",
                        }
                    ]
                )
            ],
            # namespace conditions str
            [
                "pod/lnm-operator-1.status.phase",
                "pod/lnm-operator-1.status.conditions.ready",
            ],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/status.phase", "Running"),
                ],
                [
                    ("status", "success"),
                    ("value/status.conditions.ready", True),
                ],
            ]
        ),
        (
            # pods
            [
                generate_pod_stub(
                    name="lnm-operator-1",
                    phase="Running",
                    conditions=[
                        {
                            "type": "Ready",
                            "status": "False",
                            "reason": "ContainersNotReady",
                            "message": "containers with unready status: [lnm-operator]",
                        }
                    ]
                )
            ],
            # namespace conditions str
            [
                "pod/lnm-operator-1.status.phase",
                "pod/lnm-operator-1.status.conditions.ready",
            ],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/status.phase", "Running"),
                ],
                [
                    ("status", "error"),
                    ("value/status.conditions.ready", False),
                ],
            ]
        ),
        (
            # pods
            [
                generate_pod_stub(
                    name="lnm-operator-1",
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
    mock_get_namespaced_pods_by_prefix,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.lnm.get_namespaced_pods_by_prefix",
        return_value=pods,
    )

    namespace = generate_generic_id()
    for pod in pods:
        pod.metadata.namespace = namespace
    result = evaluate_core_service_runtime(detail_level=detail_level)

    assert result["name"] == "evalCoreServiceRuntime"
    assert result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

    for namespace in target:
        assert namespace in result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
