# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.providers.edge_api.lnm import LnmResourceKinds
from azext_edge.edge.providers.check.lnm import evaluate_lnms

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
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
        LnmResourceKinds.LNM.value: "azext_edge.edge.providers.check.lnm.evaluate_lnms",
    }

    assert_check_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


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
            ["len(lnms)>=1", "status.configStatusLevel", "spec.allowList", "spec.image"],
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
    assert result["targets"]["lnmz.aio.com"]
    target = result["targets"]["lnmz.aio.com"]

    for namespace in target:
        assert namespace in result["targets"]["lnmz.aio.com"]

        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
