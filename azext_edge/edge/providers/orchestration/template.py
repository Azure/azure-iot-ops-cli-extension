# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Any, Dict, List, NamedTuple, Optional, Union

from .common import (
    AIO_INSECURE_LISTENER_NAME,
    AIO_INSECURE_LISTENER_SERVICE_NAME,
    AIO_INSECURE_LISTENER_SERVICE_PORT,
    MqServiceType,
)


class TemplateBlueprint(NamedTuple):
    commit_id: str
    content: Dict[str, Any]

    def get_type_definition(self, key: str) -> dict:
        return self.content["definitions"].get(key, {"properties": {}})

    @property
    def parameters(self) -> dict:
        return self.content["parameters"]

    def get_resource_by_key(self, key: str) -> Optional[dict]:
        return self.content["resources"].get(key)

    def get_resource_by_type(self, type_name: str, first=True) -> Optional[Union[List[dict], dict]]:
        r = []
        for key in self.content["resources"]:
            if self.content["resources"][key]["type"] == type_name:
                r.append(self.content["resources"][key])
        if r:
            return r[0] if first else r

    def add_resource(self, resource_key: str, resource_def: dict):
        self.content["resources"][resource_key] = resource_def

    def copy(self) -> "TemplateBlueprint":
        return TemplateBlueprint(
            commit_id=self.commit_id,
            content=deepcopy(self.content),
        )


TEMPLATE_BLUEPRINT_ENABLEMENT = TemplateBlueprint(
    commit_id="db955b7c1f5942ed6adb355b6ce997d7c753a055",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "languageVersion": "2.0",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.33.93.31351", "templateHash": "11793491850121040860"}
        },
        "definitions": {
            "_1.AdvancedConfig": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "aio": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                            "configurationSettingsOverride": {"type": "object", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "secretSyncController": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "observability": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "bool", "nullable": True},
                            "otelCollectorAddress": {"type": "string", "nullable": True},
                            "otelExportIntervalSeconds": {"type": "int", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "openServiceMesh": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "edgeStorageAccelerator": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                            "diskStorageClass": {"type": "string", "nullable": True},
                            "faultToleranceEnabled": {"type": "bool", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "resourceSuffix": {"type": "string", "nullable": True},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.BrokerConfig": {
                "type": "object",
                "properties": {
                    "frontendReplicas": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker frontend replicas. The default is 2."},
                    },
                    "frontendWorkers": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker frontend workers. The default is 2."},
                    },
                    "backendRedundancyFactor": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 5,
                        "metadata": {"description": "The AIO Broker backend redundancy factory. The default is 2."},
                    },
                    "backendWorkers": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker backend workers. The default is 2."},
                    },
                    "backendPartitions": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker backend partitions. The default is 2."},
                    },
                    "memoryProfile": {
                        "type": "string",
                        "allowedValues": ["High", "Low", "Medium", "Tiny"],
                        "nullable": True,
                        "metadata": {"description": 'The AIO Broker memory profile. The default is "Medium".'},
                    },
                    "serviceType": {
                        "type": "string",
                        "allowedValues": ["ClusterIp", "LoadBalancer", "NodePort"],
                        "nullable": True,
                        "metadata": {"description": 'The AIO Broker service type. The default is "ClusterIp".'},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.CustomerManaged": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "allowedValues": ["CustomerManaged"]},
                    "settings": {"$ref": "#/definitions/_1.TrustBundleSettings"},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.SelfSigned": {
                "type": "object",
                "properties": {"source": {"type": "string", "allowedValues": ["SelfSigned"]}},
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.TrustBundleSettings": {
                "type": "object",
                "properties": {
                    "issuerName": {"type": "string"},
                    "issuerKind": {"type": "string", "allowedValues": ["ClusterIssuer", "Issuer"]},
                    "configMapName": {"type": "string"},
                    "configMapKey": {"type": "string"},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.TrustConfig": {
                "type": "object",
                "discriminator": {
                    "propertyName": "source",
                    "mapping": {
                        "SelfSigned": {"$ref": "#/definitions/_1.SelfSigned"},
                        "CustomerManaged": {"$ref": "#/definitions/_1.CustomerManaged"},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
        },
        "parameters": {
            "clusterName": {"type": "string"},
            "trustConfig": {"$ref": "#/definitions/_1.TrustConfig", "defaultValue": {"source": "SelfSigned"}},
            "advancedConfig": {"$ref": "#/definitions/_1.AdvancedConfig", "defaultValue": {}},
        },
        "variables": {
            "VERSIONS": {
                "platform": "0.7.11",
                "secretStore": "0.7.5",
                "containerStorage": "2.2.4",
                "openServiceMesh": "1.2.10",
            },
            "TRAINS": {
                "platform": "preview",
                "secretStore": "preview",
                "containerStorage": "stable",
                "openServiceMesh": "stable",
            },
            "faultTolerantStorageClass": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'diskStorageClass'), 'acstor-arccontainerstorage-storage-pool')]",
            "nonFaultTolerantStorageClass": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'diskStorageClass'), 'default,local-path')]",
            "kubernetesStorageClass": "[if(equals(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'faultToleranceEnabled'), true()), variables('faultTolerantStorageClass'), variables('nonFaultTolerantStorageClass'))]",
        },
        "resources": {
            "cluster": {
                "existing": True,
                "type": "Microsoft.Kubernetes/connectedClusters",
                "apiVersion": "2021-03-01",
                "name": "[parameters('clusterName')]",
            },
            "aio_platform_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "azure-iot-operations-platform",
                "properties": {
                    "extensionType": "microsoft.iotoperations.platform",
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'platform'), 'version'), variables('VERSIONS').platform)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'platform'), 'train'), variables('TRAINS').platform)]",
                    "autoUpgradeMinorVersion": False,
                    "scope": {"cluster": {"releaseNamespace": "cert-manager"}},
                    "configurationSettings": {
                        "installCertManager": "[if(equals(parameters('trustConfig').source, 'SelfSigned'), 'true', 'false')]",
                        "installTrustManager": "[if(equals(parameters('trustConfig').source, 'SelfSigned'), 'true', 'false')]",
                    },
                },
            },
            "secret_store_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "azure-secret-store",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.azure.secretstore",
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'secretSyncController'), 'version'), variables('VERSIONS').secretStore)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'secretSyncController'), 'train'), variables('TRAINS').secretStore)]",
                    "autoUpgradeMinorVersion": False,
                    "configurationSettings": {
                        "rotationPollIntervalInSeconds": "120",
                        "validatingAdmissionPolicies.applyPolicies": "false",
                    },
                },
                "dependsOn": ["aio_platform_extension"],
            },
            "open_service_mesh_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "open-service-mesh",
                "properties": {
                    "extensionType": "microsoft.openservicemesh",
                    "autoUpgradeMinorVersion": False,
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'openServiceMesh'), 'version'), variables('VERSIONS').openServiceMesh)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'openServiceMesh'), 'train'), variables('TRAINS').openServiceMesh)]",
                    "configurationSettings": {
                        "osm.osm.enablePermissiveTrafficPolicy": "false",
                        "osm.osm.featureFlags.enableWASMStats": "false",
                        "osm.osm.configResyncInterval": "10s",
                        "osm.osm.osmController.resource.requests.cpu": "100m",
                        "osm.osm.osmBootstrap.resource.requests.cpu": "100m",
                        "osm.osm.injector.resource.requests.cpu": "100m",
                    },
                },
            },
            "container_storage_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "azure-arc-containerstorage",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.arc.containerstorage",
                    "autoUpgradeMinorVersion": False,
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'version'), variables('VERSIONS').containerStorage)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'train'), variables('TRAINS').containerStorage)]",
                    "configurationSettings": "[union(createObject('edgeStorageConfiguration.create', 'true', 'feature.diskStorageClass', variables('kubernetesStorageClass')), if(equals(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'faultToleranceEnabled'), true()), createObject('acstorConfiguration.create', 'true', 'acstorConfiguration.properties.diskMountPoint', '/mnt'), createObject()))]",
                },
                "dependsOn": ["aio_platform_extension", "open_service_mesh_extension"],
            },
        },
        "outputs": {
            "clExtensionIds": {
                "type": "array",
                "items": {"type": "string"},
                "value": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-iot-operations-platform')]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-secret-store')]",
                ],
            },
            "extensions": {
                "type": "object",
                "value": {
                    "platform": {
                        "name": "azure-iot-operations-platform",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-iot-operations-platform')]",
                        "version": "[reference('aio_platform_extension').version]",
                        "releaseTrain": "[reference('aio_platform_extension').releaseTrain]",
                    },
                    "secretStore": {
                        "name": "azure-secret-store",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-secret-store')]",
                        "version": "[reference('secret_store_extension').version]",
                        "releaseTrain": "[reference('secret_store_extension').releaseTrain]",
                    },
                    "openServiceMesh": {
                        "name": "open-service-mesh",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'open-service-mesh')]",
                        "version": "[reference('open_service_mesh_extension').version]",
                        "releaseTrain": "[reference('open_service_mesh_extension').releaseTrain]",
                    },
                    "containerStorage": {
                        "name": "azure-arc-containerstorage",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-arc-containerstorage')]",
                        "version": "[reference('container_storage_extension').version]",
                        "releaseTrain": "[reference('container_storage_extension').releaseTrain]",
                    },
                },
            },
        },
    },
)

TEMPLATE_BLUEPRINT_INSTANCE = TemplateBlueprint(
    commit_id="db955b7c1f5942ed6adb355b6ce997d7c753a055",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "languageVersion": "2.0",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.33.93.31351", "templateHash": "674500957660366604"}
        },
        "definitions": {
            "_1.AdvancedConfig": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "aio": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                            "configurationSettingsOverride": {"type": "object", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "secretSyncController": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "observability": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "bool", "nullable": True},
                            "otelCollectorAddress": {"type": "string", "nullable": True},
                            "otelExportIntervalSeconds": {"type": "int", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "openServiceMesh": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "edgeStorageAccelerator": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "nullable": True},
                            "train": {"type": "string", "nullable": True},
                            "diskStorageClass": {"type": "string", "nullable": True},
                            "faultToleranceEnabled": {"type": "bool", "nullable": True},
                        },
                        "nullable": True,
                    },
                    "resourceSuffix": {"type": "string", "nullable": True},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.BrokerConfig": {
                "type": "object",
                "properties": {
                    "frontendReplicas": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker frontend replicas. The default is 2."},
                    },
                    "frontendWorkers": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker frontend workers. The default is 2."},
                    },
                    "backendRedundancyFactor": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 5,
                        "metadata": {"description": "The AIO Broker backend redundancy factory. The default is 2."},
                    },
                    "backendWorkers": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker backend workers. The default is 2."},
                    },
                    "backendPartitions": {
                        "type": "int",
                        "nullable": True,
                        "minValue": 1,
                        "maxValue": 16,
                        "metadata": {"description": "Number of AIO Broker backend partitions. The default is 2."},
                    },
                    "memoryProfile": {
                        "type": "string",
                        "allowedValues": ["High", "Low", "Medium", "Tiny"],
                        "nullable": True,
                        "metadata": {"description": 'The AIO Broker memory profile. The default is "Medium".'},
                    },
                    "serviceType": {
                        "type": "string",
                        "allowedValues": ["ClusterIp", "LoadBalancer", "NodePort"],
                        "nullable": True,
                        "metadata": {"description": 'The AIO Broker service type. The default is "ClusterIp".'},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.CustomerManaged": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "allowedValues": ["CustomerManaged"]},
                    "settings": {"$ref": "#/definitions/_1.TrustBundleSettings"},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.SelfSigned": {
                "type": "object",
                "properties": {"source": {"type": "string", "allowedValues": ["SelfSigned"]}},
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.TrustBundleSettings": {
                "type": "object",
                "properties": {
                    "issuerName": {"type": "string"},
                    "issuerKind": {"type": "string", "allowedValues": ["ClusterIssuer", "Issuer"]},
                    "configMapName": {"type": "string"},
                    "configMapKey": {"type": "string"},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.TrustConfig": {
                "type": "object",
                "discriminator": {
                    "propertyName": "source",
                    "mapping": {
                        "SelfSigned": {"$ref": "#/definitions/_1.SelfSigned"},
                        "CustomerManaged": {"$ref": "#/definitions/_1.CustomerManaged"},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
        },
        "parameters": {
            "clusterName": {"type": "string"},
            "clusterNamespace": {"type": "string", "defaultValue": "azure-iot-operations"},
            "clusterLocation": {"type": "string", "defaultValue": "[resourceGroup().location]"},
            "kubernetesDistro": {"type": "string", "defaultValue": "K8s", "allowedValues": ["K3s", "K8s", "MicroK8s"]},
            "containerRuntimeSocket": {"type": "string", "defaultValue": ""},
            "customLocationName": {
                "type": "string",
                "defaultValue": "[format('location-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5)))]",
            },
            "clExtentionIds": {"type": "array", "items": {"type": "string"}},
            "deployResourceSyncRules": {"type": "bool", "defaultValue": False},
            "userAssignedIdentity": {"type": "string", "nullable": True},
            "schemaRegistryId": {"type": "string"},
            "brokerConfig": {"$ref": "#/definitions/_1.BrokerConfig", "nullable": True},
            "trustConfig": {"$ref": "#/definitions/_1.TrustConfig", "defaultValue": {"source": "SelfSigned"}},
            "defaultDataflowinstanceCount": {"type": "int", "defaultValue": 1},
            "advancedConfig": {"$ref": "#/definitions/_1.AdvancedConfig", "defaultValue": {}},
        },
        "variables": {
            "AIO_EXTENSION_SUFFIX": "[take(uniqueString(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))), 5)]",
            "AIO_EXTENSION_SCOPE": {"cluster": {"releaseNamespace": "azure-iot-operations"}},
            "VERSIONS": {"iotOperations": "1.0.15"},
            "TRAINS": {"iotOperations": "integration"},
            "MQTT_SETTINGS": {
                "brokerListenerServiceName": "aio-broker",
                "brokerListenerPort": 18883,
                "serviceAccountAudience": "aio-internal",
                "selfSignedIssuerName": "[format('{0}-aio-certificate-issuer', parameters('clusterNamespace'))]",
                "selfSignedConfigMapName": "[format('{0}-aio-ca-trust-bundle', parameters('clusterNamespace'))]",
            },
            "BROKER_CONFIG": {
                "frontendReplicas": "[coalesce(tryGet(parameters('brokerConfig'), 'frontendReplicas'), 2)]",
                "frontendWorkers": "[coalesce(tryGet(parameters('brokerConfig'), 'frontendWorkers'), 2)]",
                "backendRedundancyFactor": "[coalesce(tryGet(parameters('brokerConfig'), 'backendRedundancyFactor'), 2)]",
                "backendWorkers": "[coalesce(tryGet(parameters('brokerConfig'), 'backendWorkers'), 2)]",
                "backendPartitions": "[coalesce(tryGet(parameters('brokerConfig'), 'backendPartitions'), 2)]",
                "memoryProfile": "[coalesce(tryGet(parameters('brokerConfig'), 'memoryProfile'), 'Medium')]",
                "serviceType": "[coalesce(tryGet(parameters('brokerConfig'), 'serviceType'), 'ClusterIp')]",
            },
            "defaultAioConfigurationSettings": {
                "AgentOperationTimeoutInMinutes": 120,
                "connectors.values.mqttBroker.address": "[format('mqtts://{0}.{1}:{2}', variables('MQTT_SETTINGS').brokerListenerServiceName, variables('AIO_EXTENSION_SCOPE').cluster.releaseNamespace, variables('MQTT_SETTINGS').brokerListenerPort)]",
                "connectors.values.mqttBroker.serviceAccountTokenAudience": "[variables('MQTT_SETTINGS').serviceAccountAudience]",
                "connectors.values.opcPlcSimulation.deploy": "false",
                "connectors.values.opcPlcSimulation.autoAcceptUntrustedCertificates": "false",
                "connectors.values.discoveryHandler.enabled": "false",
                "adr.values.Microsoft.CustomLocation.ServiceAccount": "default",
                "akri.values.webhookConfiguration.enabled": "false",
                "akri.values.certManagerWebhookCertificate.enabled": "false",
                "akri.values.agent.extensionService.mqttBroker.hostName": "[format('{0}.{1}', variables('MQTT_SETTINGS').brokerListenerServiceName, variables('AIO_EXTENSION_SCOPE').cluster.releaseNamespace)]",
                "akri.values.agent.extensionService.mqttBroker.port": "[variables('MQTT_SETTINGS').brokerListenerPort]",
                "akri.values.agent.extensionService.mqttBroker.serviceAccountAudience": "[variables('MQTT_SETTINGS').serviceAccountAudience]",
                "akri.values.agent.host.containerRuntimeSocket": "[parameters('containerRuntimeSocket')]",
                "akri.values.kubernetesDistro": "[toLower(parameters('kubernetesDistro'))]",
                "mqttBroker.values.global.quickstart": "false",
                "mqttBroker.values.operator.firstPartyMetricsOn": "true",
                "observability.metrics.enabled": "[format('{0}', coalesce(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'enabled'), false()))]",
                "observability.metrics.openTelemetryCollectorAddress": "[if(coalesce(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'enabled'), false()), format('{0}', tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'otelCollectorAddress')), '')]",
                "observability.metrics.exportIntervalSeconds": "[format('{0}', coalesce(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'otelExportIntervalSeconds'), 60))]",
                "trustSource": "[parameters('trustConfig').source]",
                "trustBundleSettings.issuer.name": "[if(equals(parameters('trustConfig').source, 'CustomerManaged'), parameters('trustConfig').settings.issuerName, variables('MQTT_SETTINGS').selfSignedIssuerName)]",
                "trustBundleSettings.issuer.kind": "[coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'issuerKind'), '')]",
                "trustBundleSettings.configMap.name": "[coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'configMapName'), '')]",
                "trustBundleSettings.configMap.key": "[coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'configMapKey'), '')]",
                "schemaRegistry.values.mqttBroker.host": "[format('mqtts://{0}.{1}:{2}', variables('MQTT_SETTINGS').brokerListenerServiceName, variables('AIO_EXTENSION_SCOPE').cluster.releaseNamespace, variables('MQTT_SETTINGS').brokerListenerPort)]",
                "schemaRegistry.values.mqttBroker.tlsEnabled": True,
                "schemaRegistry.values.mqttBroker.serviceAccountTokenAudience": "[variables('MQTT_SETTINGS').serviceAccountAudience]",
            },
        },
        "resources": {
            "cluster": {
                "existing": True,
                "type": "Microsoft.Kubernetes/connectedClusters",
                "apiVersion": "2021-03-01",
                "name": "[parameters('clusterName')]",
            },
            "aio_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations",
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'aio'), 'version'), variables('VERSIONS').iotOperations)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'aio'), 'train'), variables('TRAINS').iotOperations)]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": "[union(variables('defaultAioConfigurationSettings'), coalesce(tryGet(tryGet(parameters('advancedConfig'), 'aio'), 'configurationSettingsOverride'), createObject()))]",
                },
            },
            "customLocation": {
                "type": "Microsoft.ExtendedLocation/customLocations",
                "apiVersion": "2021-08-31-preview",
                "name": "[parameters('customLocationName')]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "hostResourceId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
                    "namespace": "[parameters('clusterNamespace')]",
                    "displayName": "[parameters('customLocationName')]",
                    "clusterExtensionIds": "[flatten(createArray(parameters('clExtentionIds'), createArray(extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))))))]",
                },
                "dependsOn": ["aio_extension"],
            },
            "aio_syncRule": {
                "condition": "[parameters('deployResourceSyncRules')]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', parameters('customLocationName'), format('{0}-broker-sync', parameters('customLocationName')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 400,
                    "selector": {"matchLabels": {"management.azure.com/provider-name": "microsoft.iotoperations"}},
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": ["customLocation"],
            },
            "deviceRegistry_syncRule": {
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
                "dependsOn": ["aio_syncRule", "customLocation"],
            },
            "aioInstance": {
                "type": "Microsoft.IoTOperations/instances",
                "apiVersion": "2024-11-01",
                "name": "[format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5)))]",
                "location": "[parameters('clusterLocation')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "identity": "[if(empty(parameters('userAssignedIdentity')), createObject('type', 'None'), createObject('type', 'UserAssigned', 'userAssignedIdentities', createObject(format('{0}', parameters('userAssignedIdentity')), createObject())))]",
                "properties": {
                    "description": "An AIO instance.",
                    "schemaRegistryRef": {"resourceId": "[parameters('schemaRegistryId')]"},
                },
                "dependsOn": ["customLocation"],
            },
            "broker": {
                "type": "Microsoft.IoTOperations/instances/brokers",
                "apiVersion": "2024-11-01",
                "name": "[format('{0}/{1}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'default')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "memoryProfile": "[variables('BROKER_CONFIG').memoryProfile]",
                    "generateResourceLimits": {"cpu": "Disabled"},
                    "cardinality": {
                        "backendChain": {
                            "partitions": "[variables('BROKER_CONFIG').backendPartitions]",
                            "workers": "[variables('BROKER_CONFIG').backendWorkers]",
                            "redundancyFactor": "[variables('BROKER_CONFIG').backendRedundancyFactor]",
                        },
                        "frontend": {
                            "replicas": "[variables('BROKER_CONFIG').frontendReplicas]",
                            "workers": "[variables('BROKER_CONFIG').frontendWorkers]",
                        },
                    },
                },
                "dependsOn": ["aioInstance", "customLocation"],
            },
            "broker_authn": {
                "type": "Microsoft.IoTOperations/instances/brokers/authentications",
                "apiVersion": "2024-11-01",
                "name": "[format('{0}/{1}/{2}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'default', 'default')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "authenticationMethods": [
                        {
                            "method": "ServiceAccountToken",
                            "serviceAccountTokenSettings": {
                                "audiences": ["[variables('MQTT_SETTINGS').serviceAccountAudience]"]
                            },
                        }
                    ]
                },
                "dependsOn": ["broker", "customLocation"],
            },
            "broker_listener": {
                "type": "Microsoft.IoTOperations/instances/brokers/listeners",
                "apiVersion": "2024-11-01",
                "name": "[format('{0}/{1}/{2}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'default', 'default')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "serviceType": "[variables('BROKER_CONFIG').serviceType]",
                    "serviceName": "[variables('MQTT_SETTINGS').brokerListenerServiceName]",
                    "ports": [
                        {
                            "authenticationRef": "default",
                            "port": "[variables('MQTT_SETTINGS').brokerListenerPort]",
                            "tls": {
                                "mode": "Automatic",
                                "certManagerCertificateSpec": {
                                    "issuerRef": {
                                        "name": "[if(equals(parameters('trustConfig').source, 'CustomerManaged'), parameters('trustConfig').settings.issuerName, variables('MQTT_SETTINGS').selfSignedIssuerName)]",
                                        "kind": "[if(equals(parameters('trustConfig').source, 'CustomerManaged'), parameters('trustConfig').settings.issuerKind, 'ClusterIssuer')]",
                                        "group": "cert-manager.io",
                                    }
                                },
                            },
                        }
                    ],
                },
                "dependsOn": ["broker", "broker_authn", "customLocation"],
            },
            "dataflow_profile": {
                "type": "Microsoft.IoTOperations/instances/dataflowProfiles",
                "apiVersion": "2024-11-01",
                "name": "[format('{0}/{1}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'default')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {"instanceCount": "[parameters('defaultDataflowinstanceCount')]"},
                "dependsOn": ["aioInstance", "customLocation"],
            },
            "dataflow_endpoint": {
                "type": "Microsoft.IoTOperations/instances/dataflowEndpoints",
                "apiVersion": "2024-11-01",
                "name": "[format('{0}/{1}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'default')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "host": "[format('{0}:{1}', variables('MQTT_SETTINGS').brokerListenerServiceName, variables('MQTT_SETTINGS').brokerListenerPort)]",
                        "authentication": {
                            "method": "ServiceAccountToken",
                            "serviceAccountTokenSettings": {
                                "audience": "[variables('MQTT_SETTINGS').serviceAccountAudience]"
                            },
                        },
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "[if(equals(parameters('trustConfig').source, 'CustomerManaged'), parameters('trustConfig').settings.configMapName, variables('MQTT_SETTINGS').selfSignedConfigMapName)]",
                        },
                    },
                },
                "dependsOn": ["aioInstance", "customLocation"],
            },
        },
        "outputs": {
            "aioExtension": {
                "type": "object",
                "value": {
                    "name": "[format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                    "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "version": "[reference('aio_extension').version]",
                    "releaseTrain": "[reference('aio_extension').releaseTrain]",
                    "config": {
                        "brokerListenerName": "[variables('MQTT_SETTINGS').brokerListenerServiceName]",
                        "brokerListenerPort": "[variables('MQTT_SETTINGS').brokerListenerPort]",
                    },
                    "identityPrincipalId": "[reference('aio_extension', '2023-05-01', 'full').identity.principalId]",
                },
            },
            "aio": {
                "type": "object",
                "value": {
                    "name": "[format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5)))]",
                    "broker": {
                        "name": "default",
                        "listener": "default",
                        "authn": "default",
                        "settings": "[variables('BROKER_CONFIG')]",
                    },
                },
            },
            "customLocation": {
                "type": "object",
                "value": {
                    "id": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "name": "[parameters('customLocationName')]",
                    "resourceSyncRulesEnabled": "[parameters('deployResourceSyncRules')]",
                    "resourceSyncRules": [
                        "[format('{0}-adr-sync', parameters('customLocationName'))]",
                        "[format('{0}-broker-sync', parameters('customLocationName'))]",
                    ],
                },
            },
        },
    },
)


def get_insecure_listener(instance_name: str, broker_name: str) -> dict:
    return {
        "type": "Microsoft.IoTOperations/instances/brokers/listeners",
        "apiVersion": "2024-11-01",
        "name": f"{instance_name}/{broker_name}/{AIO_INSECURE_LISTENER_NAME}",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "properties": {
            "serviceType": MqServiceType.load_balancer.value,
            "serviceName": AIO_INSECURE_LISTENER_SERVICE_NAME,
            "ports": [
                {
                    "port": AIO_INSECURE_LISTENER_SERVICE_PORT,
                }
            ],
        },
        "dependsOn": ["broker", "customLocation"],
    }
