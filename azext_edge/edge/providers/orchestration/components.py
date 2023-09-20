# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


def get_observability(version: str, **kwargs):
    std = {
        "name": "observability",
        "type": "helm.v3",
        "properties": {
            "chart": {
                "repo": "alicesprings.azurecr.io/helm/opentelemetry-collector",
                "version": version,
            },
            "values": {
                "mode": "deployment",
                "fullnameOverride": "otel-collector",
                "config": {
                    "receivers": {
                        "otlp": {
                            "protocols": {
                                "grpc": {"endpoint": ":4317"},
                                "http": {"endpoint": ":4318"},
                            }
                        }
                    },
                    "exporters": {
                        "prometheus": {
                            "endpoint": ":8889",
                            "resource_to_telemetry_conversion": {"enabled": True},
                        }
                    },
                    "service": {
                        "pipelines": {
                            "metrics": {"receivers": ["otlp"], "exporters": ["prometheus"]},
                            "logs": None,
                        }
                    },
                },
                "ports": {
                    "metrics": {
                        "enabled": True,
                        "containerPort": 8889,
                        "servicePort": 8889,
                        "protocol": "TCP",
                    },
                    "jaeger-compact": {"enabled": False},
                    "jaeger-grpc": {"enabled": False},
                    "jaeger-thrift": {"enabled": False},
                    "zipkin": {"enabled": False},
                },
            },
        },
    }
    if kwargs:
        std.update(kwargs)

    return std


def get_e4in(version: str, **kwargs):
    std = {
        "name": "e4in",
        "type": "helm.v3",
        "properties": {
            "chart": {
                "repo": "alicesprings.azurecr.io/az-e4in",
                "version": version,
            }
        },
    }
    std.update(kwargs)
    return std


def get_akri(version: str, opcua_discovery_endpoint: str, kubernetes_distro: str, **kwargs):
    std = {
        "name": "akri",
        "type": "helm.v3",
        "properties": {
            "chart": {
                "repo": "alicesprings.azurecr.io/helm/microsoft-managed-akri",
                "version": version,
            },
            "values": {
                "custom": {
                    "configuration": {
                        "enabled": True,
                        "name": "akri-opcua-asset",
                        "discoveryHandlerName": "opcua-asset",
                        "discoveryDetails": opcua_discovery_endpoint,
                    },
                    "discovery": {
                        "enabled": True,
                        "name": "akri-opcua-asset-discovery",
                        "image": {
                            "repository": "e4ipreview.azurecr.io/e4i/workload/akri-opc-ua-asset-discovery",
                            "tag": "latest",
                            "pullPolicy": "Always",
                        },
                        "useNetworkConnection": True,
                        "port": 80,
                        "resources": {
                            "memoryRequest": "64Mi",
                            "cpuRequest": "10m",
                            "memoryLimit": "512Mi",
                            "cpuLimit": "1000m",
                        },
                    },
                },
                "kubernetesDistro": kubernetes_distro,
                "prometheus": {"enabled": True},
                "opentelemetry": {"enabled": True},
            },
        },
    }
    std.update(kwargs)
    return std


def get_opcua_broker(
    version: str,
    namespace: str,
    otel_collector_addr: str,
    geneva_collector_addr: str,
    simulate_plc: bool = False,
    **kwargs
):
    std = {
        "name": "opc-ua-broker",
        "type": "helm.v3",
        "properties": {
            "chart": {
                "repo": "alicesprings.azurecr.io/helm/az-e4i",
                "version": version,
            },
            "values": {
                "mqttBroker": {
                    "authenticationMethod": "serviceAccountToken",
                    "name": "azedge-dmqtt-frontend",
                    "namespace": namespace,
                },
                "opcPlcSimulation": {"deploy": simulate_plc},
                "openTelemetry": {
                    "enabled": True,
                    "endpoints": {
                        "default": {
                            "uri": otel_collector_addr,
                            "protocol": "grpc",
                            "emitLogs": False,
                            "emitMetrics": True,
                            "emitTraces": False,
                        },
                        "geneva": {
                            "uri": geneva_collector_addr,
                            "protocol": "grpc",
                            "emitLogs": False,
                            "emitMetrics": True,
                            "emitTraces": False,
                        },
                    },
                },
            },
        },
        "dependencies": [],
    }
    std.update(kwargs)
    return std
