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

    def get_component_vers(self) -> dict:
        # Don't need a deep copy here.
        return self.content["variables"]["VERSIONS"].copy()

    @property
    def parameters(self) -> dict:
        return self.content["parameters"]


V1_TEMPLATE = TemplateVer(
    commit_id="6a6ce36417fce836dcc9b5b2bc525dcf92534b41",
    moniker="v0.6.0-preview",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.28.1.47646", "templateHash": "10535093290625077776"},
            "description": "This template deploys Azure IoT Operations.",
            "aziotopsCliVersion": "0.6.0a1",
        },
        "parameters": {
            "clusterName": {"type": "string"},
            "instanceName": {"type": "string", "defaultValue": "aio-instance"},
            "instanceDescription": {"type": "string", "defaultValue": ""},
            "clusterLocation": {"type": "string", "defaultValue": "[parameters('location')]"},
            "location": {"type": "string", "defaultValue": "[resourceGroup().location]"},
            "customLocationName": {"type": "string", "defaultValue": "[format('{0}-cl', parameters('clusterName'))]"},
            "simulatePLC": {"type": "bool", "defaultValue": False},
            "mqFrontendServer": {"type": "string", "defaultValue": "mq-dmqtt-frontend"},
            "mqListenerName": {"type": "string", "defaultValue": "listener"},
            "mqBrokerName": {"type": "string", "defaultValue": "broker"},
            "mqAuthnName": {"type": "string", "defaultValue": "authn"},
            "mqFrontendReplicas": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqFrontendWorkers": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqBackendRedundancyFactor": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqBackendWorkers": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqBackendPartitions": {"type": "int", "defaultValue": 2, "minValue": 1},
            "mqMemoryProfile": {
                "type": "string",
                "defaultValue": "Medium",
                "allowedValues": ["Tiny", "Low", "Medium", "High"],
            },
            "mqServiceType": {
                "type": "string",
                "defaultValue": "ClusterIp",
                "allowedValues": ["ClusterIp", "LoadBalancer", "NodePort"],
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
            "deploySecretSyncController": {"type": "bool", "defaultValue": False},
        },
        "variables": {
            "AIO_CLUSTER_RELEASE_NAMESPACE": "azure-iot-operations",
            "AIO_EXTENSION_SCOPE": {"cluster": {"releaseNamespace": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]"}},
            "AIO_EXTENSION_SUFFIX": "[take(uniqueString(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))), 5)]",
            "AIO_TRUST_CONFIG_MAP": "aio-ca-trust-bundle-test-only",
            "AIO_TRUST_ISSUER": "aio-ca-issuer",
            "AIO_TRUST_CONFIG_MAP_KEY": "ca.crt",
            "AIO_TRUST_SECRET_NAME": "aio-ca-key-pair-test-only",
            "OBSERVABILITY": {
                "targetName": "[format('{0}-observability', toLower(parameters('clusterName')))]",
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
                "mqBrokerName": "[parameters('mqBrokerName')]",
                "mqListenerName": "[parameters('mqListenerName')]",
                "mqAuthnName": "[parameters('mqAuthnName')]",
                "mqFrontendServer": "[parameters('mqFrontendServer')]",
                "mqFrontendReplicas": "[parameters('mqFrontendReplicas')]",
                "mqFrontendWorkers": "[parameters('mqFrontendWorkers')]",
                "mqBackendRedundancyFactor": "[parameters('mqBackendRedundancyFactor')]",
                "mqBackendWorkers": "[parameters('mqBackendWorkers')]",
                "mqBackendPartitions": "[parameters('mqBackendPartitions')]",
                "mqMemoryProfile": "[parameters('mqMemoryProfile')]",
                "mqServiceType": "[parameters('mqServiceType')]",
            },
            "VERSIONS": {
                "platform": "0.6.0-preview-rc20240709.2",
                "aio": "0.6.0-preview-rc20240715.1",
                "observability": "0.1.0-preview",
                "secretSyncController": "0.3.0-97225789",
            },
            "TRAINS": {"platform": "integration", "aio": "integration", "secretSyncController": "preview"},
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
        },
        "resources": [
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations.platform",
                    "version": "[variables('VERSIONS').platform]",
                    "releaseTrain": "[variables('TRAINS').platform]",
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
                "condition": "[parameters('deploySecretSyncController')]",
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('secret-sync-controller-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.secretsynccontroller",
                    "version": "[variables('VERSIONS').secretSyncController]",
                    "releaseTrain": "[variables('TRAINS').secretSyncController]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "rotationPollIntervalInSeconds": "120",
                        "validatingAdmissionPolicies.applyPolicies": "false",
                    },
                },
            },
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
                        "connectors.opcua.values.nameOverride": "microsoft-iotoperations-opcuabroker",
                        "connectors.opcua.values.mqttBroker.authenticationMethod": "serviceAccountToken",
                        "connectors.opcua.values.mqttBroker.serviceAccountTokenAudience": "[variables('MQ_PROPERTIES').satAudience]",
                        "connectors.opcua.values.mqttBroker.caCertConfigMapRef": "[variables('AIO_TRUST_CONFIG_MAP')]",
                        "connectors.opcua.values.mqttBroker.caCertKey": "[variables('AIO_TRUST_CONFIG_MAP_KEY')]",
                        "connectors.opcua.values.mqttBroker.address": "[variables('MQ_PROPERTIES').localUrl]",
                        "connectors.opcua.values.mqttBroker.connectUserProperties.metriccategory": "aio-opc",
                        "connectors.opcua.values.opcPlcSimulation.deploy": "[format('{0}', parameters('simulatePLC'))]",
                        "connectors.opcua.values.opcPlcSimulation.autoAcceptUntrustedCertificates": "[format('{0}', parameters('simulatePLC'))]",
                        "connectors.opcua.values.discoveryHandler.enabled": "true",
                        "connectors.opcua.values.openTelemetry.enabled": "true",
                        "connectors.opcua.values.openTelemetry.endpoints.default.uri": "[variables('OBSERVABILITY').otelCollectorAddress]",
                        "connectors.opcua.values.openTelemetry.endpoints.default.protocol": "grpc",
                        "connectors.opcua.values.openTelemetry.endpoints.default.emitLogs": "false",
                        "connectors.opcua.values.openTelemetry.endpoints.default.emitMetrics": "true",
                        "connectors.opcua.values.openTelemetry.endpoints.default.emitTraces": "false",
                        "connectors.opcua.values.openTelemetry.endpoints.geneva.uri": "[variables('OBSERVABILITY').genevaCollectorAddress]",
                        "connectors.opcua.values.openTelemetry.endpoints.geneva.protocol": "grpc",
                        "connectors.opcua.values.openTelemetry.endpoints.geneva.emitLogs": "false",
                        "connectors.opcua.values.openTelemetry.endpoints.geneva.emitMetrics": "true",
                        "connectors.opcua.values.openTelemetry.endpoints.geneva.emitTraces": "false",
                        "connectors.opcua.values.openTelemetry.endpoints.geneva.temporalityPreference": "delta",
                        "connectors.opcua.values.secrets.kind": "[parameters('opcUaBrokerSecrets').kind]",
                        "connectors.opcua.values.secrets.csiServicePrincipalSecretRef": "[parameters('opcUaBrokerSecrets').csiServicePrincipalSecretRef]",
                        "connectors.opcua.values.secrets.csiDriver": "secrets-store.csi.k8s.io",
                        "adr.values.Microsoft.CustomLocation.ServiceAccount": "default",
                        "akri.values.webhookConfiguration.enabled": "false",
                        "akri.values.certManagerWebhookCertificate.enabled": "false",
                        "akri.values.agent.host.containerRuntimeSocket": "[parameters('containerRuntimeSocket')]",
                        "akri.values.kubernetesDistro": "[parameters('kubernetesDistro')]",
                        "mqttBroker.values.global.quickstart": "false",
                        "mqttBroker.values.global.openTelemetryCollectorAddr": "[variables('OBSERVABILITY').otelCollectorAddress]",
                        "mqttBroker.values.secrets.enabled": "[parameters('mqSecrets').enabled]",
                        "mqttBroker.values.secrets.secretProviderClassName": "[parameters('mqSecrets').secretProviderClassName]",
                        "mqttBroker.values.secrets.servicePrincipalSecretRef": "[parameters('mqSecrets').servicePrincipalSecretRef]",
                        "observability.metrics.openTelemetryCollectorAddress": "[variables('OBSERVABILITY').otelCollectorAddressNoProtocol]",
                        "adr.enabled": "true",
                        "adr.image.registry": "azureiotoperations.azurecr.io",
                        "adr.image.repository": "helm/adr/assets-arc-extension",
                        "adr.image.tag": "0.1.1-preview-rc.2",
                        "akri.enabled": "true",
                        "akri.image.registry": "akripreview.azurecr.io",
                        "akri.image.repository": "helm/microsoft-managed-akri",
                        "akri.image.tag": "0.3.3-preview",
                        "connectors.opcua.enabled": "true",
                        "connectors.opcua.image.registry": "azureiotoperations.azurecr.io",
                        "connectors.opcua.image.repository": "aio-connectors/helmchart/microsoft-aio-connectors",
                        "connectors.opcua.image.tag": "0.7.0-preview.3",
                        "dataFlows.enabled": "true",
                        "dataFlows.image.registry": "mqpreview.azurecr.io",
                        "dataFlows.image.repository": "helm/dataflows",
                        "dataFlows.image.tag": "0.1.0-preview-rc8",
                        "mqttBroker.enabled": "true",
                        "mqttBroker.image.registry": "mqpreview.azurecr.io",
                        "mqttBroker.image.repository": "helm/mq",
                        "mqttBroker.image.tag": "0.5.0-preview-rc5",
                    },
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX')))]"
                ],
            },
            {
                "type": "Microsoft.IoTOperationsOrchestrator/targets",
                "apiVersion": "2023-10-04-preview",
                "name": "[variables('OBSERVABILITY').targetName]",
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
            {
                "type": "Microsoft.ExtendedLocation/customLocations",
                "apiVersion": "2021-08-31-preview",
                "name": "[parameters('customLocationName')]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "hostResourceId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
                    "namespace": "[variables('AIO_CLUSTER_RELEASE_NAMESPACE')]",
                    "displayName": "[parameters('customLocationName')]",
                    "clusterExtensionIds": [
                        "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                        "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    ],
                },
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
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
                    "[resourceId('Microsoft.ExtendedLocation/customLocations/resourceSyncRules', parameters('customLocationName'), format('{0}-aio-sync', parameters('customLocationName')))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperations/instances",
                "apiVersion": "2024-07-01-preview",
                "name": "[parameters('instanceName')]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {"description": "[parameters('instanceDescription')]"},
                "dependsOn": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.IoTOperationsOrchestrator/targets', variables('OBSERVABILITY').targetName)]",
                ],
            },
            {
                "type": "Microsoft.IoTOperations/instances/brokers",
                "apiVersion": "2024-07-01-preview",
                "name": "[format('{0}/{1}', parameters('instanceName'), parameters('mqBrokerName'))]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "memoryProfile": "[parameters('mqMemoryProfile')]",
                    "generateResourceLimits": {"cpu": "Disabled"},
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
                    "[resourceId('Microsoft.IoTOperations/instances', parameters('instanceName'))]",
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperations/instances/brokers/listeners",
                "apiVersion": "2024-07-01-preview",
                "name": "[format('{0}/{1}/{2}', parameters('instanceName'), parameters('mqBrokerName'), parameters('mqListenerName'))]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "brokerRef": "[parameters('mqBrokerName')]",
                    "serviceType": "[parameters('mqServiceType')]",
                    "serviceName": "[variables('MQ_PROPERTIES').name]",
                    "ports": [
                        {
                            "authenticationRef": "[parameters('mqAuthnName')]",
                            "port": 8883,
                            "tls": {
                                "mode": "Automatic",
                                "automatic": {
                                    "issuerRef": {
                                        "name": "[parameters('mqFrontendServer')]",
                                        "kind": "Issuer",
                                        "apiGroup": "cert-manager.io",
                                    }
                                },
                            },
                        }
                    ],
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.IoTOperations/instances/brokers', parameters('instanceName'), parameters('mqBrokerName'))]",
                ],
            },
            {
                "type": "Microsoft.IoTOperations/instances/brokers/authentications",
                "apiVersion": "2024-07-01-preview",
                "name": "[format('{0}/{1}/{2}', parameters('instanceName'), parameters('mqBrokerName'), parameters('mqAuthnName'))]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "authenticationMethods": [
                        {
                            "method": "ServiceAccountToken",
                            "serviceAccountToken": {"audiences": ["[variables('MQ_PROPERTIES').satAudience]"]},
                        }
                    ]
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "[resourceId('Microsoft.IoTOperations/instances/brokers', parameters('instanceName'), parameters('mqBrokerName'))]",
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
            "targetName": {"type": "string", "value": "[variables('OBSERVABILITY').targetName]"},
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
            "orchestrator": {
                "type": "object",
                "value": {"enabled": True, "targetName": "[variables('OBSERVABILITY').targetName]"},
            },
            "customLocation": {
                "type": "object",
                "value": {
                    "id": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "name": "[parameters('customLocationName')]",
                    "resourceSyncRulesEnabled": "[parameters('deployResourceSyncRules')]",
                    "resourceSyncRules": [
                        "[format('{0}-aio-sync', parameters('customLocationName'))]",
                        "[format('{0}-adr-sync', parameters('customLocationName'))]",
                        "[format('{0}-mq-sync', parameters('customLocationName'))]",
                    ],
                },
            },
        },
    },
)


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
