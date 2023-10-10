# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import binascii
import json

from datetime import datetime
from time import sleep
from typing import List, Optional, Tuple, Union, Dict, TYPE_CHECKING

from azure.cli.core.azclierror import ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console

from ..common import AZEDGE_DIAGNOSTICS_SERVICE, METRICS_SERVICE_API_PORT, PROTOBUF_SERVICE_API_PORT
from ..util import get_timestamp_now_utc
from .base import get_namespaced_pods_by_prefix, portforward_http, portforward_socket, V1Pod

logger = get_logger(__name__)

console = Console(highlight=True)

if TYPE_CHECKING:
    # pylint: disable=no-name-in-module
    from opentelemetry.proto.trace.v1.trace_pb2 import TracesData


def _preprocess_stats(
    namespace: Optional[str] = None, diag_service_pod_prefix: str = AZEDGE_DIAGNOSTICS_SERVICE
) -> Tuple[str, V1Pod]:
    if not namespace:
        from .base import DEFAULT_NAMESPACE

        namespace = DEFAULT_NAMESPACE

    target_pods = get_namespaced_pods_by_prefix(prefix=diag_service_pod_prefix, namespace=namespace)
    if not target_pods:
        raise ResourceNotFoundError(
            f"Diagnostics service pod '{diag_service_pod_prefix}' does not exist in namespace '{namespace}'."
        )
    diagnostic_pod = target_pods[0]

    return namespace, diagnostic_pod


def get_stats(
    namespace: Optional[str] = None,
    diag_service_pod_prefix: str = AZEDGE_DIAGNOSTICS_SERVICE,
    pod_metrics_port: int = METRICS_SERVICE_API_PORT,
    raw_response=False,
    raw_response_print=False,
    refresh_in_seconds: int = 10,
    watch: bool = False,
) -> Union[Dict[str, dict], str, None]:
    namespace, diagnostic_pod = _preprocess_stats(namespace=namespace, diag_service_pod_prefix=diag_service_pod_prefix)

    from rich import box
    from rich.live import Live
    from rich.table import Table

    table = Table(box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Stat")
    table.add_column("Value")
    table.add_column("Description")

    with portforward_http(
        namespace=namespace,
        pod_name=diagnostic_pod.metadata.name,
        pod_port=pod_metrics_port,
    ) as pf:
        try:
            raw_metrics = pf.get("/metrics")
            if raw_response:
                return raw_metrics
            elif raw_response_print:
                console.print(raw_metrics)
                return
            stats = dict(sorted(_clean_stats(raw_metrics).items()))
            if not watch:
                return stats
            logger.warning(f"Refreshing every {refresh_in_seconds} seconds. Use ctrl-c to terminate stats watch.\n")
            with Live(table, refresh_per_second=4, auto_refresh=False) as live:
                while True:
                    stats = dict(sorted(_clean_stats(raw_metrics).items()))
                    table = Table(
                        box=box.ROUNDED,
                        caption=f"Last refresh {datetime.now().isoformat()}",
                        highlight=True,
                        expand=False,
                        min_width=100,
                    )
                    table.add_column("Stat")
                    table.add_column("Value", min_width=10)
                    table.add_column("Description")
                    for s in stats:
                        table.add_row(
                            stats[s]["displayName"],
                            "[green]Pass[/green]"
                            if str(stats[s]["value"]) == "Pass"
                            else "[red]Fail[/red]"
                            if str(stats[s]["value"]) == "Fail"
                            else str(stats[s]["value"]),
                            stats[s]["description"],
                        )
                    live.update(table)
                    live.refresh()
                    sleep(refresh_in_seconds)
                    raw_metrics = pf.get("/metrics")
        except KeyboardInterrupt:
            return
        except Exception as e:
            if str(e).startswith("HTTPConnectionPool"):
                return
            logger.warning(f"Failure in stats processing\n\n{str(e)}")


def _clean_stats(raw_stats: str) -> dict:
    from ..common import E4kDiagnosticPropertyIndex as keys

    def _get_pass_fail(value: float) -> str:
        if value >= 1.0:
            return "Pass"
        else:
            return "Fail"

    result = {}
    test = raw_stats.split("\n")
    for line in test:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        key = None
        value = None
        if "{" in line:
            t = line.split("{")
            key = t[0]
            if len(t) > 1:
                value = line.split("}")[-1]
                value = float(value.strip())
        else:
            t = line.split(" ")
            key = t[0]
            value = float(t[1].strip())

        if key not in result:
            result[key] = value
        else:
            if key == keys.publishes_received_per_second.value or key == keys.publishes_sent_per_second.value:
                result[key] = result[key] + value
            elif key == keys.publish_route_replication_correctness.value:
                result[key] = result[key] * value
            else:
                result[key] = value
    if result:
        normalized = {}
        if keys.publish_route_replication_correctness.value in result:
            normalized["publish_route_replication_correctness"] = {
                "displayName": "Replication Correctness",
                "description": "Replication correctness.",
                "value": _get_pass_fail(result[keys.publish_route_replication_correctness.value]),
            }
        if keys.publish_latency_mu_ms.value in result:
            normalized["publish_latency_mu_ms"] = {
                "displayName": "P99 Average",
                "description": "Average 99th percentile of publish message latency (ms).",
                "value": round(result[keys.publish_latency_mu_ms.value], 5),
            }
        if keys.publish_latency_sigma_ms.value in result:
            normalized["publish_latency_sigma_ms"] = {
                "displayName": "P99 Standard Deviation",
                "description": "Standard deviation of the 99th percentile publish message latency (ms).",
                "value": round(result[keys.publish_latency_sigma_ms.value], 5),
            }
        if keys.publishes_received_per_second.value in result:
            normalized["publishes_received_per_second"] = {
                "displayName": "Inbound Message Rate",
                "description": "Rate of inbound messages per second.",
                "value": round(result[keys.publishes_received_per_second.value], 5),
            }
        if keys.publishes_sent_per_second.value in result:
            normalized["publishes_sent_per_second"] = {
                "displayName": "Outbound Message Rate",
                "description": "Rate of outgoing messages per second.",
                "value": round(result[keys.publishes_sent_per_second.value], 5),
            }
        if keys.connected_sessions.value in result:
            normalized["connected_sessions"] = {
                "displayName": "Connected Sessions",
                "description": "Total number of connected sessions.",
                "value": result[keys.connected_sessions.value],
            }
        if keys.total_subscriptions.value in result:
            normalized["total_subscriptions"] = {
                "displayName": "Total Subscriptions",
                "description": "Total number of topic subscriptions.",
                "value": result[keys.total_subscriptions.value],
            }
        return normalized

    return result


def get_traces(
    namespace: Optional[str] = None,
    diag_service_pod_prefix: str = AZEDGE_DIAGNOSTICS_SERVICE,
    pod_protobuf_port: int = PROTOBUF_SERVICE_API_PORT,
    trace_ids: Optional[List[str]] = None,
    trace_dir: Optional[str] = None,
) -> Union[List["TracesData"], None]:
    """
    trace_ids: List[str] hex representation of trace Ids.
    """
    if not any([trace_ids, trace_dir]):
        raise ValueError("At least trace_ids or trace_dir is required.")

    from zipfile import ZIP_DEFLATED, ZipFile

    from google.protobuf.json_format import MessageToDict
    from rich.progress import MofNCompleteColumn, Progress

    # pylint: disable=no-name-in-module
    from .proto.diagnostics_service_pb2 import Request, Response, TraceRetrievalInfo
    from .support.base import normalize_dir

    namespace, diagnostic_pod = _preprocess_stats(namespace=namespace, diag_service_pod_prefix=diag_service_pod_prefix)

    if not trace_ids:
        trace_ids = []
    else:
        trace_ids = [binascii.unhexlify(t) for t in trace_ids]

    with Progress(
        *Progress.get_default_columns(), MofNCompleteColumn(), transient=False, disable=bool(trace_ids)
    ) as progress:
        with portforward_socket(
            namespace=namespace, pod_name=diagnostic_pod.metadata.name, pod_port=pod_protobuf_port
        ) as socket:
            request = Request(get_traces=TraceRetrievalInfo(trace_ids=trace_ids))
            serialized_request = request.SerializeToString()
            request_len_b = len(serialized_request).to_bytes(4, byteorder="big")

            socket.sendall(request_len_b)
            socket.sendall(serialized_request)

            traces: List[dict] = []
            if trace_dir:
                normalized_dir_path = normalize_dir(dir_path=trace_dir)
                normalized_dir_path = normalized_dir_path.joinpath(
                    f"e4k_traces_{get_timestamp_now_utc(format='%Y%m%dT%H%M%S')}.zip"
                )
                # pylint: disable=consider-using-with
                myzip = ZipFile(file=str(normalized_dir_path), mode="w", compression=ZIP_DEFLATED)

            progress_set = False
            progress_task = None
            try:
                while True:
                    rbytes = socket.recv(4)
                    response_size = int.from_bytes(rbytes, byteorder="big")
                    response_bytes = socket.recv(response_size)
                    if response_bytes == b"":
                        logger.warning("TCP socket closed. Processing aborted.")
                        return
                    response = Response.FromString(response_bytes)

                    if not progress.disable and not progress_set:
                        progress_task = progress.add_task(
                            "[deep_sky_blue4]Gathering traces...", total=response.retrieved_trace.total_trace_count
                        )
                        progress_set = True

                    msg_dict = MessageToDict(message=response.retrieved_trace.trace, use_integers_for_enums=True)
                    root_span, resource_name = _determine_root_span(message_dict=msg_dict)

                    if progress_set:
                        progress.update(progress_task, advance=1)
                    if not root_span:
                        logger.warning("Could not determine root span. Skipping trace.")
                        continue

                    span_trace_id = root_span["traceId"]
                    span_name = root_span["name"]

                    if trace_ids:
                        traces.append(msg_dict)
                    if trace_dir:
                        archive = f"{resource_name}.{span_name}.{span_trace_id}"
                        pb_suffix = ".otlp.pb"
                        tempo_suffix = ".tempo.json"

                        # Original OLTP
                        myzip.writestr(
                            zinfo_or_arcname=f"{archive}{pb_suffix}",
                            data=response.retrieved_trace.trace.SerializeToString(),
                        )
                        # Tempo
                        myzip.writestr(
                            zinfo_or_arcname=f"{archive}{tempo_suffix}",
                            data=json.dumps(_convert_otlp_to_tempo(msg_dict), sort_keys=True),
                        )

                    if response.retrieved_trace.current_trace_count == response.retrieved_trace.total_trace_count:
                        break

                if trace_ids:
                    return traces

            finally:
                if trace_dir:
                    myzip.close()


def _determine_root_span(message_dict: dict) -> Tuple[str, str]:
    """
    Attempts to determine root span, and normalizes traceId and spaceId to hex.
    """
    import base64

    root_span = None
    resource_name = None

    for resource_span in message_dict.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                span["traceId"] = base64.b64decode(span["traceId"]).hex()
                span["spanId"] = base64.b64decode(span["spanId"]).hex()
                if not span.get("parentSpanId"):
                    root_span = span
                    # determine resource name
                    resource = resource_span["resource"]
                    attributes = resource["attributes"]
                    for a in attributes:
                        if a["key"] == "service.name":
                            resource_name = a["value"].get("stringValue", "unknown")

    return root_span, resource_name


def _convert_otlp_to_tempo(message_dict: dict) -> dict:
    """
    Convert OTLP payload to Grafana Tempo.
    """
    from copy import deepcopy

    new_dict = deepcopy(message_dict)

    new_dict["batches"] = new_dict.pop("resourceSpans")
    for batch in new_dict.get("batches", []):
        batch["instrumentationLibrarySpans"] = batch.pop("scopeSpans", [])
        for inst_lib_span in batch.get("instrumentationLibrarySpans", []):
            inst_lib_span["instrumentationLibrary"] = inst_lib_span.pop("scope", {})

    return new_dict
