# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from enum import Enum
from typing import Optional, List


class EdgeResourceVersions(Enum):
    adr = "0.9.0"
    akri = "0.1.0"
    bluefin = "0.2.4"
    e4k = "0.5.1"
    e4in = "0.1.1"
    observability = "0.62.3"
    opcua = "0.7.0"
    symphony = "0.44.9"


extension_to_rp_map = {
    "microsoft.alicesprings": "microsoft.symphony",
    "microsoft.alicesprings.dataplane": None,
    "microsoft.alicesprings.processor": "microsoft.bluefin",
    "microsoft.deviceregistry.assets": "microsoft.deviceregistry",
}

extension_to_version_map = {
    "microsoft.alicesprings": EdgeResourceVersions.symphony.value,
    "microsoft.alicesprings.dataplane": EdgeResourceVersions.e4k.value,
    "microsoft.alicesprings.processor": EdgeResourceVersions.bluefin.value,
    "microsoft.deviceregistry.assets": EdgeResourceVersions.adr.value,
}


def get_otel_collector_addr(namespace: str, prefix_protocol: bool = False):
    port_map = {"http": "4317", "grpc": "4318"}

    addr = f"otel-collector.{namespace}.svc.cluster.local:4317"
    if prefix_protocol:
        return f"http://{addr}"
    return addr


def get_geneva_metrics_addr(namespace: str, prefix_protocol: bool = False):
    addr = f"geneva-metrics-service.{namespace}.svc.cluster.local:4317"
    if prefix_protocol:
        return f"http://{addr}"
    return addr


class ManifestBuilder:
    def __init__(
        self,
        cluster_name: str,
        custom_location_name: str,
        custom_location_namespace: str,
        cluster_namespace: str = "alice-springs",
        **kwargs,
    ):
        self.cluster_name = cluster_name
        self.cluster_namespace = cluster_namespace
        self.custom_location_name = custom_location_name
        self.custom_location_namespace = custom_location_namespace
        self.last_sync_priority: int = 0
        self.symphony_components: List[dict] = []
        self.resources: List[dict] = []
        self.extension_ids: List[str] = []
        self.kwargs = kwargs

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
                "customLocationName": {"type": "string", "defaultValue": custom_location_name},
                "location": {
                    "type": "string",
                    "defaultValue": "[resourceGroup().location]",
                    "allowedValues": ["eastus2", "westus3", "westeurope"],
                },
                "targetName": {"type": "string", "defaultValue": "init"},
                "kubernetesDistro": {"type": "string", "defaultValue": "k8s"},
                "bluefinInstanceName": {"type": "string", "defaultValue": "bluefin-instance"},
            },
            "variables": {
                "clusterId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
                "customLocationNamespace": custom_location_namespace,
                "extensionInfix": "/providers/Microsoft.KubernetesConfiguration/extensions/",
            },
            "resources": [],
            "outputs": {
                "customLocationId": {
                    "type": "string",
                    "value": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                }
            },
        }
        self._symphony_target_template: dict = {
            "type": "Microsoft.Symphony/targets",
            "name": "[parameters('targetName')]",
            "location": "[parameters('clusterLocation')]",
            "apiVersion": "2023-05-22-preview",
            "extendedLocation": {
                "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
                "type": "CustomLocation",
            },
            "properties": {
                "scope": cluster_namespace,
                "version": "0.1.1",
                "components": [],
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
        }

    def get_next_priority(self) -> int:
        self.last_sync_priority = self.last_sync_priority + 100
        return self.last_sync_priority

    def add_extension(
        self, extension_type: str, name: str, include_sync_rule: bool, configuration: Optional[dict] = None
    ):
        extension = {
            "type": "Microsoft.KubernetesConfiguration/extensions",
            "apiVersion": "2022-03-01",
            "name": name,
            "properties": {
                "extensionType": extension_type,
                "autoUpgradeMinorVersion": False,
                "scope": {"cluster": {"releaseNamespace": self.cluster_namespace}},
                "version": extension_to_version_map[extension_type],
                "releaseTrain": "private-preview",
                "configurationSettings": {},
            },
            "scope": f"Microsoft.Kubernetes/connectedClusters/{self.cluster_name}",
        }
        if configuration:
            extension["properties"]["configurationSettings"].update(configuration)
        self.resources.append(extension)
        self.extension_ids.append(f"[concat(variables('clusterId'), variables('extensionInfix'), '{name}')]")

        if include_sync_rule:
            sync_rule = {
                "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                "apiVersion": "2021-08-31-preview",
                "name": f"{self.custom_location_name}/{self.custom_location_name}-{extension_type.split()[-1]}-sync",
                "location": "[parameters('clusterLocation')]",
                "properties": {
                    "priority": self.get_next_priority(),
                    "selector": {
                        "matchLabels": {"management.azure.com/provider-name": extension_to_rp_map[extension_type]}
                    },
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
                ],
            }
            self.resources.append(sync_rule)

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
                "clusterExtensionIds": self.extension_ids,
            },
            "dependsOn": self.extension_ids,
        }
        self.resources.append(payload)

    def add_std_symphony_components(self):
        from .components import get_akri, get_e4in, get_observability, get_opcua_broker

        self.symphony_components.append(
            get_observability(
                version=EdgeResourceVersions.observability.value,
            )
        )
        self.symphony_components.append(get_e4in(version=EdgeResourceVersions.e4in.value))
        self.symphony_components.append(
            get_akri(
                version=EdgeResourceVersions.akri.value,
                opcua_discovery_endpoint=self.kwargs.get("opcua_discovery_endpoint", "opc.tcp://<notset>:50000/"),
                kubernetes_distro=self.kwargs.get("kubernetes_distro", "k8s"),
            )
        )
        self.symphony_components.append(
            get_opcua_broker(
                version=EdgeResourceVersions.opcua.value,
                namespace=self.cluster_namespace,
                otel_collector_addr=get_otel_collector_addr(self.cluster_namespace, True),
                geneva_collector_addr=get_geneva_metrics_addr(self.cluster_namespace, True),
                simulate_plc=self.kwargs.get("simulate_plc", False),
            )
        )

    @property
    def manifest(self):
        from copy import deepcopy

        m = deepcopy(self._manifest)
        if self.resources:
            m["resources"].extend(self.resources)
        if self.symphony_components:
            t = deepcopy(self._symphony_target_template)
            t["properties"]["components"].extend(self.symphony_components)
            m["resources"].append(t)

        return m


def deploy(
    subscription_id: str,
    cluster_name: str,
    cluster_namespace: str,
    resource_group_name: str,
    custom_location_name: str,
    custom_location_namespace: str,
    location: Optional[str] = None,
    **kwargs,
):
    from azure.mgmt.resource import ResourceManagementClient
    from azure.identity import DefaultAzureCredential
    from azure.core.exceptions import HttpResponseError
    from azure.cli.core.azclierror import AzureResponseError
    from uuid import uuid4
    import json

    resource_client = ResourceManagementClient(credential=DefaultAzureCredential(), subscription_id=subscription_id)
    manifest_builder = ManifestBuilder(
        cluster_name=cluster_name,
        custom_location_name=custom_location_name,
        custom_location_namespace=custom_location_namespace,
        cluster_namespace=cluster_namespace,
        **kwargs,
    )
    manifest_builder.add_extension(
        extension_type="microsoft.alicesprings",
        name="alice-springs",
        include_sync_rule=True,
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "default",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
        },
    )
    manifest_builder.add_extension(
        extension_type="microsoft.alicesprings.dataplane",
        name="data-plane",
        include_sync_rule=False,
        configuration={
            "global.quickstart": True,
            "global.openTelemetryCollectorAddr": get_otel_collector_addr(cluster_namespace, True),
        },
    )
    manifest_builder.add_extension(
        extension_type="microsoft.alicesprings.processor",
        name="processor",
        include_sync_rule=True,
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "microsoft.bluefin",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
        },
    )
    manifest_builder.add_extension(
        extension_type="microsoft.deviceregistry.assets",
        name="assets",
        include_sync_rule=True,
    )
    manifest_builder.add_custom_location()
    manifest_builder.add_std_symphony_components()

    deployment_params = {"clusterName": {"value": cluster_name}}
    if location:
        deployment_params["location"] = {"value": location}

    if kwargs.get("what_if"):
        return manifest_builder.manifest

    try:
        deployment = resource_client.deployments.begin_create_or_update(
            resource_group_name=resource_group_name,
            deployment_name=f"azedge.init.pas.{str(uuid4()).replace('-', '')}",
            parameters={
                "properties": {
                    "mode": "Incremental",
                    "template": manifest_builder.manifest,
                    "parameters": deployment_params,
                }
            },
        ).result()
    except HttpResponseError as e:
        # TODO: repeated error message.
        if "Deployment template validation failed:" in e.message:
            e.message = json.loads(e.response.text())["error"]["message"]
        raise AzureResponseError(e.message)

    result = [resource.id for resource in deployment.properties.output_resources]
    return result
