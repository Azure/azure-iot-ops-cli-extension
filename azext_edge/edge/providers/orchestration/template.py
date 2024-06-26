# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from typing import NamedTuple, Optional

from ...util import read_file_content


class TemplateVer(NamedTuple):
    commit_id: str
    content: dict
    moniker: str

    def get_component_vers(self, include_dp: bool = False) -> dict:
        # Don't need a deep copy here.
        component_copy = self.content["variables"]["VERSIONS"].copy()
        if not include_dp:
            del component_copy["processor"]

        return component_copy

    @property
    def parameters(self) -> dict:
        return self.content["parameters"]


V1_TEMPLATE = TemplateVer(
    commit_id="6a6ce36417fce836dcc9b5b2bc525dcf92534b41",
    moniker="v0.5.1-preview",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.27.1.19265", "templateHash": "16616801464074805120"},
            "description": "This template deploys Azure IoT Operations.",
        },
        "parameters": {
            "clusterName": {"type": "string"},
            "clusterLocation": {"type": "string", "defaultValue": "[parameters('location')]"},
            "location": {"type": "string", "defaultValue": "[resourceGroup().location]"},
            "customLocationName": {"type": "string", "defaultValue": "[format('{0}-cl', parameters('clusterName'))]"},
            "simulatePLC": {"type": "bool", "defaultValue": False},
            "opcuaDiscoveryEndpoint": {"type": "string", "defaultValue": "opc.tcp://<NOT_SET>:<NOT_SET>"},
            "targetName": {
                "type": "string",
                "defaultValue": "[format('{0}-target', toLower(parameters('clusterName')))]",
            },
            "dataProcessorInstanceName": {
                "type": "string",
                "defaultValue": "[format('{0}-processor', toLower(parameters('clusterName')))]",
            },
            "mqInstanceName": {"type": "string", "defaultValue": "mq-instance"},
            "mqFrontendServer": {"type": "string", "defaultValue": "mq-dmqtt-frontend"},
            "mqListenerName": {"type": "string", "defaultValue": "listener"},
            "mqBrokerName": {"type": "string", "defaultValue": "broker"},
            "mqAuthnName": {"type": "string", "defaultValue": "authn"},
            "mqFrontendReplicas": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqFrontendWorkers": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqBackendRedundancyFactor": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqBackendWorkers": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqBackendPartitions": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqMode": {"type": "string", "defaultValue": "distributed", "allowedValues": ["auto", "distributed"]},
            "mqMemoryProfile": {
                "type": "string",
                "defaultValue": "medium",
                "allowedValues": ["tiny", "low", "medium", "high"],
            },
            "mqServiceType": {
                "type": "string",
                "defaultValue": "clusterIp",
                "allowedValues": ["clusterIp", "loadBalancer", "nodePort"],
            },
            "deployDataProcessor": {"type": "bool", "defaultValue": False},
            "deployLayeredNetworking": {"type": "bool", "defaultValue": True},
            "dataProcessorSecrets": {
                "type": "object",
                "defaultValue": {
                    "secretProviderClassName": "aio-default-spc",
                    "servicePrincipalSecretRef": "aio-akv-sp",
                },
            },
            "mqSecrets": {
                "type": "object",
                "defaultValue": {
                    "enabled": True,
                    "secretProviderClassName": "aio-default-spc",
                    "servicePrincipalSecretRef": "aio-akv-sp",
                },
            },
            "opcUaBrokerSecrets": {
                "type": "object",
                "defaultValue": {"kind": "csi", "csiServicePrincipalSecretRef": "aio-akv-sp"},
            },
            "kubernetesDistro": {"type": "string", "defaultValue": "k8s", "allowedValues": ["k3s", "k8s", "microk8s"]},
            "containerRuntimeSocket": {"type": "string", "defaultValue": ""},
            "deployResourceSyncRules": {"type": "bool", "defaultValue": True},
        },
        "variables": {
            "akri": {
                "opcUaDiscoveryDetails": '[format(\'opcuaDiscoveryMethod:\n  - asset:\n      endpointUrl: "{0}"\n      useSecurity: false\n      autoAcceptUntrustedCertificates: true\n      userName: "user1"\n      password: "password"  \n\', parameters(\'opcuaDiscoveryEndpoint\'))]'
            },
            "AIO_CLUSTER_RELEASE_NAMESPACE": "azure-iot-operations",
            "AIO_EXTENSION_SCOPE": {"cluster": {"releaseNamespace": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]"}},
            "AIO_EXTENSION_SUFFIX": "[take(uniqueString(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))), 5)]",
            "AIO_TRUST_CONFIG_MAP": "aio-ca-trust-bundle-test-only",
            "AIO_TRUST_ISSUER": "aio-ca-issuer",
            "AIO_TRUST_CONFIG_MAP_KEY": "ca.crt",
            "AIO_TRUST_SECRET_NAME": "aio-ca-key-pair-test-only",
            "OBSERVABILITY": {
                "genevaCollectorAddressNoProtocol": "[format('geneva-metrics-service.{0}.svc.cluster.local:4317', variables('AIO_CLUSTER_RELEASE_NAMESPACE'))]",
                "otelCollectorAddressNoProtocol": "[format('aio-otel-collector.{0}.svc.cluster.local:4317', variables('AIO_CLUSTER_RELEASE_NAMESPACE'))]",
                "otelCollectorAddress": "[format('http://aio-otel-collector.{0}.svc.cluster.local:4317', variables('AIO_CLUSTER_RELEASE_NAMESPACE'))]",
                "genevaCollectorAddress": "[format('http://geneva-metrics-service.{0}.svc.cluster.local:4317', variables('AIO_CLUSTER_RELEASE_NAMESPACE'))]",
            },
            "MQ_PROPERTIES": {
                "domain": "[format('aio-mq-dmqtt-frontend.{0}', variables('AIO_CLUSTER_RELEASE_NAMESPACE'))]",
                "port": 8883,
                "localUrl": "[format('mqtts://aio-mq-dmqtt-frontend.{0}:8883', variables('AIO_CLUSTER_RELEASE_NAMESPACE'))]",
                "name": "aio-mq-dmqtt-frontend",
                "satAudience": "aio-mq",
                "mqInstanceName": "[parameters('mqInstanceName')]",
                "mqBrokerName": "[parameters('mqBrokerName')]",
                "mqListenerName": "[parameters('mqListenerName')]",
                "mqAuthnName": "[parameters('mqAuthnName')]",
                "mqFrontendServer": "[parameters('mqFrontendServer')]",
                "mqFrontendReplicas": "[parameters('mqFrontendReplicas')]",
                "mqFrontendWorkers": "[parameters('mqFrontendWorkers')]",
                "mqBackendRedundancyFactor": "[parameters('mqBackendRedundancyFactor')]",
                "mqBackendWorkers": "[parameters('mqBackendWorkers')]",
                "mqBackendPartitions": "[parameters('mqBackendPartitions')]",
                "mqMode": "[parameters('mqMode')]",
                "mqMemoryProfile": "[parameters('mqMemoryProfile')]",
                "mqServiceType": "[parameters('mqServiceType')]",
            },
            "DEFAULT_CONTAINER_REGISTRY": "mcr.microsoft.com/azureiotoperations",
            "CONTAINER_REGISTRY_DOMAINS": {
                "mq": "[variables('DEFAULT_CONTAINER_REGISTRY')]",
                "opcUaBroker": "[variables('DEFAULT_CONTAINER_REGISTRY')]",
            },
            "VERSIONS": {
                "mq": "0.4.0-preview",
                "observability": "0.1.0-preview",
                "aio": "0.5.1-preview",
                "layeredNetworking": "0.1.0-preview",
                "processor": "0.2.1-preview",
                "opcUaBroker": "0.4.0-preview",
                "adr": "0.1.0-preview",
                "akri": "0.3.0-preview",
            },
            "TRAINS": {
                "mq": "preview",
                "aio": "preview",
                "processor": "preview",
                "adr": "preview",
                "akri": "preview",
                "layeredNetworking": "preview",
                "opcUaBroker": "preview",
            },
            "broker_fe_issuer_configuration": {
                "name": "mq-fe-issuer-configuration",
                "type": "yaml.k8s",
                "properties": {
                    "resource": {
                        "apiVersion": "cert-manager.io/v1",
                        "kind": "Issuer",
                        "metadata": {"name": "[parameters('mqFrontendServer')]"},
                        "spec": {"ca": {"secretName": "[variables('AIO_TRUST_SECRET_NAME')]"}},
                    }
                },
            },
            "observability_helmChart": {
                "name": "aio-observability",
                "type": "helm.v3",
                "properties": {
                    "chart": {
                        "repo": "mcr.microsoft.com/azureiotoperations/helm/aio-opentelemetry-collector",
                        "version": "[variables('VERSIONS').observability]",
                    },
                    "values": {
                        "mode": "deployment",
                        "fullnameOverride": "aio-otel-collector",
                        "config": {
                            "processors": {
                                "memory_limiter": {
                                    "limit_percentage": 80,
                                    "spike_limit_percentage": 10,
                                    "check_interval": "60s",
                                }
                            },
                            "receivers": {
                                "jaeger": None,
                                "prometheus": None,
                                "zipkin": None,
                                "otlp": {"protocols": {"grpc": {"endpoint": ":4317"}, "http": {"endpoint": ":4318"}}},
                            },
                            "exporters": {
                                "prometheus": {
                                    "endpoint": ":8889",
                                    "resource_to_telemetry_conversion": {"enabled": True},
                                }
                            },
                            "service": {
                                "extensions": ["health_check"],
                                "pipelines": {
                                    "metrics": {"receivers": ["otlp"], "exporters": ["prometheus"]},
                                    "logs": None,
                                    "traces": None,
                                },
                                "telemetry": None,
                            },
                            "extensions": {"memory_ballast": {"size_mib": 0}},
                        },
                        "resources": {"limits": {"cpu": "100m", "memory": "512Mi"}},
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
            },
            "akri_daemonset": {
                "name": "aio-opc-asset-discovery",
                "type": "yaml.k8s",
                "properties": {
                    "resource": {
                        "apiVersion": "apps/v1",
                        "kind": "DaemonSet",
                        "metadata": {
                            "name": "aio-opc-asset-discovery",
                            "labels": {"app.kubernetes.io/part-of": "aio"},
                        },
                        "spec": {
                            "selector": {"matchLabels": {"name": "aio-opc-asset-discovery"}},
                            "template": {
                                "metadata": {
                                    "labels": {"name": "aio-opc-asset-discovery", "app.kubernetes.io/part-of": "aio"}
                                },
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "aio-opc-asset-discovery",
                                            "image": "[format('{0}/opcuabroker/discovery-handler:{1}', variables('CONTAINER_REGISTRY_DOMAINS').opcUaBroker, variables('VERSIONS').opcUaBroker)]",
                                            "imagePullPolicy": "Always",
                                            "resources": {
                                                "requests": {"memory": "64Mi", "cpu": "10m"},
                                                "limits": {"memory": "300Mi", "cpu": "100m"},
                                            },
                                            "ports": [{"name": "discovery", "containerPort": 80}],
                                            "env": [
                                                {"name": "DISCOVERY_HANDLERS_DIRECTORY", "value": "/var/lib/akri"},
                                                {"name": "AKRI_AGENT_REGISTRATION", "value": "true"},
                                            ],
                                            "volumeMounts": [
                                                {"name": "discovery-handlers", "mountPath": "/var/lib/akri"}
                                            ],
                                        }
                                    ],
                                    "volumes": [{"name": "discovery-handlers", "hostPath": {"path": "/var/lib/akri"}}],
                                },
                            },
                        },
                    }
                },
            },
            "asset_configuration": {
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
                                "discoveryDetails": "[variables('akri').opcUaDiscoveryDetails]",
                            },
                            "brokerProperties": {},
                            "capacity": 1,
                        },
                    }
                },
            },
        },
        "resources": [
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations",
                    "version": "[variables('VERSIONS').aio]",
                    "releaseTrain": "[variables('TRAINS').aio]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "rbac.cluster.admin": "true",
                        "aioTrust.enabled": "true",
                        "aioTrust.secretName": "[variables('AIO_TRUST_SECRET_NAME')]",
                        "aioTrust.configmapName": "[variables('AIO_TRUST_CONFIG_MAP')]",
                        "aioTrust.issuerName": "[variables('AIO_TRUST_ISSUER')]",
                        "Microsoft.CustomLocation.ServiceAccount": "default",
                        "otelCollectorAddress": "[variables('OBSERVABILITY').otelCollectorAddressNoProtocol]",
                        "genevaCollectorAddress": "[variables('OBSERVABILITY').genevaCollectorAddressNoProtocol]",
                    },
                },
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('assets-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "properties": {
                    "extensionType": "microsoft.deviceregistry.assets",
                    "version": "[variables('VERSIONS').adr]",
                    "releaseTrain": "[variables('TRAINS').adr]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {"Microsoft.CustomLocation.ServiceAccount": "default"},
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]"
                ],
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('mq-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations.mq",
                    "version": "[variables('VERSIONS').mq]",
                    "releaseTrain": "[variables('TRAINS').mq]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "global.quickstart": "false",
                        "global.openTelemetryCollectorAddr": "[variables('OBSERVABILITY').otelCollectorAddress]",
                        "secrets.enabled": "[parameters('mqSecrets').enabled]",
                        "secrets.secretProviderClassName": "[parameters('mqSecrets').secretProviderClassName]",
                        "secrets.servicePrincipalSecretRef": "[parameters('mqSecrets').servicePrincipalSecretRef]",
                    },
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]"
                ],
            },
            {
                "condition": "[parameters('deployDataProcessor')]",
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('processor-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations.dataprocessor",
                    "version": "[variables('VERSIONS').processor]",
                    "releaseTrain": "[variables('TRAINS').processor]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "Microsoft.CustomLocation.ServiceAccount": "default",
                        "otelCollectorAddress": "[variables('OBSERVABILITY').otelCollectorAddressNoProtocol]",
                        "genevaCollectorAddress": "[variables('OBSERVABILITY').genevaCollectorAddressNoProtocol]",
                        "secrets.secretProviderClassName": "[parameters('dataProcessorSecrets').secretProviderClassName]",
                        "secrets.servicePrincipalSecretRef": "[parameters('dataProcessorSecrets').servicePrincipalSecretRef]",
                        "caTrust.enabled": "true",
                        "caTrust.configmapName": "[variables('AIO_TRUST_CONFIG_MAP')]",
                        "serviceAccountTokens.MQClient.audience": "[variables('MQ_PROPERTIES').satAudience]",
                    },
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]"
                ],
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('akri-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "properties": {
                    "extensionType": "microsoft.iotoperations.akri",
                    "version": "[variables('VERSIONS').akri]",
                    "releaseTrain": "[variables('TRAINS').akri]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "webhookConfiguration.enabled": "false",
                        "certManagerWebhookCertificate.enabled": "false",
                        "agent.host.containerRuntimeSocket": "[parameters('containerRuntimeSocket')]",
                        "kubernetesDistro": "[parameters('kubernetesDistro')]",
                    },
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]"
                ],
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('opc-ua-broker-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "properties": {
                    "extensionType": "microsoft.iotoperations.opcuabroker",
                    "version": "[variables('VERSIONS').opcUaBroker]",
                    "releaseTrain": "[variables('TRAINS').opcUaBroker]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "mqttBroker.authenticationMethod": "serviceAccountToken",
                        "mqttBroker.serviceAccountTokenAudience": "[variables('MQ_PROPERTIES').satAudience]",
                        "mqttBroker.caCertConfigMapRef": "[variables('AIO_TRUST_CONFIG_MAP')]",
                        "mqttBroker.caCertKey": "[variables('AIO_TRUST_CONFIG_MAP_KEY')]",
                        "mqttBroker.address": "[variables('MQ_PROPERTIES').localUrl]",
                        "mqttBroker.connectUserProperties.metriccategory": "aio-opc",
                        "opcPlcSimulation.deploy": "[format('{0}', parameters('simulatePLC'))]",
                        "opcPlcSimulation.autoAcceptUntrustedCertificates": "[format('{0}', parameters('simulatePLC'))]",
                        "openTelemetry.enabled": "true",
                        "openTelemetry.endpoints.default.uri": "[variables('OBSERVABILITY').otelCollectorAddress]",
                        "openTelemetry.endpoints.default.protocol": "grpc",
                        "openTelemetry.endpoints.default.emitLogs": "false",
                        "openTelemetry.endpoints.default.emitMetrics": "true",
                        "openTelemetry.endpoints.default.emitTraces": "false",
                        "openTelemetry.endpoints.geneva.uri": "[variables('OBSERVABILITY').genevaCollectorAddress]",
                        "openTelemetry.endpoints.geneva.protocol": "grpc",
                        "openTelemetry.endpoints.geneva.emitLogs": "false",
                        "openTelemetry.endpoints.geneva.emitMetrics": "true",
                        "openTelemetry.endpoints.geneva.emitTraces": "false",
                        "openTelemetry.endpoints.geneva.temporalityPreference": "delta",
                        "secrets.kind": "[parameters('opcUaBrokerSecrets').kind]",
                        "secrets.csiServicePrincipalSecretRef": "[parameters('opcUaBrokerSecrets').csiServicePrincipalSecretRef]",
                        "secrets.csiDriver": "secrets-store.csi.k8s.io",
                    },
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[resourceId('Microsoft.IoTOperationsMQ/mq', parameters('mqInstanceName'))]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('mq-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                ],
            },
            {
                "condition": "[parameters('deployLayeredNetworking')]",
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('layered-networking-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "properties": {
                    "extensionType": "microsoft.iotoperations.layerednetworkmanagement",
                    "version": "[variables('VERSIONS').layeredNetworking]",
                    "releaseTrain": "[variables('TRAINS').layeredNetworking]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {},
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]"
                ],
            },
            {
                "type": "Microsoft.ExtendedLocation/customLocations",
                "apiVersion": "2021-08-31-preview",
                "name": "[parameters('customLocationName')]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "hostResourceId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
                    "namespace": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]",
                    "displayName": "[parameters('customLocationName')]",
                    "clusterExtensionIds": "[union(createArray(extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))), extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('assets-{0}', variables('AIO_EXTENSION_SUFFIX'))), extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('mq-{0}', variables('AIO_EXTENSION_SUFFIX')))), if(parameters('deployDataProcessor'), createArray(extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('processor-{0}', variables('AIO_EXTENSION_SUFFIX')))), createArray()))]",
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('processor-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('assets-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('mq-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                ],
            },
            {
                "condition": "[parameters('deployResourceSyncRules')]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', parameters('customLocationName'), format('{0}-aio-sync', parameters('customLocationName')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 100,
                    "selector": {
                        "matchLabels": {"management.azure.com/provider-name": "microsoft.iotoperationsorchestrator"}
                    },
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            },
            {
                "condition": "[parameters('deployResourceSyncRules')]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', parameters('customLocationName'), format('{0}-adr-sync', parameters('customLocationName')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 200,
                    "selector": {"matchLabels": {"management.azure.com/provider-name": "Microsoft.DeviceRegistry"}},
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-mq-sync', parameters('customLocationName')))]",
                ],
            },
            {
                "condition": "[and(parameters('deployResourceSyncRules'), parameters('deployDataProcessor'))]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', parameters('customLocationName'), format('{0}-dp-sync', parameters('customLocationName')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 300,
                    "selector": {
                        "matchLabels": {"management.azure.com/provider-name": "microsoft.iotoperationsdataprocessor"}
                    },
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-aio-sync', parameters('customLocationName')))]",
                ],
            },
            {
                "condition": "[parameters('deployResourceSyncRules')]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', parameters('customLocationName'), format('{0}-mq-sync', parameters('customLocationName')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 400,
                    "selector": {"matchLabels": {"management.azure.com/provider-name": "microsoft.iotoperationsmq"}},
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-dp-sync', parameters('customLocationName')))]",
                ],
            },
            {
                "condition": "[parameters('deployDataProcessor')]",
                "type": "Microsoft.IoTOperationsDataProcessor/instances",
                "apiVersion": "2023-10-04-preview",
                "name": "[parameters('dataProcessorInstanceName')]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {},
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-dp-sync', parameters('customLocationName')))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperationsMQ/mq",
                "apiVersion": "2023-10-04-preview",
                "name": "[parameters('mqInstanceName')]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {},
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-mq-sync', parameters('customLocationName')))]",
                    "[resourceId('Microsoft.IoTOperationsOrchestrator/targets', parameters('targetName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperationsMQ/mq/broker",
                "apiVersion": "2023-10-04-preview",
                "name": "[format('{0}/{1}', parameters('mqInstanceName'), parameters('mqBrokerName'))]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "authImage": {
                        "pullPolicy": "Always",
                        "repository": "[format('{0}/dmqtt-authentication', variables('CONTAINER_REGISTRY_DOMAINS').mq)]",
                        "tag": "[variables('VERSIONS').mq]",
                    },
                    "brokerImage": {
                        "pullPolicy": "Always",
                        "repository": "[format('{0}/dmqtt-pod', variables('CONTAINER_REGISTRY_DOMAINS').mq)]",
                        "tag": "[variables('VERSIONS').mq]",
                    },
                    "healthManagerImage": {
                        "pullPolicy": "Always",
                        "repository": "[format('{0}/dmqtt-operator', variables('CONTAINER_REGISTRY_DOMAINS').mq)]",
                        "tag": "[variables('VERSIONS').mq]",
                    },
                    "diagnostics": {
                        "probeImage": "[format('{0}/diagnostics-probe:{1}', variables('CONTAINER_REGISTRY_DOMAINS').mq, variables('VERSIONS').mq)]",
                        "enableSelfCheck": True,
                    },
                    "mode": "[parameters('mqMode')]",
                    "memoryProfile": "[parameters('mqMemoryProfile')]",
                    "cardinality": {
                        "backendChain": {
                            "partitions": "[parameters('mqBackendPartitions')]",
                            "workers": "[parameters('mqBackendWorkers')]",
                            "redundancyFactor": "[parameters('mqBackendRedundancyFactor')]",
                        },
                        "frontend": {
                            "replicas": "[parameters('mqFrontendReplicas')]",
                            "workers": "[parameters('mqFrontendWorkers')]",
                        },
                    },
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.IoTOperationsMQ/mq', parameters('mqInstanceName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperationsMQ/mq/diagnosticService",
                "apiVersion": "2023-10-04-preview",
                "name": "[format('{0}/{1}', parameters('mqInstanceName'), 'diagnostics')]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "image": {
                        "repository": "[format('{0}/diagnostics-service', variables('CONTAINER_REGISTRY_DOMAINS').mq)]",
                        "tag": "[variables('VERSIONS').mq]",
                    },
                    "logLevel": "info",
                    "logFormat": "text",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.IoTOperationsMQ/mq', parameters('mqInstanceName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperationsMQ/mq/broker/listener",
                "apiVersion": "2023-10-04-preview",
                "name": "[format('{0}/{1}/{2}', parameters('mqInstanceName'), parameters('mqBrokerName'), parameters('mqListenerName'))]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "serviceType": "[parameters('mqServiceType')]",
                    "authenticationEnabled": True,
                    "authorizationEnabled": False,
                    "brokerRef": "[parameters('mqBrokerName')]",
                    "port": 8883,
                    "tls": {
                        "automatic": {
                            "issuerRef": {
                                "name": "[parameters('mqFrontendServer')]",
                                "kind": "Issuer",
                                "group": "cert-manager.io",
                            }
                        }
                    },
                },
                "dependsOn": [
                    "[resourceId('Microsoft.IoTOperationsMQ/mq/broker', parameters('mqInstanceName'), parameters('mqBrokerName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperationsMQ/mq/broker/authentication",
                "apiVersion": "2023-10-04-preview",
                "name": "[format('{0}/{1}/{2}', parameters('mqInstanceName'), parameters('mqBrokerName'), parameters('mqAuthnName'))]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "listenerRef": ["[parameters('mqListenerName')]"],
                    "authenticationMethods": [{"sat": {"audiences": ["[variables('MQ_PROPERTIES').satAudience]"]}}],
                },
                "dependsOn": [
                    "[resourceId('Microsoft.IoTOperationsMQ/mq/broker', parameters('mqInstanceName'), parameters('mqBrokerName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.IoTOperationsMQ/mq/broker/listener', parameters('mqInstanceName'), parameters('mqBrokerName'), parameters('mqListenerName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperationsOrchestrator/targets",
                "apiVersion": "2023-10-04-preview",
                "name": "[parameters('targetName')]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "scope": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]",
                    "version": "[deployment().properties.template.contentVersion]",
                    "components": [
                        "[variables('observability_helmChart')]",
                        "[variables('akri_daemonset')]",
                        "[variables('asset_configuration')]",
                        "[variables('broker_fe_issuer_configuration')]",
                    ],
                    "topologies": [
                        {
                            "bindings": [
                                {
                                    "role": "helm.v3",
                                    "provider": "providers.target.helm",
                                    "config": {"inCluster": "true"},
                                },
                                {
                                    "role": "yaml.k8s",
                                    "provider": "providers.target.kubectl",
                                    "config": {"inCluster": "true"},
                                },
                            ]
                        }
                    ],
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-aio-sync', parameters('customLocationName')))]",
                ],
            },
        ],
        "outputs": {
            "clusterName": {"type": "string", "value": "[parameters('clusterName')]"},
            "customLocationId": {
                "type": "string",
                "value": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            },
            "customLocationName": {"type": "string", "value": "[parameters('customLocationName')]"},
            "targetName": {"type": "string", "value": "[parameters('targetName')]"},
            "processorInstanceName": {"type": "string", "value": "[parameters('dataProcessorInstanceName')]"},
            "aioNamespace": {"type": "string", "value": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]"},
            "mq": {"type": "object", "value": "[variables('MQ_PROPERTIES')]"},
            "observability": {"type": "object", "value": "[variables('OBSERVABILITY')]"},
            "clusterInfo": {
                "type": "object",
                "value": {
                    "clusterName": "[parameters('clusterName')]",
                    "aioNamespace": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]",
                },
            },
            "dataprocessor": {
                "type": "object",
                "value": {
                    "enabled": "[parameters('deployDataProcessor')]",
                    "name": "[parameters('dataProcessorInstanceName')]",
                },
            },
            "lnm": {"type": "object", "value": {"enabled": "[parameters('deployLayeredNetworking')]"}},
            "orchestrator": {"type": "object", "value": {"enabled": True, "targetName": "[parameters('targetName')]"}},
            "customLocation": {
                "type": "object",
                "value": {
                    "id": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "name": "[parameters('customLocationName')]",
                    "resourceSyncRulesEnabled": "[parameters('deployResourceSyncRules')]",
                    "resourceSyncRules": "[union(createArray(format('{0}-aio-sync', parameters('customLocationName')), format('{0}-adr-sync', parameters('customLocationName')), format('{0}-mq-sync', parameters('customLocationName'))), if(parameters('deployDataProcessor'), createArray(format('{0}-dp-sync', parameters('customLocationName'))), createArray()))]",
                },
            },
        },
    },
)


def get_insecure_mq_listener():
    return {
        "type": "Microsoft.IoTOperationsMQ/mq/broker/listener",
        "apiVersion": "2023-10-04-preview",
        "name": "[format('{0}/{1}/{2}', parameters('mqInstanceName'), parameters('mqBrokerName'), 'non-tls-listener')]",
        "location": "[parameters('location')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "properties": {
            "serviceType": "[parameters('mqServiceType')]",
            "authenticationEnabled": False,
            "authorizationEnabled": False,
            "brokerRef": "[parameters('mqBrokerName')]",
            "port": 1883,
        },
        "dependsOn": [
            "[resourceId('Microsoft.IoTOperationsMQ/mq/broker', parameters('mqInstanceName'), parameters('mqBrokerName'))]",
            "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
        ],
    }


CURRENT_TEMPLATE = V1_TEMPLATE


def get_current_template_copy(custom_template_path: Optional[str] = None) -> TemplateVer:
    if custom_template_path:
        content = json.loads(read_file_content(custom_template_path))
        return TemplateVer(commit_id="custom", moniker="custom", content=content)

    return TemplateVer(
        commit_id=CURRENT_TEMPLATE.commit_id,
        moniker=CURRENT_TEMPLATE.moniker,
        content=deepcopy(CURRENT_TEMPLATE.content),
    )
