# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import binascii
from unittest.mock import MagicMock
from kubernetes.client.models import V1ObjectMeta, V1Pod, V1PodList

from azext_edge.edge.commands_e4k import stats
from azext_edge.edge.common import AZEDGE_DIAGNOSTICS_SERVICE, METRICS_SERVICE_API_PORT

# pylint: disable=no-name-in-module
from azext_edge.edge.providers.proto.diagnostics_service_pb2 import Request, Response, TraceRetrievalInfo

from ...generators import generate_generic_id


def test_stats(mocker, mocked_cmd, mocked_client, mocked_config, mocked_urlopen, stub_raw_stats):
    pods = [V1Pod(metadata=V1ObjectMeta(name=AZEDGE_DIAGNOSTICS_SERVICE, namespace="namespace"))]
    pod_list = V1PodList(items=pods)
    mocked_client.CoreV1Api().list_namespaced_pod.return_value = pod_list

    attrs = {"read.return_value": stub_raw_stats.read()}
    response = MagicMock(**attrs)
    mocked_urlopen.return_value.__enter__.return_value = response

    namespace = generate_generic_id()
    context_name = generate_generic_id()
    result = stats(cmd=mocked_cmd, namespace=namespace, context_name=context_name)
    min_stats_assert(result)
    mocked_urlopen.assert_called_with(
        f"http://{AZEDGE_DIAGNOSTICS_SERVICE}.{namespace}.kubernetes:{METRICS_SERVICE_API_PORT}/metrics"
    )

    console_mock = mocker.patch("azext_edge.edge.providers.stats.console", autospec=True)
    stats(cmd=mocked_cmd, namespace=namespace, context_name=context_name, raw_response_print=True)
    console_mock.print.assert_called_once()

    trace_id1 = "2f799d7a9d1e8e182a52dc190baebce2"
    trace_id2 = "4a32aaad8f3c5483b5b4960a06b82dfd"
    trace_ids = [trace_id1, trace_id2]
    trace_ids_hex = [binascii.unhexlify(t) for t in trace_ids]

    serialized_request = Request(get_traces=TraceRetrievalInfo(trace_ids=trace_ids_hex)).SerializeToString()
    request_len_b = len(serialized_request).to_bytes(4, byteorder="big")

    portforward_socket_mock = mocker.patch("azext_edge.edge.providers.stats.portforward_socket")
    portforward_socket_mock().__enter__().recv.side_effect = [int(0).to_bytes(length=4, byteorder="big"), b""]

    result = stats(cmd=mocked_cmd, namespace=namespace, context_name=context_name, trace_ids=trace_ids)
    request_bytes_length = portforward_socket_mock().__enter__().sendall.call_args_list[0].args[0]
    assert request_bytes_length == request_len_b

    request_bytes_trace_ids = portforward_socket_mock().__enter__().sendall.call_args_list[1].args[0]
    assert request_bytes_trace_ids == serialized_request


def min_stats_assert(stats_map: dict):
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
