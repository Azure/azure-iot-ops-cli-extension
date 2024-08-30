# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import List, NamedTuple, Union, Any, Dict, Optional

from ...common import DEFAULT_DATAFLOW_PROFILE


class TemplateBlueprint(NamedTuple):
    commit_id: str
    content: Dict[str, Any]
    moniker: str

    def get_component_vers(self) -> dict:
        # Don't need a deep copy here.
        return self.content["variables"]["VERSIONS"].copy()

    @property
    def parameters(self) -> dict:
        return self.content["parameters"]

    def get_resource_by_key(self, key: str) -> Optional[dict]:
        return self.content["resource"].get(key)

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
            moniker=self.moniker,
            content=deepcopy(self.content),
        )


M2_ENABLEMENT_TEMPLATE = TemplateBlueprint(
    commit_id="f8fc2737da7d276a8e44f3d3abc74348bc7135c0",
    moniker="v0.7.0-preview.enablement",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "languageVersion": "2.0",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.29.47.4906", "templateHash": "6877356660753947778"}
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
            "kubernetesDistro": {"type": "string", "defaultValue": "K8s", "allowedValues": ["K3s", "K8s", "MicroK8s"]},
            "containerRuntimeSocket": {"type": "string", "defaultValue": ""},
            "trustConfig": {"$ref": "#/definitions/_1.TrustConfig", "defaultValue": {"source": "SelfSigned"}},
            "schemaRegistryId": {"type": "string"},
            "advancedConfig": {"$ref": "#/definitions/_1.AdvancedConfig", "defaultValue": {}},
        },
        "variables": {
            "AIO_EXTENSION_SCOPE": {"cluster": {"releaseNamespace": "azure-iot-operations"}},
            "AIO_EXTENSION_SUFFIX": "[take(uniqueString(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))), 5)]",
            "VERSIONS": {
                "platform": "0.7.0-preview-rc20240816.2",
                "aio": "0.7.0-develop.20240828.5",
                "secretSyncController": "0.5.1-100124415",
                "edgeStorageAccelerator": "2.0.0-preview",
                "openServiceMesh": "1.2.9",
            },
            "TRAINS": {
                "platform": "integration",
                "aio": "dev",
                "secretSyncController": "preview",
                "openServiceMesh": "stable",
                "edgeStorageAccelerator": "preview",
            },
            "OBSERVABILITY_ENABLED": "[not(equals(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'otelCollectorAddress'), null()))]",
            "OPCUA_BROKER_SETTINGS": {
                "brokerListenerServiceName": "aio-mq-dmqtt-frontend",
                "brokerListenerPort": 8883,
                "selfSignedIssuerName": "[format('{0}-aio-certificate-issuer', variables('AIO_EXTENSION_SCOPE').cluster.releaseNamespace)]",
            },
            "faultTolerantStorageClass": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'diskStorageClass'), 'acstor-arcstorage-storage-pool')]",
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
                "name": "[format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations.platform",
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'platform'), 'version'), variables('VERSIONS').platform)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'platform'), 'train'), variables('TRAINS').platform)]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "rbac.cluster.admin": "true",
                        "aioTrust.enabled": "false",
                        "cert-manager.install": "[if(equals(parameters('trustConfig').source, 'SelfSigned'), 'true', 'false')]",
                        "installTrustManager": "[if(equals(parameters('trustConfig').source, 'SelfSigned'), 'true', 'false')]",
                    },
                },
                "dependsOn": ["cluster"],
            },
            "secret_sync_controller_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "azure-secret-store",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.secretsynccontroller",
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'secretSyncController'), 'version'), variables('VERSIONS').secretSyncController)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'secretSyncController'), 'train'), variables('TRAINS').secretSyncController)]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": {
                        "rotationPollIntervalInSeconds": "120",
                        "validatingAdmissionPolicies.applyPolicies": "false",
                    },
                },
                "dependsOn": ["aio_platform_extension", "cluster"],
            },
            "open_service_mesh_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('open-service-mesh-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "properties": {
                    "extensionType": "microsoft.openservicemesh",
                    "autoUpgradeMinorVersion": False,
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'openServiceMesh'), 'version'), variables('VERSIONS').openServiceMesh)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'openServiceMesh'), 'train'), variables('TRAINS').openServiceMesh)]",
                },
                "dependsOn": ["cluster"],
            },
            "edge_storage_accelerator_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "azure-arc-containerstorage",
                "properties": {
                    "extensionType": "microsoft.edgestorageaccelerator",
                    "autoUpgradeMinorVersion": False,
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'version'), variables('VERSIONS').edgeStorageAccelerator)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'train'), variables('TRAINS').edgeStorageAccelerator)]",
                    "configurationSettings": "[union(createObject('edgeStorageConfiguration.create', 'true', 'feature.diskStorageClass', variables('kubernetesStorageClass')), if(equals(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'faultToleranceEnabled'), true()), createObject('acstorConfiguration.create', 'true', 'acstorConfiguration.properties.diskMountPoint', '/mnt'), createObject()))]",
                },
                "dependsOn": ["aio_platform_extension", "cluster", "open_service_mesh_extension"],
            },
            "aio_extension": {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2023-05-01",
                "scope": "[format('Microsoft.Kubernetes/connectedClusters/{0}', parameters('clusterName'))]",
                "name": "[format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "extensionType": "microsoft.iotoperations",
                    "version": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'aio'), 'version'), variables('VERSIONS').aio)]",
                    "releaseTrain": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'aio'), 'train'), variables('TRAINS').aio)]",
                    "autoUpgradeMinorVersion": False,
                    "scope": "[variables('AIO_EXTENSION_SCOPE')]",
                    "configurationSettings": "[union(createObject('connectors.values.mqttBroker.address', format('mqtts://{0}.{1}:{2}', variables('OPCUA_BROKER_SETTINGS').brokerListenerServiceName, variables('AIO_EXTENSION_SCOPE').cluster.releaseNamespace, variables('OPCUA_BROKER_SETTINGS').brokerListenerPort), 'connectors.values.opcPlcSimulation.deploy', 'false', 'connectors.values.opcPlcSimulation.autoAcceptUntrustedCertificates', 'false', 'connectors.values.discoveryHandler.enabled', 'false', 'adr.values.Microsoft.CustomLocation.ServiceAccount', 'default', 'akri.values.webhookConfiguration.enabled', 'false', 'akri.values.certManagerWebhookCertificate.enabled', 'false', 'akri.values.agent.host.containerRuntimeSocket', parameters('containerRuntimeSocket'), 'akri.values.kubernetesDistro', toLower(parameters('kubernetesDistro')), 'akri.values.agent.extensionService.mqttBroker.hostName', variables('OPCUA_BROKER_SETTINGS').brokerListenerServiceName, 'mqttBroker.values.global.quickstart', 'false', 'mqttBroker.values.operator.firstPartyMetricsOn', 'false', 'observability.metrics.enabled', format('{0}', variables('OBSERVABILITY_ENABLED')), 'observability.metrics.openTelemetryCollectorAddress', if(variables('OBSERVABILITY_ENABLED'), format('{0}', tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'otelCollectorAddress')), ''), 'observability.metrics.exportIntervalSeconds', format('{0}', coalesce(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'otelExportIntervalSeconds'), 60)), 'trustSource', parameters('trustConfig').source, 'trustBundleSettings.issuer.name', if(equals(parameters('trustConfig').source, 'CustomerManaged'), parameters('trustConfig').settings.issuerName, variables('OPCUA_BROKER_SETTINGS').selfSignedIssuerName), 'trustBundleSettings.issuer.kind', coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'issuerKind'), ''), 'trustBundleSettings.configMap.name', coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'configMapName'), ''), 'trustBundleSettings.configMap.key', coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'configMapKey'), ''), 'schemaRegistry.values.resourceId', parameters('schemaRegistryId'), 'schemaRegistry.values.mqttBroker.host', format('mqtts://{0}.{1}:{2}', variables('OPCUA_BROKER_SETTINGS').brokerListenerServiceName, variables('AIO_EXTENSION_SCOPE').cluster.releaseNamespace, variables('OPCUA_BROKER_SETTINGS').brokerListenerPort), 'schemaRegistry.values.mqttBroker.tlsEnabled', 'true', 'dataFlows.helm.upgrade.disableHooks', 'true'), coalesce(tryGet(tryGet(parameters('advancedConfig'), 'aio'), 'configurationSettingsOverride'), createObject()))]",
                },
                "dependsOn": ["aio_platform_extension", "cluster"],
            },
        },
        "outputs": {
            "clExtensionIds": {
                "type": "array",
                "items": {"type": "string"},
                "value": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                ],
            },
            "extensions": {
                "type": "object",
                "value": {
                    "aio": {
                        "name": "[format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                        "version": "[reference('aio_extension').version]",
                        "releaseTrain": "[reference('aio_extension').releaseTrain]",
                        "config": {
                            "brokerListenerName": "[variables('OPCUA_BROKER_SETTINGS').brokerListenerServiceName]",
                            "brokerListenerPort": "[variables('OPCUA_BROKER_SETTINGS').brokerListenerPort]",
                        },
                    },
                    "platform": {
                        "name": "[format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-platform-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                        "version": "[reference('aio_platform_extension').version]",
                        "releaseTrain": "[reference('aio_platform_extension').releaseTrain]",
                    },
                    "secretSyncController": {
                        "name": "azure-secret-store",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-secret-store')]",
                        "version": "[reference('secret_sync_controller_extension').version]",
                        "releaseTrain": "[reference('secret_sync_controller_extension').releaseTrain]",
                    },
                    "openServiceMesh": {
                        "name": "[format('open-service-mesh-{0}', variables('AIO_EXTENSION_SUFFIX'))]",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('open-service-mesh-{0}', variables('AIO_EXTENSION_SUFFIX')))]",
                        "version": "[reference('open_service_mesh_extension').version]",
                        "releaseTrain": "[reference('open_service_mesh_extension').releaseTrain]",
                    },
                    "edgeStorageAccelerator": {
                        "name": "azure-arc-containerstorage",
                        "id": "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-arc-containerstorage')]",
                        "version": "[reference('edge_storage_accelerator_extension').version]",
                        "releaseTrain": "[reference('edge_storage_accelerator_extension').releaseTrain]",
                    },
                },
            },
        },
    },
)

M2_INSTANCE_TEMPLATE = TemplateBlueprint(
    commit_id="f8fc2737da7d276a8e44f3d3abc74348bc7135c0",
    moniker="v0.6.0-preview",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "languageVersion": "2.0",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.29.47.4906", "templateHash": "9344632464849307200"}
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
            "customLocationName": {
                "type": "string",
                "defaultValue": "[format('location-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5)))]",
            },
            "clExtentionIds": {"type": "array", "items": {"type": "string"}},
            "deployResourceSyncRules": {"type": "bool", "defaultValue": True},
            "userAssignedIdentity": {"type": "string", "nullable": True},
            "schemaRegistryId": {"type": "string"},
            "brokerConfig": {"$ref": "#/definitions/_1.BrokerConfig", "nullable": True},
            "trustConfig": {"$ref": "#/definitions/_1.TrustConfig", "defaultValue": {"source": "SelfSigned"}},
            "advancedConfig": {"$ref": "#/definitions/_1.AdvancedConfig", "defaultValue": {}},
        },
        "variables": {
            "OPCUA_BROKER_SETTINGS": {
                "brokerListenerServiceName": "aio-mq-dmqtt-frontend",
                "brokerListenerPort": 8883,
                "selfSignedIssuerName": "[format('{0}-aio-certificate-issuer', parameters('clusterNamespace'))]",
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
        },
        "resources": {
            "cluster": {
                "existing": True,
                "type": "Microsoft.Kubernetes/connectedClusters",
                "apiVersion": "2021-03-01",
                "name": "[parameters('clusterName')]",
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
                    "clusterExtensionIds": "[parameters('clExtentionIds')]",
                },
                "dependsOn": ["cluster"],
            },
            "broker_syncRule": {
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
                "dependsOn": ["broker_syncRule", "customLocation"],
            },
            "aioInstance": {
                "type": "Microsoft.IoTOperations/instances",
                "apiVersion": "2024-08-15-preview",
                "name": "[format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5)))]",
                "location": "[parameters('clusterLocation')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "identity": "[if(empty(parameters('userAssignedIdentity')), createObject('type', 'None'), createObject('type', 'UserAssigned', 'userAssignedIdentities', createObject(format('{0}', parameters('userAssignedIdentity')), createObject())))]",
                "properties": {
                    "description": "An AIO instance.",
                    "schemaRegistryNamespace": "[reference(parameters('schemaRegistryId'), '2024-07-01-preview').namespace]",
                },
                "dependsOn": ["customLocation"],
            },
            "broker": {
                "type": "Microsoft.IoTOperations/instances/brokers",
                "apiVersion": "2024-08-15-preview",
                "name": "[format('{0}/{1}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'broker')]",
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
                "apiVersion": "2024-08-15-preview",
                "name": "[format('{0}/{1}/{2}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'broker', 'broker-authn')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "authenticationMethods": [
                        {"method": "ServiceAccountToken", "serviceAccountTokenSettings": {"audiences": ["aio-mq"]}}
                    ]
                },
                "dependsOn": ["broker", "customLocation"],
            },
            "broker_listener": {
                "type": "Microsoft.IoTOperations/instances/brokers/listeners",
                "apiVersion": "2024-08-15-preview",
                "name": "[format('{0}/{1}/{2}', format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))), 'broker', 'broker-listener')]",
                "extendedLocation": {
                    "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                    "type": "CustomLocation",
                },
                "properties": {
                    "serviceType": "[variables('BROKER_CONFIG').serviceType]",
                    "serviceName": "[variables('OPCUA_BROKER_SETTINGS').brokerListenerServiceName]",
                    "ports": [
                        {
                            "authenticationRef": "broker-authn",
                            "port": "[variables('OPCUA_BROKER_SETTINGS').brokerListenerPort]",
                            "tls": {
                                "mode": "Automatic",
                                "certManagerCertificateSpec": {
                                    "issuerRef": {
                                        "name": "[if(equals(parameters('trustConfig').source, 'CustomerManaged'), parameters('trustConfig').settings.issuerName, variables('OPCUA_BROKER_SETTINGS').selfSignedIssuerName)]",
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
        },
        "outputs": {
            "aio": {
                "type": "object",
                "value": {
                    "name": "[format('aio-{0}', coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5)))]",
                    "broker": {
                        "name": "broker",
                        "listener": "broker-listener",
                        "authn": "broker-authn",
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


def get_basic_dataflow_profile(profile_name: str = DEFAULT_DATAFLOW_PROFILE, instance_count: int = 1) -> dict:
    return {
        "type": "Microsoft.IoTOperations/instances/dataflowProfiles",
        "apiVersion": "2024-07-01-preview",
        "name": f"[format('{{0}}/{{1}}', parameters('instanceName'), '{profile_name}')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "properties": {
            "instanceCount": instance_count,
        },
        "dependsOn": [
            "[resourceId('Microsoft.IoTOperations/instances', parameters('instanceName'))]",
            "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
        ],
    }


def get_basic_listener(listener_name: str = "") -> dict:
    return {}
