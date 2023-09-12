# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Optional
from .aio_versions import AioVersionDef, EdgeServiceMoniker, get_aio_version_map


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
        cluster_namespace: str,
        version_def: AioVersionDef,
        location: str = None,
        **kwargs,
    ):
        self.cluster_name = cluster_name
        self.cluster_namespace = cluster_namespace
        self.custom_location_name = custom_location_name
        self.custom_location_namespace = custom_location_namespace
        self.location = location
        self.version_def = version_def

        self.last_sync_priority: int = 0
        self.symphony_components: List[dict] = []
        self.resources: List[dict] = []
        self.extension_ids: List[str] = []
        self.kwargs = kwargs

        self._manifest: dict = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "0.1.1.0",
            "metadata": {"description": "Az Edge CLI PAS deployment."},
            "variables": {
                "clusterId": f"[resourceId('Microsoft.Kubernetes/connectedClusters', '{self.cluster_name}')]",
                "customLocationNamespace": self.custom_location_namespace,
                "customLocationName": self.custom_location_name,
                "extensionInfix": "/providers/Microsoft.KubernetesConfiguration/extensions/",
                "targetName": f"{self.cluster_name}-{self.cluster_namespace}-init",
                "location": self.location or "[resourceGroup().location]",
            },
            "resources": [],
            "outputs": {
                "customLocationId": {
                    "type": "string",
                    "value": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
                }
            },
        }
        self._symphony_target_template: dict = {
            "type": "Microsoft.Symphony/targets",
            "name": "[variables('targetName')]",
            "location": "[variables('location')]",
            "apiVersion": "2023-05-22-preview",
            "extendedLocation": {
                "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
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
                "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
            ],
        }

    def get_next_priority(self) -> int:
        self.last_sync_priority = self.last_sync_priority + 100
        return self.last_sync_priority

    def add_extension(
        self,
        extension_type: str,
        name: str,
        include_sync_rule: bool,
        configuration: Optional[dict] = None,
    ):
        extension = {
            "type": "Microsoft.KubernetesConfiguration/extensions",
            "apiVersion": "2022-03-01",
            "name": name,
            "properties": {
                "extensionType": extension_type,
                "autoUpgradeMinorVersion": False,
                "scope": {"cluster": {"releaseNamespace": self.cluster_namespace}},
                "version": self.version_def.extension_to_vers_map[extension_type],
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
                "location": "[variables('location')]",
                "properties": {
                    "priority": self.get_next_priority(),
                    "selector": {
                        "matchLabels": {
                            "management.azure.com/provider-name": self.version_def.extension_to_rp_map[extension_type]
                        }
                    },
                    "targetResourceGroup": "[resourceGroup().id]",
                },
                "dependsOn": [
                    "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
                ],
            }
            self.resources.append(sync_rule)

    def add_custom_location(self):
        payload = {
            "type": "Microsoft.ExtendedLocation/customLocations",
            "apiVersion": "2021-08-31-preview",
            "name": self.custom_location_name,
            "location": "[variables('location')]",
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
                version=self.version_def.moniker_to_version_map[EdgeServiceMoniker.obs.value],
            )
        )
        self.symphony_components.append(
            get_e4in(version=self.version_def.moniker_to_version_map[EdgeServiceMoniker.e4in.value])
        )
        self.symphony_components.append(
            get_akri(
                version=self.version_def.moniker_to_version_map[EdgeServiceMoniker.akri.value],
                opcua_discovery_endpoint=self.kwargs.get("opcua_discovery_endpoint", "opc.tcp://<notset>:50000/"),
                kubernetes_distro=self.kwargs.get("kubernetes_distro", "k8s"),
            )
        )
        self.symphony_components.append(
            get_opcua_broker(
                version=self.version_def.moniker_to_version_map[EdgeServiceMoniker.opcua.value],
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
    aio_version: str,
    location: Optional[str] = None,
    **kwargs,
):
    import json
    from uuid import uuid4

    from azure.cli.core.azclierror import AzureResponseError
    from azure.core.exceptions import HttpResponseError
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.resource import ResourceManagementClient
    from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

    version_def = get_aio_version_map(version=aio_version)

    resource_client = ResourceManagementClient(credential=DefaultAzureCredential(), subscription_id=subscription_id)
    manifest_builder = ManifestBuilder(
        cluster_name=cluster_name,
        custom_location_name=custom_location_name,
        custom_location_namespace=custom_location_namespace,
        cluster_namespace=cluster_namespace,
        location=location,
        version_def=version_def,
        **kwargs,
    )
    no_progress = kwargs.get("no_progress", False)
    if "custom_version" in kwargs:
        import pdb

        pdb.set_trace()
        pass

    manifest_builder.add_extension(
        extension_type="microsoft.alicesprings",
        name="iotoperations",
        include_sync_rule=True,
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "default",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
        },
    )
    manifest_builder.add_extension(
        extension_type="microsoft.alicesprings.dataplane",
        name="mq",
        include_sync_rule=False,
        configuration={
            "global.quickstart": True,
            "global.openTelemetryCollectorAddr": get_otel_collector_addr(cluster_namespace, True),
        },
    )
    if False:
        manifest_builder.add_extension(
            extension_type="microsoft.alicesprings.processor",
            name="dataprocessor",
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

    if kwargs.get("what_if"):
        return manifest_builder.manifest

    with Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        "Elapsed:",
        TimeElapsedColumn(),
        transient=False,
        disable=no_progress,
    ) as progress:
        progress.add_task(description=f"Deploying AIO version: {aio_version}", total=None)
        try:
            deployment = resource_client.deployments.begin_create_or_update(
                resource_group_name=resource_group_name,
                deployment_name=f"azedge.init.pas.{str(uuid4()).replace('-', '')}",
                parameters={
                    "properties": {
                        "mode": "Incremental",
                        "template": manifest_builder.manifest,
                    }
                },
            ).result()
        except HttpResponseError as e:
            # TODO: repeated error message.
            if "Deployment template validation failed:" in e.message:
                e.message = json.loads(e.response.text())["error"]["message"]
            raise AzureResponseError(e.message)

        result = {}
        result["provisioningState"] = deployment.properties.provisioning_state
        result["correlationId"] = deployment.properties.correlation_id
        result["name"] = deployment.name
        result["resourceIds"] = [resource.id for resource in deployment.properties.output_resources]

        import pdb

        pdb.set_trace()
        pass
