# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from zipfile import ZipInfo

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1ObjectMeta, V1Pod, V1PodList, V1PodStatus

from azext_edge.edge.common import AIO_BROKER_DIAGNOSTICS_SERVICE
from azext_edge.edge.providers import base, stats
from azext_edge.edge.providers.support import mq


@pytest.fixture
def trace_cluster(mocker, mocked_client):
    mocker.patch.object(base, "client", mocked_client)
    mocker.patch.object(base, "_namespaced_pods_cache", {})
    mocker.patch.object(mq, "get_mq_namespaces", return_value=["broker-ns"])
    mocked_client.CoreV1Api().list_namespaced_pod.return_value = V1PodList(items=[])
    return mocked_client.CoreV1Api()


def test_missing_diagnostics_pod_warns_without_connecting(mocker, trace_cluster, caplog):
    portforward = mocker.patch.object(stats, "portforward_socket")

    assert not mq.fetch_diagnostic_traces()

    assert "Broker traces unavailable in namespace 'broker-ns'" in caplog.text
    assert "The diagnostics service is removed in AIO 2610 and later" in caplog.text
    assert "Unable to collect broker traces" not in caplog.text
    trace_cluster.list_namespaced_pod.assert_called_once_with("broker-ns", label_selector=None)
    portforward.assert_not_called()


@pytest.mark.parametrize("phase", ["Pending", "Failed", "Succeeded"])
def test_nonrunning_diagnostics_pod_is_not_reported_as_retired(trace_cluster, caplog, phase):
    trace_cluster.list_namespaced_pod.return_value = V1PodList(items=[
        V1Pod(
            metadata=V1ObjectMeta(name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-0"),
            status=V1PodStatus(phase=phase),
        ),
    ])

    assert not mq.fetch_diagnostic_traces()

    assert "Unable to collect broker traces in namespace 'broker-ns'" in caplog.text
    assert "in phase 'running'" in caplog.text
    assert "Broker traces unavailable" not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
def test_trace_lookup_failure_is_visible_and_not_reported_as_retirement(trace_cluster, caplog, status):
    trace_cluster.list_namespaced_pod.side_effect = ApiException(status=status, reason="lookup failed")

    assert not mq.fetch_diagnostic_traces()

    assert "Unable to collect broker traces in namespace 'broker-ns'" in caplog.text
    assert "lookup failed" in caplog.text
    assert "Broker traces unavailable" not in caplog.text


@pytest.mark.parametrize("error", [TimeoutError("connection timed out"), ConnectionError("connection refused")])
def test_trace_connection_failure_is_visible(mocker, trace_cluster, caplog, error):
    trace_cluster.list_namespaced_pod.return_value = V1PodList(items=[
        V1Pod(
            metadata=V1ObjectMeta(name=f"{AIO_BROKER_DIAGNOSTICS_SERVICE}-0"),
            status=V1PodStatus(phase="Running"),
        ),
    ])
    mocker.patch.object(stats, "portforward_socket", side_effect=error)

    assert not mq.fetch_diagnostic_traces()

    assert str(error) in caplog.text
    assert "Unable to collect broker traces" in caplog.text
    assert "Broker traces unavailable" not in caplog.text


@pytest.mark.parametrize("missing_error", [
    stats.DiagnosticsServiceNotFoundError("absent"),
    ResourceNotFoundError("no running pod"),
    ApiException(status=403, reason="forbidden"),
])
def test_other_namespaces_still_collect_legacy_traces(mocker, caplog, missing_error):
    mocker.patch.object(mq, "get_mq_namespaces", return_value=["missing-ns", "legacy-ns"])
    zip_info = ZipInfo("frontend.publish.trace.otlp.pb", date_time=(2026, 1, 1, 0, 0, 0))
    get_traces = mocker.patch.object(mq, "get_traces", side_effect=[missing_error, [(zip_info, b"trace")]])

    result = mq.fetch_diagnostic_traces()

    assert len(result) == 1
    assert result[0]["zinfo"].filename == "legacy-ns/broker/traces/frontend.publish.trace.otlp.pb"
    assert result[0]["zinfo"].date_time == zip_info.date_time
    assert result[0]["data"] == b"trace"
    assert get_traces.call_args_list == [
        mocker.call(namespace="missing-ns", trace_ids=["!support_bundle!"]),
        mocker.call(namespace="legacy-ns", trace_ids=["!support_bundle!"]),
    ]
    assert "missing-ns" in caplog.text


@pytest.mark.parametrize("include_traces", [False, None])
def test_prepare_bundle_does_not_leak_traces_or_log_age(include_traces):
    enabled = mq.prepare_bundle(include_mq_traces=True, log_age_seconds=100)
    disabled = mq.prepare_bundle(include_mq_traces=include_traces, log_age_seconds=200)

    assert enabled["traces"] is mq.fetch_diagnostic_traces
    assert "traces" not in disabled
    assert enabled["pods"].keywords["since_seconds"] == 100
    assert disabled["pods"].keywords["since_seconds"] == 200
    assert "traces" not in mq.support_runtime_elements
    assert "pods" not in mq.support_runtime_elements
    assert set(mq.support_runtime_elements) <= set(enabled)
    assert set(mq.support_runtime_elements) <= set(disabled)


@pytest.mark.parametrize("namespace", ["broker-ns", ""])
@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_pod_lookup_strict_mode_preserves_errors_without_changing_default(trace_cluster, namespace, status):
    error = ApiException(status=status, reason="lookup failed")
    trace_cluster.list_namespaced_pod.side_effect = error
    trace_cluster.list_pod_for_all_namespaces.side_effect = error

    assert base.get_namespaced_pods_by_prefix("aio-broker", namespace) == []
    with pytest.raises(ApiException) as raised:
        base.get_namespaced_pods_by_prefix("aio-broker", namespace, raise_on_error=True)
    assert raised.value is error


def test_missing_pod_has_distinct_not_found_type(trace_cluster):
    with pytest.raises(stats.DiagnosticsServiceNotFoundError):
        stats._preprocess_stats(namespace="broker-ns")


@pytest.mark.parametrize("error", [
    *(ApiException(status=status, reason="broker lookup failed") for status in [401, 403, 404, 429, 500, 503]),
    ConnectionError("broker lookup connection failed"),
    TimeoutError("broker lookup timed out"),
])
def test_namespace_discovery_failure_warns(mocker, mocked_client, caplog, error):
    mocker.patch.object(base, "client", mocked_client)
    mocked_client.CustomObjectsApi().list_cluster_custom_object.side_effect = error
    get_traces = mocker.patch.object(mq, "get_traces")

    assert not mq.fetch_diagnostic_traces()

    assert "Unable to collect broker traces: broker namespace discovery failed" in caplog.text
    assert str(error) in caplog.text
    assert "Broker traces unavailable" not in caplog.text
    get_traces.assert_not_called()


def test_namespace_discovery_uses_strict_broker_lookup(mocker, mocked_client, caplog):
    mocker.patch.object(base, "client", mocked_client)
    mocked_client.CustomObjectsApi().list_cluster_custom_object.return_value = {
        "items": [{"metadata": {"namespace": "legacy-ns"}}],
    }
    get_traces = mocker.patch.object(mq, "get_traces", return_value=None)

    assert not mq.fetch_diagnostic_traces()

    mocked_client.CustomObjectsApi().list_cluster_custom_object.assert_called_once_with(
        group=mq.MQ_ACTIVE_API.group, version=mq.MQ_ACTIVE_API.version, plural="brokers",
    )
    get_traces.assert_called_once_with(namespace="legacy-ns", trace_ids=["!support_bundle!"])
    assert not caplog.text
