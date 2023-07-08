# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import MagicMock
from kubernetes.client.models import V1ObjectMeta, V1Pod, V1PodList

from azext_edge.edge.commands_e4k import stats
from azext_edge.edge.common import AZEDGE_DIAGNOSTICS_SERVICE, METRICS_SERVICE_API_PORT

from ...generators import generate_generic_id


def test_stats(mocker, mocked_client, mocked_config, mocked_urlopen, stub_raw_stats):
    pods = [V1Pod(metadata=V1ObjectMeta(name=AZEDGE_DIAGNOSTICS_SERVICE, namespace="namespace"))]
    pod_list = V1PodList(items=pods)
    mocked_client.CoreV1Api().list_namespaced_pod.return_value = pod_list

    attrs = {"read.return_value": stub_raw_stats.read()}
    response = MagicMock(**attrs)
    mocked_urlopen.return_value.__enter__.return_value = response

    namespace = generate_generic_id()
    context_name = generate_generic_id()
    result = stats(cmd=None, namespace=namespace, context_name=context_name)
    min_stats_assert(result)
    mocked_urlopen.assert_called_with(
        f"http://{AZEDGE_DIAGNOSTICS_SERVICE}.{namespace}.kubernetes:{METRICS_SERVICE_API_PORT}/metrics"
    )

    console_mock = mocker.patch("azext_edge.edge.providers.stats.console", autospec=True)
    stats(cmd=None, namespace=namespace, context_name=context_name, raw_response_print=True)
    console_mock.print.assert_called_once()


def min_stats_assert(stats_map: dict):
    _assert_stats_kpi(stats_map, "azedge_selftest_latest_run_status_total", value_pass_fail=True)
    _assert_stats_kpi(stats_map, "connected_sessions")
    _assert_stats_kpi(stats_map, "publish_latency_mu_ms")
    _assert_stats_kpi(stats_map, "publish_latency_sigma_ms")
    _assert_stats_kpi(stats_map, "publish_route_replication_correctness", value_pass_fail=True)
    _assert_stats_kpi(stats_map, "publishes_received_per_second")
    _assert_stats_kpi(stats_map, "publishes_sent_per_second")
    _assert_stats_kpi(stats_map, "total_subscriptions")


def _assert_stats_kpi(stats_map: dict, kpi: str, value_pass_fail: bool = False):
    assert kpi in stats_map
    assert "displayName" in stats_map[kpi]
    assert "description" in stats_map[kpi]
    assert "value" in stats_map[kpi]
    if value_pass_fail:
        stats_map[kpi]["value"] in ["Pass", "Fail"]
