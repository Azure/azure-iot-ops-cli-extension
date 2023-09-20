# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Optional

from .aio_versions import (
    AioVersionDef,
    EdgeServiceMoniker,
    get_aio_version_def,
    extension_name_to_type_map,
    EdgeExtensionName,
)


def get_otel_collector_addr(namespace: str, prefix_protocol: bool = False):
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
        self.target_name = f"{self.cluster_name}-azedge-init-target"
        self.symphony_components: List[dict] = []
        self.resources: List[dict] = []
        self.extension_ids: List[str] = []
        self.kwargs = kwargs
        self.create_sync_rules = self.kwargs.get("create_sync_rules")

        self._manifest: dict = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "0.1.1.0",
            "metadata": {"description": "Az Edge CLI PAS deployment."},
            "variables": {
                "clusterId": f"[resourceId('Microsoft.Kubernetes/connectedClusters', '{self.cluster_name}')]",
                "customLocationName": self.custom_location_name,
                "extensionInfix": "/providers/Microsoft.KubernetesConfiguration/extensions/",
                "location": self.location or "[resourceGroup().location]",
            },
            "resources": [],
        }
        self._symphony_target_template: dict = {
            "type": "Microsoft.Symphony/targets",
            "name": self.target_name,
            "location": "[variables('location')]",
            "apiVersion": "2023-05-22-preview",
            "extendedLocation": {
                "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
                "type": "CustomLocation",
            },
            "properties": {
                "scope": cluster_namespace,
                "version": "0.1.1",
                "displayName": self.target_name,
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
        configuration: Optional[dict] = None,
        release_train: str = "private-preview",
    ):
        target_version = self.version_def.extension_to_vers_map.get(extension_type)
        if target_version:
            extension = {
                "type": "Microsoft.KubernetesConfiguration/extensions",
                "apiVersion": "2022-03-01",
                "name": name,
                "properties": {
                    "extensionType": extension_type,
                    "autoUpgradeMinorVersion": False,
                    "scope": {"cluster": {"releaseNamespace": self.cluster_namespace}},
                    "version": target_version,
                    "releaseTrain": release_train,
                    "configurationSettings": {},
                },
                "scope": f"Microsoft.Kubernetes/connectedClusters/{self.cluster_name}",
            }
            if configuration:
                extension["properties"]["configurationSettings"].update(configuration)
            self.resources.append(extension)
            self.extension_ids.append(f"[concat(variables('clusterId'), variables('extensionInfix'), '{name}')]")

            if self.create_sync_rules:
                # TODO: self.version_def.extension_to_rp_map
                sync_rule = {
                    "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                    "apiVersion": "2021-08-31-preview",
                    "name": f"{self.custom_location_name}/{self.custom_location_name}-{extension_type.split()[-1]}-sync",
                    "location": "[variables('location')]",
                    "properties": {
                        "priority": self.get_next_priority(),
                        "selector": {
                            "matchLabels": {
                                "management.azure.com/provider-name": self.version_def.extension_to_rp_map[
                                    extension_type
                                ]
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
                "namespace": self.custom_location_namespace,
                "displayName": self.custom_location_name,
                "clusterExtensionIds": self.extension_ids,
            },
            "dependsOn": self.extension_ids,
        }
        self.resources.append(payload)

    def add_bluefin_instance(self, name: str):
        payload = {
            "type": "Microsoft.Bluefin/instances",
            "apiVersion": "2023-06-26-preview",
            "name": name,
            "location": "[variables('location')]",
            "extendedLocation": {
                "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
                "type": "CustomLocation",
            },
            "properties": {},
            "dependsOn": [
                "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
            ],
        }
        self.resources.append(payload)

    def add_std_symphony_components(self):
        from .components import get_akri, get_e4in, get_observability, get_opcua_broker

        # TODO: Primitive pattern
        obs_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.obs.value)
        if obs_version:
            self.symphony_components.append(get_observability(version=obs_version))

        e4in_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.e4in.value)
        if e4in_version:
            self.symphony_components.append(get_e4in(version=e4in_version))

        akri_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.akri.value)
        if akri_version:
            self.symphony_components.append(
                get_akri(
                    version=akri_version,
                    opcua_discovery_endpoint=self.kwargs.get("opcua_discovery_endpoint"),
                    kubernetes_distro=self.kwargs.get("kubernetes_distro", "k8s"),
                )
            )

        opcua_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.opcua.value)
        if opcua_version:
            self.symphony_components.append(
                get_opcua_broker(
                    version=opcua_version,
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
    from uuid import uuid4

    from azure.cli.core.azclierror import AzureResponseError
    from azure.core.exceptions import HttpResponseError
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.resource import ResourceManagementClient
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
    from rich.table import Table

    version_def = process_deployable_version(aio_version, **kwargs)
    detail_aio_version = kwargs.get("detail_aio_version", False)
    if detail_aio_version:
        console = Console()
        table = Table(title=f"Azure IoT Ops {version_def.version}")
        table.add_column("Component", justify="left", style="cyan")
        table.add_column("Version", justify="left", style="magenta")
        for moniker in version_def.moniker_to_version_map:
            table.add_row(moniker, version_def.moniker_to_version_map[moniker])
        console.print(table)
        return

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

    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.iotoperations.value],
        name=EdgeExtensionName.iotoperations.value,
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "default",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
        },
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.mq.value],
        name=EdgeExtensionName.mq.value,
        configuration={
            "global.quickstart": True,
            "global.openTelemetryCollectorAddr": get_otel_collector_addr(cluster_namespace, True),
        },
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.processor.value],
        name=EdgeExtensionName.processor.value,
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "microsoft.bluefin",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
        },
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.assets.value],
        name=EdgeExtensionName.assets.value,
    )
    manifest_builder.add_custom_location()
    manifest_builder.add_std_symphony_components()

    if EdgeServiceMoniker.bluefin.value in version_def.moniker_to_version_map:
        manifest_builder.add_bluefin_instance(name=kwargs["processor_instance_name"])

    if kwargs.get("show_template"):
        return manifest_builder.manifest

    with Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        "Elapsed:",
        TimeElapsedColumn(),
        transient=False,
        disable=no_progress,
    ) as progress:
        deployment_name = f"azedge.init.pas.{str(uuid4()).replace('-', '')}"
        deployment_params = {
            "properties": {
                "mode": "Incremental",
                "template": manifest_builder.manifest,
            }
        }

        try:
            if kwargs.get("what_if"):
                from azure.cli.command_modules.resource.custom import format_what_if_operation_result

                progress.add_task(description=f"What-if of deploying AIO version: {version_def.version}", total=None)
                what_if_deployment = resource_client.deployments.begin_what_if(
                    resource_group_name=resource_group_name,
                    deployment_name=deployment_name,
                    parameters=deployment_params,
                ).result()
                progress.stop()
                print(format_what_if_operation_result(what_if_operation_result=what_if_deployment))

                return

            progress.add_task(description=f"Deploying AIO version: {version_def.version}", total=None)
            deployment = resource_client.deployments.begin_create_or_update(
                resource_group_name=resource_group_name,
                deployment_name=deployment_name,
                parameters=deployment_params,
            ).result()
        except HttpResponseError as e:
            # TODO: repeated error messages.
            raise AzureResponseError(e.message)
        except KeyboardInterrupt:
            return

        # TODO: result structure
        result = {}
        result["provisioningState"] = deployment.properties.provisioning_state
        result["correlationId"] = deployment.properties.correlation_id
        result["name"] = deployment.name
        result["aioBundle"] = manifest_builder.version_def.moniker_to_version_map
        result["resourceIds"] = [resource.id for resource in deployment.properties.output_resources]

        return result


def process_deployable_version(aio_version: str, **kwargs) -> AioVersionDef:
    from ...util import assemble_nargs_to_dict

    base_version_def = get_aio_version_def(version=aio_version)
    custom_version = kwargs.get("custom_version")
    only_deploy_custom = kwargs.get("only_deploy_custom")

    if not custom_version:
        return base_version_def

    custom_version_map = assemble_nargs_to_dict(custom_version)
    # Basic moniker validation.
    monikers = set(EdgeServiceMoniker.list())
    for key in custom_version_map:
        if key not in monikers:
            raise ValueError(f"Moniker '{key}' is not supported.")

    base_version_def.set_moniker_to_version_map(custom_version_map, only_deploy_custom)
    return base_version_def
