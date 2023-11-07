# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


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
@pytest.mark.parametrize(
    "instance, namespace_conditions, all_conditions, namespace_evaluations, all_evaluations",
    [
        (
            # instance
            generate_resource_stub(
                metadata={"name": "test_instance"},
                status={"provisioningStatus": {"status": ProvisioningState.succeeded.value}}
            ),
            # instance namespace conditions str
            ["len(instances)==1", "provisioningStatus"],
            # instance all conditions str
            ["instances"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/provisioningStatus", ProvisioningState.succeeded.value),
                ],
            ],
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/instances", 1),
                ]
            ]
        ),
        (
            # instance
            {
                "metadata": {"name": "test_instance"},
                "status": {"provisioningStatus": {
                    "error": {"message": "test error"},
                    "status": ProvisioningState.failed.value}
                },
            },
            # namespace conditions str
            ["len(instances)==1", "provisioningStatus"],
            # all namespace conditions str
            ["instances"],
            # namespace evaluations str
            [
                [
                    ("status", "error"),
                    ("value/provisioningStatus", ProvisioningState.failed.value),
                ],
            ],
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/instances", 1),
                ]
            ]
        ),
    ],
)
def test_instance_checks(
    mocker,
    mock_evaluate_dataprocessor_pod_health,
    instance,
    namespace_conditions,
    all_conditions,
    namespace_evaluations,
    all_evaluations,
    detail_level
):
    namespace = generate_generic_id()
    instance['metadata']['namespace'] = namespace
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": [instance]}],
    )

    result = evaluate_instances(detail_level=detail_level)

    assert result["name"] == "evalInstances"
    assert result["targets"]["instances.dataprocessor.iotoperations.azure.com"]
    target = result["targets"]["instances.dataprocessor.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["instances.dataprocessor.iotoperations.azure.com"]
        if namespace == ALL_NAMESPACES_TARGET:
            assert_conditions(target[namespace], all_conditions)
            assert_evaluations(target[namespace], all_evaluations)
        else:
            assert_conditions(target[namespace], namespace_conditions)
            assert_evaluations(target[namespace], namespace_evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "pipelines, namespace_conditions, all_conditions, namespace_evaluations, all_evaluations",
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
            # all namespace conditions str
            ["pipelines"],
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
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/pipelines", 1),
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
            # all namespace conditions str
            ["pipelines"],
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
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/pipelines", 2),
                ]
            ]
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
            # all namespace conditions str
            ["pipelines"],
            # namespace evaluations str
            [
                [
                    ("status", "skipped"),
                    ("value/mode.enabled", "not running"),
                ],
            ],
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/pipelines", 1),
                ]
            ],
        ),
        (
            # pipelines
            [],
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
            # all namespace conditions str
            ["pipelines"],
            # namespace evaluations str
            [],
            # all namespace evaluation str
            [
                [
                    ("status", "skipped"),
                    ("value/pipelines", None),
                ]
            ],
        ),
    ]
)
def test_pipeline_checks(
    mocker,
    mock_evaluate_dataprocessor_pod_health,
    pipelines,
    namespace_conditions,
    all_conditions,
    namespace_evaluations,
    all_evaluations,
    detail_level
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": pipelines}],
    )

    namespace = generate_generic_id()
    for pipeline in pipelines:
        pipeline['metadata']['namespace'] = namespace
    result = evaluate_pipelines(detail_level=detail_level)

    assert result["name"] == "evalPipelines"
    assert result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"]
    target = result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["pipelines.dataprocessor.iotoperations.azure.com"]
        if namespace == ALL_NAMESPACES_TARGET:
            assert_conditions(target[namespace], all_conditions)
            assert_evaluations(target[namespace], all_evaluations)
        else:
            assert_conditions(target[namespace], namespace_conditions)
            assert_evaluations(target[namespace], namespace_evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "datasets, namespace_conditions, all_conditions, namespace_evaluations, all_evaluations",
    [
        (
            # datasets
            [
                generate_resource_stub(
                    metadata={"name": "test-dataset"},
                    status={"provisioningStatus": {"status": ProvisioningState.succeeded.value}}
                )
            ],
            # namespace conditions str
            ["provisioningState"],
            # all namespace conditions str
            ["datasets"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/provisioningState", ProvisioningState.succeeded.value),
                ],
            ],
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/datasets", 1),
                ]
            ]
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
            # namespace conditions str
            ["provisioningState"],
            # all namespace conditions str
            ["datasets"],
            # namespace evaluations str
            [
                [
                    ("status", "error"),
                    ("value/provisioningState", ProvisioningState.failed.value),
                ],
            ],
            # all namespace evaluation str
            [
                [
                    ("status", "success"),
                    ("value/datasets", 1),
                ]
            ]
        ),
    ]
)
def test_dataset_checks(
    mocker,
    mock_evaluate_dataprocessor_pod_health,
    datasets,
    namespace_conditions,
    all_conditions,
    namespace_evaluations,
    all_evaluations,
    detail_level
):
    namespace = generate_generic_id()
    for dataset in datasets:
        dataset['metadata']['namespace'] = namespace
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": datasets}],
    )

    result = evaluate_datasets(detail_level=detail_level)

    assert result["name"] == "evalDatasets"
    assert result["targets"]["datasets.dataprocessor.iotoperations.azure.com"]
    target = result["targets"]["datasets.dataprocessor.iotoperations.azure.com"]

    for namespace in target:
        assert namespace in result["targets"]["datasets.dataprocessor.iotoperations.azure.com"]
        if namespace == ALL_NAMESPACES_TARGET:
            assert_conditions(target[namespace], all_conditions)
            assert_evaluations(target[namespace], all_evaluations)
        else:
            assert_conditions(target[namespace], namespace_conditions)
            assert_evaluations(target[namespace], namespace_evaluations)
