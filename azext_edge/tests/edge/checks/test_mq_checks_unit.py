# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from azext_edge.edge.providers.check.cloud_connectors import filter_connector_and_topic_map_resources
import pytest
from functools import partial
from azext_edge.edge.common import (
    CheckTaskStatus,
    ResourceState,
)
from azext_edge.edge.providers.check.mq import (
    evaluate_broker_listeners,
    evaluate_brokers,
    evaluate_diagnostics_service,
    evaluate_mqtt_bridge_connectors,
    evaluate_datalake_connectors,
    evaluate_kafka_connectors,
)
from azext_edge.edge.providers.edge_api.mq import MqResourceKinds
from azext_edge.edge.providers.check.common import (
    ALL_NAMESPACES_TARGET,
    KafkaTopicMapRouteType,
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
        [MqResourceKinds.DIAGNOSTIC_SERVICE.value],
        [
            MqResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
            MqResourceKinds.DATALAKE_CONNECTOR.value,
        ],
        [
            MqResourceKinds.BROKER.value,
            MqResourceKinds.BROKER_LISTENER.value,
            MqResourceKinds.DIAGNOSTIC_SERVICE.value,
            MqResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
            MqResourceKinds.DATALAKE_CONNECTOR.value,
        ],
    ],
)
@pytest.mark.parametrize("ops_service", ["mqttbroker"])
def test_check_mq_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        MqResourceKinds.BROKER.value: "azext_edge.edge.providers.check.mq.evaluate_brokers",
        MqResourceKinds.BROKER_LISTENER.value: "azext_edge.edge.providers.check.mq.evaluate_broker_listeners",
        MqResourceKinds.DIAGNOSTIC_SERVICE.value: "azext_edge.edge.providers.check.mq.evaluate_diagnostics_service",
        MqResourceKinds.MQTT_BRIDGE_CONNECTOR.value:
            "azext_edge.edge.providers.check.mq.evaluate_mqtt_bridge_connectors",
        MqResourceKinds.DATALAKE_CONNECTOR.value: "azext_edge.edge.providers.check.mq.evaluate_datalake_connectors",
    }

    assert_check_by_resource_types(ops_service, mocker, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "mock*", "mock-name"])
@pytest.mark.parametrize(
    "broker, conditions, evaluations",
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
                status={"status": ResourceState.running.value, "statusDescription": ""},
            ),
            # conditions str
            [
                "len(brokers)==1",
                "status",
                "spec.mode",
                "spec.cardinality",
                "spec.cardinality.backendChain.partitions>=1",
                "spec.cardinality.backendChain.redundancyFactor>=1",
                "spec.cardinality.frontend.replicas>=1",
            ],
            # evaluations
            [
                [
                    ("status", "warning"),  # unable to fetch broker diagnostics
                ],
                [
                    ("status", "success"),
                    ("name", "mock-name"),
                    ("value/status/status", "Running"),
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
                    ("name", "mock-name"),
                    ("value/status/status", "Starting"),
                ],
            ],
        ),
    ],
)
def test_broker_checks(
    mocker,
    mock_evaluate_mq_pod_health,
    broker,
    conditions,
    evaluations,
    detail_level,
    resource_name
):
    namespace = generate_random_string()
    broker["metadata"]["namespace"] = namespace
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [broker]},
    )
    result = evaluate_brokers(detail_level=detail_level, resource_name=resource_name)

    # all evalBroker assertions
    assert result["name"] == "evalBrokers"
    assert namespace in result["targets"]["brokers.mq.iotoperations.azure.com"]
    target = result["targets"]["brokers.mq.iotoperations.azure.com"][namespace]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "mock*", "mock-name"])
@pytest.mark.parametrize(
    "listener, service, conditions, evaluations",
    [
        (
            # listener with valid broker ref
            generate_resource_stub(
                spec={
                    "serviceName": "name",
                    "serviceType": "loadbalancer",
                    "brokerRef": "mock-broker",
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
                "valid(spec.brokerRef)",
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
                    ("value/spec/brokerRef", "mock-broker"),
                    ("value/spec/port", 8080),
                    ("value/spec/authenticationEnabled", "True"),
                    ("value/valid(spec.brokerRef)", True),
                ],
            ],
        ),
        (
            # listener with valid broker ref
            generate_resource_stub(
                spec={
                    "serviceName": "name",
                    "serviceType": "clusterip",
                    "brokerRef": "mock-broker",
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
                "valid(spec.brokerRef)",
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
                    ("value/spec/brokerRef", "mock-broker"),
                    ("value/spec/port", 8080),
                    ("value/spec/authenticationEnabled", "True"),
                    ("value/valid(spec.brokerRef)", True),
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
    # broker ref
    mocker.patch(
        "azext_edge.edge.providers.check.mq._get_valid_references",
        return_value={"mock-broker": True},
    )
    mocker.patch(
        "azext_edge.edge.providers.check.mq.get_namespaced_service",
        return_value=service,
    )

    result = evaluate_broker_listeners(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalBrokerListeners"
    assert namespace in result["targets"]["brokerlisteners.mq.iotoperations.azure.com"]
    target = result["targets"]["brokerlisteners.mq.iotoperations.azure.com"][namespace]

    # conditions
    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "mock*", "mock-name"])
@pytest.mark.parametrize(
    "resource, service, conditions, evaluations",
    [
        (
            # diagnostic resource
            generate_resource_stub(
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
            generate_resource_stub(
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
    mocker,
    mock_evaluate_mq_pod_health,
    resource,
    service,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    # mock service values
    namespace = generate_random_string()
    resource["metadata"]["namespace"] = namespace
    service["metadata"]["namespace"] = namespace
    mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": [resource]},
    )

    mocker.patch(
        "azext_edge.edge.providers.check.mq.get_namespaced_service",
        return_value=service,
    )

    result = evaluate_diagnostics_service(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalBrokerDiag"
    assert namespace in result["targets"]["diagnosticservices.mq.iotoperations.azure.com"]
    target = result["targets"]["diagnosticservices.mq.iotoperations.azure.com"][namespace]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None])
@pytest.mark.parametrize(
    "bridge, topic_map, conditions, evaluations",
    [
        (
            # mqtt bridge
            generate_resource_stub(
                metadata={"name": "test_bridge"},
                spec={
                    "localBrokerConnection": {"authentication": {"x509": "localbrokerauth"}},
                    "remoteBrokerConnection": {"authentication": {"kubernetes": "remotebrokerauth"}},
                    "tls": {"tlsEnabled": True},
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic map
            generate_resource_stub(spec={"mqttBridgeConnectorRef": "test_bridge"}),
            # conditions str
            ["status", "valid(spec)"],
            # evaluations
            [
                [("status", "success"), ("kind", "mqttbridgeconnector")],
                [
                    ("status", "success"),
                    (
                        "value/spec/localBrokerConnection/authentication/x509",
                        "localbrokerauth",
                    ),
                    (
                        "value/spec/remoteBrokerConnection/authentication/kubernetes",
                        "remotebrokerauth",
                    ),
                    ("value/spec/tls/tlsEnabled", True),
                ],
            ],
        ),
        (
            # mqtt bridge
            generate_resource_stub(
                metadata={"name": "test_bridge"},
                spec={
                    "localBrokerConnection": {"authentication": {"x509": "localbrokerauth"}},
                    "remoteBrokerConnection": {"authentication": {"kubernetes": "remotebrokerauth"}},
                    "tls": {"tlsEnabled": True},
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic map with routes
            generate_resource_stub(
                spec={
                    "mqttBridgeConnectorRef": "test_bridge",
                    "routes": [
                        {
                            "name": "route1",
                            "direction": "local-to-remote",
                            "source": "local",
                            "target": "remote",
                            "qos": 0,
                        },
                        {
                            "name": "route2",
                            "direction": "remote-to-local",
                            "source": "remote",
                            "target": "local",
                            "qos": 1,
                        },
                    ],
                }
            ),
            # conditions str
            ["status", "valid(spec)"],
            # evaluations
            [
                [("status", "success"), ("kind", "mqttbridgeconnector")],
                [
                    ("status", "success"),
                    (
                        "value/spec/localBrokerConnection/authentication/x509",
                        "localbrokerauth",
                    ),
                    (
                        "value/spec/remoteBrokerConnection/authentication/kubernetes",
                        "remotebrokerauth",
                    ),
                    ("value/spec/tls/tlsEnabled", True),
                ],
            ],
        ),
    ],
)
def test_mqtt_checks(
    mocker,
    mock_evaluate_cloud_connector_pod_health,
    bridge,
    topic_map,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
    )
    namespace = generate_random_string()
    bridge["metadata"]["namespace"] = namespace
    topic_map["metadata"]["namespace"] = namespace
    mocker.side_effect = [{"items": [bridge]}, {"items": [topic_map]}]
    result = evaluate_mqtt_bridge_connectors(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalmqttbridgeconnectors"
    assert namespace in result["targets"]["mqttbridgeconnectors.mq.iotoperations.azure.com"]
    target = result["targets"]["mqttbridgeconnectors.mq.iotoperations.azure.com"][namespace]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)
    mocker.reset_mock()


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None])
@pytest.mark.parametrize(
    "connector, topic_map, conditions, evaluations",
    [
        (
            # localstorage target
            generate_resource_stub(
                metadata={"name": "test_connector"},
                spec={
                    "instances": 2,
                    "target": {"localStorage": {"volumeName": "sample_volume"}},
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic map
            generate_resource_stub(spec={"dataLakeConnectorRef": "test_connector"}),
            # conditions str
            ["status", "valid(spec)"],
            # evaluations
            [
                [("status", "success"), ("kind", "datalakeconnector")],
                [
                    ("status", "success"),
                    ("value/spec/instances", 2),
                    ("value/spec/target/localStorage/volumeName", "sample_volume"),
                ],
            ],
        ),
        (
            # datalakestorage target
            generate_resource_stub(
                metadata={"name": "test_connector"},
                spec={
                    "instances": 2,
                    "target": {"datalakeStorage": {"endpoint": "test_endpoint"}},
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic map
            generate_resource_stub(spec={"dataLakeConnectorRef": "test_connector"}),
            # conditions str
            ["status", "valid(spec)"],
            # evaluations
            [
                [("status", "success"), ("kind", "datalakeconnector")],
                [
                    ("status", "success"),
                    ("value/spec/instances", 2),
                    ("value/spec/target/datalakeStorage/endpoint", "test_endpoint"),
                ],
            ],
        ),
        (
            # fabriconelake target
            generate_resource_stub(
                metadata={"name": "test_connector"},
                spec={
                    "instances": 2,
                    "target": {"fabricOneLake": {"endpoint": "test_endpoint"}},
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic map
            generate_resource_stub(spec={"dataLakeConnectorRef": "test_connector"}),
            # conditions str
            ["status", "valid(spec)"],
            # evaluations
            [
                [("status", "success"), ("kind", "datalakeconnector")],
                [
                    ("status", "success"),
                    ("value/spec/instances", 2),
                    ("value/spec/target/fabricOneLake/endpoint", "test_endpoint"),
                ],
            ],
        ),
    ],
)
def test_datalake_checks(
    mocker,
    mock_evaluate_cloud_connector_pod_health,
    connector,
    topic_map,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
    )
    namespace = generate_random_string()
    connector["metadata"]["namespace"] = namespace
    topic_map["metadata"]["namespace"] = namespace
    mocker.side_effect = [{"items": [connector]}, {"items": [topic_map]}]
    result = evaluate_datalake_connectors(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evaldatalakeconnectors"
    assert namespace in result["targets"]["datalakeconnectors.mq.iotoperations.azure.com"]
    target = result["targets"]["datalakeconnectors.mq.iotoperations.azure.com"][namespace]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None])
@pytest.mark.parametrize(
    "connector, topic_map, conditions, evaluations",
    [
        (
            # kafka_connector
            generate_resource_stub(
                metadata={"name": "mock-kafka-connector"},
                spec={
                    "clientIdPrefix": "kafka-prefix",
                    "instances": 3,
                    "localBrokerConnection": {
                        "authentication": {"kubernetes": {}},
                        "endpoint": "local-auth-endpoint",
                        "tls": {"tlsEnabled": True},
                    },
                    "kafkaConnection": {
                        "authentication": {"authType": {"sasl": {}}},
                        "endpoint": "kafka-endpoint",
                        "tls": {"tlsEnabled": True},
                    },
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic_map
            generate_resource_stub(spec={"kafkaConnectorRef": "mock-kafka-connector"}),
            # conditions
            ["status", "valid(spec)"],
            # evals
            [
                [("status", "success")],
                [
                    ("status", "success"),
                    ("value/spec/clientIdPrefix", "kafka-prefix"),
                    ("value/spec/instances", 3),
                    (
                        "value/spec/localBrokerConnection/endpoint",
                        "local-auth-endpoint",
                    ),
                    ("value/spec/kafkaConnection/endpoint", "kafka-endpoint"),
                    ("value/spec/clientIdPrefix", "kafka-prefix"),
                ],
            ],
        ),
        (
            # kafka_connector
            generate_resource_stub(
                metadata={"name": "mock-kafka-connector"},
                spec={
                    "clientIdPrefix": "kafka-prefix",
                    "instances": 2,
                    "localBrokerConnection": {
                        "authentication": {"kubernetes": {}},
                        "endpoint": "local-auth-endpoint",
                        "tls": {"tlsEnabled": True},
                    },
                    "kafkaConnection": {
                        "authentication": {"authType": {"sasl": {}}},
                        "endpoint": "kafka-endpoint",
                        "tls": {"tlsEnabled": True},
                    },
                },
                status={"configStatusLevel": ResourceState.running.value},
            ),
            # topic_map with routes
            generate_resource_stub(
                spec={
                    "kafkaConnectorRef": "mock-kafka-connector",
                    "routes": [
                        {
                            KafkaTopicMapRouteType.mqtt_to_kafka.value: {
                                "kafkaTopic": "kafka_topic",
                                "mqttTopic": "mqtt_topic",
                                "qos": 1,
                                "kafkaAcks": 3,
                                "sharedSubscription": {
                                    "groupName": "test_group",
                                    "groupMinimumShareNumber": 1,
                                },
                            }
                        },
                        {
                            KafkaTopicMapRouteType.kafka_to_mqtt.value: {
                                "kafkaTopic": "kafka_topic",
                                "mqttTopic": "mqtt_topic",
                                "qos": 0,
                                "consumerGroupId": "$default",
                            }
                        },
                    ],
                }
            ),
            # conditions
            ["status", "valid(spec)"],
            # evals
            [
                [("status", "success")],
                [
                    ("status", "success"),
                    ("value/spec/clientIdPrefix", "kafka-prefix"),
                    ("value/spec/instances", 2),
                    (
                        "value/spec/localBrokerConnection/endpoint",
                        "local-auth-endpoint",
                    ),
                    ("value/spec/kafkaConnection/endpoint", "kafka-endpoint"),
                    ("value/spec/clientIdPrefix", "kafka-prefix"),
                ],
            ],
        ),
    ],
)
def test_kafka_checks(
    mocker,
    mock_evaluate_cloud_connector_pod_health,
    connector,
    topic_map,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch("azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources")
    namespace = generate_random_string()
    connector["metadata"]["namespace"] = namespace
    topic_map["metadata"]["namespace"] = namespace
    mocker.side_effect = [{"items": [connector]}, {"items": [topic_map]}]
    result = evaluate_kafka_connectors(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalkafkaconnectors"
    assert namespace in result["targets"]["kafkaconnectors.mq.iotoperations.azure.com"]
    target = result["targets"]["kafkaconnectors.mq.iotoperations.azure.com"][namespace]

    assert_conditions(target, conditions)
    assert_evaluations(target, evaluations)


@pytest.mark.parametrize(
    "eval_func, name, target",
    (
        (
            evaluate_mqtt_bridge_connectors,
            "evalmqttbridgeconnectors",
            "mqttbridgeconnectors.mq.iotoperations.azure.com",
        ),
        (
            evaluate_datalake_connectors,
            "evaldatalakeconnectors",
            "datalakeconnectors.mq.iotoperations.azure.com",
        ),
        (
            evaluate_kafka_connectors,
            "evalkafkaconnectors",
            "kafkaconnectors.mq.iotoperations.azure.com",
        ),
    ),
)
def test_empty_connector_results(mocker, mock_evaluate_cloud_connector_pod_health, eval_func: partial, name, target):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        return_value={"items": []},
    )

    result = eval_func()
    assert result["name"] == name
    assert all(
        [
            result["targets"][target][ALL_NAMESPACES_TARGET],
            not result["targets"][target][ALL_NAMESPACES_TARGET]["conditions"],
            (
                result["targets"][target][ALL_NAMESPACES_TARGET]["evaluations"][0]["status"]
                == CheckTaskStatus.skipped.value,
            ),
            result["targets"][target][ALL_NAMESPACES_TARGET]["status"] == CheckTaskStatus.skipped.value,
        ]
    )


@pytest.mark.parametrize(
    """connector_resource_name, topic_map_reference_key, all_connectors,
        all_topic_maps, filtered_connectors, filtered_topic_maps""",
    [
        # filter by connector name
        (
            "mock-connector",
            "mqttBridgeConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"mqttBridgeConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"mqttBridgeConnectorRef": "mock-connector2"}),
            ],
            [generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"})],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"mqttBridgeConnectorRef": "mock-connector"})
            ],
        ),
        # filter by connector name with wildcard
        (
            "mock-connector*",
            "dataLakeConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"dataLakeConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"dataLakeConnectorRef": "mock-connector2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"dataLakeConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"dataLakeConnectorRef": "mock-connector2"}),
            ],
        ),
        # no name filter
        (
            None,
            "kafkaConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
        ),
        # filter with non-matching connector name
        (
            "test",
            "kafkaConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
            [],
            [],
        ),
        # topic map contains different namespace than connector
        (
            "mock-connector2",
            "kafkaConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
        ),
        # connector contains different namespace but same name
        (
            "mock-connector2",
            "kafkaConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map3", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map4", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace2"}),
            ]
            ,
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map4", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
        ),
        # combined 2 different scenarios above
        (
            "mock-connector",
            "kafkaConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace2"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace3"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map3", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map4", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map5", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace2"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace3"}),
            ],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map3", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map4", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
            ],
        ),
        # no connector
        (
            "mock-connector",
            "kafkaConnectorRef",
            [],
            [
                generate_resource_stub(metadata={"name": "mock-topic-map", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
                generate_resource_stub(metadata={"name": "mock-topic-map2", "namespace": "mock-namespace"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map3", "namespace": "mock-namespace3"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map4", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector"}),
                generate_resource_stub(metadata={"name": "mock-topic-map5", "namespace": "mock-namespace2"},
                                       spec={"kafkaConnectorRef": "mock-connector2"}),
            ],
            [],
            [],
        ),
        # no topic map
        (
            "mock-connector",
            "kafkaConnectorRef",
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace2"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace3"}),
                generate_resource_stub(metadata={"name": "mock-connector2", "namespace": "mock-namespace2"}),
            ],
            [],
            [
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace2"}),
                generate_resource_stub(metadata={"name": "mock-connector", "namespace": "mock-namespace3"}),
            ],
            [],
        ),
        # no connector and no topic map
        (
            "test",
            "kafkaConnectorRef",
            [],
            [],
            [],
            [],
        ),
    ],
)
def test_filtered_process_cloud_connector(
    connector_resource_name,
    topic_map_reference_key,
    all_connectors,
    all_topic_maps,
    filtered_connectors,
    filtered_topic_maps,
):
    connectors, topics = filter_connector_and_topic_map_resources(
        connector_resource_name, topic_map_reference_key, all_connectors, all_topic_maps
    )

    assert connectors == filtered_connectors
    assert topics == filtered_topic_maps
