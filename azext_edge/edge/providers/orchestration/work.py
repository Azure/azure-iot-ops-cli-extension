# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from enum import IntEnum
from time import sleep
from typing import Dict, Tuple
from uuid import uuid4

from azure.cli.core.azclierror import AzureResponseError
from azure.core.exceptions import HttpResponseError
from rich.console import NewLine
from rich.live import Live
from rich.padding import Padding
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.style import Style
from rich.table import Table
from knack.log import get_logger

from ...util import get_timestamp_now_utc
from ...util.x509 import DEFAULT_EC_ALGO
from .template import TEMPLATE_MANAGER, TemplateVer

logger = get_logger(__name__)


class WorkCategoryKey(IntEnum):
    CSI_DRIVER = 1
    TLS_CA = 2
    DEPLOY_AIO = 3


class WorkStepKey(IntEnum):
    SP = 1
    KV_CLOUD_AP = 2
    KV_CLOUD_SEC = 3
    KV_CSI_DEPLOY = 4
    KV_CSI_CLUSTER = 5
    TLS_CERT = 6
    TLS_CLUSTER = 7


class WorkRecord:
    def __init__(self, title: str):
        self.title = title


CLUSTER_SECRET_REF = "aio-akv-sp"
CLUSTER_SECRET_CLASS_NAME = "aio-default-spc"


class WorkDisplay:
    def __init__(self):
        self._categories: Dict[int, Tuple[WorkRecord, bool]] = {}
        self._steps: Dict[int, Dict[int, str]] = {}

    def add_category(self, category: WorkCategoryKey, title: str, skipped: bool = False):
        self._categories[category] = (WorkRecord(title), skipped)
        self._steps[category] = {}

    def add_step(self, category: WorkCategoryKey, step: WorkStepKey, description: str):
        self._steps[category][step] = WorkRecord(description)

    @property
    def categories(self) -> Dict[int, Tuple[WorkRecord, bool]]:
        return self._categories

    @property
    def steps(self) -> Dict[int, Dict[int, WorkRecord]]:
        return self._steps


class WorkManager:
    def __init__(self, **kwargs):
        self.display = WorkDisplay()
        self._progress_bar = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
        )
        self._work_name = f"aziotops.init.{str(uuid4()).replace('-', '')}"
        self._no_progress: bool = kwargs.get("no_progress", False)
        self._no_block: bool = kwargs.get("no_block", False)
        self._no_deploy: bool = kwargs.get("no_deploy", False)
        self._keyvault_resource_id = kwargs.get("keyvault_resource_id")
        if self._keyvault_resource_id:
            self._keyvault_name = self._keyvault_resource_id.split("/")[-1]
        self._keyvault_secret_name = kwargs.get("keyvault_secret_name")
        self._sp_app_id = kwargs.get("service_principal_app_id")
        self._sp_obj_id = kwargs.get("service_principal_object_id")
        self._tls_ca_path = kwargs.get("tls_ca_path")
        self._tls_ca_key_path = kwargs.get("tls_ca_key_path")
        self._tls_insecure = kwargs.get("tls_insecure", False)
        self._progress_shown = False
        self._render_progress = not self._no_progress
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=self._render_progress)
        self._completed_steps: Dict[int, int] = {}
        self._subscription_id = kwargs.get("subscription_id")
        self._template_manager = TEMPLATE_MANAGER
        self._cluster_secret_ref = CLUSTER_SECRET_REF
        self._cluster_secret_class_name = CLUSTER_SECRET_CLASS_NAME
        self._cmd = kwargs.get("cmd")
        self._kwargs = kwargs

        self._build_display()

    def _build_display(self):
        kv_csi_cat_desc = "KeyVault CSI Driver"
        self.display.add_category(WorkCategoryKey.CSI_DRIVER, kv_csi_cat_desc, skipped=not self._keyvault_resource_id)

        if self._sp_app_id:
            sp_desc = f"Use app '[green]{self._sp_app_id}[/green]'"
        elif self._sp_obj_id:
            sp_desc = f"Use SP object Id '[green]{self._sp_obj_id}[/green]'"
        else:
            sp_desc = "Created app"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.SP, description=sp_desc)

        kv_cloud_ap_desc = "Ensure KeyVault{}access policy"
        kv_cloud_ap_desc = kv_cloud_ap_desc.format(
            f" '[green]{self._keyvault_name}[/green]' " if self._keyvault_resource_id else " "
        )
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_AP, description=kv_cloud_ap_desc)

        kv_cloud_sec_desc = (
            f"Validate secret name '[green]{self._keyvault_secret_name}[/green]'"
            if self._keyvault_secret_name
            else "Created secret"
        )
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_SEC, description=kv_cloud_sec_desc)

        kv_csi_deploy_desc = "Deploy driver to cluster"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_DEPLOY, description=kv_csi_deploy_desc)

        kv_csi_configure_desc = "Configure driver"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_CLUSTER, description=kv_csi_configure_desc)

        # TODO @digimaun - insecure mode
        self.display.add_category(WorkCategoryKey.TLS_CA, "TLS", self._tls_insecure)
        if self._tls_ca_path:
            tls_ca_desc = "User provided CA"
        else:
            tls_ca_desc = f"Generate test CA using '[green]{DEFAULT_EC_ALGO.name}[/green]'"

        self.display.add_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CERT, tls_ca_desc)
        self.display.add_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CLUSTER, "Configure cluster for tls")

        # TODO: add skip deployment
        self.display.add_category(WorkCategoryKey.DEPLOY_AIO, "Deploy AIO", skipped=self._no_deploy)

    def do_work(self):
        from .base import (
            configure_cluster_secrets,
            configure_cluster_tls,
            deploy_template,
            prepare_ca,
            prepare_keyvault_access_policy,
            prepare_keyvault_secret,
            prepare_sp,
            provision_akv_csi_driver,
            wait_for_terminal_state,
        )

        work_kpis = {}

        try:
            # CSI driver segment
            if self._keyvault_resource_id:
                work_kpis["csiDriver"] = {}
                if (
                    WorkCategoryKey.CSI_DRIVER in self.display.categories
                    and not self.display.categories[WorkCategoryKey.CSI_DRIVER][1]
                ):
                    self.render_display(category=WorkCategoryKey.CSI_DRIVER)
                    if WorkStepKey.SP in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                        sp_record = prepare_sp(deployment_name=self._work_name, **self._kwargs)
                        if sp_record.created_app:
                            self.display.steps[WorkCategoryKey.CSI_DRIVER][
                                WorkStepKey.SP
                            ].title = f"Created app '[green]{sp_record.client_id}[/green]'"
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)
                        work_kpis["csiDriver"]["spAppId"] = sp_record.client_id
                        work_kpis["csiDriver"]["spObjectId"] = sp_record.object_id
                        work_kpis["csiDriver"]["kvId"] = self._keyvault_resource_id

                        self._completed_steps[WorkStepKey.SP] = 1
                        self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                        if WorkStepKey.KV_CLOUD_AP in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                            vault_uri = prepare_keyvault_access_policy(
                                sp_record=sp_record,
                                **self._kwargs,
                            )

                            self._completed_steps[WorkStepKey.KV_CLOUD_AP] = 1
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                            if WorkStepKey.KV_CLOUD_SEC in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                                keyvault_secret_name = prepare_keyvault_secret(
                                    deployment_name=self._work_name,
                                    vault_uri=vault_uri,
                                    **self._kwargs,
                                )
                                work_kpis["csiDriver"]["kvSecretName"] = keyvault_secret_name

                                self._completed_steps[WorkStepKey.KV_CLOUD_SEC] = 1
                                self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                        if WorkStepKey.KV_CSI_DEPLOY in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                            enable_secret_rotation = not self._kwargs.get("disable_secret_rotation", False)
                            enable_secret_rotation = "true" if enable_secret_rotation else "false"
                            work_kpis["csiDriver"]["rotationPollInterval"] = self._kwargs.get("rotation_poll_interval")
                            work_kpis["csiDriver"]["enableSecretRotation"] = enable_secret_rotation

                            provision_akv_csi_driver(enable_secret_rotation=enable_secret_rotation, **self._kwargs)

                            self._completed_steps[WorkStepKey.KV_CSI_DEPLOY] = 1
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                        if WorkStepKey.KV_CSI_CLUSTER in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                            configure_cluster_secrets(
                                cluster_secret_ref=self._cluster_secret_ref,
                                cluster_akv_secret_class_name=self._cluster_secret_class_name,
                                sp_record=sp_record,
                                **self._kwargs,
                            )

                            self._completed_steps[WorkStepKey.KV_CSI_CLUSTER] = 1
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)
            else:
                if not self._render_progress:
                    logger.warning("Skipped AKV CSI driver setup as requested.")

            # TLS segment
            work_kpis["tls"] = {}
            if (
                WorkCategoryKey.TLS_CA in self.display.categories
                and not self.display.categories[WorkCategoryKey.TLS_CA][1]
            ):
                self.render_display(category=WorkCategoryKey.TLS_CA)
                # TODO: support ca file path, update workkpis with them
                public_ca, private_key, secret_name, cm_name = prepare_ca(ca_path=None, key_path=None, **self._kwargs)
                work_kpis["tls"]["aioTrustConfigMap"] = cm_name
                work_kpis["tls"]["aioTrustSecretName"] = secret_name

                self._completed_steps[WorkStepKey.TLS_CERT] = 1
                self.render_display(category=WorkCategoryKey.TLS_CA)

                configure_cluster_tls(
                    public_ca=public_ca,
                    private_key=private_key,
                    secret_name=secret_name,
                    cm_name=cm_name,
                    **self._kwargs,
                )
                self._completed_steps[WorkStepKey.TLS_CLUSTER] = 1
                self.render_display(category=WorkCategoryKey.TLS_CA)

            # Deployment segment
            if self._no_deploy:
                if not self._render_progress:
                    logger.warning("Skipped deployment of AIO as requested.")
                return work_kpis

            if (
                WorkCategoryKey.DEPLOY_AIO in self.display.categories
                and not self.display.categories[WorkCategoryKey.DEPLOY_AIO][1]
            ):
                self.render_display(category=WorkCategoryKey.DEPLOY_AIO)
                template = self._template_manager.version_map["1.0.0.0"]
                template, parameters = self.build_template()

                deployment_result, deployment_poller = deploy_template(
                    template=template.content, parameters=parameters, deployment_name=self._work_name, **self._kwargs
                )
                work_kpis.update(deployment_result)

                if self._no_block:
                    return work_kpis

                # Pattern needs work, its this way to dynamically update UI
                self.display.categories[WorkCategoryKey.DEPLOY_AIO][0].title = (
                    f"[link={deployment_result['deploymentLink']}]"
                    f"{self.display.categories[WorkCategoryKey.DEPLOY_AIO][0].title}[/link]"
                )
                self.render_display(category=WorkCategoryKey.DEPLOY_AIO)

                terminal_deployment = wait_for_terminal_state(deployment_poller)
                deployment_result["deploymentState"]["status"] = terminal_deployment.properties.provisioning_state
                deployment_result["deploymentState"]["correlationId"] = terminal_deployment.properties.correlation_id
                deployment_result["deploymentState"]["aioVersion"] = template.component_vers
                deployment_result["deploymentState"]["timestampUtc"]["ended"] = get_timestamp_now_utc()
                deployment_result["deploymentState"]["resources"] = [
                    resource.id.split(
                        f"/subscriptions/{self._subscription_id}/resourceGroups/"
                        f"{self._kwargs['resource_group_name']}/providers/"
                    )[1]
                    for resource in terminal_deployment.properties.output_resources
                ]

                work_kpis.update(deployment_result)
                return work_kpis

        except HttpResponseError as e:
            # TODO: repeated error messages.
            raise AzureResponseError(e.message)
        except KeyboardInterrupt:
            return
        finally:
            self.stop_display()

    def render_display(self, category: WorkCategoryKey = None, step: WorkStepKey = None):
        if self._render_progress:
            grid = Table.grid(expand=False)
            grid.add_column()
            header_grid = Table.grid(expand=False)
            header_grid.add_column()

            header_grid.add_row(NewLine(1))
            header_grid.add_row("[light_slate_gray]Azure IoT Operations init", style=Style(bold=True))
            header_grid.add_row(f"Workflow Id: [dark_orange3]{self._work_name.split('.')[2]}")
            header_grid.add_row(NewLine(1))

            content_grid = Table.grid(expand=False)
            content_grid.add_column(max_width=3)
            content_grid.add_column()

            active_str = "[cyan]->[/cyan] "
            complete_str = "[green]:heavy_check_mark:[/green]"
            for c in self.display.categories:
                cat_prefix = active_str if c == category else ""
                content_grid.add_row(
                    cat_prefix,
                    f"{self.display.categories[c][0].title} "
                    f"{'[[dark_khaki]skipped[/dark_khaki]]' if self.display.categories[c][1] else ''}",
                )
                if c in self.display.steps:
                    for s in self.display.steps[c]:
                        step_prefix = complete_str if s in self._completed_steps else "-"
                        content_grid.add_row(
                            "",
                            Padding(
                                f"{step_prefix} {self.display.steps[c][s].title} ",
                                (0, 0, 0, 2),
                            ),
                        )
            content_grid.add_row(NewLine(1), NewLine(1))

            footer_grid = Table.grid(expand=False)
            footer_grid.add_column()

            footer_grid.add_row(self._progress_bar)
            footer_grid.add_row(NewLine(1))

            grid.add_row(header_grid)
            grid.add_row(content_grid)
            grid.add_row(footer_grid)

            if not self._progress_shown:
                self._task_id = self._progress_bar.add_task(description="Work.", total=None)
                self._progress_shown = True
            self._live.update(grid)
            sleep(0.5)  # min presentation delay

        if self._render_progress and not self._live.is_started:
            self._live.start(True)

    def stop_display(self):
        if self._render_progress and self._live.is_started:
            if self._progress_shown:
                self._progress_bar.update(self._task_id, description="DONE!")
                sleep(0.5)
            self._live.stop()

    def build_template(self) -> Tuple[TemplateVer, dict]:
        # TODO refactor
        template = self._template_manager.version_map["1.0.0.0"]
        parameters = {}
        parameters["clusterName"] = {"value": self._kwargs["cluster_name"]}
        if self._kwargs["location"]:
            parameters["location"] = {"value": self._kwargs["location"]}
            parameters["clusterLocation"] = {"value": self._kwargs["location"]}  # TODO:
        if self._kwargs["custom_location_name"]:
            parameters["customLocationName"] = {"value": self._kwargs["custom_location_name"]}
        if self._kwargs["custom_location_name"]:
            parameters["customLocationName"] = {"value": self._kwargs["custom_location_name"]}
        if self._kwargs["simulate_plc"]:
            parameters["simulatePlc"] = {"value": self._kwargs["simulate_plc"]}
        if self._kwargs["opcua_discovery_endpoint"]:
            parameters["opcuaDiscoveryEndpoint"] = {"value": self._kwargs["opcua_discovery_endpoint"]}
        if self._kwargs["target_name"]:
            parameters["targetName"] = {"value": self._kwargs["target_name"]}
        if self._kwargs["processor_instance_name"]:
            parameters["dataProcessorInstanceName"] = {"value": self._kwargs["processor_instance_name"]}

        parameters["dataProcessorSecrets"] = {
            "value": {
                "enabled": True,
                "secretProviderClassName": self._cluster_secret_class_name,
                "servicePrincipalSecretRef": self._cluster_secret_ref,
            }
        }
        parameters["mqSecrets"] = {
            "value": {
                "enabled": True,
                "secretProviderClassName": self._cluster_secret_class_name,
                "servicePrincipalSecretRef": self._cluster_secret_ref,
            }
        }
        parameters["opcUaBrokerSecrets"] = {
            "value": {"kind": "csi", "csiServicePrincipalSecretRef": self._cluster_secret_ref}
        }

        template.content["variables"]["AIO_CLUSTER_RELEASE_NAMESPACE"] = self._kwargs["cluster_namespace"]
        return template, parameters
