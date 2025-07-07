# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Dict, List, NamedTuple, Optional, Union

from .common import (
    AIO_INSECURE_LISTENER_NAME,
    AIO_INSECURE_LISTENER_SERVICE_NAME,
    AIO_INSECURE_LISTENER_SERVICE_PORT,
    MqServiceType,
)


class TemplateBlueprint(NamedTuple):
    commit_id: str
    content: Dict[str, Dict[str, dict]]

    def get_type_definition(self, key: str) -> dict:
        return self.content["definitions"].get(key, {"properties": {}})

    @property
    def parameters(self) -> dict:
        return self.content["parameters"]

    def get_resource_by_key(self, key: str) -> dict:
        return self.content["resources"].get(key, {"properties": {}})

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
    commit_id="f9eaf713ec57783d5776885096bf076b3b516f2b",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "languageVersion": "2.0",
        "contentVersion": "1.0.0.0",
        "metadata": {
            "_generator": {"name": "bicep", "version": "0.36.1.42791", "templateHash": "13806746648919550554"}
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
                            "diskMountPoint": {"type": "string", "nullable": True},
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
                    "persistence": {
                        "$ref": "#/definitions/_1.BrokerPersistence",
                        "nullable": True,
                        "metadata": {"description": "The persistence settings of the Broker."},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.BrokerPersistence": {
                "type": "object",
                "properties": {
                    "dynamicSettings": {
                        "$ref": "#/definitions/_1.BrokerPersistenceDynamicSettings",
                        "nullable": True,
                        "metadata": {
                            "description": "Client sets the specified user property key/value in the CONNECT/SUBSCRIBE/PUBLISH.\nOptionally, if the customer specifies a configurable user property, it will work to enable persistence dynamically.\nDefault: key 'aio-persistence', value 'true'.\n"
                        },
                    },
                    "maxSize": {
                        "type": "string",
                        "metadata": {
                            "description": "The max size of the message buffer on disk. If a PVC template is specified, this size\nis used as the request and limit sizes of that template. If unset, a local-path provisioner is used.\n"
                        },
                    },
                    "persistentVolumeClaimSpec": {
                        "$ref": "#/definitions/_1.VolumeClaimSpec",
                        "nullable": True,
                        "metadata": {
                            "description": "Use the specified PersistentVolumeClaim template to mount a persistent volume.\nIf unset, a default PVC with default properties will be used.\n"
                        },
                    },
                    "retain": {
                        "$ref": "#/definitions/_1.BrokerRetainMessagesPolicy",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls which topic's retained messages should be persisted to disk."
                        },
                    },
                    "stateStore": {
                        "$ref": "#/definitions/_1.BrokerStateStorePolicy",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls which keys should be persisted to disk for the state store."
                        },
                    },
                    "subscriberQueue": {
                        "$ref": "#/definitions/_1.BrokerSubscriberQueuePolicy",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls which subscriber message queues should be persisted to disk.\nSession state metadata are always written to disk if any persistence is specified.\n"
                        },
                    },
                    "encryption": {
                        "$ref": "#/definitions/_1.BrokerPersistenceEncryption",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls settings related to encryption of the persistence database.\nOptional, defaults to enabling encryption.\n"
                        },
                    },
                },
                "metadata": {
                    "description": "Disk persistence configuration for the Broker.\nOptional. Everything is in-memory if not set.\nNote: if configured, all MQTT session states are written to disk.\n",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerPersistenceDynamicSettings": {
                "type": "object",
                "properties": {
                    "userPropertyKey": {
                        "type": "string",
                        "metadata": {"description": "The user property key to enable persistence."},
                    },
                    "userPropertyValue": {
                        "type": "string",
                        "metadata": {"description": "The user property value to enable persistence."},
                    },
                },
                "metadata": {
                    "description": "Dynamic settings to toggle persistence via MQTTv5 user properties.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerPersistenceEncryption": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Determines if encryption is enabled."},
                    }
                },
                "metadata": {
                    "description": "Encryption settings for the persistence database.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesCustomPolicy": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "allowedValues": ["Custom"]},
                    "retainSettings": {
                        "$ref": "#/definitions/_1.BrokerRetainMessagesSettings",
                        "metadata": {"description": "Settings for the Custom mode."},
                    },
                },
                "metadata": {
                    "description": "Custom retain messages policy for the Broker.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesDynamic": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Mode of dynamic retain settings."},
                    }
                },
                "metadata": {
                    "description": "Dynamic toggles for retain messages policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesPolicy": {
                "type": "object",
                "discriminator": {
                    "propertyName": "mode",
                    "mapping": {
                        "All": {"type": "object", "properties": {"mode": {"type": "string", "allowedValues": ["All"]}}},
                        "None": {
                            "type": "object",
                            "properties": {"mode": {"type": "string", "allowedValues": ["None"]}},
                        },
                        "Custom": {"$ref": "#/definitions/_1.BrokerRetainMessagesCustomPolicy"},
                    },
                },
                "metadata": {
                    "description": "Controls which retained messages are persisted.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesSettings": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True,
                        "metadata": {"description": "Topics to persist (wildcards # and + supported)."},
                    },
                    "dynamic": {
                        "$ref": "#/definitions/_1.BrokerRetainMessagesDynamic",
                        "nullable": True,
                        "metadata": {"description": "Dynamic toggle via MQTTv5 user property."},
                    },
                },
                "metadata": {
                    "description": "Settings for a custom retain messages policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStoreCustomPolicy": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "allowedValues": ["Custom"]},
                    "stateStoreSettings": {
                        "$ref": "#/definitions/_1.BrokerStateStorePolicySettings",
                        "metadata": {"description": "Settings for the Custom mode."},
                    },
                },
                "metadata": {
                    "description": "Custom state store policy for the Broker.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStoreDynamic": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Mode of dynamic state store settings."},
                    }
                },
                "metadata": {
                    "description": "Dynamic toggles for state store policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStorePolicy": {
                "type": "object",
                "discriminator": {
                    "propertyName": "mode",
                    "mapping": {
                        "All": {"type": "object", "properties": {"mode": {"type": "string", "allowedValues": ["All"]}}},
                        "None": {
                            "type": "object",
                            "properties": {"mode": {"type": "string", "allowedValues": ["None"]}},
                        },
                        "Custom": {"$ref": "#/definitions/_1.BrokerStateStoreCustomPolicy"},
                    },
                },
                "metadata": {
                    "description": "Controls which state store entries are persisted.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStorePolicyResources": {
                "type": "object",
                "properties": {
                    "keyType": {
                        "type": "string",
                        "allowedValues": ["Binary", "Pattern", "String"],
                        "metadata": {"description": "Type of key matching."},
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "metadata": {"description": "List of keys to persist."},
                    },
                },
                "metadata": {
                    "description": "A key-type and its associated keys for state store persistence.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStorePolicySettings": {
                "type": "object",
                "properties": {
                    "stateStoreResources": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/_1.BrokerStateStorePolicyResources"},
                        "nullable": True,
                        "metadata": {"description": "Resources to persist (keyType and list of keys)."},
                    },
                    "dynamic": {
                        "$ref": "#/definitions/_1.BrokerStateStoreDynamic",
                        "nullable": True,
                        "metadata": {"description": "Dynamic toggle via MQTTv5 user property."},
                    },
                },
                "metadata": {
                    "description": "Settings for a custom state store policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerSubscriberQueueCustomPolicy": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "allowedValues": ["Custom"]},
                    "subscriberQueueSettings": {
                        "$ref": "#/definitions/_1.BrokerSubscriberQueueCustomPolicySettings",
                        "metadata": {"description": "Settings for the Custom mode."},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.BrokerSubscriberQueueCustomPolicySettings": {
                "type": "object",
                "properties": {
                    "subscriberClientIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True,
                        "metadata": {"description": "Subscriber client IDs to persist (wildcard * supported)."},
                    },
                    "dynamic": {
                        "$ref": "#/definitions/_1.BrokerSubscriberQueueDynamic",
                        "nullable": True,
                        "metadata": {"description": "Dynamic toggle via MQTTv5 user property."},
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True,
                        "metadata": {"description": "Topics to persist per subscriber (wildcards # and + supported)."},
                    },
                },
                "metadata": {
                    "description": "Settings for a custom subscriber queue policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerSubscriberQueueDynamic": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Mode of dynamic subscriber queue settings."},
                    }
                },
                "metadata": {
                    "description": "Dynamic toggles for subscriber queue policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerSubscriberQueuePolicy": {
                "type": "object",
                "discriminator": {
                    "propertyName": "mode",
                    "mapping": {
                        "All": {"type": "object", "properties": {"mode": {"type": "string", "allowedValues": ["All"]}}},
                        "None": {
                            "type": "object",
                            "properties": {"mode": {"type": "string", "allowedValues": ["None"]}},
                        },
                        "Custom": {"$ref": "#/definitions/_1.BrokerSubscriberQueueCustomPolicy"},
                    },
                },
                "metadata": {
                    "description": "Controls which subscriber queues are persisted.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.CustomerManaged": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "allowedValues": ["CustomerManaged"]},
                    "settings": {"$ref": "#/definitions/_1.TrustBundleSettings"},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.Features": {
                "type": "object",
                "properties": {},
                "additionalProperties": {
                    "$ref": "#/definitions/_1.InstanceFeature",
                    "metadata": {"description": "Object of features"},
                },
                "metadata": {
                    "description": "AIO Instance features.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.InstanceFeature": {
                "type": "object",
                "properties": {
                    "mode": {"$ref": "#/definitions/_1.InstanceFeatureMode", "nullable": True},
                    "settings": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": {"$ref": "#/definitions/_1.InstanceFeatureSettingValue"},
                    },
                },
                "metadata": {
                    "description": "Individual feature object within the AIO instance.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.InstanceFeatureMode": {
                "type": "string",
                "allowedValues": ["Disabled", "Preview", "Stable"],
                "metadata": {
                    "description": 'The mode of the AIO instance feature. Either "Stable", "Preview" or "Disabled".',
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.InstanceFeatureSettingValue": {
                "$ref": "#/definitions/_1.OperationalMode",
                "metadata": {
                    "description": 'The setting value of the AIO instance feature. Either "Enabled" or "Disabled".',
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.OperationalMode": {
                "type": "string",
                "allowedValues": ["Disabled", "Enabled"],
                "metadata": {
                    "description": 'Defines operational mode. Either "Enabled" or "Disabled".',
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
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
            "_1.VolumeClaimSpec": {
                "type": "object",
                "properties": {
                    "volumeName": {"type": "string", "nullable": True},
                    "volumeMode": {"type": "string", "nullable": True},
                    "storageClassName": {"type": "string", "nullable": True},
                    "accessModes": {"type": "array", "items": {"type": "string"}, "nullable": True},
                    "dataSource": {"type": "object", "nullable": True},
                    "dataSourceRef": {"type": "object", "nullable": True},
                    "resources": {"type": "object", "nullable": True},
                    "selector": {"type": "object", "nullable": True},
                },
                "metadata": {
                    "description": "Kubernetes PersistentVolumeClaim spec.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
        },
        "parameters": {
            "clusterName": {"type": "string"},
            "trustConfig": {"$ref": "#/definitions/_1.TrustConfig", "defaultValue": {"source": "SelfSigned"}},
            "advancedConfig": {"$ref": "#/definitions/_1.AdvancedConfig", "defaultValue": {}},
        },
        "variables": {
            "VERSIONS": {"platform": "0.7.25", "secretStore": "0.10.0", "containerStorage": "2.6.0"},
            "TRAINS": {"platform": "preview", "secretStore": "preview", "containerStorage": "stable"},
            "faultTolerantStorageClass": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'diskStorageClass'), 'acstor-arccontainerstorage-storage-pool')]",
            "nonFaultTolerantStorageClass": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'diskStorageClass'), 'default,local-path')]",
            "diskStorageClass": "[if(equals(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'faultToleranceEnabled'), true()), variables('faultTolerantStorageClass'), variables('nonFaultTolerantStorageClass'))]",
            "diskMountPoint": "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'diskMountPoint'), '/mnt')]",
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
                    "configurationSettings": "[union(createObject('edgeStorageConfiguration.create', 'true', 'feature.diskStorageClass', variables('diskStorageClass')), if(equals(tryGet(tryGet(parameters('advancedConfig'), 'edgeStorageAccelerator'), 'faultToleranceEnabled'), true()), createObject('acstorConfiguration.create', 'true', 'acstorConfiguration.properties.diskMountPoint', variables('diskMountPoint')), createObject()))]",
                },
                "dependsOn": ["aio_platform_extension"],
            },
        },
        "outputs": {
            "clExtensionIds": {
                "type": "array",
                "items": {"type": "string"},
                "value": [
                    "[extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', 'azure-secret-store')]"
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
    commit_id="4049d5d37378dd869c361583310d138d9217a968",
    content={
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "languageVersion": "2.0",
        "contentVersion": "1.0.0.0",
        "metadata": {"_generator": {"name": "bicep", "version": "0.36.1.42791", "templateHash": "6060386194716746867"}},
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
                            "diskMountPoint": {"type": "string", "nullable": True},
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
                    "persistence": {
                        "$ref": "#/definitions/_1.BrokerPersistence",
                        "nullable": True,
                        "metadata": {"description": "The persistence settings of the Broker."},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.BrokerPersistence": {
                "type": "object",
                "properties": {
                    "dynamicSettings": {
                        "$ref": "#/definitions/_1.BrokerPersistenceDynamicSettings",
                        "nullable": True,
                        "metadata": {
                            "description": "Client sets the specified user property key/value in the CONNECT/SUBSCRIBE/PUBLISH.\nOptionally, if the customer specifies a configurable user property, it will work to enable persistence dynamically.\nDefault: key 'aio-persistence', value 'true'.\n"
                        },
                    },
                    "maxSize": {
                        "type": "string",
                        "metadata": {
                            "description": "The max size of the message buffer on disk. If a PVC template is specified, this size\nis used as the request and limit sizes of that template. If unset, a local-path provisioner is used.\n"
                        },
                    },
                    "persistentVolumeClaimSpec": {
                        "$ref": "#/definitions/_1.VolumeClaimSpec",
                        "nullable": True,
                        "metadata": {
                            "description": "Use the specified PersistentVolumeClaim template to mount a persistent volume.\nIf unset, a default PVC with default properties will be used.\n"
                        },
                    },
                    "retain": {
                        "$ref": "#/definitions/_1.BrokerRetainMessagesPolicy",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls which topic's retained messages should be persisted to disk."
                        },
                    },
                    "stateStore": {
                        "$ref": "#/definitions/_1.BrokerStateStorePolicy",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls which keys should be persisted to disk for the state store."
                        },
                    },
                    "subscriberQueue": {
                        "$ref": "#/definitions/_1.BrokerSubscriberQueuePolicy",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls which subscriber message queues should be persisted to disk.\nSession state metadata are always written to disk if any persistence is specified.\n"
                        },
                    },
                    "encryption": {
                        "$ref": "#/definitions/_1.BrokerPersistenceEncryption",
                        "nullable": True,
                        "metadata": {
                            "description": "Controls settings related to encryption of the persistence database.\nOptional, defaults to enabling encryption.\n"
                        },
                    },
                },
                "metadata": {
                    "description": "Disk persistence configuration for the Broker.\nOptional. Everything is in-memory if not set.\nNote: if configured, all MQTT session states are written to disk.\n",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerPersistenceDynamicSettings": {
                "type": "object",
                "properties": {
                    "userPropertyKey": {
                        "type": "string",
                        "metadata": {"description": "The user property key to enable persistence."},
                    },
                    "userPropertyValue": {
                        "type": "string",
                        "metadata": {"description": "The user property value to enable persistence."},
                    },
                },
                "metadata": {
                    "description": "Dynamic settings to toggle persistence via MQTTv5 user properties.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerPersistenceEncryption": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Determines if encryption is enabled."},
                    }
                },
                "metadata": {
                    "description": "Encryption settings for the persistence database.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesCustomPolicy": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "allowedValues": ["Custom"]},
                    "retainSettings": {
                        "$ref": "#/definitions/_1.BrokerRetainMessagesSettings",
                        "metadata": {"description": "Settings for the Custom mode."},
                    },
                },
                "metadata": {
                    "description": "Custom retain messages policy for the Broker.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesDynamic": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Mode of dynamic retain settings."},
                    }
                },
                "metadata": {
                    "description": "Dynamic toggles for retain messages policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesPolicy": {
                "type": "object",
                "discriminator": {
                    "propertyName": "mode",
                    "mapping": {
                        "All": {"type": "object", "properties": {"mode": {"type": "string", "allowedValues": ["All"]}}},
                        "None": {
                            "type": "object",
                            "properties": {"mode": {"type": "string", "allowedValues": ["None"]}},
                        },
                        "Custom": {"$ref": "#/definitions/_1.BrokerRetainMessagesCustomPolicy"},
                    },
                },
                "metadata": {
                    "description": "Controls which retained messages are persisted.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerRetainMessagesSettings": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True,
                        "metadata": {"description": "Topics to persist (wildcards # and + supported)."},
                    },
                    "dynamic": {
                        "$ref": "#/definitions/_1.BrokerRetainMessagesDynamic",
                        "nullable": True,
                        "metadata": {"description": "Dynamic toggle via MQTTv5 user property."},
                    },
                },
                "metadata": {
                    "description": "Settings for a custom retain messages policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStoreCustomPolicy": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "allowedValues": ["Custom"]},
                    "stateStoreSettings": {
                        "$ref": "#/definitions/_1.BrokerStateStorePolicySettings",
                        "metadata": {"description": "Settings for the Custom mode."},
                    },
                },
                "metadata": {
                    "description": "Custom state store policy for the Broker.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStoreDynamic": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Mode of dynamic state store settings."},
                    }
                },
                "metadata": {
                    "description": "Dynamic toggles for state store policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStorePolicy": {
                "type": "object",
                "discriminator": {
                    "propertyName": "mode",
                    "mapping": {
                        "All": {"type": "object", "properties": {"mode": {"type": "string", "allowedValues": ["All"]}}},
                        "None": {
                            "type": "object",
                            "properties": {"mode": {"type": "string", "allowedValues": ["None"]}},
                        },
                        "Custom": {"$ref": "#/definitions/_1.BrokerStateStoreCustomPolicy"},
                    },
                },
                "metadata": {
                    "description": "Controls which state store entries are persisted.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStorePolicyResources": {
                "type": "object",
                "properties": {
                    "keyType": {
                        "type": "string",
                        "allowedValues": ["Binary", "Pattern", "String"],
                        "metadata": {"description": "Type of key matching."},
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "metadata": {"description": "List of keys to persist."},
                    },
                },
                "metadata": {
                    "description": "A key-type and its associated keys for state store persistence.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerStateStorePolicySettings": {
                "type": "object",
                "properties": {
                    "stateStoreResources": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/_1.BrokerStateStorePolicyResources"},
                        "nullable": True,
                        "metadata": {"description": "Resources to persist (keyType and list of keys)."},
                    },
                    "dynamic": {
                        "$ref": "#/definitions/_1.BrokerStateStoreDynamic",
                        "nullable": True,
                        "metadata": {"description": "Dynamic toggle via MQTTv5 user property."},
                    },
                },
                "metadata": {
                    "description": "Settings for a custom state store policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerSubscriberQueueCustomPolicy": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "allowedValues": ["Custom"]},
                    "subscriberQueueSettings": {
                        "$ref": "#/definitions/_1.BrokerSubscriberQueueCustomPolicySettings",
                        "metadata": {"description": "Settings for the Custom mode."},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.BrokerSubscriberQueueCustomPolicySettings": {
                "type": "object",
                "properties": {
                    "subscriberClientIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True,
                        "metadata": {"description": "Subscriber client IDs to persist (wildcard * supported)."},
                    },
                    "dynamic": {
                        "$ref": "#/definitions/_1.BrokerSubscriberQueueDynamic",
                        "nullable": True,
                        "metadata": {"description": "Dynamic toggle via MQTTv5 user property."},
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True,
                        "metadata": {"description": "Topics to persist per subscriber (wildcards # and + supported)."},
                    },
                },
                "metadata": {
                    "description": "Settings for a custom subscriber queue policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerSubscriberQueueDynamic": {
                "type": "object",
                "properties": {
                    "mode": {
                        "$ref": "#/definitions/_1.OperationalMode",
                        "metadata": {"description": "Mode of dynamic subscriber queue settings."},
                    }
                },
                "metadata": {
                    "description": "Dynamic toggles for subscriber queue policy.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.BrokerSubscriberQueuePolicy": {
                "type": "object",
                "discriminator": {
                    "propertyName": "mode",
                    "mapping": {
                        "All": {"type": "object", "properties": {"mode": {"type": "string", "allowedValues": ["All"]}}},
                        "None": {
                            "type": "object",
                            "properties": {"mode": {"type": "string", "allowedValues": ["None"]}},
                        },
                        "Custom": {"$ref": "#/definitions/_1.BrokerSubscriberQueueCustomPolicy"},
                    },
                },
                "metadata": {
                    "description": "Controls which subscriber queues are persisted.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.CustomerManaged": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "allowedValues": ["CustomerManaged"]},
                    "settings": {"$ref": "#/definitions/_1.TrustBundleSettings"},
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
            },
            "_1.Features": {
                "type": "object",
                "properties": {},
                "additionalProperties": {
                    "$ref": "#/definitions/_1.InstanceFeature",
                    "metadata": {"description": "Object of features"},
                },
                "metadata": {
                    "description": "AIO Instance features.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.InstanceFeature": {
                "type": "object",
                "properties": {
                    "mode": {"$ref": "#/definitions/_1.InstanceFeatureMode", "nullable": True},
                    "settings": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": {"$ref": "#/definitions/_1.InstanceFeatureSettingValue"},
                    },
                },
                "metadata": {
                    "description": "Individual feature object within the AIO instance.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.InstanceFeatureMode": {
                "type": "string",
                "allowedValues": ["Disabled", "Preview", "Stable"],
                "metadata": {
                    "description": 'The mode of the AIO instance feature. Either "Stable", "Preview" or "Disabled".',
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.InstanceFeatureSettingValue": {
                "$ref": "#/definitions/_1.OperationalMode",
                "metadata": {
                    "description": 'The setting value of the AIO instance feature. Either "Enabled" or "Disabled".',
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_1.OperationalMode": {
                "type": "string",
                "allowedValues": ["Disabled", "Enabled"],
                "metadata": {
                    "description": 'Defines operational mode. Either "Enabled" or "Disabled".',
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
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
            "_1.VolumeClaimSpec": {
                "type": "object",
                "properties": {
                    "volumeName": {"type": "string", "nullable": True},
                    "volumeMode": {"type": "string", "nullable": True},
                    "storageClassName": {"type": "string", "nullable": True},
                    "accessModes": {"type": "array", "items": {"type": "string"}, "nullable": True},
                    "dataSource": {"type": "object", "nullable": True},
                    "dataSourceRef": {"type": "object", "nullable": True},
                    "resources": {"type": "object", "nullable": True},
                    "selector": {"type": "object", "nullable": True},
                },
                "metadata": {
                    "description": "Kubernetes PersistentVolumeClaim spec.",
                    "__bicep_imported_from!": {"sourceTemplate": "types.bicep"},
                },
            },
            "_2.Identity": {
                "type": "object",
                "discriminator": {
                    "propertyName": "type",
                    "mapping": {
                        "None": {"$ref": "#/definitions/_2.NoIdentity"},
                        "UserAssigned": {"$ref": "#/definitions/_2.UserAssignedIdentity"},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "utils.bicep"}},
            },
            "_2.NoIdentity": {
                "type": "object",
                "properties": {"type": {"type": "string", "allowedValues": ["None"]}},
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "utils.bicep"}},
            },
            "_2.UserAssignedIdentity": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "allowedValues": ["UserAssigned"]},
                    "userAssignedIdentities": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": {"type": "object", "properties": {}},
                    },
                },
                "metadata": {"__bicep_imported_from!": {"sourceTemplate": "utils.bicep"}},
            },
        },
        "functions": [
            {
                "namespace": "_2",
                "members": {
                    "buildIdentity": {
                        "parameters": [
                            {
                                "type": "array",
                                "items": {"type": "string", "nullable": True},
                                "nullable": True,
                                "name": "identities",
                            }
                        ],
                        "output": {
                            "$ref": "#/definitions/_2.Identity",
                            "value": "[if(or(empty(parameters('identities')), equals(length(filter(parameters('identities'), lambda('id', not(empty(lambdaVariables('id')))))), 0)), createObject('type', 'None'), createObject('type', 'UserAssigned', 'userAssignedIdentities', toObject(filter(parameters('identities'), lambda('identity', not(empty(lambdaVariables('identity'))))), lambda('identity', lambdaVariables('identity')), lambda('identity', createObject()))))]",
                        },
                        "metadata": {
                            "description": 'Builds a UserAssigned identity object for the given array of identities.\nIf the list is empty, it will return {type: \'None\'}\ne.g\n```bicep\nvar identites = [\'/subscriptions/.../id1\', \'/subscriptions/.../id2\']\noutput userIdentities object = buildUserIdentities(identites)\n// The output will be:\n// {\n//   "type": "UserAssigned",\n//   "userAssignedIdentities": {\n//     "/subscriptions/.../id1": {},\n//     "/subscriptions/.../id2": {}\n//   }\n// }\n}\n',
                            "__bicep_imported_from!": {"sourceTemplate": "utils.bicep"},
                        },
                    }
                },
            }
        ],
        "parameters": {
            "clusterName": {"type": "string"},
            "clusterNamespace": {"type": "string", "defaultValue": "azure-iot-operations"},
            "clusterLocation": {"type": "string", "defaultValue": "[resourceGroup().location]"},
            "kubernetesDistro": {
                "type": "string",
                "defaultValue": "K8s",
                "allowedValues": ["K3s", "K8s", "MicroK8s"],
                "metadata": {
                    "deprecated": "This parameter is not used anymore.",
                    "description": "The Kubernetes distro to run AIO on. The default is k8s.",
                },
            },
            "containerRuntimeSocket": {
                "type": "string",
                "defaultValue": "",
                "metadata": {
                    "deprecated": "This parameter is not used anymore.",
                    "description": "The default node path of the container runtime socket. The default is empty.\nIf it's empty, socket path is determined by param kubernetesDistro.\n",
                },
            },
            "customLocationName": {"type": "string", "nullable": True},
            "clExtentionIds": {"type": "array", "items": {"type": "string"}},
            "deployResourceSyncRules": {"type": "bool", "defaultValue": False},
            "aioInstanceName": {"type": "string", "nullable": True},
            "userAssignedIdentity": {"type": "string", "nullable": True},
            "schemaRegistryId": {"type": "string"},
            "adrNamespaceId": {"type": "string", "nullable": True},
            "features": {"$ref": "#/definitions/_1.Features", "nullable": True},
            "brokerConfig": {"$ref": "#/definitions/_1.BrokerConfig", "nullable": True},
            "trustConfig": {"$ref": "#/definitions/_1.TrustConfig", "defaultValue": {"source": "SelfSigned"}},
            "defaultDataflowinstanceCount": {"type": "int", "defaultValue": 1},
            "advancedConfig": {"$ref": "#/definitions/_1.AdvancedConfig", "defaultValue": {}},
        },
        "variables": {
            "VERSIONS": {"iotOperations": "1.2.18"},
            "TRAINS": {"iotOperations": "integration"},
            "HASH": "[coalesce(tryGet(parameters('advancedConfig'), 'resourceSuffix'), take(uniqueString(resourceGroup().id, parameters('clusterName'), parameters('clusterNamespace')), 5))]",
            "AIO_EXTENSION_SUFFIX": "[take(uniqueString(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))), 5)]",
            "CUSTOM_LOCATION_NAMESPACE": "[parameters('clusterNamespace')]",
            "AIO_EXTENSION_SCOPE": {"cluster": {"releaseNamespace": "[parameters('clusterNamespace')]"}},
            "customerManagedTrust": "[equals(parameters('trustConfig').source, 'CustomerManaged')]",
            "ISSUER_NAME": "[if(variables('customerManagedTrust'), parameters('trustConfig').settings.issuerName, format('{0}-aio-certificate-issuer', parameters('clusterNamespace')))]",
            "TRUST_CONFIG_MAP": "[if(variables('customerManagedTrust'), parameters('trustConfig').settings.configMapName, format('{0}-aio-ca-trust-bundle', parameters('clusterNamespace')))]",
            "MQTT_SETTINGS": {
                "brokerListenerServiceName": "aio-broker",
                "brokerListenerPort": 18883,
                "brokerListenerHost": "[format('aio-broker.{0}', variables('CUSTOM_LOCATION_NAMESPACE'))]",
                "serviceAccountAudience": "aio-internal",
            },
            "BROKER_CONFIG": {
                "frontendReplicas": "[coalesce(tryGet(parameters('brokerConfig'), 'frontendReplicas'), 2)]",
                "frontendWorkers": "[coalesce(tryGet(parameters('brokerConfig'), 'frontendWorkers'), 2)]",
                "backendRedundancyFactor": "[coalesce(tryGet(parameters('brokerConfig'), 'backendRedundancyFactor'), 2)]",
                "backendWorkers": "[coalesce(tryGet(parameters('brokerConfig'), 'backendWorkers'), 2)]",
                "backendPartitions": "[coalesce(tryGet(parameters('brokerConfig'), 'backendPartitions'), 2)]",
                "memoryProfile": "[coalesce(tryGet(parameters('brokerConfig'), 'memoryProfile'), 'Medium')]",
                "serviceType": "[coalesce(tryGet(parameters('brokerConfig'), 'serviceType'), 'ClusterIp')]",
                "persistence": "[tryGet(parameters('brokerConfig'), 'persistence')]",
            },
            "defaultAioConfigurationSettings": {
                "AgentOperationTimeoutInMinutes": "120",
                "connectors.values.mqttBroker.address": "[format('mqtts://{0}:{1}', variables('MQTT_SETTINGS').brokerListenerHost, variables('MQTT_SETTINGS').brokerListenerPort)]",
                "connectors.values.mqttBroker.serviceAccountTokenAudience": "[variables('MQTT_SETTINGS').serviceAccountAudience]",
                "observability.metrics.enabled": "[format('{0}', coalesce(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'enabled'), false()))]",
                "observability.metrics.openTelemetryCollectorAddress": "[if(coalesce(tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'enabled'), false()), format('{0}', tryGet(tryGet(parameters('advancedConfig'), 'observability'), 'otelCollectorAddress')), '')]",
                "trustSource": "[parameters('trustConfig').source]",
                "trustBundleSettings.issuer.name": "[variables('ISSUER_NAME')]",
                "trustBundleSettings.issuer.kind": "[coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'issuerKind'), '')]",
                "trustBundleSettings.configMap.name": "[coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'configMapName'), '')]",
                "trustBundleSettings.configMap.key": "[coalesce(tryGet(tryGet(parameters('trustConfig'), 'settings'), 'configMapKey'), '')]",
                "schemaRegistry.values.mqttBroker.host": "[format('mqtts://{0}:{1}', variables('MQTT_SETTINGS').brokerListenerHost, variables('MQTT_SETTINGS').brokerListenerPort)]",
                "schemaRegistry.values.mqttBroker.serviceAccountTokenAudience": "[variables('MQTT_SETTINGS').serviceAccountAudience]",
            },
            "extendedLocation": {
                "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH'))))]",
                "type": "CustomLocation",
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
                "name": "[coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "hostResourceId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
                    "namespace": "[parameters('clusterNamespace')]",
                    "displayName": "[coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH')))]",
                    "clusterExtensionIds": "[flatten(createArray(parameters('clExtentionIds'), createArray(extensionResourceId(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), 'Microsoft.KubernetesConfiguration/extensions', format('azure-iot-operations-{0}', variables('AIO_EXTENSION_SUFFIX'))))))]",
                },
                "dependsOn": ["aio_extension"],
            },
            "aio_syncRule": {
                "condition": "[parameters('deployResourceSyncRules')]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH'))), format('{0}-aio-sync', parameters('customLocationName')))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 400,
                    "selector": {
                        "matchExpressions": [
                            {
                                "key": "management.azure.com/provider-name",
                                "operator": "In",
                                "values": ["Microsoft.IoTOperations", "microsoft.iotoperations"],
                            }
                        ]
                    },
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": ["customLocation"],
            },
            "deviceRegistry_syncRule": {
                "condition": "[parameters('deployResourceSyncRules')]",
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": "[format('{0}/{1}', coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH'))), format('{0}-adr-sync', coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH')))))]",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": 200,
                    "selector": {
                        "matchExpressions": [
                            {
                                "key": "management.azure.com/provider-name",
                                "operator": "In",
                                "values": ["Microsoft.DeviceRegistry", "microsoft.deviceregistry"],
                            }
                        ]
                    },
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": ["aio_syncRule", "customLocation"],
            },
            "aioInstance": {
                "type": "Microsoft.IoTOperations/instances",
                "apiVersion": "2025-07-01-preview",
                "name": "[coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH')))]",
                "location": "[parameters('clusterLocation')]",
                "extendedLocation": "[variables('extendedLocation')]",
                "identity": "[_2.buildIdentity(createArray(parameters('userAssignedIdentity')))]",
                "properties": {
                    "description": "An AIO instance.",
                    "schemaRegistryRef": {"resourceId": "[parameters('schemaRegistryId')]"},
                    "features": "[parameters('features')]",
                    "adrNamespaceRef": "[if(not(empty(parameters('adrNamespaceId'))), createObject('resourceId', parameters('adrNamespaceId')), null())]",
                },
                "dependsOn": ["customLocation"],
            },
            "broker": {
                "type": "Microsoft.IoTOperations/instances/brokers",
                "apiVersion": "2025-07-01-preview",
                "name": "[format('{0}/{1}', coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH'))), 'default')]",
                "extendedLocation": "[variables('extendedLocation')]",
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
                    "persistence": "[tryGet(variables('BROKER_CONFIG'), 'persistence')]",
                },
                "dependsOn": ["aioInstance", "customLocation"],
            },
            "broker_authn": {
                "type": "Microsoft.IoTOperations/instances/brokers/authentications",
                "apiVersion": "2025-07-01-preview",
                "name": "[format('{0}/{1}/{2}', coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH'))), 'default', 'default')]",
                "extendedLocation": "[variables('extendedLocation')]",
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
                "apiVersion": "2025-07-01-preview",
                "name": "[format('{0}/{1}/{2}', coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH'))), 'default', 'default')]",
                "extendedLocation": "[variables('extendedLocation')]",
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
                                        "name": "[variables('ISSUER_NAME')]",
                                        "kind": "[if(variables('customerManagedTrust'), parameters('trustConfig').settings.issuerKind, 'ClusterIssuer')]",
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
                "apiVersion": "2025-07-01-preview",
                "name": "[format('{0}/{1}', coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH'))), 'default')]",
                "extendedLocation": "[variables('extendedLocation')]",
                "properties": {"instanceCount": "[parameters('defaultDataflowinstanceCount')]"},
                "dependsOn": ["aioInstance", "customLocation"],
            },
            "dataflow_endpoint": {
                "type": "Microsoft.IoTOperations/instances/dataflowEndpoints",
                "apiVersion": "2025-07-01-preview",
                "name": "[format('{0}/{1}', coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH'))), 'default')]",
                "extendedLocation": "[variables('extendedLocation')]",
                "properties": {
                    "endpointType": "Mqtt",
                    "mqttSettings": {
                        "host": "[format('{0}:{1}', variables('MQTT_SETTINGS').brokerListenerHost, variables('MQTT_SETTINGS').brokerListenerPort)]",
                        "authentication": {
                            "method": "ServiceAccountToken",
                            "serviceAccountTokenSettings": {
                                "audience": "[variables('MQTT_SETTINGS').serviceAccountAudience]"
                            },
                        },
                        "tls": {
                            "mode": "Enabled",
                            "trustedCaCertificateConfigMapRef": "[variables('TRUST_CONFIG_MAP')]",
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
                    "config": {"trustConfig": "[parameters('trustConfig')]"},
                    "identityPrincipalId": "[reference('aio_extension', '2023-05-01', 'full').identity.principalId]",
                },
            },
            "aio": {
                "type": "object",
                "value": {
                    "name": "[coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH')))]",
                    "broker": {
                        "name": "default",
                        "listener": "default",
                        "authn": "default",
                        "settings": "[shallowMerge(createArray(variables('BROKER_CONFIG'), variables('MQTT_SETTINGS')))]",
                    },
                },
            },
            "customLocation": {
                "type": "object",
                "value": {
                    "id": "[resourceId('Microsoft.ExtendedLocation/customLocations', coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH'))))]",
                    "name": "[coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH')))]",
                    "resourceSyncRulesEnabled": "[parameters('deployResourceSyncRules')]",
                    "resourceSyncRules": [
                        "[format('{0}-adr-sync', coalesce(parameters('customLocationName'), format('location-{0}', variables('HASH'))))]",
                        "[format('{0}-aio-sync', parameters('customLocationName'))]",
                    ],
                },
            },
        },
    },
)


def get_insecure_listener(instance_name: str, broker_name: str) -> dict:
    return {
        "type": "Microsoft.IoTOperations/instances/brokers/listeners",
        "apiVersion": "2025-07-01-preview",
        "name": f"{instance_name}/{broker_name}/{AIO_INSECURE_LISTENER_NAME}",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "properties": {
            "serviceType": MqServiceType.LOADBALANCER.value,
            "serviceName": AIO_INSECURE_LISTENER_SERVICE_NAME,
            "ports": [
                {
                    "port": AIO_INSECURE_LISTENER_SERVICE_PORT,
                }
            ],
        },
        "dependsOn": ["broker", "customLocation"],
    }
