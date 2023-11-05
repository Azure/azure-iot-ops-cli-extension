# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


import pytest
from kubernetes.client.models import V1Scale, V1ObjectMeta, V1ScaleSpec, V1ScaleStatus
from azext_edge.edge.providers.edge_api.lnm import LnmResourceKinds
from azext_edge.edge.providers.check.lnm import evaluate_lnms, evaluate_scales

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_resource_stub,
)
from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [LnmResourceKinds.LNM.value],
        [LnmResourceKinds.SCALE.value],
        [LnmResourceKinds.LNM.value, LnmResourceKinds.SCALE.value],
    ],
)
@pytest.mark.parametrize('edge_service', ['lnm'])
def test_check_lnm_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        LnmResourceKinds.LNM.value: "azext_edge.edge.providers.check.lnm.evaluate_lnms",
        LnmResourceKinds.SCALE.value: "azext_edge.edge.providers.check.lnm.evaluate_scales",
    }

    assert_check_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


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
                                "microsoft.com",
                                "microsoftonline.com"
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
                                "microsoftonline.com"
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
            ["len(lnms)>=0", "status.configStatusLevel", "spec.allowList", "spec.image"],
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
                                "microsoft.com",
                                "microsoftonline.com"
                            ],
                            "enableArcDomains": True,
                            "sourceIpRange": ""
                        }
                    }
                }
            ],
            # namespace conditions str
            ["len(lnms)>=0", "status.configStatusLevel", "spec.allowList", "spec.image"],
            # namespace evaluations str
            [
                [
                    ("status", "warning"),
                    ("value/status.configStatusLevel", "warn"),
                ],
            ]
        ),
    ]
)
def test_lnm_checks(
    mocker,
    mock_evaluate_lnm_pod_health,
    mock_evaluate_pod_for_other_namespace,
    lnms,
    namespace_conditions,
    namespace_evaluations,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": lnms}],
    )

    namespace = generate_generic_id()
    for lnm in lnms:
        lnm['metadata']['namespace'] = namespace
    result = evaluate_lnms()

    assert result["name"] == "evalLnms"
    assert result["targets"]["lnmz.layerednetworkmgmt.iotoperations.azure.com"]
    target = result["targets"]["lnmz.layerednetworkmgmt.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["lnmz.layerednetworkmgmt.iotoperations.azure.com"]

        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)


def generate_scale_resource_stub(
    name: str,
    replicas: int,
) -> V1Scale:
    meta = V1ObjectMeta(name=name)
    spec = V1ScaleSpec(replicas=replicas)
    status = V1ScaleStatus(replicas=replicas, selector=None)

    v1scale_obj = V1Scale(
        api_version="autoscaling/v1",
        kind="Scale",
        metadata=meta,
        spec=spec,
        status=status
    )

    return v1scale_obj


@pytest.mark.parametrize(
    "scales, namespace_conditions, namespace_evaluations",
    [
        (
            # scales
            [
                generate_scale_resource_stub(
                    name="test-scale",
                    replicas=1,
                ),
                generate_scale_resource_stub(
                    name="test-scale2",
                    replicas=3,
                ),
            ],
            # namespace conditions str
            ["len(scales)>=0", "spec.replicas", "status.replicas"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.replicas", 1),
                ],
                [
                    ("status", "success"),
                    ("value/status.replicas", 1),
                ],
            ]
        ),
        (
            # scales
            [
                generate_scale_resource_stub(
                    name="test-scale2",
                    replicas=-1,
                ),
            ],
            # namespace conditions str
            ["len(scales)>=0", "spec.replicas", "status.replicas"],
            # namespace evaluations str
            [
                [
                    ("status", "error"),
                    ("value/spec.replicas", -1),
                ],
                [
                    ("status", "error"),
                    ("value/status.replicas", -1),
                ],
            ]
        ),
    ]
)
def test_scale_checks(
    mocker,
    scales,
    namespace_conditions,
    namespace_evaluations,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.lnm.get_deployment_scale_grouped_by_namespace",
        side_effect=[[("items", scales)]],
    )

    namespace = generate_generic_id()
    for scale in scales:
        scale.metadata.namespace = namespace
    result = evaluate_scales()

    assert result["name"] == "evalScales"
    assert result["targets"]["scales.autoscaling"]
    target = result["targets"]["scales.autoscaling"]

    for namespace in target:
        assert namespace in result["targets"]["scales.autoscaling"]

        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
