# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.providers.check.dataflow import (
    evaluate_dataflow_endpoints,
    evaluate_core_service_runtime,
    evaluate_dataflow_profiles,
    evaluate_dataflows,
)
from azext_edge.edge.providers.check.common import (
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel,
)
from azext_edge.edge.providers.edge_api.dataflow import DataflowResourceKinds

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_pod_stub,
)
from ...generators import generate_random_string


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [DataflowResourceKinds.DATAFLOW.value],
        [
            DataflowResourceKinds.DATAFLOW.value,
            DataflowResourceKinds.DATAFLOWENDPOINT.value,
        ],
        [
            DataflowResourceKinds.DATAFLOW.value,
            DataflowResourceKinds.DATAFLOWENDPOINT.value,
            DataflowResourceKinds.DATAFLOWPROFILE.value,
        ],
    ],
)
@pytest.mark.parametrize("ops_service", ["dataflow"])
def test_check_dataflow_by_resource_types(
    ops_service, mocker, mock_resource_types, resource_kinds
):
    eval_lookup = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE.value:
            "azext_edge.edge.providers.check.dataflow.evaluate_core_service_runtime",
        DataflowResourceKinds.DATAFLOW.value:
            "azext_edge.edge.providers.check.dataflow.evaluate_dataflows",
        DataflowResourceKinds.DATAFLOWENDPOINT.value:
            "azext_edge.edge.providers.check.dataflow.evaluate_dataflow_endpoints",
        DataflowResourceKinds.DATAFLOWPROFILE.value:
            "azext_edge.edge.providers.check.dataflow.evaluate_dataflow_profiles",
    }

    assert_check_by_resource_types(ops_service, mocker, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "dataflows, profiles, endpoints, conditions, evaluations",
    [
        # dataflows (valid)
        (
            # dataflows
            [
                {
                    "metadata": {
                        "name": "dataflow-2",
                    },
                    "spec": {
                        "mode": "Enabled",
                        "profileRef": "dataflow-profile-1",
                        "operations": [
                            {
                                "operationType": "source",
                                "sourceSettings": {
                                    "endpointRef": "dataflow-endpoint-1",
                                    "assetRef": "asset-ref",
                                    "serializationFormat": "JSON",
                                    "dataSources": ["one", "two"]
                                }
                            },
                            {
                                "operationType": "builtintransformation",
                                "builtInTransformationSettings": {
                                    "schemaRef": "Schema",
                                    "datasets": [
                                        {
                                            "description": "desc",
                                            "key": "key",
                                            "expression": "$1 < 20",
                                            "inputs": [
                                                "temperature",
                                                "pressure"
                                            ]
                                        },
                                    ],
                                    "filter": [
                                        {
                                            "expression": "$1 > 10",
                                            "type": "operationType",
                                            "inputs": [
                                                "temperature",
                                                "pressure"
                                            ]
                                        }
                                    ],
                                    "map": [
                                        {
                                            "description": "desc",
                                            "output": "output",
                                            "inputs": [
                                                "temperature",
                                                "pressure"
                                            ]
                                        }
                                    ]
                                }
                            },
                            {
                                "operationType": "destination",
                                "destinationSettings": {
                                    "endpointRef": "dataflow-endpoint-2",
                                    "dataDestination": "destination"
                                }
                            }
                        ]
                    },
                },
            ],
            # profiles
            [{
                "metadata": {
                    "name": "dataflow-profile-1"
                }
            }],
            # endpoints
            [
                {
                    "metadata": {
                        "name": "dataflow-endpoint-1"
                    }
                },
                {
                    "metadata": {
                        "name": "dataflow-endpoint-2"
                    }
                }
            ],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "success"),
                ],
            ],
        ),
        # no dataflows
        (
            # dataflows
            [],
            # profiles
            [],
            # endpoints
            [],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "skipped"),
                    (
                        "value/dataflows",
                        "No Dataflow resources detected in any namespace.",
                    ),
                ]
            ],
        ),
    ],
)
def test_evaluate_dataflows(
    mocker,
    dataflows,
    profiles,
    endpoints,
    conditions,
    evaluations,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": dataflows}, {"items": profiles}, {"items": endpoints}],
    )

    namespace = generate_random_string()
    for dataflow in dataflows:
        dataflow["metadata"]["namespace"] = namespace
    result = evaluate_dataflows(detail_level=detail_level)

    assert result["name"] == "evalDataflows"
    assert result["targets"]["dataflows.connectivity.iotoperations.azure.com"]
    target = result["targets"]["dataflows.connectivity.iotoperations.azure.com"]

    for namespace in target:
        assert (
            namespace
            in result["targets"]["dataflows.connectivity.iotoperations.azure.com"]
        )

        target[namespace]["conditions"] = (
            []
            if not target[namespace]["conditions"]
            else target[namespace]["conditions"]
        )
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", ["endpoint*", "endpoint-?", "*point-?"])
@pytest.mark.parametrize(
    "endpoints, conditions, evaluations",
    [
        (
            # endpoints
            [
                # kafka endpoint
                {
                    "metadata": {
                        "name": "endpoint-1",
                    },
                    "spec": {
                        "endpointType": "kafka",
                        "authentication": {"method": "authMethod"},
                        "kafkaSettings": {
                            "host": "kafkaHost",
                            "consumerGroupId": None,
                            "compression": "compression",
                            "kafkaAcks": 3,
                            "tls": {
                                "mode": "Enabled"
                            },
                            "batching": {
                                "latencyMs": 300
                            }
                        }
                    },
                },
                # localStorage
                {
                    "metadata": {
                        "name": "endpoint-2",
                    },
                    "spec": {
                        "endpointType": "localstorage",
                        "authentication": {"method": "authMethod"},
                        "localStorageSettings": {
                            "persistentVolumeClaimRef": "ref"
                        }
                    },
                },
                # Fabric Onelake
                {
                    "metadata": {
                        "name": "endpoint-3",
                    },
                    "spec": {
                        "endpointType": "fabriconelake",
                        "authentication": {"method": "authMethod"},
                        "fabricOneLakeSettings": {
                            "host": "fabric_host",
                            "names": {
                                "lakehouseName": "lakehouse",
                                "workspaceName": "workspaceName"
                            },
                            "batching": {
                                "latencySeconds": 2
                            }
                        }
                    },
                },
                # datalake storage
                {
                    "metadata": {
                        "name": "endpoint-4",
                    },
                    "spec": {
                        "endpointType": "datalakestorage",
                        "authentication": {"method": "authMethod"},
                        "datalakeStorageSettings": {
                            "host": "datalakeHost",
                            "batching": {
                                "latencySeconds": 12
                            }
                        }
                    },
                },
                # dataExplorer
                {
                    "metadata": {
                        "name": "endpoint-5",
                    },
                    "spec": {
                        "endpointType": "dataExplorer",
                        "authentication": {"method": "authMethod"},
                        "dataExplorerSettings": {
                            "database": "databse",
                            "host": "data_explorer_host",
                            "batching": {
                                "latencySeconds": 3
                            }
                        }
                    },
                },
                # mqtt
                {
                    "metadata": {
                        "name": "endpoint-6",
                    },
                    "spec": {
                        "endpointType": "mqtt",
                        "authentication": {"method": "authMethod"},
                        "mqttSettings": {
                            "host": "mqttHost",
                            "protocol": "Websockets",
                            "clientIdPrefix": None,
                            "qos": 3,
                            "maxInflightMessages": 100,
                            "tls": {
                                "mode": "Enabled",
                                "trustedCaCertificateConfigMapRef": "ref"
                            }
                        }
                    },
                },
            ],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "success"),
                ],
            ],
        ),
        # no endpoints
        (
            # endpoints
            [],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "skipped"),
                    (
                        "value/endpoints",
                        "No Dataflow Endpoints detected in any namespace.",
                    ),
                ]
            ],
        ),
    ],
)
def test_evaluate_dataflow_endpoints(
    mocker,
    endpoints,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": endpoints}],
    )

    namespace = generate_random_string()
    for endpoint in endpoints:
        endpoint["metadata"]["namespace"] = namespace
    result = evaluate_dataflow_endpoints(
        detail_level=detail_level, resource_name=resource_name
    )

    assert result["name"] == "evalDataflowEndpoints"
    assert result["targets"]["dataflowendpoints.connectivity.iotoperations.azure.com"]
    target = result["targets"]["dataflowendpoints.connectivity.iotoperations.azure.com"]

    for namespace in target:
        assert (
            namespace
            in result["targets"][
                "dataflowendpoints.connectivity.iotoperations.azure.com"
            ]
        )

        target[namespace]["conditions"] = (
            []
            if not target[namespace]["conditions"]
            else target[namespace]["conditions"]
        )
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "profiles, conditions, evaluations",
    [
        (
            # profiles
            [
                {
                    "metadata": {
                        "name": "profile-1",
                    },
                    "spec": {"mode": "Enabled", "profileRef": "dataflow-profile-1", "instanceCount": 1},
                }
            ],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "success"),
                ],
            ],
        ),
        # no profiles
        (
            # profiles
            [],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "skipped"),
                    (
                        "value/profiles",
                        "No Dataflow Profiles detected in any namespace.",
                    ),
                ]
            ],
        ),
    ],
)
def test_evaluate_dataflow_profiles(
    mocker,
    profiles,
    conditions,
    evaluations,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": profiles}],
    )

    namespace = generate_random_string()
    for endpoint in profiles:
        endpoint["metadata"]["namespace"] = namespace
    result = evaluate_dataflow_profiles(detail_level=detail_level)

    assert result["name"] == "evalDataflowProfiles"
    assert result["targets"]["dataflowprofiles.connectivity.iotoperations.azure.com"]
    target = result["targets"]["dataflowprofiles.connectivity.iotoperations.azure.com"]

    for namespace in target:
        assert (
            namespace
            in result["targets"][
                "dataflowprofiles.connectivity.iotoperations.azure.com"
            ]
        )

        target[namespace]["conditions"] = (
            []
            if not target[namespace]["conditions"]
            else target[namespace]["conditions"]
        )
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "resource_name",
    [
        None,
        "aio-dataflow-*",
    ],
)
@pytest.mark.parametrize(
    "pods, namespace_conditions, namespace_evaluations",
    [
        (
            # pods
            [
                generate_pod_stub(
                    name="aio-dataflow-operator-12345",
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
            ],
        ),
        (
            # pods
            [
                generate_pod_stub(
                    name="aio-dataflow-operator-12345",
                    phase="Failed",
                )
            ],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [("status", "error")],
            ],
        ),
    ],
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
        "azext_edge.edge.providers.check.dataflow.get_namespaced_pods_by_prefix",
        return_value=pods,
    )

    namespace = generate_random_string()
    for pod in pods:
        pod.metadata.namespace = namespace
    result = evaluate_core_service_runtime(
        detail_level=detail_level, resource_name=resource_name
    )

    assert result["name"] == "evalCoreServiceRuntime"
    assert result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

    for namespace in target:
        assert (
            namespace
            in result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
        )

        target[namespace]["conditions"] = (
            []
            if not target[namespace]["conditions"]
            else target[namespace]["conditions"]
        )
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
