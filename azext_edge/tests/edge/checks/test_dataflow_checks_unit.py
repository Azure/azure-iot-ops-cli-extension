# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
from azext_edge.edge.providers.check.dataflow import (
    DEFAULT_DATAFLOW_PROFILE,
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

dataflow_conditions = [
    "spec.profileRef",
    "len(spec.operations)<=3",
    "spec.operations[*].sourceSettings.endpointRef",
    "ref(spec.operations[*].sourceSettings.endpointRef).endpointType in ('kafka','mqtt')",
    "spec.operations[*].destinationSettings.endpointRef",
    "len(spec.operations[*].sourceSettings)==1",
    "len(spec.operations[*].destinationSettings)==1",
]


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
def test_check_dataflow_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
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
                                    "dataSources": ["one", "two"],
                                },
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
                                            "inputs": ["temperature", "pressure"],
                                        },
                                    ],
                                    "filter": [
                                        {
                                            "expression": "$1 > 10",
                                            "type": "operationType",
                                            "inputs": ["temperature", "pressure"],
                                        }
                                    ],
                                    "map": [
                                        {
                                            "description": "desc",
                                            "output": "output",
                                            "inputs": ["temperature", "pressure"],
                                        }
                                    ],
                                },
                            },
                            {
                                "operationType": "destination",
                                "destinationSettings": {
                                    "endpointRef": "dataflow-endpoint-2",
                                    "dataDestination": "destination",
                                },
                            },
                        ],
                    },
                },
            ],
            # profiles
            [{"metadata": {"name": "dataflow-profile-1"}}],
            # endpoints
            [
                {
                    "metadata": {
                        "name": "dataflow-endpoint-1",
                    },
                    "spec": {"endpointType": "mqtt"},
                },
                {
                    "metadata": {
                        "name": "dataflow-endpoint-2",
                    },
                    "spec": {"endpointType": "kafka"},
                },
            ],
            # conditions
            dataflow_conditions,
            # evaluations
            [
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"spec.profileRef": "dataflow-profile-1"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"len(operations)": 3}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"spec.operations[*].sourceSettings.endpointRef": "dataflow-endpoint-1"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"ref(spec.operations[*].sourceSettings.endpointRef).endpointType": "mqtt"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"spec.operations[*].destinationSettings.endpointRef": "dataflow-endpoint-2"}),
                ],
            ],
        ),
        # dataflows (invalid)
        (
            # dataflows
            [
                {
                    "metadata": {
                        "name": "dataflow-1",
                    },
                    "spec": {
                        "mode": "Enabled",
                        # invalid profileRef
                        "profileRef": "nonexistent-dataflow-profile",
                        "operations": [
                            # only one destination
                            {
                                "operationType": "destination",
                                "destinationSettings": {
                                    "endpointRef": "invalid-endpoint",
                                },
                            }
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "dataflow-2",
                    },
                    "spec": {
                        "mode": "Enabled",
                        "profileRef": "real-dataflow-profile",
                        "operations": [
                            # good destination, bad source
                            {
                                "operationType": "source",
                                "sourceSettings": {
                                    "endpointRef": "invalid-endpoint",
                                },
                            },
                            {
                                "operationType": "destination",
                                "destinationSettings": {
                                    "endpointRef": "real-endpoint",
                                },
                            },
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "dataflow-3",
                    },
                    "spec": {
                        "mode": "Enabled",
                        "profileRef": "real-dataflow-profile",
                        "operations": [
                            # invalid source type
                            {
                                "operationType": "source",
                                "sourceSettings": {
                                    "endpointRef": "bad-source-endpoint",
                                },
                            },
                            {
                                "operationType": "destination",
                                "destinationSettings": {
                                    "endpointRef": "real-endpoint",
                                },
                            },
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "dataflow-4",
                    },
                    "spec": {
                        "mode": "Enabled",
                        "profileRef": "real-dataflow-profile",
                        # no operations
                        "operations": [],
                    },
                },
            ],
            # profiles
            [{"metadata": {"name": "real-dataflow-profile"}}],
            # endpoints
            [
                {
                    "metadata": {
                        "name": "real-endpoint",
                    },
                    "spec": {"endpointType": "kafka"},
                },
                {
                    "metadata": {
                        "name": "bad-source-endpoint",
                    },
                    "spec": {"endpointType": "fabriconelake"},
                },
            ],
            # conditions
            dataflow_conditions,
            # evaluations
            [
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-1",
                    ),
                    ("value", {"spec.profileRef": "nonexistent-dataflow-profile"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-1",
                    ),
                    ("value", {"len(operations)": 1}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-1",
                    ),
                    ("value", {"spec.operations[*].destinationSettings.endpointRef": "invalid-endpoint"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-1",
                    ),
                    ("value", {"len(spec.operations[*].sourceSettings)": 0}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-1",
                    ),
                    ("value", {"len(spec.operations[*].destinationSettings)": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"spec.profileRef": "real-dataflow-profile"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"len(operations)": 2}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"spec.operations[*].sourceSettings.endpointRef": "invalid-endpoint"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"ref(spec.operations[*].sourceSettings.endpointRef).endpointType": None}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"spec.operations[*].destinationSettings.endpointRef": "real-endpoint"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"len(spec.operations[*].sourceSettings)": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-2",
                    ),
                    ("value", {"len(spec.operations[*].destinationSettings)": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"spec.profileRef": "real-dataflow-profile"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"len(operations)": 2}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"spec.operations[*].sourceSettings.endpointRef": "bad-source-endpoint"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"ref(spec.operations[*].sourceSettings.endpointRef).endpointType": "fabriconelake"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"spec.operations[*].destinationSettings.endpointRef": "real-endpoint"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"len(spec.operations[*].sourceSettings)": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-3",
                    ),
                    ("value", {"len(spec.operations[*].destinationSettings)": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "dataflow-4",
                    ),
                    ("value", {"spec.profileRef": "real-dataflow-profile"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-4",
                    ),
                    ("value", {"len(operations)": 0}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-4",
                    ),
                    ("value", {"len(spec.operations[*].sourceSettings)": 0}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "dataflow-4",
                    ),
                    ("value", {"len(spec.operations[*].destinationSettings)": 0}),
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
    namespace = generate_random_string()
    for resource in [dataflows, profiles, endpoints]:
        for item in resource:
            item["metadata"]["namespace"] = namespace
    # this expects the logic to follow this path:
    # 1. get all dataflows
    # 2. get all profiles
    # 3. get all endpoints
    side_effects = [{"items": dataflows}, {"items": profiles}, {"items": endpoints}]

    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=side_effects,
    )

    result = evaluate_dataflows(detail_level=detail_level)

    assert result["name"] == "evalDataflows"
    assert result["targets"]["dataflows.connectivity.iotoperations.azure.com"]
    target = result["targets"]["dataflows.connectivity.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["dataflows.connectivity.iotoperations.azure.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
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
                            "tls": {"mode": "Enabled"},
                            "batching": {"latencyMs": 300},
                        },
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
                        "localStorageSettings": {"persistentVolumeClaimRef": "ref"},
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
                            "names": {"lakehouseName": "lakehouse", "workspaceName": "workspaceName"},
                            "batching": {"latencySeconds": 2},
                        },
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
                        "datalakeStorageSettings": {"host": "datalakeHost", "batching": {"latencySeconds": 12}},
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
                            "batching": {"latencySeconds": 3},
                        },
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
                            "tls": {"mode": "Enabled", "trustedCaCertificateConfigMapRef": "ref"},
                        },
                    },
                },
                # invalid endpoint type
                {
                    "metadata": {
                        "name": "endpoint-7",
                    },
                    "spec": {
                        "endpointType": "invalid",
                    },
                },
            ],
            # conditions
            [
                "spec.endpointType",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    (
                        "name",
                        "endpoint-1",
                    ),
                    ("value", {"spec.endpointType": "kafka"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "endpoint-2",
                    ),
                    ("value", {"spec.endpointType": "localstorage"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "endpoint-3",
                    ),
                    ("value", {"spec.endpointType": "fabriconelake"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "endpoint-4",
                    ),
                    ("value", {"spec.endpointType": "datalakestorage"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "endpoint-5",
                    ),
                    ("value", {"spec.endpointType": "dataExplorer"}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "endpoint-6",
                    ),
                    ("value", {"spec.endpointType": "mqtt"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "endpoint-7",
                    ),
                    ("value", {"spec.endpointType": "invalid"}),
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
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": endpoints}],
    )

    namespace = generate_random_string()
    for endpoint in endpoints:
        endpoint["metadata"]["namespace"] = namespace
    result = evaluate_dataflow_endpoints(detail_level=detail_level)

    assert result["name"] == "evalDataflowEndpoints"
    assert result["targets"]["dataflowendpoints.connectivity.iotoperations.azure.com"]
    target = result["targets"]["dataflowendpoints.connectivity.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["dataflowendpoints.connectivity.iotoperations.azure.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "profiles, pods, conditions, evaluations",
    [
        # good default profile (name, namespace, instance count and diagnostic vals)
        (
            # profiles
            [
                {
                    "metadata": {
                        "name": DEFAULT_DATAFLOW_PROFILE,
                        "namespace": DEFAULT_NAMESPACE,
                    },
                    "spec": {
                        "instanceCount": 1,
                        "diagnostics": {
                            "logs": {
                                "level": "info",
                                "openTelemetryExportConfig": {
                                    "otlpGrpcEndpoint": "endpoint",
                                },
                            },
                            "metrics": {
                                "openTelemetryExportConfig": {
                                    "otlpGrpcEndpoint": "endpoint",
                                }
                            },
                        },
                    },
                },
            ],
            # pods
            [
                # good profile pod
                generate_pod_stub(
                    name=f"aio-dataflow-{DEFAULT_DATAFLOW_PROFILE}-0",
                    phase="Running",
                ),
            ],
            # conditions
            [
                "spec.instanceCount",
                f"[*].metadata.name=='{DEFAULT_DATAFLOW_PROFILE}'",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    (
                        "name",
                        "profile",
                    ),
                    ("value", {"spec.instanceCount": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "pod/aio-dataflow-profile-0",
                    ),
                    ("value", {"status.phase": "Running"}),
                ],
            ],
        ),
        # good and bad profiles, no default profile warning
        (
            # profiles
            [
                {
                    "metadata": {
                        "name": "good-profile",
                        "namespace": DEFAULT_NAMESPACE,
                    },
                    "spec": {
                        "instanceCount": 1,
                        "diagnostics": {
                            "logs": {
                                "level": "info",
                                "openTelemetryExportConfig": {
                                    "otlpGrpcEndpoint": "endpoint",
                                },
                            },
                            "metrics": {
                                "openTelemetryExportConfig": {
                                    "otlpGrpcEndpoint": "endpoint",
                                }
                            },
                        },
                    },
                },
                {
                    "metadata": {
                        "name": "bad-profile",
                        "namespace": DEFAULT_NAMESPACE,
                    },
                    "spec": {
                        "instanceCount": None,
                    },
                },
            ],
            # pods
            [
                # good profile pod
                generate_pod_stub(
                    name="aio-dataflow-good-profile-0",
                    phase="Running",
                ),
            ],
            # conditions
            [
                "spec.instanceCount",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    (
                        "name",
                        "good-profile",
                    ),
                    ("value", {"spec.instanceCount": 1}),
                ],
                [
                    ("status", "success"),
                    (
                        "name",
                        "pod/aio-dataflow-good-profile-0",
                    ),
                    ("value", {"status.phase": "Running"}),
                ],
                [
                    ("status", "error"),
                    (
                        "name",
                        "bad-profile",
                    ),
                    ("value", {"spec.instanceCount": None}),
                ],
                [
                    ("status", "warning"),
                    ("name", "pod/aio-dataflow-bad-profile-"),
                ],
                [
                    ("status", "warning"),
                    (
                        "value",
                        {"[*].metadata.name=='profile'": "warning"},
                    ),
                ],
            ],
        ),
        # no profiles
        (
            # profiles
            [],
            # pods
            [],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "error"),
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
    pods,
    conditions,
    evaluations,
    detail_level,
):

    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources", side_effect=[{"items": profiles}]
    )
    mocker.patch(
        "azext_edge.edge.providers.check.dataflow.get_namespaced_pods_by_prefix",
        return_value=pods,
        side_effect=[pods, []],
    )
    result = evaluate_dataflow_profiles(detail_level=detail_level)

    assert result["name"] == "evalDataflowProfiles"
    assert result["targets"]["dataflowprofiles.connectivity.iotoperations.azure.com"]
    target = result["targets"]["dataflowprofiles.connectivity.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["dataflowprofiles.connectivity.iotoperations.azure.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
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
        # no pods
        (
            # pods
            [],
            # namespace conditions str
            [],
            # namespace evaluations str
            [],
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
    result = evaluate_core_service_runtime(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalCoreServiceRuntime"
    assert result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

    for namespace in target:
        assert namespace in result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
