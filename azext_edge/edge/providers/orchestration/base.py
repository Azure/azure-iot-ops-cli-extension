# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from enum import Enum


class EdgeResourceVersions(Enum):
    adr = "0.9.0"
    akri = "0.1.0"
    bluefin = "0.2.4"
    e4k = "0.5.1"
    e4in = "0.1.1"
    observability = "0.62.3"
    opcua = "0.7.0"
    symphony = "0.44.9"


def get_otel_collector_addr(namespace: str, protocol: bool = False):
    addr = f"otel-collector.{namespace}.svc.cluster.local:4317"
    if protocol:
        return f"http://{addr}"
    return addr


def get_geneva_metrics_addr(namespace: str, protocol: bool = False):
    addr = f"geneva-metrics-service.{namespace}.svc.cluster.local:4317"
    if protocol:
        return f"http://{addr}"
    return addr


class ManifestBuilder:
    def __init__(self, cluster_name: str, custom_location_name: str, cluster_namespace: str = "alice-springs"):
        self.cluster_name = cluster_name
        self.cluster_namespace = cluster_namespace
        self.custom_location_name = custom_location_name
        self._manifest: dict = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "0.1.1.0",
            "metadata": {"description": "Az Edge CLI PAS deployment."},
            "parameters": {
                "clusterName": {"type": "string"},
                "clusterLocation": {
                    "type": "string",
                    "defaultValue": "[parameters('location')]",
                    "allowedValues": ["eastus2", "westus3", "westeurope"],
                },
                "simulatePLC": {"type": "bool", "defaultValue": False},
                "location": {
                    "type": "string",
                    "defaultValue": "[resourceGroup().location]",
                    "allowedValues": ["eastus2", "westus3", "westeurope"],
                },
                "targetName": {"type": "string", "defaultValue": "my-target"},
                "opcuaDiscoveryEndpoint": {"type": "string", "defaultValue": "opc.tcp://<NOT_SET>:<NOT_SET>"},
                "kubernetesDistro": {"type": "string", "defaultValue": "k8s"},
                "bluefinInstanceName": {"type": "string", "defaultValue": "bluefin-instance"},
            },
            "variables": {
                "clusterId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
                "customLocationNamespace": "alice-springs-solution1",
                "extensionInfix": "/providers/Microsoft.KubernetesConfiguration/extensions/",
            },
            "resources": [],
        }
        self._extension_ids = []

    def add_symphony_extension(self, name: str = "alice-springs"):
        payload = {
            "type": "Microsoft.KubernetesConfiguration/extensions",
            "apiVersion": "2022-03-01",
            "name": name,
            "properties": {
                "extensionType": "microsoft.alicesprings",
                "autoUpgradeMinorVersion": False,
                "scope": {"cluster": {"releaseNamespace": self.cluster_namespace}},
                "version": EdgeResourceVersions.symphony.value,
                "releaseTrain": "private-preview",
                "configurationSettings": {
                    "Microsoft.CustomLocation.ServiceAccount": "default",
                    "otelCollectorAddress": get_otel_collector_addr(self.cluster_namespace),
                    "genevaCollectorAddress": get_geneva_metrics_addr(self.cluster_namespace),
                },
            },
            "scope": f"Microsoft.Kubernetes/connectedClusters/{self.cluster_name}",
        }
        self._manifest["resources"].append(payload)
        self._extension_ids.append(f"[concat(variables('clusterId'), variables('extensionInfix'), '{name}')]")

    def add_e4k_extension(self, name: str = "data-plane"):
        payload = {
            "type": "Microsoft.KubernetesConfiguration/extensions",
            "apiVersion": "2022-03-01",
            "name": name,
            "identity": {"type": "SystemAssigned"},
            "properties": {
                "extensionType": "microsoft.alicesprings.dataplane",
                "autoUpgradeMinorVersion": False,
                "scope": {"cluster": {"releaseNamespace": self.cluster_namespace}},
                "version": EdgeResourceVersions.e4k.value,
                "releaseTrain": "private-preview",
                "configurationSettings": {
                    "global.quickstart": True,
                    "global.openTelemetryCollectorAddr": get_otel_collector_addr(self.cluster_namespace, True),
                },
            },
            "scope": f"Microsoft.Kubernetes/connectedClusters/{self.cluster_name}",
        }
        self._manifest["resources"].append(payload)
        self._extension_ids.append(f"[concat(variables('clusterId'), variables('extensionInfix'), '{name}')]")

    def add_custom_location(self):
        payload = {
            "type": "Microsoft.ExtendedLocation/customLocations",
            "apiVersion": "2021-08-31-preview",
            "name": self.custom_location_name,
            "location": "[parameters('clusterLocation')]",
            "properties": {
                "hostResourceId": "[variables('clusterId')]",
                "namespace": "[variables('customLocationNamespace')]",
                "displayName": self.custom_location_name,
                "clusterExtensionIds": self._extension_ids,
            },
            "dependsOn": self._extension_ids,
        }
        self._manifest["resources"].append(payload)

    @property
    def manifest(self):
        return self._manifest


def get_deploy_pas_template():
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "0.1.1.0",
        "metadata": {
            "description": "This deploys Symphony to an Azure Arc enabled Kubernetes cluster along with\n- A custom location\n- A resource-sync rule \n- A symphony target representing alice springs. \n\nAlice Springs is made up of:\n- E4K operator\n- E4I operator\n- Bluefin operator\n- Observability pack with Prometheus and Grafana"
        },
        "parameters": {
            "clusterName": {"type": "string"},
            "clusterLocation": {
                "type": "string",
                "defaultValue": "[parameters('location')]",
                "allowedValues": ["eastus2", "westus3", "westeurope"],
            },
            "customLocationName": {"type": "string", "defaultValue": "my-custom-location"},
            "targetName": {"type": "string", "defaultValue": "my-target"},
            "simulatePLC": {"type": "bool", "defaultValue": False},
            "location": {
                "type": "string",
                "defaultValue": "[resourceGroup().location]",
                "allowedValues": ["eastus2", "westus3", "westeurope"],
            },
            "opcuaDiscoveryEndpoint": {"type": "string", "defaultValue": "opc.tcp://<NOT_SET>:<NOT_SET>"},
            "kubernetesDistro": {"type": "string", "defaultValue": "k8s"},
            "bluefinInstanceName": {"type": "string", "defaultValue": "bluefin-instance"},
        },
        "variables": {
            "adrName": "assets",
            "adrExtensionID": "[concat(variables('clusterId'), variables('extensionInfix'), variables('adrName'))]",
            "adrSyncRuleName": "[concat(parameters('customLocationName'), '-adr-sync')]",
            "akriOpcUaDiscoveryDetails": "[concat('opcuaDiscoveryMethod:\n  - asset:\n      endpointUrl: \"', parameters('opcuaDiscoveryEndpoint'), '\"\n      useSecurity: False\n      autoAcceptUntrustedCertificates: True\n      userName: \"user1\"\n      password: \"password\"  \n')]",
            "bluefinExtensionID": "[concat(variables('clusterId'), variables('extensionInfix'), variables('bluefinName'))]",
            "bluefinName": "processor",
            "bluefinSyncRuleName": "[concat(parameters('customLocationName'), '-bluefin-sync')]",
            "clusterId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
            "customLocationNamespace": "alice-springs-solution",
            "e4kName": "data-plane",
            "e4kExtensionID": "[concat(variables('clusterId'), variables('extensionInfix'), variables('e4kName'))]",
            "e4kSyncRuleName": "[concat(parameters('customLocationName'), '-e4k-sync')]",
            "extensionInfix": "/providers/Microsoft.KubernetesConfiguration/extensions/",
            "genevaCollectorAddressNoProtocol": "[concat('geneva-metrics-service.', variables('projectAliceSpringsNamespace'), '.svc.cluster.local:4317')]",
            "genevaCollectorAddress": "[concat('http://', variables('genevaCollectorAddressNoProtocol'))]",
            "otelCollectorAddressNoProtocol": "[concat('otel-collector.', variables('projectAliceSpringsNamespace'), '.svc.cluster.local:4317')]",
            "otelCollectorAddress": "[concat('http://', variables('otelCollectorAddressNoProtocol'))]",
            "projectAliceSpringsExtensionID": "[concat(variables('clusterId'), variables('extensionInfix'), variables('projectAliceSpringsName'))]",
            "projectAliceSpringsName": "alice-springs",
            "projectAliceSpringsNamespace": "alice-springs",
            "projectAliceSpringsSyncRuleName": "[concat(parameters('customLocationName'), '-sync')]",
            "versionAdr": "0.9.0",
            "versionAkri": "0.1.0",
            "versionBluefin": "0.2.4",
            "versionE4k": "0.5.1",
            "versionE4in": "0.1.1",
            "versionObservability": "0.62.3",
            "versionOpcUaBroker": "0.7.0",
            "versionProjectAliceSprings": "0.44.9",
        },
        "resources": [
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "name": "[variables('projectAliceSpringsName')]",
                "properties": {
                    "extensionType": "microsoft.alicesprings",
                    "autoUpgradeMinorVersion": False,
                    "scope": {"cluster": {"releaseNamespace": "[variables('projectAliceSpringsNamespace')]"}},
                    "version": "[variables('versionProjectAliceSprings')]",
                    "releaseTrain": "private-preview",
                    "configurationSettings": {
                        "Microsoft.CustomLocation.ServiceAccount": "default",
                        "otelCollectorAddress": "[variables('otelCollectorAddressNoProtocol')]",
                        "genevaCollectorAddress": "[variables('genevaCollectorAddressNoProtocol')]",
                    },
                },
                "scope": "[concat('Microsoft.Kubernetes/connectedClusters/', parameters('clusterName'))]",
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "name": "[variables('adrName')]",
                "properties": {
                    "extensionType": "microsoft.deviceregistry.assets",
                    "autoUpgradeMinorVersion": False,
                    "scope": {"cluster": {"releaseNamespace": "[variables('projectAliceSpringsNamespace')]"}},
                    "releaseTrain": "private-preview",
                    "version": "[variables('versionAdr')]",
                    "configurationSettings": {},
                },
                "scope": "[concat('Microsoft.Kubernetes/connectedClusters/', parameters('clusterName'))]",
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "name": "[variables('e4kName')]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.alicesprings.dataplane",
                    "autoUpgradeMinorVersion": False,
                    "scope": {"cluster": {"releaseNamespace": "[variables('projectAliceSpringsNamespace')]"}},
                    "version": "[variables('versionE4k')]",
                    "releaseTrain": "private-preview",
                    "configurationSettings": {
                        "global.quickstart": True,
                        "global.openTelemetryCollectorAddr": "[variables('otelCollectorAddress')]",
                    },
                },
                "scope": "[concat('Microsoft.Kubernetes/connectedClusters/', parameters('clusterName'))]",
            },
            {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "name": "[variables('bluefinName')]",
                "properties": {
                    "extensionType": "microsoft.alicesprings.processor",
                    "autoUpgradeMinorVersion": False,
                    "scope": {"cluster": {"releaseNamespace": "[variables('projectAliceSpringsNamespace')]"}},
                    "version": "[variables('versionBluefin')]",
                    "releaseTrain": "private-preview",
                    "configurationSettings": {
                        "Microsoft.CustomLocation.ServiceAccount": "microsoft.bluefin",
                        "otelCollectorAddress": "[variables('otelCollectorAddressNoProtocol')]",
                        "genevaCollectorAddress": "[variables('genevaCollectorAddressNoProtocol')]",
                    },
                },
                "scope": "[concat('Microsoft.Kubernetes/connectedClusters/', parameters('clusterName'))]",
            },
            {
                "type": "Microsoft.ExtendedLocation/customLocations",
                "apiVersion": "2021-08-31-preview",
                "name": "[parameters('customLocationName')]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "hostResourceId": "[variables('clusterId')]",
                    "namespace": "[variables('customLocationNamespace')]",
                    "displayName": "[parameters('customLocationName')]",
                    "clusterExtensionIds": [
                        "[variables('projectAliceSpringsExtensionID')]",
                        "[variables('e4kExtensionID')]",
                        "[variables('adrExtensionID')]",
                        "[variables('bluefinExtensionID')]",
                    ],
                },
                "dependsOn": [
                    "[variables('projectAliceSpringsExtensionID')]",
                    "[variables('e4kExtensionID')]",
                    "[variables('adrExtensionID')]",
                    "[variables('bluefinExtensionID')]",
                ],
            },
            {
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[concat(parameters('customLocationName'), '/', variables('projectAliceSpringsSyncRuleName'))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 100,
                    "selector": {"matchLabels": {"management.azure.com/provider-name": "microsoft.symphony"}},
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            },
            {
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[concat(parameters('customLocationName'), '/', variables('adrSyncRuleName'))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 200,
                    "selector": {"matchLabels": {"management.azure.com/provider-name": "Microsoft.DeviceRegistry"}},
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            },
            {
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[concat(parameters('customLocationName'), '/', variables('bluefinSyncRuleName'))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 300,
                    "selector": {"matchLabels": {"management.azure.com/provider-name": "microsoft.bluefin"}},
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            },
            {
                "type": "Microsoft.Symphony/targets",
                "name": "[parameters('targetName')]",
                "location": "[parameters('location')]",
                "apiVersion": "2023-05-22-preview",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "scope": "[variables('projectAliceSpringsNamespace')]",
                    "version": "0.1.1",
                    "components": [
                        {
                            "name": "observability",
                            "type": "helm.v3",
                            "properties": {
                                "chart": {
                                    "repo": "alicesprings.azurecr.io/helm/opentelemetry-collector",
                                    "version": "[variables('versionObservability')]",
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
                        },
                        {
                            "name": "e4in",
                            "type": "helm.v3",
                            "properties": {
                                "chart": {
                                    "repo": "alicesprings.azurecr.io/az-e4in",
                                    "version": "[variables('versionE4in')]",
                                }
                            },
                        },
                        {
                            "name": "akri",
                            "type": "helm.v3",
                            "properties": {
                                "chart": {
                                    "repo": "alicesprings.azurecr.io/helm/microsoft-managed-akri",
                                    "version": "[variables('versionAkri')]",
                                },
                                "values": {
                                    "custom": {
                                        "configuration": {
                                            "enabled": True,
                                            "name": "akri-opcua-asset",
                                            "discoveryHandlerName": "opcua-asset",
                                            "discoveryDetails": "[variables('akriOpcUaDiscoveryDetails')]",
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
                                    "kubernetesDistro": "[parameters('kubernetesDistro')]",
                                    "prometheus": {"enabled": True},
                                    "opentelemetry": {"enabled": True},
                                },
                            },
                        },
                        {
                            "name": "opc-ua-broker",
                            "type": "helm.v3",
                            "properties": {
                                "chart": {
                                    "repo": "alicesprings.azurecr.io/helm/az-e4i",
                                    "version": "[variables('versionOpcUaBroker')]",
                                },
                                "values": {
                                    "mqttBroker": {
                                        "authenticationMethod": "serviceAccountToken",
                                        "name": "azedge-dmqtt-frontend",
                                        "namespace": "[variables('projectAliceSpringsNamespace')]",
                                    },
                                    "opcPlcSimulation": {"deploy": "[parameters('simulatePLC')]"},
                                    "openTelemetry": {
                                        "enabled": True,
                                        "endpoints": {
                                            "default": {
                                                "uri": "[variables('otelCollectorAddress')]",
                                                "protocol": "grpc",
                                                "emitLogs": False,
                                                "emitMetrics": True,
                                                "emitTraces": False,
                                            },
                                            "geneva": {
                                                "uri": "[variables('genevaCollectorAddress')]",
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
                        },
                    ],
                    "topologies": [
                        {
                            "bindings": [
                                {
                                    "role": "instance",
                                    "provider": "providers.target.k8s",
                                    "config": {"inCluster": "True"},
                                },
                                {
                                    "role": "helm.v3",
                                    "provider": "providers.target.helm",
                                    "config": {"inCluster": "True"},
                                },
                                {
                                    "role": "yaml.k8s",
                                    "provider": "providers.target.kubectl",
                                    "config": {"inCluster": "True"},
                                },
                            ]
                        }
                    ],
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            },
            {
                "type": "Microsoft.Bluefin/instances",
                "apiVersion": "2023-06-26-preview",
                "name": "[parameters('bluefinInstanceName')]",
                "location": "[parameters('location')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {},
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            },
        ],
        "outputs": {
            "customLocationId": {
                "type": "string",
                "value": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            }
        },
    }


def deploy(
    subscription_id: str,
    cluster_name: str,
    cluster_namespace: str,
    resource_group_name: str,
    custom_location_name: str,
):
    from azure.mgmt.resource import ResourceManagementClient
    from azure.identity import DefaultAzureCredential
    from azure.core.exceptions import HttpResponseError
    from azure.cli.core.azclierror import AzureResponseError
    from uuid import uuid4
    import json

    resource_client = ResourceManagementClient(credential=DefaultAzureCredential(), subscription_id=subscription_id)
    manifest_builder = ManifestBuilder(
        cluster_name=cluster_name, custom_location_name=custom_location_name, cluster_namespace=cluster_namespace
    )
    manifest_builder.add_symphony_extension()
    manifest_builder.add_e4k_extension()
    manifest_builder.add_custom_location()
    import pdb

    pdb.set_trace()
    try:
        deployment = resource_client.deployments.begin_create_or_update(
            resource_group_name=resource_group_name,
            deployment_name=f"azedge.init.pas.{str(uuid4()).replace('-', '')}",
            parameters={
                "properties": {
                    "mode": "Incremental",
                    "template": manifest_builder.manifest,
                    "parameters": {
                        "clusterName": {"value": cluster_name},
                    },
                }
            },
        ).result()
    except HttpResponseError as e:
        # TODO: repeated error message.
        if "Deployment template validation failed:" in e.message:
            e.message = json.loads(e.response.text())["error"]["message"]
        raise AzureResponseError(e.message)

    import pdb

    pdb.set_trace()
    pass
