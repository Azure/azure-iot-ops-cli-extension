# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from opentelemetry.proto.metrics.v1 import metrics_pb2 as _metrics_pb2
from opentelemetry.proto.trace.v1 import trace_pb2 as _trace_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Request(_message.Message):
    __slots__ = ["put_traces", "get_traces", "put_metrics"]
    PUT_TRACES_FIELD_NUMBER: _ClassVar[int]
    GET_TRACES_FIELD_NUMBER: _ClassVar[int]
    PUT_METRICS_FIELD_NUMBER: _ClassVar[int]
    put_traces: _trace_pb2.TracesData
    get_traces: TraceRetrievalInfo
    put_metrics: _metrics_pb2.MetricsData
    def __init__(self, put_traces: _Optional[_Union[_trace_pb2.TracesData, _Mapping]] = ..., get_traces: _Optional[_Union[TraceRetrievalInfo, _Mapping]] = ..., put_metrics: _Optional[_Union[_metrics_pb2.MetricsData, _Mapping]] = ...) -> None: ...

class Response(_message.Message):
    __slots__ = ["retrieved_trace"]
    RETRIEVED_TRACE_FIELD_NUMBER: _ClassVar[int]
    retrieved_trace: RetrievedTraceWrapper
    def __init__(self, retrieved_trace: _Optional[_Union[RetrievedTraceWrapper, _Mapping]] = ...) -> None: ...

class TraceRetrievalInfo(_message.Message):
    __slots__ = ["trace_ids"]
    TRACE_IDS_FIELD_NUMBER: _ClassVar[int]
    trace_ids: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, trace_ids: _Optional[_Iterable[bytes]] = ...) -> None: ...

class RetrievedTraceWrapper(_message.Message):
    __slots__ = ["trace", "current_trace_count", "total_trace_count"]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TRACE_COUNT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TRACE_COUNT_FIELD_NUMBER: _ClassVar[int]
    trace: _trace_pb2.TracesData
    current_trace_count: int
    total_trace_count: int
    def __init__(self, trace: _Optional[_Union[_trace_pb2.TracesData, _Mapping]] = ..., current_trace_count: _Optional[int] = ..., total_trace_count: _Optional[int] = ...) -> None: ...
