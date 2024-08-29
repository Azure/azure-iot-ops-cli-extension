# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.common import (
    ResourceState,
)
from azext_edge.edge.providers.check.mq import (
    evaluate_broker_listeners,
    evaluate_brokers,
)
from azext_edge.edge.providers.edge_api.mq import MqResourceKinds
from azext_edge.edge.providers.check.common import (
    ResourceOutputDetailLevel,
)

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_resource_stub,
)
from ...generators import generate_random_string


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [MqResourceKinds.BROKER.value],
        [MqResourceKinds.BROKER.value, MqResourceKinds.BROKER_LISTENER.value],
    ],
)
@pytest.mark.parametrize("ops_service", ["broker"])
def test_check_mq_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        MqResourceKinds.BROKER.value: "azext_edge.edge.providers.check.mq.evaluate_brokers",
        MqResourceKinds.BROKER_LISTENER.value: "azext_edge.edge.providers.check.mq.evaluate_broker_listeners",
    }

    assert_check_by_resource_types(ops_service, mocker, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "mock*", "mock-name"])
@pytest.mark.parametrize(
    "broker, service, conditions, evaluations",
    [
        (
            # broker (distributed)
            generate_resource_stub(
                spec={
                    "diagnostics": {},  # required
                    "cardinality": {
                        "backendChain": {
                            "partitions": 1,
                            "redundancyFactor": 2,
                            "workers": 1,
                        },
                        "frontend": {"replicas": 1},
                    },
                    "mode": "distributed",
                },
                status={"runtimeStatus": {"status": ResourceState.running.value, "statusDescription": ""}},
            ),
            # service obj
            generate_resource_stub(
                metadata={"name": "mock-name"},
                spec={
                    "clusterIP": "10.0.222.134",
                    "ports": [
                        {"name": "bincode-listener-service", "port": 9700, "protocol": "TCP", "targetPort": 9700},
                        {"name": "protobuf-listener-service", "port": 9800, "protocol": "TCP", "targetPort": 9800},
                        {"name": "aio-mq-metrics-service", "port": 9600, "protocol": "TCP", "targetPort": 9600},
                    ],
                },
            ),
            # conditions str
            [
                "len(brokers)==1",
                "runtimeStatus",
                "spec.mode",
                "spec.diagnostics",
                "spec.cardinality",
                "spec.cardinality.backendChain.partitions>=1",
                "spec.cardinality.backendChain.redundancyFactor>=1",
                "spec.cardinality.frontend.replicas>=1",
            ],
            # evaluations
            [
                [
                    ("status", "warning"),
                    ("name", "mock-name"),
                    ("value/runtimeStatus/status", "Running"),
                    ("value/spec.diagnostics", {}),
                    ("value/spec.cardinality/backendChain/partitions", 1),
                    ("value/spec.cardinality/backendChain/redundancyFactor", 2),
                    ("value/spec.cardinality/backendChain/workers", 1),
                    ("value/spec.cardinality/frontend/replicas", 1),
                ],
            ],
        ),
        (
            # broker 2 - not distributed, so less conditions on cardinality
            generate_resource_stub(
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
                    "runtimeStatus": {"status": ResourceState.starting.value, "statusDescription": ""},
                },
            ),
            # service obj
            generate_resource_stub(
                metadata={"name": "mock-name"},
                spec={
                    "clusterIP": "10.0.222.134",
                    "ports": [
                        {"name": "bincode-listener-service", "port": 9700, "protocol": "TCP", "targetPort": 9700},
                        {"name": "protobuf-listener-service", "port": 9800, "protocol": "TCP", "targetPort": 9800},
                        {"name": "aio-mq-metrics-service", "port": 9600, "protocol": "TCP", "targetPort": 9600},
                    ],
                },
            ),
            # conditions
            [
                "len(brokers)==1",
                "runtimeStatus",
                "spec.mode",
            ],
            # evaluations
            [
                [
                    ("status", "error"),  # error: no backendChain.redundancyFactor
                    ("name", "mock-name"),
                    ("value/runtimeStatus/status", "Starting"),
                    ("value/spec.cardinality/backendChain/partitions", 1),
                    ("value/spec.cardinality/backendChain/replicas", 2),
                    ("value/spec.cardinality/backendChain/workers", 1),
                    ("value/spec.cardinality/frontend/replicas", 1),
                ],
            ],
        ),
        (
            # broker 3 - (distributed) success
            generate_resource_stub(
                spec={
                    "diagnostics": {
                        "logs": {
                            "exportIntervalSeconds": 30,
                            "exportLevel": "info",
                            "level": "info",
                            "openTelemetryCollectorAddress": None,
                        }
                    },
                    "cardinality": {
                        "backendChain": {
                            "partitions": 1,
                            "redundancyFactor": 2,
                            "workers": 1,
                        },
                        "frontend": {"replicas": 1},
                    },
                    "mode": "distributed",
                },
                status={"runtimeStatus": {"status": ResourceState.running.value, "statusDescription": ""}},
            ),
            # service obj
            generate_resource_stub(
                metadata={"name": "mock-name"},
                spec={
                    "clusterIP": "10.0.222.134",
                    "ports": [
                        {"name": "bincode-listener-service", "port": 9700, "protocol": "TCP", "targetPort": 9700},
                        {"name": "protobuf-listener-service", "port": 9800, "protocol": "TCP", "targetPort": 9800},
                        {"name": "aio-mq-metrics-service", "port": 9600, "protocol": "TCP", "targetPort": 9600},
                    ],
                },
            ),
            # conditions str
            [
                "len(brokers)==1",
                "runtimeStatus",
                "spec.mode",
                "spec.diagnostics",
                "spec.cardinality",
                "spec.cardinality.backendChain.partitions>=1",
                "spec.cardinality.backendChain.redundancyFactor>=1",
                "spec.cardinality.frontend.replicas>=1",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("name", "mock-name"),
                    ("value/runtimeStatus/status", "Running"),
                    ("value/spec.cardinality/backendChain/partitions", 1),
                    ("value/spec.cardinality/backendChain/redundancyFactor", 2),
                    ("value/spec.cardinality/backendChain/workers", 1),
                    ("value/spec.cardinality/frontend/replicas", 1),
                    ("value/spec.diagnostics/logs/exportIntervalSeconds", 30),
                    ("value/spec.diagnostics/logs/exportLevel", "info"),
                    ("value/spec.diagnostics/logs/level", "info"),
                    ("value/spec.diagnostics/logs/openTelemetryCollectorAddress", None),
                ],
            ],
        ),
    ],
)
def test_broker_checks(
    mocker, mock_evaluate_mq_pod_health, broker, service, conditions, evaluations, detail_level, resource_name
):
    namespace = generate_random_string()
    broker["metadata"]["namespace"] = namespace
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [broker]},
    )
    mocker.patch(
        "azext_edge.edge.providers.check.mq.get_namespaced_service",
        return_value=service,
    )
    result = evaluate_brokers(detail_level=detail_level, resource_name=resource_name)

    # all evalBroker assertions
    assert result["name"] == "evalBrokers"
    assert namespace in result["targets"]["brokers.mqttbroker.iotoperations.azure.com"]
    target = result["targets"]["brokers.mqttbroker.iotoperations.azure.com"][namespace]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "mock*", "mock-name"])
@pytest.mark.parametrize(
    "listener, service, conditions, evaluations",
    [
        (
            # listener
            generate_resource_stub(
                spec={
                    "serviceName": "name",
                    "serviceType": "loadbalancer",
                    "port": 8080,
                    "authenticationEnabled": "True",
                },
                status={"status": ResourceState.running.value, "statusDescription": ""},
            ),
            # service obj
            generate_resource_stub(
                status={"loadBalancer": {"ingress": [{"ip": "127.0.0.1"}]}},
                spec={"clusterIP": "127.0.0.1"},
            ),
            # conditions str
            [
                "len(brokerlisteners)>=1",
                "spec",
                "spec.serviceName",
                "status",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("name", "mock-name"),
                    ("value/spec/serviceName", "name"),
                    ("value/spec/serviceType", "loadbalancer"),
                    ("value/spec/port", 8080),
                    ("value/spec/authenticationEnabled", "True"),
                ],
            ],
        ),
        (
            # listener
            generate_resource_stub(
                spec={
                    "serviceName": "name",
                    "serviceType": "clusterip",
                    "port": 8080,
                    "authenticationEnabled": "True",
                },
                status={"status": ResourceState.running.value, "statusDescription": ""},
            ),
            # service obj
            generate_resource_stub(
                status={"loadBalancer": {"ingress": [{"ip": "127.0.0.1"}]}},
                spec={"clusterIP": "127.0.0.1"},
            ),
            # conditions str
            [
                "len(brokerlisteners)>=1",
                "spec",
                "spec.serviceName",
                "status",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("name", "mock-name"),
                    ("value/spec/serviceName", "name"),
                    ("value/spec/serviceType", "clusterip"),
                    ("value/spec/port", 8080),
                    ("value/spec/authenticationEnabled", "True"),
                ],
            ],
        ),
    ],
)
def test_broker_listener_checks(
    mocker,
    mock_evaluate_mq_pod_health,
    listener,
    service,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    # mock listener values
    namespace = generate_random_string()
    listener["metadata"]["namespace"] = namespace
    service["metadata"]["namespace"] = namespace
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [listener]},
    )
    mocker.patch(
        "azext_edge.edge.providers.check.mq.get_namespaced_service",
        return_value=service,
    )

    result = evaluate_broker_listeners(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalBrokerListeners"
    assert namespace in result["targets"]["brokerlisteners.mqttbroker.iotoperations.azure.com"]
    target = result["targets"]["brokerlisteners.mqttbroker.iotoperations.azure.com"][namespace]

    # conditions
    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)
