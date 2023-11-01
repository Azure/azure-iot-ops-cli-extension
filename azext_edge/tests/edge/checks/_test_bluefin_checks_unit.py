# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.common import ProvisioningState
from azext_edge.edge.providers.check.bluefin import (
    evaluate_datasets,
    evaluate_instances,
    evaluate_pipelines,
)
from azext_edge.edge.providers.edge_api.dataprocessor import DataProcessorResourceKinds
from .conftest import assert_check_by_resource_types, assert_conditions, assert_evaluations
from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "instance, conditions, evaluations",
    [
        (
            # instance
            {
                "metadata": {"name": "test_instance"},
                "status": {"provisioningStatus": {"status": ProvisioningState.succeeded.value}},
            }
            ,
            # conditions str
            ["len(instances)==1", "provisioningState"],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/provisioningState", ProvisioningState.succeeded.value),
                ],
            ],
        ),
        (
            # instance
            {
                "metadata": {"name": "test_instance"},
                "status": {"provisioningStatus": {
                    "error": {"message": "test error"},
                    "status": ProvisioningState.failed.value}
                },
            }
            ,
            # conditions str
            ["len(instances)==1", "provisioningState"],
            # evaluations
            [
                [
                    ("status", "error"),
                    ("value/provisioningState", ProvisioningState.failed.value),
                ],
            ],
        ),
    ],
)
def test_instance_checks(
    mocker, mock_evaluate_bluefin_pod_health, instance, conditions, evaluations
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": [instance]}],
    )

    namespace = generate_generic_id()
    result = evaluate_instances(namespace=namespace)

    assert result["name"] == "evalInstances"
    assert result["namespace"] == namespace
    assert result["targets"]["instances.bluefin.az-bluefin.com"]
    target = result["targets"]["instances.bluefin.az-bluefin.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "pipelines, conditions, evaluations",
    [
        (
            # pipelines
            [
                {
                    "metadata": {
                        "name": "test-pipeline",
                    },
                    "spec": {
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
                    "status": {
                        "provisioningStatus": {
                            "status": "Succeeded",
                            "error": {
                                "message": "No error"
                            }
                        }
                    }
                }
            ],
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "len(spec.input.topics)>=1",
                "spec.input.partitionCount>=1",
                "destinationNodeCount==1"
            ],
            # evaluations
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
                    ("value/destinationNodeCount", 1),
                ]
            ],
        ),
        (
            # pipelines
            [
                {
                    "metadata": {
                        "name": "test-pipeline",
                    },
                    "spec": {
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
                    "status": {
                        "provisioningStatus": {
                            "status": "Failed",
                            "error": {
                                "message": "error message"
                            }
                        }
                    }
                }
            ],
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "len(spec.input.topics)>=1",
                "spec.input.partitionCount>=1",
                "destinationNodeCount==1"
            ],
            # evaluations
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
                {
                    "metadata": {
                        "name": "test-pipeline",
                    },
                    "spec": {
                        "enabled": False,
                    },
                    "status": {
                        "provisioningStatus": {
                            "status": "Failed",
                            "error": {
                                "message": "error message"
                            }
                        }
                    }
                }
            ],
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "len(spec.input.topics)>=1",
                "spec.input.partitionCount>=1",
                "destinationNodeCount==1"
            ],
            # evaluations
            [
                [
                    ("status", "skipped"),
                    ("value/mode.enabled", "not running"),
                ],
            ],
        ),
    ]
)
def test_pipeline_checks(
    mocker, mock_evaluate_bluefin_pod_health, pipelines, conditions, evaluations
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": pipelines}],
    )

    namespace = generate_generic_id()
    result = evaluate_pipelines(namespace=namespace)

    assert result["name"] == "evalPipelines"
    assert result["namespace"] == namespace
    assert result["targets"]["pipelines.bluefin.az-bluefin.com"]
    target = result["targets"]["pipelines.bluefin.az-bluefin.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "datasets, conditions, evaluations",
    [
        (
            # datasets
            [
                {
                    "metadata": {
                        "name": "test-dataset",
                    },
                    "status": {
                        "provisioningStatus": {
                            "status": "Succeeded",
                        }
                    },
                    "spec": {}
                }
            ],
            # conditions str
            ["provisioningState"],
            # evaluations
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
                {
                    "metadata": {
                        "name": "test-dataset",
                    },
                    "status": {
                        "provisioningStatus": {
                            "status": "Failed",
                            "error": {
                                "message": "error message"
                            }
                        }
                    },
                    "spec": {}
                }
            ],
            # conditions str
            ["provisioningState"],
            # evaluations
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
    mocker, mock_evaluate_bluefin_pod_health, datasets, conditions, evaluations
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": datasets}],
    )

    namespace = generate_generic_id()
    result = evaluate_datasets(namespace=namespace)

    assert result["name"] == "evalDatasets"
    assert result["namespace"] == namespace
    assert result["targets"]["datasets.bluefin.az-bluefin.com"]
    target = result["targets"]["datasets.bluefin.az-bluefin.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


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
@pytest.mark.parametrize('edge_service', ['bluefin'])
def test_check_bluefin_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        DataProcessorResourceKinds.DATASET.value: "azext_edge.edge.providers.check.bluefin.evaluate_datasets",
        DataProcessorResourceKinds.INSTANCE.value: "azext_edge.edge.providers.check.bluefin.evaluate_instances",
        DataProcessorResourceKinds.PIPELINE.value: "azext_edge.edge.providers.check.bluefin.evaluate_pipelines",
    }

    assert_check_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds, eval_lookup)
