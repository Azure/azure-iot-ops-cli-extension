# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------
import pytest


@pytest.fixture
def mock_evaluate_pod_health(mocker):
    patched = mocker.patch("azext_edge.edge.providers.checks.evaluate_pod_health", return_value={})
    yield patched


@pytest.fixture
def mock_e4k_resource_types(mocker):
    patched = mocker.patch("azext_edge.edge.providers.checks.enumerate_e4k_resources")
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
