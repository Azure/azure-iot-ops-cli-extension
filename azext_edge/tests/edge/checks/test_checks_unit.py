# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


import pytest
from typing import Dict, Any, List
from azext_edge.edge.common import (
    CheckTaskStatus,
    ProvisioningState,
    ResourceState,
)
from azext_edge.edge.providers.check.base import CheckManager
from azext_edge.edge.providers.check.e4k import (
    evaluate_broker_listeners,
    evaluate_brokers,
    evaluate_diagnostics_service,
    evaluate_mqtt_bridge_connectors,
    evaluate_datalake_connectors,
)
from azext_edge.edge.providers.check.bluefin import (
    evaluate_datasets,
    evaluate_instances,
    evaluate_pipelines,
)
from azext_edge.edge.providers.checks import run_checks
from azext_edge.edge.providers.edge_api.bluefin import BluefinResourceKinds
from azext_edge.edge.providers.edge_api.e4k import E4kResourceKinds

from ...generators import generate_generic_id


def test_check_manager():
    name = generate_generic_id()
    desc = f"{generate_generic_id()} {generate_generic_id()}"
    namespace = generate_generic_id()
    check_manager = CheckManager(check_name=name, check_desc=desc, namespace=namespace)
    assert_check_manager_dict(
        check_manager=check_manager, expected_name=name, expected_desc=desc
    )

    target_1 = generate_generic_id()
    target_1_condition_1 = generate_generic_id()
    target_1_conditions = [target_1_condition_1]
    target_1_eval_1_value = {generate_generic_id(): generate_generic_id()}
    target_1_display_1 = generate_generic_id()

    check_manager.add_target(target_name=target_1, conditions=target_1_conditions)
    check_manager.add_target_eval(
        target_name=target_1,
        status=CheckTaskStatus.success.value,
        value=target_1_eval_1_value,
    )
    check_manager.add_display(target_name=target_1, display=target_1_display_1)
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {
                    "status": CheckTaskStatus.success.value,
                    "value": target_1_eval_1_value,
                }
            ],
            "status": CheckTaskStatus.success.value,
        }
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_target_displays={target_1: [target_1_display_1]},
    )
    check_manager.add_target_eval(
        target_name=target_1, status=CheckTaskStatus.warning.value
    )
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {
                    "status": CheckTaskStatus.success.value,
                    "value": target_1_eval_1_value,
                },
                {"status": CheckTaskStatus.warning.value},
            ],
            "status": CheckTaskStatus.warning.value,
        }
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_status=CheckTaskStatus.warning.value,
    )

    target_2 = generate_generic_id()
    target_2_condition_1 = generate_generic_id()
    target_2_conditions = [target_2_condition_1]
    check_manager.add_target(target_name=target_2, conditions=target_2_conditions)
    check_manager.add_target_eval(
        target_name=target_2, status=CheckTaskStatus.error.value
    )

    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {
                    "status": CheckTaskStatus.success.value,
                    "value": target_1_eval_1_value,
                },
                {"status": CheckTaskStatus.warning.value},
            ],
            "status": CheckTaskStatus.warning.value,
        },
        target_2: {
            "conditions": target_2_conditions,
            "evaluations": [{"status": CheckTaskStatus.error.value}],
            "status": CheckTaskStatus.error.value,
        },
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_status=CheckTaskStatus.error.value,
    )

    # Re-create check manager with target 1 kpis and assert skipped status
    check_manager = CheckManager(check_name=name, check_desc=desc, namespace=namespace)
    check_manager.add_target(target_name=target_1, conditions=target_1_conditions)
    check_manager.add_target_eval(
        target_name=target_1, status=CheckTaskStatus.skipped.value, value=None
    )
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [{"status": CheckTaskStatus.skipped.value}],
            "status": CheckTaskStatus.skipped.value,
        }
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_status=CheckTaskStatus.skipped.value,
    )


def assert_check_manager_dict(
    check_manager: CheckManager,
    expected_name: str,
    expected_desc: str,
    expected_targets: dict = None,
    expected_status: str = CheckTaskStatus.success.value,
    expected_target_displays: dict = None,
):
    result_check_dict = check_manager.as_dict()
    if not expected_targets:
        expected_targets = {}

    assert "name" in result_check_dict
    assert result_check_dict["name"] == expected_name

    assert "description" in result_check_dict
    assert result_check_dict["description"] == expected_desc

    assert "targets" in result_check_dict
    assert result_check_dict["targets"] == expected_targets

    assert "status" in result_check_dict
    assert result_check_dict["status"] == expected_status

    if expected_target_displays:
        result_check_dict_displays = check_manager.as_dict(as_list=True)
        for target in expected_target_displays:
            assert (
                expected_target_displays[target]
                == result_check_dict_displays["targets"][target]["displays"]
            )


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [E4kResourceKinds.BROKER.value],
        [E4kResourceKinds.BROKER.value, E4kResourceKinds.BROKER_LISTENER.value],
        [E4kResourceKinds.DIAGNOSTIC_SERVICE.value],
        [
            E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
            E4kResourceKinds.DATALAKE_CONNECTOR.value,
        ],
        [
            E4kResourceKinds.BROKER.value,
            E4kResourceKinds.BROKER_LISTENER.value,
            E4kResourceKinds.DIAGNOSTIC_SERVICE.value,
            E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
            E4kResourceKinds.DATALAKE_CONNECTOR.value,
        ],
    ],
)
@pytest.mark.parametrize('edge_service', ['e4k'])
def test_check_e4k_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        E4kResourceKinds.BROKER.value: "azext_edge.edge.providers.check.e4k.evaluate_brokers",
        E4kResourceKinds.BROKER_LISTENER.value: "azext_edge.edge.providers.check.e4k.evaluate_broker_listeners",
        E4kResourceKinds.DIAGNOSTIC_SERVICE.value: "azext_edge.edge.providers.check.e4k.evaluate_diagnostics_service",
        E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value:
            "azext_edge.edge.providers.check.e4k.evaluate_mqtt_bridge_connectors",
        E4kResourceKinds.DATALAKE_CONNECTOR.value: "azext_edge.edge.providers.check.e4k.evaluate_datalake_connectors",
    }

    assert_check_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [BluefinResourceKinds.DATASET.value],
        [BluefinResourceKinds.INSTANCE.value],
        [BluefinResourceKinds.PIPELINE.value],
        [
            BluefinResourceKinds.DATASET.value,
            BluefinResourceKinds.INSTANCE.value,
        ],
        [
            BluefinResourceKinds.DATASET.value,
            BluefinResourceKinds.INSTANCE.value,
            BluefinResourceKinds.PIPELINE.value,
        ],
    ],
)
@pytest.mark.parametrize('edge_service', ['bluefin'])
def test_check_bluefin_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        BluefinResourceKinds.DATASET.value: "azext_edge.edge.providers.check.bluefin.evaluate_datasets",
        BluefinResourceKinds.INSTANCE.value: "azext_edge.edge.providers.check.bluefin.evaluate_instances",
        BluefinResourceKinds.PIPELINE.value: "azext_edge.edge.providers.check.bluefin.evaluate_pipelines",
    }

    assert_check_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


def _generate_resource_stub(
    metadata: Dict[str, Any] = {},
    spec: Dict[str, Any] = {},
    status: Dict[str, Any] = {},
):
    resource = {}

    # fill metadata
    resource["metadata"] = {"namespace": "mock_namespace", "name": "mock_name"}
    resource["spec"] = {}
    resource["status"] = {}

    for key in metadata:
        resource["metadata"][key] = metadata[key]
    for key in spec:
        resource["spec"][key] = spec[key]
    for key in status:
        resource["status"][key] = status[key]
    return resource


@pytest.mark.parametrize(
    "broker, conditions, evaluations",
    [
        (
            # broker (distributed)
            _generate_resource_stub(
                spec={
                    "diagnostics": {},  # required
                    "cardinality": {
                        "backendChain": {"partitions": 1, "replicas": 2, "workers": 1},
                        "frontend": {"replicas": 1},
                    },
                    "mode": "distributed",
                },
                status={"status": ResourceState.running.value, "statusDescription": ""},
            ),
            # conditions str
            [
                "len(brokers)==1",
                "status",
                "spec.mode",
                "spec.cardinality",
                "spec.cardinality.backendChain.partitions>=1",
                "spec.cardinality.backendChain.replicas>=1",
                "spec.cardinality.frontend.replicas>=1",
            ],
            # evaluations
            [
                [
                    ("status", "warning"),  # unable to fetch broker diagnostics
                ],
                [
                    ("status", "success"),
                    ("name", "mock_name"),
                    ("value/status/status", "Running"),
                    ("value/spec.cardinality/backendChain/partitions", 1),
                    ("value/spec.cardinality/backendChain/replicas", 2),
                    ("value/spec.cardinality/backendChain/workers", 1),
                    ("value/spec.cardinality/frontend/replicas", 1),
                ],
            ],
        ),
        (
            # broker 2 - not distributed, so less conditions on cardinality
            _generate_resource_stub(
                spec={
                    "diagnostics": {
                        "diagnosticServiceEndpoint": "test",
                        "enableMetrics": "test",
                        "enableSelfCheck": "test",
                        "enableTracing": "test",
                        "logLevel": "test",
                    },
                    "cardinality": {
                        "backendChain": {"partitions": 1, "replicas": 2, "workers": 1},
                        "frontend": {"replicas": 1},
                    },
                },
                status={
                    "status": ResourceState.starting.value,
                    "statusDescription": "",
                },
            ),
            # conditions
            [
                "len(brokers)==1",
                "status",
                "spec.mode",
            ],
            # evaluations
            [
                [
                    ("status", "warning"),  # still starting, so warning status
                    ("name", "mock_name"),
                    ("value/status/status", "Starting"),
                ],
            ],
        ),
    ],
)
def test_broker_checks(
    mocker, mock_evaluate_e4k_pod_health, broker, conditions, evaluations
):
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [broker]},
    )

    namespace = generate_generic_id()
    result = evaluate_brokers(namespace=namespace)

    # all evalBroker assertions
    assert result["name"] == "evalBrokers"
    assert result["namespace"] == namespace
    assert result["targets"]["brokers.az-edge.com"]
    target = result["targets"]["brokers.az-edge.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "listener, service, conditions, evaluations",
    [
        (
            # listener with valid broker ref
            _generate_resource_stub(
                spec={
                    "serviceName": "name",
                    "serviceType": "type",
                    "brokerRef": "mock_broker",
                    "port": 8080,
                    "authenticationEnabled": "True",
                },
                status={"status": ResourceState.running.value, "statusDescription": ""},
            ),
            # service obj
            _generate_resource_stub(
                status={"loadBalancer": {"ingress": [{"ip": "127.0.0.1"}]}},
                spec={"clusterIP": "127.0.0.1"},
            ),
            # conditions str
            [
                "len(brokerlisteners)>=1",
                "spec",
                "valid(spec.brokerRef)",
                "spec.serviceName",
                "status",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("name", "mock_name"),
                    ("value/spec/serviceName", "name"),
                    ("value/spec/serviceType", "type"),
                    ("value/spec/brokerRef", "mock_broker"),
                    ("value/spec/port", 8080),
                    ("value/spec/authenticationEnabled", "True"),
                    ("value/valid(spec.brokerRef)", True),
                ],
            ],
        ),
    ],
)
def test_broker_listener_checks(
    mocker, mock_evaluate_e4k_pod_health, listener, service, conditions, evaluations
):
    # mock listener values
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [listener]},
    )
    # broker ref
    mocker.patch(
        "azext_edge.edge.providers.check.e4k._get_valid_references",
        return_value={"mock_broker": True},
    )
    mocker.patch(
        "azext_edge.edge.providers.check.e4k.get_namespaced_service", return_value=service
    )

    namespace = generate_generic_id()
    result = evaluate_broker_listeners(namespace=namespace)

    assert result["name"] == "evalBrokerListeners"
    assert result["namespace"] == namespace
    assert result["targets"]["brokerlisteners.az-edge.com"]
    target = result["targets"]["brokerlisteners.az-edge.com"]

    # conditions
    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "resource, service, conditions, evaluations",
    [
        (
            # diagnostic resource
            _generate_resource_stub(
                spec={
                    "dataExportFrequencySeconds": 10,
                    "logFormat": "text",
                    "logLevel": "info",
                    "maxDataStorageSize": 16,
                    "metricsPort": 9600,
                    "staleDataTimeoutSeconds": 600,
                },
            ),
            # service obj
            _generate_resource_stub(
                spec={
                    "clusterIP": "127.0.0.1",
                    "ports": [{"name": "port", "protocol": "protocol"}],
                }
            ),
            # conditions str
            ["len(diagnosticservices)==1", "spec"],
            # evaluations
            [
                [
                    ("status", "success"),
                ],
                [
                    ("status", "success"),
                    ("value/spec/dataExportFrequencySeconds", 10),
                    ("value/spec/logFormat", "text"),
                    ("value/spec/logLevel", "info"),
                    ("value/spec/maxDataStorageSize", 16),
                    ("value/spec/metricsPort", 9600),
                    ("value/spec/staleDataTimeoutSeconds", 600),
                ],
            ],
        ),
    ],
)
def test_diagnostic_service_checks(
    mocker, mock_evaluate_e4k_pod_health, resource, service, conditions, evaluations
):
    # mock service values
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [resource]},
    )

    mocker.patch(
        "azext_edge.edge.providers.check.e4k.get_namespaced_service", return_value=service
    )

    namespace = generate_generic_id()
    result = evaluate_diagnostics_service(namespace=namespace)

    assert result["name"] == "evalBrokerDiag"
    assert result["namespace"] == namespace
    assert result["targets"]["diagnosticservices.az-edge.com"]
    target = result["targets"]["diagnosticservices.az-edge.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "bridge, topic_map, conditions, evaluations",
    [
        (
            # mqtt bridge
            _generate_resource_stub(
                metadata={"name": "test_bridge"},
                spec={
                    "localBrokerConnection": {
                        "authentication": {"x509": "localbrokerauth"}
                    },
                    "remoteBrokerConnection": {
                        "authentication": {"kubernetes": "remotebrokerauth"}
                    },
                    "tls": {"tlsEnabled": True},
                },
                status={
                    "configStatusLevel": ResourceState.running.value
                }
            ),
            # topic map
            _generate_resource_stub(spec={"mqttBridgeConnectorRef": "test_bridge"}),
            # conditions str
            ["status", "valid(spec)"],
            # evaluations
            [
                [("status", "success"), ("kind", "mqttbridgeconnector")],
                [
                    ("status", "success"),
                    (
                        "value/localBrokerConnection/authentication/x509",
                        "localbrokerauth",
                    ),
                    (
                        "value/remoteBrokerConnection/authentication/kubernetes",
                        "remotebrokerauth",
                    ),
                    ("value/tls/tlsEnabled", True),
                ],
            ],
        ),
    ],
)
def test_mqtt_checks(
    mocker, mock_evaluate_e4k_pod_health, bridge, topic_map, conditions, evaluations
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": [bridge]}, {"items": [topic_map]}],
    )

    namespace = generate_generic_id()
    result = evaluate_mqtt_bridge_connectors(namespace=namespace)

    assert result["name"] == "evalMQTTBridgeConnectors"
    assert result["namespace"] == namespace
    assert result["targets"]["mqttbridgeconnectors.az-edge.com"]
    target = result["targets"]["mqttbridgeconnectors.az-edge.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "connector, topic_map, conditions, evaluations",
    [
        (
            # datalake connector
            _generate_resource_stub(
                metadata={"name": "test_connector"},
                spec={
                    "instances": 2,
                    "target": {"datalakeStorage": {"endpoint": "test_endpoint"}},
                },
                status={
                    "configStatusLevel": ResourceState.running.value
                }
            ),
            # topic map
            _generate_resource_stub(spec={"dataLakeConnectorRef": "test_connector"}),
            # conditions str
            ["status", "valid(spec)", "len(spec.instances)>=1"],
            # evaluations
            [
                [("status", "success"), ("kind", "datalakeconnector")],
                [
                    ("status", "success"),
                    ("value/instances", 2),
                    ("value/target/datalakeStorage/endpoint", "test_endpoint"),
                ],
            ],
        ),
    ],
)
def test_datalake_checks(
    mocker, mock_evaluate_e4k_pod_health, connector, topic_map, conditions, evaluations
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": [connector]}, {"items": [topic_map]}],
    )

    namespace = generate_generic_id()
    result = evaluate_datalake_connectors(namespace=namespace)

    assert result["name"] == "evalDataLakeConnectors"
    assert result["namespace"] == namespace
    assert result["targets"]["datalakeconnectors.az-edge.com"]
    target = result["targets"]["datalakeconnectors.az-edge.com"]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


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


def assert_dict_props(path: str, expected: str, obj: Dict[str, str]):
    val = obj
    for key in path.split("/"):
        val = val[key]
    if isinstance(val, list) or isinstance(val, dict):
        assert expected in val
    else:
        assert val == expected


def assert_conditions(target: Dict[str, Any], conditions: List[str]):
    target_conditions = target["conditions"]
    for condition in conditions:
        assert condition in target_conditions


def assert_evaluations(target: Dict[str, Any], evaluations: List[List[tuple]]):
    result_evals = target["evaluations"]
    for idx, evals in enumerate(evaluations):
        for eval in evals:
            assert_dict_props(path=eval[0], expected=eval[1], obj=result_evals[idx])


def assert_check_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds, eval_lookup):
    # Mock the functions
    for key, value in eval_lookup.items():
        eval_lookup[key] = mocker.patch(value, return_value={})

    # run the checks
    run_checks(
        edge_service=edge_service,
        namespace="default",
        pre_deployment=False,
        post_deployment=True,
        as_list=False,
        resource_kinds=resource_kinds,
    )

    if not resource_kinds:
        # ensure all checks were run
        [eval_lookup[evaluator].assert_called_once() for evaluator in eval_lookup]
    else:
        # ensure each individual resource kind check was run once
        for resource_kind in resource_kinds:
            eval_lookup[resource_kind].assert_called_once()
            del eval_lookup[resource_kind]
        # ensure no other checks were run
        [eval_lookup[evaluator].assert_not_called() for evaluator in eval_lookup]
