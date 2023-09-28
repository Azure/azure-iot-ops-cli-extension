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


def get_akri_opcua_asset(opcua_discovery_endpoint: str, **kwargs):
    std = {
        "name": "akri-opcua-asset",
        "type": "yaml.k8s",
        "properties": {
            "resource": {
                "apiVersion": "akri.sh/v0",
                "kind": "Configuration",
                "metadata": {"name": "akri-opcua-asset"},
                "spec": {
                    "discoveryHandler": {
                        "name": "opcua-asset",
                        "discoveryDetails": opcua_discovery_endpoint,
                    },
                    "brokerProperties": {},
                    "capacity": 1,
                },
            }
        },
    }
    std.update(kwargs)
    return std


def get_akri_opcua_discovery_daemonset(version: str, kubernetes_distro: str, **kwargs):
    std = {
        "name": "akri-opcua-asset-discovery-daemonset",
        "type": "yaml.k8s",
        "properties": {
            "resource": {
                "apiVersion": "apps/v1",
                "kind": "DaemonSet",
                "metadata": {"name": "akri-opcua-asset-discovery-daemonset"},
                "spec": {
                    "selector": {"matchLabels": {"name": "akri-opcua-asset-discovery"}},
                    "template": {
                        "metadata": {"labels": {"name": "akri-opcua-asset-discovery"}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "akri-opcua-asset-discovery",
                                    "image": "e4ipreview.azurecr.io/e4i/workload/akri-opc-ua-asset-discovery:latest",
                                    "imagePullPolicy": "Always",
                                    "resources": {
                                        "requests": {"memory": "64Mi", "cpu": "10m"},
                                        "limits": {"memory": "512Mi", "cpu": "100m"},
                                    },
                                    "ports": [{"name": "discovery", "containerPort": 80}],
                                    "env": [
                                        {"name": "POD_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.podIP"}}},
                                        {"name": "DISCOVERY_HANDLERS_DIRECTORY", "value": "/var/lib/akri"},
                                    ],
                                    "volumeMounts": [{"name": "discovery-handlers", "mountPath": "/var/lib/akri"}],
                                }
                            ],
                            "volumes": [{"name": "discovery-handlers", "hostPath": {"path": "/var/lib/akri"}}],
                        },
                    },
                },
            }
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
