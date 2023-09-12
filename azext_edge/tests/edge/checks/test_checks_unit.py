# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


from azext_edge.edge.providers.checks import CheckManager, run_checks, E4kResourceKinds, ResourceState
from azext_edge.edge.common import CheckTaskStatus
from ...generators import generate_generic_id
import pytest

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
    "mock_resource_items, assertions",
    [
        (
            # broker items
            [
                {
                    "metadata": {"namespace": "mock_namespace", "name": "mock_name"},
                    "spec": {
                        "diagnostics": {
                            "diagnosticServiceEndpoint": "None",
                            "enableMetrics": "True",
                            "enableSelfCheck": "True",
                            "enableSelfTracing": "True",
                            "enableTracing": "True",
                            "logFormat": "text",
                            "logLevel": "info,hyper=off,kube_client=off,tower=off,conhash=off,h2=off",
                        },
                        "cardinality": {
                            "backendChain": { "partitions": 1, "replicas": 2, "workers": 1 },
                            "frontend": { "replicas": 1 }
                        },
                    },
                    "status": {
                        "status": ResourceState.running.value,
                        "statusDescription": ""
                    }
                }
            ],
            # assertions
            {
                'test': 'test'
            }
        )
    ]
)
def test_broker_checks(
    mocker,
    mock_evaluate_pod_health,
    mock_resource_items,
    assertions
):
    # from unittest.mock import MagicMock
    from azext_edge.edge.providers.checks import evaluate_brokers
    
    # broker_list: dict = E4K_ACTIVE_API.get_resources(E4kResourceKinds.BROKER, namespace=namespace)
    mocker.patch('azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources', return_value={
        "items": mock_resource_items
    })

    namespace = generate_generic_id()
    result = evaluate_brokers(namespace=namespace)

def test_broker_listner_checks():
    pass

def test_diagnostic_service_checks():
    pass

def test_mqtt_checks():
    pass

def test_datalake_checks():
    pass