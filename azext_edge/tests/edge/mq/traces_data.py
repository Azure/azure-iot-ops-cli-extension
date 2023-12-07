# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
# flake8: noqa

from typing import NamedTuple
from datetime import datetime


class TestTraceData(NamedTuple):
    data: dict
    root_span: dict
    resource_name: str
    timestamp: datetime


TEST_TRACE_PARTIAL = TestTraceData(
    data={
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "wmjcIjQ/3BA=",
                                "parentSpanId": "IL5uvxCNGaU=",
                                "name": "receive publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984146892",
                                "endTimeUnixNano": "1701380840984183921",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":14008688680399526928,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":2359445021684210085,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
        ]
    },
    root_span=None,
    resource_name=None,
    timestamp=None,
)

TEST_TRACE = TestTraceData(
    data={
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "wmjcIjQ/3BA=",
                                "parentSpanId": "IL5uvxCNGaU=",
                                "name": "receive publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984146892",
                                "endTimeUnixNano": "1701380840984183921",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":14008688680399526928,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":2359445021684210085,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "+1vSYvmUlOs=",
                                "parentSpanId": "wmjcIjQ/3BA=",
                                "name": "dmqtt_event",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984161730",
                                "endTimeUnixNano": "1701380840984183290",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":18112301648936473835,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":14008688680399526928,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "Utzd/U9gz2c=",
                                "parentSpanId": "+1vSYvmUlOs=",
                                "name": "check_backpressure",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984171778",
                                "endTimeUnixNano": "1701380840984175185",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":5970891286014644071,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":18112301648936473835,"flags":1}'
                                        },
                                    },
                                    {"key": "current_read_buffer_pool_usage", "value": {"stringValue": "0"}},
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "Fhj9sg2MbOI=",
                                "parentSpanId": "5iWJpurliIc=",
                                "name": "Publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982763916",
                                "endTimeUnixNano": "1701380840982812196",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":1592301409448783074,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":16583812552860207239,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "PvLJ69d6aKY=",
                                "parentSpanId": "Fhj9sg2MbOI=",
                                "name": "replicate_packet_frontend",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982772682",
                                "endTimeUnixNano": "1701380840982811514",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":4535909789485131942,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":1592301409448783074,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "yrXqTFMQuJ0=",
                                "parentSpanId": "PvLJ69d6aKY=",
                                "name": "get_pub_authz_context",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982778883",
                                "endTimeUnixNano": "1701380840982783071",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":14606838579978090653,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":4535909789485131942,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "FhQSUYg5GrI=",
                                "parentSpanId": "PvLJ69d6aKY=",
                                "name": "replicate_packet_backend",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982789453",
                                "endTimeUnixNano": "1701380840982810553",
                                "attributes": [
                                    {"key": "cell_map_version", "value": {"stringValue": "3"}},
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":1590916709755722418,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":4535909789485131942,"flags":1}'
                                        },
                                    },
                                    {"key": "pod_id", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}},
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "w4unhlsKgjg=",
                                "parentSpanId": "FhQSUYg5GrI=",
                                "name": "encapsulate",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982796006",
                                "endTimeUnixNano": "1701380840982805583",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":14090540054653600312,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":1590916709755722418,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "/GMPFZn5oVs=",
                                "parentSpanId": "Fhj9sg2MbOI=",
                                "name": "replicate_pubacks",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982822244",
                                "endTimeUnixNano": "1701380840982832594",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":18186396305704198491,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":1592301409448783074,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-frontend-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "CGMHOgMhvl0=",
                                "parentSpanId": "/GMPFZn5oVs=",
                                "name": "backend_client_replicate_pubacks",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840982827664",
                                "endTimeUnixNano": "1701380840982831562",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":604334720739819101,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":18186396305704198491,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "FvXRIof6j1w=",
                                "parentSpanId": "w4unhlsKgjg=",
                                "name": "receive publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983250304",
                                "endTimeUnixNano": "1701380840983325865",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":1654458384368963420,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":14090540054653600312,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "2VTCMm2FuRI=",
                                "parentSpanId": "FvXRIof6j1w=",
                                "name": "dmqtt_event",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983261605",
                                "endTimeUnixNano": "1701380840983292252",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":15660355326115690770,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":1654458384368963420,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "NkMIytOlem4=",
                                "parentSpanId": "2VTCMm2FuRI=",
                                "name": "check_backpressure",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983274079",
                                "endTimeUnixNano": "1701380840983277244",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":3909978568714975854,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":15660355326115690770,"flags":1}'
                                        },
                                    },
                                    {"key": "current_read_buffer_pool_usage", "value": {"stringValue": "0"}},
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "/gmFFwGKzls=",
                                "parentSpanId": "2VTCMm2FuRI=",
                                "name": "replicate",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983394713",
                                "endTimeUnixNano": "1701380840983439567",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":18305308494280707675,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":15660355326115690770,"flags":1}'
                                        },
                                    },
                                    {"key": "cell_map_version", "value": {"stringValue": "3"}},
                                    {
                                        "key": "cell_map",
                                        "value": {
                                            "stringValue": "ReplicaCellMap { id: aio-mq-dmqtt-backend-2-0:1, position: Some(Backend((3, 0, Replica))), cell_map: CellMap { backends: [Chain { id: 0, replicas: [ReplicaInfo { state: Ready, role:Replica, address: aio-mq-dmqtt-backend-1-0.aio-mq-dmqtt-backend.azure-iot"
                                        },
                                    },
                                    {"key": "pod_id", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0:1"}},
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "NqXpeoeUKpQ=",
                                "parentSpanId": "/gmFFwGKzls=",
                                "name": "publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983411454",
                                "endTimeUnixNano": "1701380840983438866",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":3937810161675283092,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":18305308494280707675,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "FSdex4kRNVY=",
                                "parentSpanId": "NqXpeoeUKpQ=",
                                "name": "prepare_patch",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983416514",
                                "endTimeUnixNano": "1701380840983419289",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":1524291209979311446,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":3937810161675283092,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "IL5uvxCNGaU=",
                                "parentSpanId": "NqXpeoeUKpQ=",
                                "name": "route_to_next_node",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840983424479",
                                "endTimeUnixNano": "1701380840983431722",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":2359445021684210085,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":3937810161675283092,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "Dld+PWiaXTk=",
                                "parentSpanId": "+1vSYvmUlOs=",
                                "name": "replicate",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984321377",
                                "endTimeUnixNano": "1701380840984477448",
                                "attributes": [
                                    {"key": "cell_map_version", "value": {"stringValue": "3"}},
                                    {"key": "pod_id", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1:1"}},
                                    {
                                        "key": "cell_map",
                                        "value": {
                                            "stringValue": "ReplicaCellMap { id: aio-mq-dmqtt-backend-2-1:1, position: Some(Backend((3, 1, Tail))), cell_map: CellMap { backends: [Chain { id: 0, replicas: [ReplicaInfo{ state: Ready, role: Replica, address: aio-mq-dmqtt-backend-1-0.aio-mq-dmqtt-backend.azure-iot-op"
                                        },
                                    },
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":1033433441717869881,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":18112301648936473835,"flags":1}'
                                        },
                                    },
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "xWcJz97/+w8=",
                                "parentSpanId": "Dld+PWiaXTk=",
                                "name": "publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984340643",
                                "endTimeUnixNano": "1701380840984476105",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":14224348736477199119,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":1033433441717869881,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "R82DXgmwKiA=",
                                "parentSpanId": "xWcJz97/+w8=",
                                "name": "prepare_patch",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984345232",
                                "endTimeUnixNano": "1701380840984347456",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":5173935986831272480,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":14224348736477199119,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "4lTad9Ucmv4=",
                                "parentSpanId": "xWcJz97/+w8=",
                                "name": "commit_patch",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984351253",
                                "endTimeUnixNano": "1701380840984396056",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":16308900358826793726,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":14224348736477199119,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "pnC72SUNHoA=",
                                "parentSpanId": "4lTad9Ucmv4=",
                                "name": "commit_patch",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984370048",
                                "endTimeUnixNano": "1701380840984389274",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":11993292348991544960,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":16308900358826793726,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "3NqQJo3KqR8=",
                                "parentSpanId": "xWcJz97/+w8=",
                                "name": "publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984401196",
                                "endTimeUnixNano": "1701380840984468842",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":15914190728529094943,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":14224348736477199119,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "59mpT6FYeMk=",
                                "parentSpanId": "3NqQJo3KqR8=",
                                "name": "dispatch_batched_publishes",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984405894",
                                "endTimeUnixNano": "1701380840984443354",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":16706570452182005961,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":15914190728529094943,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "YT7Lh9HMvAE=",
                                "parentSpanId": "3NqQJo3KqR8=",
                                "name": "dispatch_publishes",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984448544",
                                "endTimeUnixNano": "1701380840984451169",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":7007261854435949569,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":15914190728529094943,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-dmqtt-backend-2-1"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "/MbwPBtopo8=",
                                "parentSpanId": "3NqQJo3KqR8=",
                                "name": "respond_and_ack",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840984461388",
                                "endTimeUnixNano": "1701380840984468110",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":18214509883895096975,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":15914190728529094943,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "aio-mq-diagnostics-probe-0"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "hHlpZk1eYWrpVvxqqq5lYA==",
                                "spanId": "5iWJpurliIc=",
                                "name": "publish",
                                "kind": 1,
                                "startTimeUnixNano": "1701380840937645506",
                                "endTimeUnixNano": "1701380840937646378",
                                "attributes": [
                                    {
                                        "key": "TraceContext",
                                        "value": {
                                            "stringValue": '{"id":16583812552860207239,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":null,"flags":1}'
                                        },
                                    }
                                ],
                                "status": {},
                            }
                        ],
                    }
                ],
            },
        ]
    },
    root_span={
        "traceId": "847969664d5e616ae956fc6aaaae6560",
        "spanId": "e62589a6eae58887",
        "name": "publish",
        "kind": 1,
        "startTimeUnixNano": "1701380840937645506",
        "endTimeUnixNano": "1701380840937646378",
        "attributes": [
            {
                "key": "TraceContext",
                "value": {
                    "stringValue": '{"id":16583812552860207239,"version":0,"trace_id":176088501121717014071716630412632417632,"parent_id":null,"flags":1}'
                },
            }
        ],
        "status": {},
    },
    resource_name="aio-mq-diagnostics-probe-0",
    timestamp=datetime(2023, 11, 30, 21, 47, 20, 937646),
)
