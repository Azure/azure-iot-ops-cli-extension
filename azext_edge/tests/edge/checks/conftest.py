# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------
import pytest


@pytest.fixture
def mock_evaluate_e4k_pod_health(mocker):
    patched = mocker.patch("azext_edge.edge.providers.check.e4k.evaluate_pod_health", return_value={})
    yield patched


@pytest.fixture
def mock_evaluate_bluefin_pod_health(mocker):
    patched = mocker.patch("azext_edge.edge.providers.check.bluefin.evaluate_pod_health", return_value={})
    yield patched


@pytest.fixture
def mock_resource_types(mocker, edge_service):
    if edge_service == "e4k":
        patched = mocker.patch("azext_edge.edge.providers.check.base.enumerate_edge_service_resources")
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
        yield patched
    elif edge_service == "bluefin":
        patched = mocker.patch("azext_edge.edge.providers.check.base.enumerate_edge_service_resources")
        patched.return_value = (
            {},
            {
                "Dataset": [{}],
                "Instance": [{}],
                "Pipeline": [{}]
            }
        )
        yield patched
