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
from ...generators import generate_random_string
from azext_edge.edge.providers.check.common import (
    ALL_NAMESPACES_TARGET,
    ResourceOutputDetailLevel,
    DataSourceStageType,
)


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
    namespace = generate_random_string()
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
    "pipelines, conditions, evaluations",
    [
        (
            # pipelines
            [
                generate_resource_stub(
                    metadata={"name": "test-pipeline"},
                    spec={
                        "enabled": True,
                        "input": {
                            "type": DataSourceStageType.mqtt.value,
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
                                "type": "processor/enrich@v1",
                                "dataset": "vendorData",
                                "outputPath": ".payload.vendor",
                                "conditions": [
                                    {
                                        "type": "pastNearest",
                                        "inputPath": ".payload.ts"
                                    }
                                ],
                            },
                            "stage2": {
                                "displayName": "HTTP Output Example",
                                "description": "Sample HTTP output stage",
                                "type": "output/http@v1",
                                "url": "https://contoso.com/some/url/path",
                                "method": "POST",
                                "authentication": {
                                    "type": "usernamePassword",
                                    "username": "test-user",
                                    "password": "test-password"
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "spec.input.broker",
                "spec.input.topics",
                "format.type",
                "authentication.type",
                "destinationNodeCount==1"
            ],
            # evaluations str
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
                    ("value/spec.input.broker", "test-broker"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.topics", ["topic1", "topic2"]),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.partitionCount", 1)
                ],
                [
                    ("status", "success"),
                    ("value/input.format.type", "json"),
                ],
                [
                    ("status", "success"),
                    ("value/input.authentication.type", "usernamePassword"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage1.dataset", "vendorData"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage1.outputPath", ".payload.vendor"),
                ],
                [
                    ("status", "success"),
                    ("value/destinationNodeCount", 1),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage2.url", "https://contoso.com/some/url/path"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage2.method", "POST"),
                ],
                [
                    ("status", "success"),
                    ("value/stage2.authentication.type", "usernamePassword"),
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
                            "type": DataSourceStageType.sql.value,
                            "query": {
                                "expression": "SELECT * FROM table"
                            },
                            "server": "test-server",
                            "database": "test-database",
                            "interval": "1m",
                            "format": {
                                "type": "json"
                            },
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "id",
                                "expression": "0"
                            },
                            "authentication": {
                                "type": "servicePrincipal",
                                "clientId": "test-client-id",
                                "clientSecret": "test-client-secret",
                                "tenantId": "test-tenant-id"
                            }
                        },
                        "stages": {
                            "stage1": {
                                "displayName": "Filter Example",
                                "description": "Sample filter stage",
                                "type": "processor/filter@v1",
                                "expression": ".payload.temperature > 50 and .payload.humidity < 20",
                            },
                            "stage2": {
                                "displayName": "Sample blobstorage output",
                                "description": "An example blobstorage output stage",
                                "type": "output/blobstorage@v1",
                                "accountName": "myStorageAccount",
                                "containerName": "mycontainer",
                                "blobPath": "path",
                                "authentication": {
                                    "type": "systemAssignedManagedIdentity"
                                },
                                "format": {
                                    "type": "json"
                                },
                                "batch": {
                                    "time": "60s",
                                    "path": ".payload"
                                },
                                "retry": {
                                    "type": "fixed"
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "format.type",
                "authentication.type",
                "destinationNodeCount==1",
                "spec.input.query",
                "spec.input.server",
                "spec.input.database",
                "spec.input.interval"
            ],
            # evaluations str
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
                    ("value/spec.input.query", {"expression": "SELECT * FROM table"}),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.server", "test-server"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.database", "test-database"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.interval", "1m"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.partitionCount", 1)
                ],
                [
                    ("status", "success"),
                    ("value/input.format.type", "json"),
                ],
                [
                    ("status", "success"),
                    ("value/input.authentication.type", "servicePrincipal"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage1.expression", ".payload.temperature > 50 and .payload.humidity < 20"),
                ],
                [
                    ("status", "success"),
                    ("value/destinationNodeCount", 1),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage2.accountName", "myStorageAccount"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage2.containerName", "mycontainer"),
                ],
                [
                    ("status", "success"),
                    ("value/stage2.format.type", "json"),
                ],
                [
                    ("status", "success"),
                    ("value/stage2.authentication.type", "systemAssignedManagedIdentity"),
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
                            "type": DataSourceStageType.http.value,
                            "url": "https://contoso.com/some/url/path",
                            "method": "GET",
                            "format": {
                                "type": "json"
                            },
                            "request": {
                                "headers": [
                                    {
                                        "key": {
                                            "value": "foo",
                                            "type": "static"
                                        },
                                    },
                                    {
                                        "key": {
                                            "value": "baz",
                                            "type": "static"
                                        },
                                    }
                                ],
                            },
                            "authentication": {
                                "type": "header",
                                "key" : "Authorization",
                                "value": "token"
                            },
                            "interval": "10s",
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "id",
                                "expression": "0"
                            },
                        },
                        "stages": {
                            "stage1": {
                                "displayName": "gRPC Callout Example",
                                "description": "Sample gRPC callout stage",
                                "type": "processor/grpc@v1",
                                "serverAddress": "my-grpc-server.default.svc.cluster.local:80",
                                "rpcName": "mypackage.SampleService/ExampleMethod",
                                "descriptor": "Zm9v...",
                                "response": {
                                    "body": ".payload",
                                    "metadata": ".metadata",
                                    "status": ".status"
                                },
                                "authentication": {
                                    "type": "metadata",
                                    "key": "authorization",
                                    "value": "token"
                                }
                            },
                            "stage2": {
                                "displayName": "Sample Data Explorer output",
                                "type": "output/dataexplorer@v1",
                                "clusterUrl": "https://contoso.eastus.kusto.windows.net",
                                "database": "TestDatabase",
                                "table": "AssetData",
                                "authentication": {
                                    "type": "systemAssignedManagedIdentity"
                                },
                                "columns": [
                                    {
                                        "name": "assetId",
                                    },
                                    {
                                        "name": "timestamp",
                                    },
                                    {
                                        "name": "temperature",
                                    }
                                ]
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "format.type",
                "authentication.type",
                "destinationNodeCount==1",
                "spec.input.url",
                "spec.input.interval"
            ],
            # evaluations str
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
                    ("value/spec.input.url", "https://contoso.com/some/url/path"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.interval", "10s"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.partitionCount", 1),
                ],
                [
                    ("status", "success"),
                    ("value/input.format.type", "json"),
                ],
                [
                    ("status", "success"),
                    ("value/input.authentication.type", "header"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage1.serverAddress", "my-grpc-server.default.svc.cluster.local:80"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage1.rpcName", "mypackage.SampleService/ExampleMethod"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.stage1.descriptor", "Zm9v..."),
                ],
                [
                    ("status", "success"),
                    ("value/stage1.authentication.type", "metadata"),
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
                            "type": DataSourceStageType.influxdb.value,
                            "query": {
                                "expression": "from(bucket:\"test-bucket\")"
                            },
                            "interval": "5s",
                            "url": "https://contoso.com/some/url/path",
                            "organization": "test-org",
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "id",
                                "expression": "0"
                            },
                            "format": {
                                "type": "json"
                            },
                            "authentication": {
                                "type": "accessToken",
                                "accessToken": "AKV_ACCESS_TOKEN"
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "format.type",
                "authentication.type",
                "destinationNodeCount==1",
                "spec.input.query",
                "spec.input.url",
                "spec.input.interval",
                "spec.input.organization"
            ],
            # evaluations str
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
                    ("value/spec.input.query", {"expression": "from(bucket:\"test-bucket\")"}),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.url", "https://contoso.com/some/url/path"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.interval", "5s"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.organization", "test-org"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.partitionCount", 1)
                ],
                [
                    ("status", "success"),
                    ("value/input.format.type", "json"),
                ],
                [
                    ("status", "success"),
                    ("value/input.authentication.type", "accessToken"),
                ],
                [
                    ("status", "success"),
                    ("value/destinationNodeCount", 1),
                ]
            ],
        ),
        # authentication error
        (
            # pipelines
            [
                generate_resource_stub(
                    metadata={"name": "test-pipeline"},
                    spec={
                        "enabled": True,
                        "input": {
                            "type": DataSourceStageType.influxdb.value,
                            "query": {
                                "expression": "from(bucket:\"test-bucket\")"
                            },
                            "interval": "5s",
                            "url": "https://contoso.com/some/url/path",
                            "organization": "test-org",
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "id",
                                "expression": "0"
                            },
                            "format": {
                                "type": "json"
                            },
                            "authentication": {
                                "type": "accessToken",
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "format.type",
                "authentication.type",
                "destinationNodeCount==1",
                "spec.input.query",
                "spec.input.url",
                "spec.input.interval",
                "spec.input.organization"
            ],
            # evaluations str
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
                    ("value/spec.input.query", {"expression": "from(bucket:\"test-bucket\")"}),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.url", "https://contoso.com/some/url/path"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.interval", "5s"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.organization", "test-org"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.input.partitionCount", 1)
                ],
                [
                    ("status", "success"),
                    ("value/input.format.type", "json"),
                ],
                [
                    ("status", "error"),
                    ("value/input.authentication.type", "accessToken"),
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
                            "type": DataSourceStageType.sql.value,
                            "query": {
                                "expression": "SELECT * FROM table"
                            },
                            "server": "test-server",
                            "database": "test-database",
                            "interval": "1m",
                            "format": {
                                "type": "json"
                            },
                            "partitionCount": 1,
                            "partitionStrategy": {
                                "type": "id",
                                "expression": "0"
                            },
                            "authentication": {
                                "type": "servicePrincipal",
                                "clientId": "test-client-id",
                                "clientSecret": "test-client-secret",
                                "tenantId": "test-tenant-id"
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
                            "type": DataSourceStageType.mqtt.value,
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "format.type",
                "authentication.type",
                "destinationNodeCount==1"
            ],
            # evaluations str
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
            # conditions str
            [
                "len(pipelines)>=1",
                "mode.enabled",
                "provisioningStatus",
                "sourceNodeCount == 1",
                "destinationNodeCount==1"
            ],
            # evaluations str
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
            # conditions str
            [],
            # evaluations str
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
    conditions,
    evaluations,
    detail_level,
    resource_name
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.dataprocessor.get_resources_by_name",
        side_effect=[pipelines],
    )

    namespace = generate_random_string()
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

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


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
    namespace = generate_random_string()
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
