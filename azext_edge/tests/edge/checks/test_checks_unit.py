# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


import pytest
from typing import Dict
from azext_edge.edge.common import CheckTaskStatus
from azext_edge.edge.providers.checks import (CheckManager, E4kResourceKinds,
                                              ResourceState,
                                              evaluate_broker_listeners,
                                              evaluate_brokers,
                                              evaluate_diagnostics_service,
                                              run_checks)

from ...generators import generate_generic_id


def test_check_manager():
    name = generate_generic_id()
    desc = f"{generate_generic_id()} {generate_generic_id()}"
    namespace = generate_generic_id()
    check_manager = CheckManager(check_name=name, check_desc=desc, namespace=namespace)
    assert_check_manager_dict(check_manager=check_manager, expected_name=name, expected_desc=desc)

    target_1 = generate_generic_id()
    target_1_condition_1 = generate_generic_id()
    target_1_conditions = [target_1_condition_1]
    target_1_eval_1_value = {generate_generic_id(): generate_generic_id()}
    target_1_display_1 = generate_generic_id()

    check_manager.add_target(target_name=target_1, conditions=target_1_conditions)
    check_manager.add_target_eval(
        target_name=target_1, status=CheckTaskStatus.success.value, value=target_1_eval_1_value
    )
    check_manager.add_display(target_name=target_1, display=target_1_display_1)
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [{"status": CheckTaskStatus.success.value, "value": target_1_eval_1_value}],
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
    check_manager.add_target_eval(target_name=target_1, status=CheckTaskStatus.warning.value)
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {"status": CheckTaskStatus.success.value, "value": target_1_eval_1_value},
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
    check_manager.add_target_eval(target_name=target_2, status=CheckTaskStatus.error.value)

    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {"status": CheckTaskStatus.success.value, "value": target_1_eval_1_value},
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
    check_manager.add_target_eval(target_name=target_1, status=CheckTaskStatus.skipped.value, value=None)
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
            assert expected_target_displays[target] == result_check_dict_displays["targets"][target]["displays"]


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [
            E4kResourceKinds.BROKER.value
        ],
        [
            E4kResourceKinds.BROKER.value,
            E4kResourceKinds.BROKER_LISTENER.value
        ],
        [
            E4kResourceKinds.DIAGNOSTIC_SERVICE.value
        ],
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
def test_check_by_resource_types(mocker, mock_e4k_resource_types, resource_kinds):
    eval_lookup = {
        E4kResourceKinds.BROKER.value: mocker.patch(
            "azext_edge.edge.providers.checks.evaluate_brokers", return_value={}
        ),
        E4kResourceKinds.BROKER_LISTENER.value: mocker.patch(
            "azext_edge.edge.providers.checks.evaluate_broker_listeners",
            return_value={},
        ),
        E4kResourceKinds.DIAGNOSTIC_SERVICE.value: mocker.patch(
            "azext_edge.edge.providers.checks.evaluate_diagnostics_service",
            return_value={},
        ),
        E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value: mocker.patch(
            "azext_edge.edge.providers.checks.evaluate_mqtt_bridge_connectors",
            return_value={},
        ),
        E4kResourceKinds.DATALAKE_CONNECTOR.value: mocker.patch(
            "azext_edge.edge.providers.checks.evaluate_datalake_connectors",
            return_value={},
        ),
    }

    # run the checks
    run_checks(
        namespace='default',
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


@pytest.mark.parametrize(
    "broker, conditions, evaluations",
    [
        (
            # broker (distributed)
            {
                "metadata": {"namespace": "mock_namespace", "name": "mock_name"},
                "spec": {
                    "diagnostics": {},  # required
                    "cardinality": {
                        "backendChain": {"partitions": 1, "replicas": 2, "workers": 1},
                        "frontend": {"replicas": 1}
                    },
                    "mode": "distributed"
                },
                "status": {
                    "status": ResourceState.running.value,
                    "statusDescription": ""
                }
            },
            # conditions str
            [
                "len(brokers)==1",
                "status",
                "spec.mode",
                "spec.cardinality",
                "spec.cardinality.backendChain.partitions>=1",
                "spec.cardinality.backendChain.replicas>=1",
                "spec.cardinality.frontend.replicas>=1"
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
            ]
        ),
        (
            # broker 2 - not distributed, so less conditions on cardinality
            {
                "metadata": {"namespace": "mock_namespace", "name": "mock_name"},
                "spec": {
                    "diagnostics": {
                        "diagnosticServiceEndpoint": "test",
                        "enableMetrics": "test",
                        "enableSelfCheck": "test",
                        "enableTracing": "test",
                        "logLevel": "test",
                    },
                    "cardinality": {
                        "backendChain": {"partitions": 1, "replicas": 2, "workers": 1},
                        "frontend": {"replicas": 1}
                    },
                },
                "status": {
                    "status": ResourceState.starting.value,
                    "statusDescription": ""
                }
            },
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
            ]
        )
    ]
)
def test_broker_checks(
    mocker,
    mock_evaluate_pod_health,
    broker,
    conditions,
    evaluations
):
    mocker.patch('azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources', return_value={
        "items": [broker]
    })

    namespace = generate_generic_id()
    result = evaluate_brokers(namespace=namespace)

    # all evalBroker assertions
    assert result['name'] == 'evalBrokers'
    assert result['namespace'] == namespace
    assert result['targets']['brokers.az-edge.com']
    target = result['targets']['brokers.az-edge.com']

    # default conditions
    result_conditions = target['conditions']
    for condition in ['len(brokers)==1', 'status', 'spec.mode']:
        assert condition in result_conditions

    # custom conditions
    for condition in conditions:
        assert condition in result_conditions

    # assert eval properties
    result_evals = target['evaluations']
    for idx, evals in enumerate(evaluations):
        for eval in evals:
            assert_dict_props(
                path=eval[0],
                expected=eval[1],
                obj=result_evals[idx]
            )


@pytest.mark.parametrize(
    "listener, conditions, evaluations",
    [
        (
            # listener with valid broker ref
            {
                "metadata": {"namespace": "mock_namespace", "name": "mock_name"},
                "spec": {
                    "serviceName": "name",
                    "serviceType": "type",
                    "brokerRef": "mock_broker",
                    "port": 8080,
                    "authenticationEnabled": "True"
                },
                "status": {
                    "status": ResourceState.running.value,
                    "statusDescription": ""
                }
            },
            # conditions str
            [
                "len(brokerlisteners)>=1",
                "spec",
                "valid(spec.brokerRef)",
                "spec.serviceName",
                "status"
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
            ]
        ),
    ]
)
def test_broker_listener_checks(
    mocker,
    mock_evaluate_pod_health,
    listener,
    conditions,
    evaluations
):
    # mock listener values
    mocker.patch('azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources', return_value={
        "items": [listener]
    })
    # broker ref
    mocker.patch('azext_edge.edge.providers.checks._get_valid_references', return_value={
        "mock_broker": True
    })

    namespace = generate_generic_id()
    result = evaluate_broker_listeners(namespace=namespace)

    assert result['name'] == 'evalBrokerListeners'
    assert result['namespace'] == namespace
    assert result['targets']['brokerlisteners.az-edge.com']
    target = result['targets']['brokerlisteners.az-edge.com']

    # conditions
    result_conditions = target['conditions']
    for condition in conditions:
        assert condition in result_conditions

    # assert eval properties
    result_evals = target['evaluations']
    for idx, evals in enumerate(evaluations):
        for eval in evals:
            assert_dict_props(
                path=eval[0],
                expected=eval[1],
                obj=result_evals[idx]
            )

@pytest.mark.parametrize(
    "service, conditions, evaluations",
    [
        (
            # diagnostic service
            {
                "metadata": {"namespace": "mock_namespace", "name": "mock_name"},
                "spec": {
                    "dataExportFrequencySeconds": 10,
                    "logFormat": "text",
                    "logLevel": "info",
                    "maxDataStorageSize": 16,
                    "metricsPort": 9600,
                    "staleDataTimeoutSeconds": 600
                },
            },
            # conditions str
            [
                "len(diagnosticservices)==1",
                "spec"
            ],
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
            ]
        ),
    ]
)
def test_diagnostic_service_checks(
    mocker,
    mock_evaluate_pod_health,
    service,
    conditions,
    evaluations
):
    # mock service values
    mocker.patch('azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources', return_value={
        "items": [service]
    })

    namespace = generate_generic_id()
    result = evaluate_diagnostics_service(namespace=namespace)

    assert result['name'] == 'evalBrokerDiag'
    assert result['namespace'] == namespace
    assert result['targets']['diagnosticservices.az-edge.com']
    target = result['targets']['diagnosticservices.az-edge.com']

    # conditions
    result_conditions = target['conditions']
    for condition in conditions:
        assert condition in result_conditions

    # assert eval properties
    result_evals = target['evaluations']
    for idx, evals in enumerate(evaluations):
        for eval in evals:
            assert_dict_props(
                path=eval[0],
                expected=eval[1],
                obj=result_evals[idx]
            )


def test_mqtt_checks():
    pass


def test_datalake_checks():
    pass


def assert_dict_props(path: str, expected: str, obj: Dict[str, str]):
    val = obj
    for key in path.split('/'):
        val = val[key]
    if isinstance(val, list) or isinstance(val, dict):
        assert expected in val
    else:
        assert val == expected
