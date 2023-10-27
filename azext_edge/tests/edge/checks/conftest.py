# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------
from typing import List, Dict, Any
import pytest

from azext_edge.edge.providers.checks import run_checks


@pytest.fixture
def mock_evaluate_e4k_pod_health(mocker):
    patched = mocker.patch("azext_edge.edge.providers.check.mq.evaluate_pod_health", return_value={})
    yield patched


@pytest.fixture
def mock_evaluate_cloud_connector_pod_health(mocker):
    patched = mocker.patch("azext_edge.edge.providers.check.cloud_connectors.evaluate_pod_health", return_value={})
    yield patched


@pytest.fixture
def mock_evaluate_bluefin_pod_health(mocker):
    patched = mocker.patch("azext_edge.edge.providers.check.bluefin.evaluate_pod_health", return_value={})
    yield patched


@pytest.fixture
def mock_resource_types(mocker, edge_service):
    patched = mocker.patch("azext_edge.edge.providers.check.base.enumerate_edge_service_resources")

    if edge_service == "mq":
        patched.return_value = (
            {},
            {
                "Broker": [{}],
                "BrokerListener": [{}],
                "DiagnosticService": [{}],
                "MqttBridgeConnector": [{}],
                "DataLakeConnector": [{}]
            }
        )
    elif edge_service == "bluefin":
        patched.return_value = (
            {},
            {
                "Dataset": [{}],
                "Instance": [{}],
                "Pipeline": [{}]
            }
        )

    yield patched


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


def generate_resource_stub(
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


def assert_check_by_resource_types(edge_service, mocker, mock_resource_types, resource_kinds, eval_lookup):
    # Mock the functions
    for key, value in eval_lookup.items():
        eval_lookup[key] = mocker.patch(value, return_value={})

    # run the checks
    run_checks(
        edge_service=edge_service,
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
