# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.common import ProvisioningState
from azext_edge.edge.providers.check.dataprocessor import (
    evaluate_datasets,
    evaluate_instances,
    evaluate_pipelines,
)
from azext_edge.edge.providers.edge_api.dataprocessor import DataProcessorResourceKinds
from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_resource_stub,
)
from ...generators import generate_generic_id
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET, ResourceOutputDetailLevel


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [DataProcessorResourceKinds.DATASET.value],
        [DataProcessorResourceKinds.INSTANCE.value],
        [DataProcessorResourceKinds.PIPELINE.value],
        [
            DataProcessorResourceKinds.DATASET.value,
            DataProcessorResourceKinds.INSTANCE.value,
        ],
        [
            DataProcessorResourceKinds.DATASET.value,
            DataProcessorResourceKinds.INSTANCE.value,
            DataProcessorResourceKinds.PIPELINE.value,
        ],
    ],
)
@pytest.mark.parametrize('ops_service', ['dataprocessor'])
def test_check_dataprocessor_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        DataProcessorResourceKinds.DATASET.value: "azext_edge.edge.providers.check.dataprocessor.evaluate_datasets",
        DataProcessorResourceKinds.INSTANCE.value: "azext_edge.edge.providers.check.dataprocessor.evaluate_instances",
        DataProcessorResourceKinds.PIPELINE.value: "azext_edge.edge.providers.check.dataprocessor.evaluate_pipelines",
    }

    assert_check_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", ["test_instance", "test_instance2"])
@pytest.mark.parametrize(
    "instances, namespace_conditions, namespace_evaluations",
    [
        (
            # instances
            [
                generate_resource_stub(
                    metadata={"name": "test_instance"},
                    status={"provisioningStatus": {"status": ProvisioningState.succeeded.value}}
                ),
            ],
            # instance namespace conditions str
            ["len(instances)==1", "provisioningStatus"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/provisioningStatus", ProvisioningState.succeeded.value),
                ],
            ],
        ),
        (
            # instances
            [
                {
                    "metadata": {"name": "test_instance"},
                    "status": {"provisioningStatus": {
                        "error": {"message": "test error"},
                        "status": ProvisioningState.failed.value}
                    },
                },
            ],
            # namespace conditions str
            ["len(instances)==1", "provisioningStatus"],
            # namespace evaluations str
            [
                [
                    ("status", "error"),
                    ("value/provisioningStatus", ProvisioningState.failed.value),
                ],
            ],
        ),
    ],
)
def test_instance_checks(
    mocker,
    mock_evaluate_dataprocessor_pod_health,
    instances,
    namespace_conditions,
    namespace_evaluations,
    detail_level,
    resource_name
):
    namespace = generate_generic_id()
    for instance in instances:
        instance['metadata']['namespace'] = namespace
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.dataprocessor.get_resources_by_name",
        side_effect=[instances],
    )

    result = evaluate_instances(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalInstances"
    assert namespace in result["targets"]["instances.dataprocessor.iotoperations.azure.com"]
    target = result["targets"]["instances.dataprocessor.iotoperations.azure.com"][namespace]

    assert_conditions(target, namespace_conditions)
    assert_evaluations(target, namespace_evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", ["test_instance", "test_instance2"])
@pytest.mark.parametrize(
    "pipelines, namespace_conditions, namespace_evaluations",
    [
        (
            # pipelines
            [
                generate_resource_stub(
                    metadata={"name": "test-pipeline"},
                    spec={
                        "enabled": True,
                        "input": {
                            "broker": "test-broker",
                            "topics": ["topic1", "topic2"],
                            "format": {
                                "type": "json"
                            },
                            "qos": 1,
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "roundRobin"
                            },
                            "authentication": {
                                "type": "usernamePassword",
                                "username": "test-user",
                                "password": "test-password"
                            }
                        },
                        "stages": {
                            "stage1": {
                                "type": "intermediate",
                                "properties": {
                                    "property1": "value1",
                                    "property2": "value2"
                                }
                            },
                            "stage2": {
                                "type": "output",
                                "properties": {
                                    "property1": "value1",
                                    "property2": "value2"
                                }
                            }
                        }
                    },
                    status={
                        "provisioningStatus": {
                            "status": "Succeeded",
                            "error": {
                                "message": "No error"
                            }
                        }
                    }
                )
            ],
            # namespace conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "len(spec.input.topics)>=1",
                "spec.input.partitionCount>=1",
                "destinationNodeCount==1"
            ],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/mode.enabled", "running"),
                ],
                [
                    ("status", "success"),
                    ("value/provisioningStatus", ProvisioningState.succeeded.value),
                ],
                [
                    ("status", "success"),
                    ("value/sourceNodeCount", 1),
                ],
                [
                    ("status", "success"),
                    ("value/len(spec.input.topics)", 2),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.partitionCount", 1),
                ],
                [
                    ("status", "success"),
                    ("value/destinationNodeCount", 1),
                ]
            ],
        ),
        (
            # pipelines
            [
                generate_resource_stub(
                    metadata={"name": "test-pipeline"},
                    spec={
                        "enabled": True,
                        "input": {
                            "broker": "test-broker",
                            "topics": ["topic1", "topic2"],
                            "format": {
                                "type": "json"
                            },
                            "qos": 1,
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "roundRobin"
                            },
                            "authentication": {
                                "type": "usernamePassword",
                                "username": "test-user",
                                "password": "test-password"
                            }
                        },
                        "stages": {
                            "stage1": {
                                "type": "intermediate",
                                "properties": {
                                    "property1": "value1",
                                    "property2": "value2"
                                }
                            },
                            "stage2": {
                                "type": "output",
                                "properties": {
                                    "property1": "value1",
                                    "property2": "value2"
                                }
                            }
                        }
                    },
                    status={
                        "provisioningStatus": {
                            "status": "Failed",
                            "error": {
                                "message": "error message"
                            }
                        }
                    }
                ),
                generate_resource_stub(
                    metadata={"name": "test-pipeline2"},
                    spec={
                        "enabled": True,
                        "input": {
                            "broker": "test-broker",
                            "topics": ["topic1", "topic2"],
                            "format": {
                                "type": "json"
                            },
                            "qos": 1,
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "roundRobin"
                            },
                            "authentication": {
                                "type": "usernamePassword",
                                "username": "test-user",
                                "password": "test-password"
                            }
                        },
                        "stages": {
                            "stage1": {
                                "type": "intermediate",
                                "properties": {
                                    "property1": "value1",
                                    "property2": "value2"
                                }
                            },
                            "stage2": {
                                "type": "output",
                                "properties": {
                                    "property1": "value1",
                                    "property2": "value2"
                                }
                            }
                        }
                    },
                    status={
                        "provisioningStatus": {
                            "status": "Failed",
                            "error": {
                                "message": "error message"
                            }
                        }
                    }
                )
            ],
            # namespace conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "len(spec.input.topics)>=1",
                "spec.input.partitionCount>=1",
                "destinationNodeCount==1"
            ],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/mode.enabled", "running"),
                ],
                [
                    ("status", "error"),
                    ("value/provisioningStatus", ProvisioningState.failed.value),
                ],
            ],
        ),
        (
            # pipelines
            [
                generate_resource_stub(
                    metadata={"name": "test-pipeline"},
                    spec={
                        "enabled": False,
                    },
                    status={
                        "provisioningStatus": {
                            "status": "Failed",
                            "error": {
                                "message": "error message"
                            }
                        }
                    }
                )
            ],
            # namespace conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "len(spec.input.topics)>=1",
                "spec.input.partitionCount>=1",
                "destinationNodeCount==1"
            ],
            # namespace evaluations str
            [
                [
                    ("status", "skipped"),
                    ("value/mode.enabled", "not running"),
                ],
            ],
        ),
        (
            # pipelines
            [],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "skipped"),
                    ("value", "Unable to fetch pipelines in any namespaces."),
                ],
            ],
        ),
    ]
)
def test_pipeline_checks(
    mocker,
    mock_evaluate_dataprocessor_pod_health,
    pipelines,
    namespace_conditions,
    namespace_evaluations,
    detail_level,
    resource_name
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.dataprocessor.get_resources_by_name",
        side_effect=[pipelines],
    )

    namespace = generate_generic_id()
    for pipeline in pipelines:
        pipeline['metadata']['namespace'] = namespace
    result = evaluate_pipelines(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalPipelines"
    assert result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"]

    if pipelines:
        assert namespace in result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"]
    else:
        namespace = ALL_NAMESPACES_TARGET
        assert namespace in result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"]
    target = result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"][namespace]

    assert_conditions(target, namespace_conditions)
    assert_evaluations(target, namespace_evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "datasets, resource_name, namespace_conditions, namespace_evaluations",
    [
        (
            # datasets
            [
                generate_resource_stub(
                    metadata={"name": "test-dataset"},
                    status={"provisioningStatus": {"status": ProvisioningState.succeeded.value}}
                )
            ],
            # resource_name
            "test-dataset",
            # namespace conditions str
            ["provisioningState"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/provisioningState", ProvisioningState.succeeded.value),
                ],
            ],
        ),
        (
            # datasets
            [
                generate_resource_stub(
                    metadata={"name": "test-dataset"},
                    status={"provisioningStatus": {"status": ProvisioningState.succeeded.value}}
                )
            ],
            # resource_name
            "test-dataset-?*",
            # namespace conditions str
            ["provisioningState"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/provisioningState", ProvisioningState.succeeded.value),
                ],
            ],
        ),
        (
            # datasets
            [
                generate_resource_stub(
                    metadata={"name": "test-dataset"},
                    status={
                        "provisioningStatus": {
                            "status": ProvisioningState.failed.value,
                            "error": {
                                "message": "error message"
                            }
                        }
                    }
                )
            ],
            # resource_name
            "test-dat*",
            # namespace conditions str
            ["provisioningState"],
            # namespace evaluations str
            [
                [
                    ("status", "error"),
                    ("value/provisioningState", ProvisioningState.failed.value),
                ],
            ],
        ),
    ]
)
def test_dataset_checks(
    mocker,
    mock_evaluate_dataprocessor_pod_health,
    datasets,
    namespace_conditions,
    namespace_evaluations,
    detail_level,
    resource_name
):
    namespace = generate_generic_id()
    for dataset in datasets:
        dataset['metadata']['namespace'] = namespace
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.dataprocessor.get_resources_by_name",
        side_effect=[datasets],
    )

    result = evaluate_datasets(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalDatasets"
    assert result["targets"]["datasets.dataprocessor.iotoperations.azure.com"]
    assert namespace in result["targets"]["datasets.dataprocessor.iotoperations.azure.com"]
    target = result["targets"]["datasets.dataprocessor.iotoperations.azure.com"][namespace]

    assert_conditions(target, namespace_conditions)
    assert_evaluations(target, namespace_evaluations)
