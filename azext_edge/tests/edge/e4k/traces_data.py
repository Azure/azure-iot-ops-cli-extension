# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

TEST_TRACES_DATA = {
    "resourceSpans": [
        {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "azedge-dmqtt-frontend-0"}}]},
            "scopeSpans": [
                {
                    "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                    "spans": [
                        {
                            "attributes": [
                                {
                                    "key": "TraceContext",
                                    "value": {
                                        "stringValue": '{"id":1837074107124811841,"version":0,"trace_id":13535267920117180670448992066091859656,"parent_id":null,"flags":1}'
                                    },
                                }
                            ],
                            "endTimeUnixNano": "1696990720594696699",
                            "kind": 1,
                            "name": "Puback",
                            "spanId": "197e992acd3e0841",
                            "startTimeUnixNano": "1696990720594673566",
                            "status": {},
                            "traceId": "0a2ecc3b430fdfd667d879bb7397bec8",
                        }
                    ],
                }
            ],
        },
        {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "azedge-dmqtt-frontend-0"}}]},
            "scopeSpans": [
                {
                    "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                    "spans": [
                        {
                            "attributes": [
                                {
                                    "key": "TraceContext",
                                    "value": {
                                        "stringValue": '{"id":1067404969482445031,"version":0,"trace_id":13535267920117180670448992066091859656,"parent_id":1837074107124811841,"flags":1}'
                                    },
                                }
                            ],
                            "endTimeUnixNano": "1696990720594696118",
                            "kind": 1,
                            "name": "replicate_pubacks",
                            "parentSpanId": "GX6ZKs0+CEE=",
                            "spanId": "0ed02f2a157ce0e7",
                            "startTimeUnixNano": "1696990720594686450",
                            "status": {},
                            "traceId": "0a2ecc3b430fdfd667d879bb7397bec8",
                        }
                    ],
                }
            ],
        },
        {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "azedge-dmqtt-frontend-0"}}]},
            "scopeSpans": [
                {
                    "scope": {"name": "microsoft.azure.e4k.obs-lib", "version": "0.1"},
                    "spans": [
                        {
                            "attributes": [
                                {
                                    "key": "TraceContext",
                                    "value": {
                                        "stringValue": '{"id":16911758998527404422,"version":0,"trace_id":13535267920117180670448992066091859656,"parent_id":1067404969482445031,"flags":1}'
                                    },
                                }
                            ],
                            "endTimeUnixNano": "1696990720594695466",
                            "kind": 1,
                            "name": "backend_client_replicate_pubacks",
                            "parentSpanId": "DtAvKhV84Oc=",
                            "spanId": "eab2a334f23de986",
                            "startTimeUnixNano": "1696990720594689986",
                            "status": {},
                            "traceId": "0a2ecc3b430fdfd667d879bb7397bec8",
                        }
                    ],
                }
            ],
        },
    ]
}
