# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Optional

from .pas_versions import (
    PasVersionDef,
    EdgeServiceMoniker,
    get_pas_version_def,
    extension_name_to_type_map,
    EdgeExtensionName,
    DEPLOYABLE_PAS_VERSION,
)
from ...util import get_timestamp_now_utc


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
        version_def: PasVersionDef,
        **kwargs,
    ):
        self.cluster_name = cluster_name
        self.cluster_namespace = cluster_namespace
        self.custom_location_name = custom_location_name
        self.custom_location_namespace = custom_location_namespace
        self.version_def = version_def

        self.last_sync_priority: int = 0
        self.symphony_components: List[dict] = []
        self.resources: List[dict] = []
        self.extension_ids: List[str] = []

        self.kwargs = kwargs
        self.create_sync_rules = self.kwargs.get("create_sync_rules")
        self.target_name = self.kwargs.get("target_name")

        self._manifest: dict = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "0.1.2.0",
            "metadata": {"description": "Az Edge CLI PAS deployment."},
            "variables": {
                "clusterId": f"[resourceId('Microsoft.Kubernetes/connectedClusters', '{self.cluster_name}')]",
                "customLocationName": self.custom_location_name,
                "location": self.kwargs.get("location") or "[resourceGroup().location]",
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
                "version": "1.2.0",
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
        release_train: str = "private-preview",
        configuration: Optional[dict] = None,
        identity: Optional[dict] = None,
        skip_sync_rule: bool = False,
        skip_custom_location_dep: bool = False,
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
            if identity:
                extension["identity"] = identity
            self.resources.append(extension)
            if not skip_custom_location_dep:
                self.extension_ids.append(
                    "[concat(variables('clusterId'), "
                    f"'/providers/Microsoft.KubernetesConfiguration/extensions/{name}')]"
                )

            if self.create_sync_rules and not skip_sync_rule and not skip_custom_location_dep:
                # TODO: self.version_def.extension_to_rp_map
                sync_rule = {
                    "type": "Microsoft.ExtendedLocation/customLocations/resourceSyncRules",
                    "apiVersion": "2021-08-31-preview",
                    "name": f"{self.custom_location_name}/"
                    f"{self.custom_location_name}-{extension_type.split()[-1]}-sync",
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
        from .components import (
            get_akri_opcua_asset,
            get_akri_opcua_discovery_daemonset,
            get_e4in,
            get_observability,
            get_opcua_broker,
        )

        # TODO: Primitive pattern
        obs_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.obs.value)
        if obs_version:
            self.symphony_components.append(get_observability(version=obs_version))

        e4in_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.e4in.value)
        if e4in_version:
            self.symphony_components.append(get_e4in(version=e4in_version))

        akri_version = self.version_def.moniker_to_version_map.get(EdgeServiceMoniker.akri.value)
        if akri_version:
            self.symphony_components.append(get_akri_opcua_discovery_daemonset())
            self.symphony_components.append(
                get_akri_opcua_asset(
                    opcua_discovery_endpoint=self.kwargs.get("opcua_discovery_endpoint"),
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
    **kwargs,
):
    from uuid import uuid4

    from azure.cli.core.azclierror import AzureResponseError
    from azure.core.exceptions import HttpResponseError
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.resource import ResourceManagementClient
    from rich.console import Console, NewLine
    from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.live import Live

    version_def = process_deployable_version(**kwargs)
    show_pas_version = kwargs.get("show_pas_version", False)
    if show_pas_version:
        console = Console()
        table = Table(title=f"Project Alice Springs {version_def.version}")
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
        version_def=version_def,
        **kwargs,
    )

    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.alicesprings.value],
        name=EdgeExtensionName.alicesprings.value,
        identity={"type": "SystemAssigned"},
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "default",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
        },
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.dataplane.value],
        name=EdgeExtensionName.dataplane.value,
        identity={"type": "SystemAssigned"},
        configuration={
            "global.quickstart": True,
            "global.openTelemetryCollectorAddr": get_otel_collector_addr(cluster_namespace, True),
        },
        skip_sync_rule=True,
        skip_custom_location_dep=True,
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.processor.value],
        name=EdgeExtensionName.processor.value,
        configuration={
            "Microsoft.CustomLocation.ServiceAccount": "default",
            "otelCollectorAddress": get_otel_collector_addr(cluster_namespace),
            "genevaCollectorAddress": get_geneva_metrics_addr(cluster_namespace),
            "tracePodFormat": "OFF",
        },
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.assets.value],
        name=EdgeExtensionName.assets.value,
    )
    manifest_builder.add_extension(
        extension_type=extension_name_to_type_map[EdgeExtensionName.akri.value],
        name=EdgeExtensionName.akri.value,
        configuration={"webhookConfiguration.enabled": False},
        skip_sync_rule=True,
        skip_custom_location_dep=True,
    )
    manifest_builder.add_custom_location()
    manifest_builder.add_std_symphony_components()

    if EdgeServiceMoniker.bluefin.value in version_def.moniker_to_version_map:
        manifest_builder.add_bluefin_instance(name=kwargs["processor_instance_name"])

    if kwargs.get("show_template"):
        return manifest_builder.manifest

    no_progress: bool = kwargs.get("no_progress", False)
    block: bool = kwargs.get("block", True)

    grid = Table.grid(expand=False)
    with Live(grid, transient=True, refresh_per_second=8) as live:
        init_progress = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
            disable=(no_progress is True) or (block is False),
        )

        deployment_name = f"azedge.init.pas.{str(uuid4()).replace('-', '')}"
        deployment_params = {
            "properties": {
                "mode": "Incremental",
                "template": manifest_builder.manifest,
            }
        }

        what_if = kwargs.get("what_if")
        header = "Deployment: {} in progress..."
        if what_if:
            header = header.format("[orange3]What-If? analysis[/orange3]")
        else:
            header = header.format(f"[medium_purple4]{deployment_name}[/medium_purple4]")

        grid = Table.grid(expand=False)
        grid.add_column()

        grid.add_row(NewLine(1))
        grid.add_row(header)
        grid.add_row(NewLine(1))
        grid.add_row(init_progress)
        live.update(grid, refresh=True)

        try:
            init_progress.add_task(description=f"PAS version: {version_def.version}", total=None)
            if what_if:
                from azure.cli.command_modules.resource.custom import format_what_if_operation_result

                what_if_deployment = resource_client.deployments.begin_what_if(
                    resource_group_name=resource_group_name,
                    deployment_name=deployment_name,
                    parameters=deployment_params,
                ).result()
                init_progress.stop()
                print(format_what_if_operation_result(what_if_operation_result=what_if_deployment))
                return

            deployment = resource_client.deployments.begin_create_or_update(
                resource_group_name=resource_group_name,
                deployment_name=deployment_name,
                parameters=deployment_params,
            )

            result = {
                "deploymentName": deployment_name,
                "resourceGroup": resource_group_name,
                "clusterName": cluster_name,
                "namespace": cluster_namespace,
                "deploymentState": {"timestampUtc": {"started": get_timestamp_now_utc()}},
            }
            if not block:
                result["deploymentState"]["status"] = deployment.status()
                return result

            deployment = deployment.result()
            result["deploymentState"]["status"] = deployment.properties.provisioning_state
            result["deploymentState"]["correlationId"] = deployment.properties.correlation_id
            result["deploymentState"]["pasVersion"] = manifest_builder.version_def.moniker_to_version_map
            result["deploymentState"]["timestampUtc"]["ended"] = get_timestamp_now_utc()
            result["deploymentState"]["resourceIds"] = [
                resource.id for resource in deployment.properties.output_resources
            ]

            return result

        except HttpResponseError as e:
            # TODO: repeated error messages.
            raise AzureResponseError(e.message)
        except KeyboardInterrupt:
            return


def process_deployable_version(**kwargs) -> PasVersionDef:
    from ...util import assemble_nargs_to_dict

    base_version_def = get_pas_version_def(version=DEPLOYABLE_PAS_VERSION)
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
