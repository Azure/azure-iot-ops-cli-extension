# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import binascii
from copy import deepcopy
from unittest.mock import MagicMock
from zipfile import ZIP_DEFLATED, ZipInfo

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError
from google.protobuf.json_format import ParseDict
from kubernetes.client.models import V1ObjectMeta, V1Pod, V1PodList, V1PodStatus
from opentelemetry.proto.trace.v1.trace_pb2 import TracesData

from azext_edge.edge.commands_mq import stats
from azext_edge.edge.common import AIO_BROKER_DIAGNOSTICS_SERVICE, METRICS_SERVICE_API_PORT, PodState

# pylint: disable=no-name-in-module
from azext_edge.edge.providers.proto.diagnostics_service_pb2 import (
    Request,
    Response,
    RetrievedTraceWrapper,
    TraceRetrievalInfo,
)

from ...generators import generate_random_string
from .traces_data import TEST_TRACE, TEST_TRACE_PARTIAL


def test_get_stats(mocker, mocked_cmd, mocked_client, mocked_config, mocked_urlopen, stub_raw_stats):
    pods = [
        V1Pod(
            metadata=V1ObjectMeta(name=AIO_BROKER_DIAGNOSTICS_SERVICE, namespace="namespace"),
            status=V1PodStatus(phase=PodState.running.value),
        )
    ]
    pod_list = V1PodList(items=pods)
    mocked_client.CoreV1Api().list_namespaced_pod.return_value = pod_list

    attrs = {"read.return_value": stub_raw_stats.read()}
    response = MagicMock(**attrs)
    # pylint: disable-next=unnecessary-dunder-call
    mocked_urlopen.return_value.__enter__.return_value = response

    namespace = generate_random_string()
    context_name = generate_random_string()
    result = stats(cmd=mocked_cmd, namespace=namespace, context_name=context_name)
    min_stats_assert(result)
    mocked_urlopen.assert_called_with(
        f"http://{AIO_BROKER_DIAGNOSTICS_SERVICE}.{namespace}.kubernetes:{METRICS_SERVICE_API_PORT}/metrics"
    )

    console_mock = mocker.patch("azext_edge.edge.providers.stats.console", autospec=True)
    stats(cmd=mocked_cmd, namespace=namespace, context_name=context_name, raw_response_print=True)
    console_mock.print.assert_called_once()


@pytest.mark.parametrize(
    "trace_ids,trace_dir,recv_side_effect",
    [
        pytest.param(
            ["2f799d7a9d1e8e182a52dc190baebce2"],
            None,
            [
                int(1).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=1,
                        total_trace_count=1,
                    )
                ).SerializeToString(),
            ],
        ),
        pytest.param(
            ["2f799d7a9d1e8e182a52dc190baebce2", "4a32aaad8f3c5483b5b4960a06b82dfd"],
            None,
            [
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=1,
                        total_trace_count=2,
                    )
                ).SerializeToString(),
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=2,
                        total_trace_count=2,
                    )
                ).SerializeToString(),
            ],
        ),
        pytest.param(
            ["!support_bundle!"],
            None,
            [
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=1,
                        total_trace_count=2,
                    )
                ).SerializeToString(),
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=2,
                        total_trace_count=2,
                    )
                ).SerializeToString(),
            ],
        ),
        pytest.param(
            [],
            ".",
            [
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=1,
                        total_trace_count=2,
                    )
                ).SerializeToString(),
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=2,
                        total_trace_count=2,
                    )
                ).SerializeToString(),
            ],
        ),
        pytest.param(
            ["2f799d7a9d1e8e182a52dc190baebce2"],
            ".",
            [
                int(2).to_bytes(length=4, byteorder="big"),
                Response(
                    retrieved_trace=RetrievedTraceWrapper(
                        trace=ParseDict(TEST_TRACE.data, TracesData()),
                        current_trace_count=1,
                        total_trace_count=1,
                    )
                ).SerializeToString(),
            ],
        ),
    ],
)
def test_get_traces(
    mocker, mocked_cmd, mocked_client, mocked_config, mocked_zipfile, trace_ids, trace_dir, recv_side_effect
):
    # pylint: disable=unnecessary-dunder-call
    pods = [
        V1Pod(
            metadata=V1ObjectMeta(name=AIO_BROKER_DIAGNOSTICS_SERVICE, namespace="namespace"),
            status=V1PodStatus(phase=PodState.running.value),
        )
    ]
    pod_list = V1PodList(items=pods)
    mocked_client.CoreV1Api().list_namespaced_pod.return_value = pod_list

    namespace = generate_random_string()
    context_name = generate_random_string()

    for_support_bundle = False
    if trace_ids:
        if trace_ids[0] == "!support_bundle!":
            for_support_bundle = True
    trace_ids_hex = [binascii.unhexlify(t) for t in trace_ids] if not for_support_bundle else []

    serialized_request = Request(get_traces=TraceRetrievalInfo(trace_ids=trace_ids_hex)).SerializeToString()
    request_len_b = len(serialized_request).to_bytes(4, byteorder="big")

    portforward_socket_mock = mocker.patch("azext_edge.edge.providers.stats.portforward_socket")
    portforward_socket_mock().__enter__().recv.side_effect = recv_side_effect
    result = stats(
        cmd=mocked_cmd,
        namespace=namespace,
        context_name=context_name,
        trace_ids=trace_ids,
        trace_dir=trace_dir,
    )

    request_bytes_length = portforward_socket_mock().__enter__().sendall.call_args_list[0].args[0]
    assert request_bytes_length == request_len_b
    request_bytes_trace_ids = portforward_socket_mock().__enter__().sendall.call_args_list[1].args[0]
    assert request_bytes_trace_ids == serialized_request

    if trace_ids:
        assert len(result) == len(recv_side_effect) / 2
        assert isinstance(result, list)
        assert isinstance(result[0], dict)

    if for_support_bundle:
        assert len(result) == len(recv_side_effect)  # for_support_bundle effectively doubles the return items
        assert isinstance(result, list)
        assert isinstance(result[0], tuple)
        assert isinstance(result[0][0], ZipInfo)

    if trace_dir:
        zipfile_init_kwargs = mocked_zipfile.mock_calls.pop(0).kwargs
        assert "broker_traces_" in zipfile_init_kwargs["file"]
        assert zipfile_init_kwargs["mode"] == "w"
        assert zipfile_init_kwargs["compression"] == ZIP_DEFLATED
        mocked_zipfile.mock_calls.pop(-1)  # Remove close()
        # When writing to zip, the operation effectively writes 2 files per trace.
        # One in vanilla OTLP one in Tempo format.
        # TODO assert formats.
        assert len(mocked_zipfile.mock_calls) == len(recv_side_effect)
    # pylint: enable=unnecessary-dunder-call


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


@pytest.mark.parametrize(
    "total_bytes,fetch_bytes",
    [
        pytest.param(10, 10),
        pytest.param(10, 5),
        pytest.param(10, 1),
        pytest.param(10, 3),
        pytest.param(10, 0),
        pytest.param(10, -1),  # -1 is a special value to exercise partial fetching of bytes
    ],
)
def test__fetch_bytes(mocker, total_bytes: int, fetch_bytes: int):
    import math
    import secrets

    from azext_edge.edge.providers.stats import _fetch_bytes

    if fetch_bytes > 0:
        total_fetches = math.ceil(total_bytes / fetch_bytes)
    elif fetch_bytes == 0:
        total_fetches = 1
    elif fetch_bytes == -1:
        total_fetches = 2
    else:
        raise RuntimeError("Unsupported scenario.")

    socket_mock = mocker.MagicMock()

    handle_fetch_count = 0

    def handle_fetch(*args, **kwargs):
        nonlocal handle_fetch_count
        if args[0] >= fetch_bytes:
            if fetch_bytes == -1:
                if handle_fetch_count > 0:
                    return_bytes = 0
                else:
                    return_bytes = 1
            else:
                return_bytes = fetch_bytes
        else:
            return_bytes = args[0]

        handle_fetch_count = handle_fetch_count + 1
        return secrets.token_bytes(return_bytes)

    socket_mock.recv.side_effect = handle_fetch
    result = _fetch_bytes(socket_mock, size=total_bytes)
    assert socket_mock.recv.call_count == total_fetches

    if fetch_bytes == 0:
        assert result == b""
        return

    if fetch_bytes == -1:
        assert len(result) == 1
        return

    assert len(result) == total_bytes


def test___determine_root_span():
    from azext_edge.edge.providers.stats import _determine_root_span

    root_span, resource_name, timestamp = _determine_root_span(message_dict=deepcopy(TEST_TRACE.data))
    assert root_span == TEST_TRACE.root_span
    assert resource_name == TEST_TRACE.resource_name
    assert timestamp == TEST_TRACE.timestamp

    root_span, resource_name, timestamp = _determine_root_span(message_dict=deepcopy(TEST_TRACE_PARTIAL.data))
    assert root_span is None
    assert resource_name is None
    assert timestamp is None

    partial_trace_mod = deepcopy(TEST_TRACE_PARTIAL.data)
    del partial_trace_mod["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    del partial_trace_mod["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["spanId"]
    del partial_trace_mod["resourceSpans"][0]["resource"]
    del partial_trace_mod["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["parentSpanId"]
    del partial_trace_mod["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["startTimeUnixNano"]
    root_span, resource_name, timestamp = _determine_root_span(message_dict=partial_trace_mod)
    assert root_span
    assert resource_name is None
    assert timestamp is None

    root_span, resource_name, timestamp = _determine_root_span(message_dict={})
    assert root_span is None
    assert resource_name is None
    assert timestamp is None


@pytest.mark.parametrize(
    "test_state",
    [
        {
            "expected_pods": [
                V1Pod(
                    metadata=V1ObjectMeta(
                        name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-{generate_random_string()}",
                        namespace="namespace",
                    ),
                    status=V1PodStatus(phase=PodState.running.value),
                )
            ],
            "expected_pod_index": 0,
        },
        {
            "expected_pods": [
                V1Pod(
                    metadata=V1ObjectMeta(
                        name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-{generate_random_string()}",
                        namespace="namespace",
                    ),
                    status=V1PodStatus(phase=PodState.failed.value),
                ),
                V1Pod(
                    metadata=V1ObjectMeta(
                        name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-{generate_random_string()}",
                        namespace="namespace",
                    ),
                    status=V1PodStatus(phase=PodState.pending.value),
                ),
                V1Pod(
                    metadata=V1ObjectMeta(
                        name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-{generate_random_string()}",
                        namespace="namespace",
                    ),
                    status=V1PodStatus(phase=PodState.running.value),
                ),
            ],
            "expected_pod_index": 2,
        },
        {
            "expected_pods": [
                V1Pod(
                    metadata=V1ObjectMeta(
                        name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-{generate_random_string()}",
                        namespace="namespace",
                    ),
                    status=V1PodStatus(phase=PodState.failed.value),
                ),
                V1Pod(
                    metadata=V1ObjectMeta(
                        name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-{generate_random_string()}",
                        namespace="namespace",
                    ),
                    status=V1PodStatus(phase=PodState.succeeded.value),
                ),
            ],
            "expected_pod_index": -1,
        },
        {
            "expected_pods": [],
            "expected_pod_index": -1,
        },
    ],
)
def test__preprocess_stats(
    mocked_client,
    test_state: dict,
):
    from azext_edge.edge.providers.stats import _preprocess_stats

    pod_list = V1PodList(items=test_state["expected_pods"])
    mocked_client.CoreV1Api().list_namespaced_pod.return_value = pod_list

    target_namespace = generate_random_string()
    if test_state["expected_pod_index"] == -1:
        with pytest.raises(ResourceNotFoundError):
            _preprocess_stats(namespace=target_namespace)
        return

    target_namespace, target_pod = _preprocess_stats(namespace=target_namespace)
    assert target_pod.metadata.name == test_state["expected_pods"][test_state["expected_pod_index"]].metadata.name
