# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import binascii
import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from azure.cli.core.azclierror import ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console

from ..common import AIO_BROKER_DIAGNOSTICS_SERVICE, PROTOBUF_SERVICE_API_PORT, PodState
from ..util import get_timestamp_now_utc
from .base import V1Pod, get_namespaced_pods_by_prefix, portforward_socket

logger = get_logger(__name__)

console = Console(highlight=True)

if TYPE_CHECKING:
    # pylint: disable=no-name-in-module
    from socket import socket
    from zipfile import ZipInfo

    from opentelemetry.proto.trace.v1.trace_pb2 import TracesData


def _preprocess_stats(
    namespace: Optional[str] = None, diag_service_pod_prefix: str = AIO_BROKER_DIAGNOSTICS_SERVICE
) -> Tuple[str, V1Pod]:
    if not namespace:
        from .base import DEFAULT_NAMESPACE

        namespace = DEFAULT_NAMESPACE

    target_pods = get_namespaced_pods_by_prefix(prefix=diag_service_pod_prefix, namespace=namespace)
    if not target_pods:
        raise ResourceNotFoundError(
            f"Diagnostics service pod '{diag_service_pod_prefix}' does not exist in namespace '{namespace}'."
        )
    for pod in target_pods:
        if pod.status.phase.lower() == PodState.running.value:
            return namespace, pod

    raise ResourceNotFoundError(
        f"No diagnostics service pod '{diag_service_pod_prefix}' in phase "
        f"'{PodState.running.value}' detected in namespace '{namespace}'."
    )


def get_traces(
    namespace: Optional[str] = None,
    diag_service_pod_prefix: str = AIO_BROKER_DIAGNOSTICS_SERVICE,
    pod_protobuf_port: int = PROTOBUF_SERVICE_API_PORT,
    trace_ids: Optional[List[str]] = None,
    trace_dir: Optional[str] = None,
) -> Union[List["TracesData"], List[Tuple["ZipInfo", str]], None]:
    """
    trace_ids: List[str] hex representation of trace Ids.
    """
    if not any([trace_ids, trace_dir]):
        raise ValueError("At least trace_ids or trace_dir is required.")

    from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

    from google.protobuf.json_format import MessageToDict
    from rich.progress import MofNCompleteColumn, Progress

    from ..util import normalize_dir

    # pylint: disable=no-name-in-module
    from .proto.diagnostics_service_pb2 import Request, Response, TraceRetrievalInfo

    namespace, diagnostic_pod = _preprocess_stats(namespace=namespace, diag_service_pod_prefix=diag_service_pod_prefix)

    for_support_bundle = False
    trace_ids = trace_ids or []

    if trace_ids:
        if trace_ids[0] == "!support_bundle!":
            trace_ids.pop()
            for_support_bundle = True
        trace_ids = [binascii.unhexlify(t) for t in trace_ids]

    with Progress(
        *Progress.get_default_columns(),
        MofNCompleteColumn(),
        transient=False,
        disable=bool(trace_ids) or for_support_bundle,
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
                    f"broker_traces_{get_timestamp_now_utc(format='%Y%m%dT%H%M%S')}.zip"
                )
                # pylint: disable=consider-using-with
                myzip = ZipFile(file=str(normalized_dir_path), mode="w", compression=ZIP_DEFLATED)

            progress_set = False
            progress_task = None
            total_trace_count = 0
            current_trace_count = 0
            try:
                while True:
                    if current_trace_count and current_trace_count >= total_trace_count:
                        break
                    rbytes = _fetch_bytes(socket, 4)
                    response_size = int.from_bytes(rbytes, byteorder="big")
                    response_bytes = _fetch_bytes(socket, response_size)

                    if response_bytes == b"":
                        logger.warning("TCP socket closed. Trace processing aborted.")
                        return

                    response = Response.FromString(response_bytes)
                    current_trace_count = current_trace_count + 1

                    if not total_trace_count:
                        total_trace_count = response.retrieved_trace.total_trace_count
                        if total_trace_count == 0:
                            logger.warning("No traces to fetch. Processing aborted.")
                            break

                    if not progress.disable and not progress_set:
                        progress_task = progress.add_task(
                            "[deep_sky_blue4]Gathering traces...", total=response.retrieved_trace.total_trace_count
                        )
                        progress_set = True

                    msg_dict = MessageToDict(message=response.retrieved_trace.trace, use_integers_for_enums=True)
                    root_span, resource_name, timestamp = _determine_root_span(message_dict=msg_dict)

                    if progress_set:
                        progress.update(progress_task, advance=1)
                    if not all([root_span, resource_name, timestamp]):
                        logger.debug("Could not process root span. Skipping trace.")
                        continue

                    span_trace_id = root_span["traceId"]
                    span_name = root_span["name"]

                    if trace_ids:
                        traces.append(msg_dict)
                    if trace_dir or for_support_bundle:
                        archive = f"{resource_name}.{span_name}.{span_trace_id}"
                        pb_suffix = ".otlp.pb"
                        tempo_suffix = ".tempo.json"

                        datetime_tuple = tuple(timestamp.timetuple())
                        zinfo_pb = ZipInfo(filename=f"{archive}{pb_suffix}", date_time=datetime_tuple)
                        # Fixed in Py 3.9 https://github.com/python/cpython/issues/70373
                        zinfo_pb.file_size = 0
                        zinfo_pb.compress_size = 0

                        zinfo_tempo = ZipInfo(filename=f"{archive}{tempo_suffix}", date_time=datetime_tuple)
                        zinfo_tempo.file_size = 0
                        zinfo_tempo.compress_size = 0

                        otlp_format_pair = (zinfo_pb, response.retrieved_trace.trace.SerializeToString())
                        tempo_format_pair = (
                            zinfo_tempo,
                            json.dumps(_convert_otlp_to_tempo(msg_dict), sort_keys=True),
                        )

                        if for_support_bundle:
                            traces.append(otlp_format_pair)
                            traces.append(tempo_format_pair)
                            continue

                        # Original OTLP
                        myzip.writestr(
                            zinfo_or_arcname=otlp_format_pair[0],
                            data=otlp_format_pair[1],
                        )
                        # Tempo
                        myzip.writestr(
                            zinfo_or_arcname=tempo_format_pair[0],
                            data=tempo_format_pair[1],
                        )

                if traces:
                    return traces

            finally:
                if trace_dir:
                    myzip.close()


def _determine_root_span(message_dict: dict) -> Tuple[str, str, Union[datetime, None]]:
    """
    Attempts to determine root span, and normalizes traceId, spanId and parentSpanId to hex.
    """
    import base64

    root_span = None
    resource_name = None
    timestamp = None

    for resource_span in message_dict.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                if "traceId" in span:
                    span["traceId"] = base64.b64decode(span["traceId"]).hex()
                if "spanId" in span:
                    span["spanId"] = base64.b64decode(span["spanId"]).hex()
                if "parentSpanId" in span:
                    span["parentSpanId"] = base64.b64decode(span["parentSpanId"]).hex()
                else:
                    root_span = span

                    if "startTimeUnixNano" in root_span:
                        timestamp_unix_nano = root_span["startTimeUnixNano"]
                        timestamp = datetime.utcfromtimestamp(float(timestamp_unix_nano) / 1e9)

                    # determine resource name
                    resource = resource_span.get("resource", {})
                    attributes = resource.get("attributes", [])
                    for a in attributes:
                        if a["key"] == "service.name":
                            resource_name = a["value"].get("stringValue", "unknown")

    return root_span, resource_name, timestamp


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


def _fetch_bytes(socket: "socket", size: int) -> bytes:
    result_bytes = socket.recv(size)
    if result_bytes == b"":
        return result_bytes

    result_bytes_len = len(result_bytes)
    while result_bytes_len < size:
        remaining_bytes_size = size - result_bytes_len
        interm_bytes = socket.recv(remaining_bytes_size)
        if interm_bytes == b"":
            break
        result_bytes += interm_bytes
        result_bytes_len += len(interm_bytes)

    return result_bytes
