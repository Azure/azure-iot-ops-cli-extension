# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import IntEnum
from time import sleep
from typing import Dict, Tuple
from uuid import uuid4

from azure.cli.core.azclierror import AzureResponseError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import NewLine
from rich.live import Live
from rich.padding import Padding
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.style import Style
from rich.table import Table

from ...util import get_timestamp_now_utc
from ...util.x509 import DEFAULT_EC_ALGO
from .template import CURRENT_TEMPLATE, TemplateVer

from time import sleep

logger = get_logger(__name__)


class WorkCategoryKey(IntEnum):
    PRE_CHECK = 1
    CSI_DRIVER = 2
    TLS_CA = 3
    DEPLOY_AIO = 4


class WorkStepKey(IntEnum):
    SP = 1
    KV_CLOUD_PERM_MODEL = 2
    KV_CLOUD_AP = 3
    KV_CLOUD_SEC = 4
    KV_CSI_DEPLOY = 5
    KV_CSI_CLUSTER = 6
    TLS_CERT = 7
    TLS_CLUSTER = 8

    REG_RP = 9


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
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.display = WorkDisplay()
        self._progress_bar = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
        )
        self._work_id = uuid4().hex
        self._work_name = f"aziotops.init.{self._work_id}"
        self._no_progress: bool = kwargs.get("no_progress", False)
        self._no_block: bool = kwargs.get("no_block", False)
        self._no_deploy: bool = kwargs.get("no_deploy", False)
        self._no_tls: bool = kwargs.get("no_tls", False)
        self._cmd = kwargs.get("cmd")
        self._keyvault_resource_id = kwargs.get("keyvault_resource_id")
        if self._keyvault_resource_id:
            self._keyvault_name = self._keyvault_resource_id.split("/")[-1]
        self._keyvault_sat_secret_name = kwargs["keyvault_sat_secret_name"]
        self._sp_app_id = kwargs.get("service_principal_app_id")
        self._sp_obj_id = kwargs.get("service_principal_object_id")
        self._tls_ca_path = kwargs.get("tls_ca_path")
        self._tls_ca_key_path = kwargs.get("tls_ca_key_path")
        self._tls_insecure = kwargs.get("tls_insecure", False)
        self._progress_shown = False
        self._render_progress = not self._no_progress
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=self._render_progress)
        self._completed_steps: Dict[int, int] = {}
        self._subscription_id = get_subscription_id(self._cmd.cli_ctx)
        kwargs["subscription_id"] = self._subscription_id  # TODO: temporary
        self._cluster_secret_ref = CLUSTER_SECRET_REF
        self._cluster_secret_class_name = CLUSTER_SECRET_CLASS_NAME
        self._kwargs = kwargs

        self._build_display()

    def _build_display(self):
        pre_check_cat_desc = "Pre-checks"
        self.display.add_category(WorkCategoryKey.PRE_CHECK, pre_check_cat_desc)
        self.display.add_step(WorkCategoryKey.PRE_CHECK, WorkStepKey.REG_RP, "Resource providers are registered")

        kv_csi_cat_desc = "Key Vault CSI Driver"
        self.display.add_category(WorkCategoryKey.CSI_DRIVER, kv_csi_cat_desc, skipped=not self._keyvault_resource_id)

        kv_cloud_perm_model_desc = "Verify Key Vault{}permission model"
        kv_cloud_perm_model_desc = kv_cloud_perm_model_desc.format(
            f" '[green]{self._keyvault_name}[/green]' " if self._keyvault_resource_id else " "
        )
        self.display.add_step(
            WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_PERM_MODEL, description=kv_cloud_perm_model_desc
        )

        if self._sp_app_id:
            sp_desc = f"Use app '[green]{self._sp_app_id}[/green]'"
        elif self._sp_obj_id:
            sp_desc = f"Use SP object Id '[green]{self._sp_obj_id}[/green]'"
        else:
            sp_desc = "Created app"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.SP, description=sp_desc)

        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_AP, description="Configure access policy")

        kv_cloud_sec_desc = f"Ensure secret name '[green]{self._keyvault_sat_secret_name}[/green]' for service account"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_SEC, description=kv_cloud_sec_desc)

        kv_csi_deploy_desc = "Deploy driver to cluster"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_DEPLOY, description=kv_csi_deploy_desc)

        kv_csi_configure_desc = "Configure driver"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_CLUSTER, description=kv_csi_configure_desc)

        # TODO @digimaun - MQ insecure mode
        self.display.add_category(WorkCategoryKey.TLS_CA, "TLS", self._no_tls)
        if self._tls_ca_path:
            tls_ca_desc = f"User provided CA '[green]{self._tls_ca_path}[/green]'"
        else:
            tls_ca_desc = f"Generate test CA using '[green]{DEFAULT_EC_ALGO.name}[/green]'"

        self.display.add_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CERT, tls_ca_desc)
        self.display.add_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CLUSTER, "Configure cluster for tls")

        # TODO: add skip deployment
        self.display.add_category(WorkCategoryKey.DEPLOY_AIO, "Deploy IoT Operations", skipped=self._no_deploy)

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
            # Pre-check segment
            self.render_display(category=WorkCategoryKey.PRE_CHECK)
            self._completed_steps[WorkStepKey.REG_RP] = 1
            sleep(1)
            self.render_display(category=WorkCategoryKey.PRE_CHECK)

            # CSI driver segment
            if self._keyvault_resource_id:
                work_kpis["csiDriver"] = {}
                if (
                    WorkCategoryKey.CSI_DRIVER in self.display.categories
                    and not self.display.categories[WorkCategoryKey.CSI_DRIVER][1]
                ):
                    self.render_display(category=WorkCategoryKey.CSI_DRIVER)
                    if WorkStepKey.KV_CLOUD_PERM_MODEL in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                        self._completed_steps[WorkStepKey.KV_CLOUD_PERM_MODEL] = 1
                        sleep(1)
                        self.render_display(category=WorkCategoryKey.CSI_DRIVER)
                        pass

                    if WorkStepKey.SP in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                        # sp_record = prepare_sp(deployment_name=self._work_name, **self._kwargs)
                        # if sp_record.created_app:
                        #     self.display.steps[WorkCategoryKey.CSI_DRIVER][
                        #         WorkStepKey.SP
                        #     ].title = f"Created app '[green]{sp_record.client_id}[/green]'"
                        #     self.render_display(category=WorkCategoryKey.CSI_DRIVER)
                        # work_kpis["csiDriver"]["spAppId"] = sp_record.client_id
                        # work_kpis["csiDriver"]["spObjectId"] = sp_record.object_id
                        # work_kpis["csiDriver"]["keyVaultId"] = self._keyvault_resource_id
                        work_kpis["csiDriver"]["spAppId"] = "mock"
                        work_kpis["csiDriver"]["spObjectId"] = "mock"
                        work_kpis["csiDriver"]["keyVaultId"] = "mock"

                        self._completed_steps[WorkStepKey.SP] = 1
                        sleep(1)
                        self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                        if WorkStepKey.KV_CLOUD_AP in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                            # vault_uri = prepare_keyvault_access_policy(
                            #     sp_record=sp_record,
                            #     **self._kwargs,
                            # )
                            sleep(1)

                            self._completed_steps[WorkStepKey.KV_CLOUD_AP] = 1
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                            if WorkStepKey.KV_CLOUD_SEC in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                                # keyvault_sat_secret_name = prepare_keyvault_secret(
                                #     deployment_name=self._work_name,
                                #     vault_uri=vault_uri,
                                #     **self._kwargs,
                                # )
                                # work_kpis["csiDriver"]["kvSatSecretName"] = keyvault_sat_secret_name
                                work_kpis["csiDriver"]["kvSatSecretName"] = "mock"
                                sleep(1)

                                self._completed_steps[WorkStepKey.KV_CLOUD_SEC] = 1
                                self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                        if WorkStepKey.KV_CSI_DEPLOY in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                            enable_secret_rotation = not self._kwargs.get("disable_secret_rotation", False)
                            enable_secret_rotation = "true" if enable_secret_rotation else "false"
                            work_kpis["csiDriver"]["rotationPollInterval"] = self._kwargs.get("rotation_poll_interval")
                            work_kpis["csiDriver"]["enableSecretRotation"] = enable_secret_rotation

                            # akv_csi_driver_result = provision_akv_csi_driver(
                            #     enable_secret_rotation=enable_secret_rotation, **self._kwargs
                            # )
                            # work_kpis["csiDriver"]["version"] = akv_csi_driver_result["properties"]["version"]
                            sleep(1)
                            work_kpis["csiDriver"]["version"] = "mock"

                            self._completed_steps[WorkStepKey.KV_CSI_DEPLOY] = 1
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                        if WorkStepKey.KV_CSI_CLUSTER in self.display.steps[WorkCategoryKey.CSI_DRIVER]:
                            # configure_cluster_secrets(
                            #     cluster_secret_ref=self._cluster_secret_ref,
                            #     cluster_akv_secret_class_name=self._cluster_secret_class_name,
                            #     sp_record=sp_record,
                            #     **self._kwargs,
                            # )
                            sleep(1)

                            self._completed_steps[WorkStepKey.KV_CSI_CLUSTER] = 1
                            self.render_display(category=WorkCategoryKey.CSI_DRIVER)
            else:
                if not self._render_progress:
                    logger.warning("Skipped AKV CSI driver setup as requested.")

            # TLS segment
            if (
                WorkCategoryKey.TLS_CA in self.display.categories
                and not self.display.categories[WorkCategoryKey.TLS_CA][1]
            ):
                work_kpis["tls"] = {}
                self.render_display(category=WorkCategoryKey.TLS_CA)

                public_ca, private_key, secret_name, cm_name = prepare_ca(**self._kwargs)
                work_kpis["tls"]["aioTrustConfigMap"] = cm_name
                work_kpis["tls"]["aioTrustSecretName"] = secret_name

                self._completed_steps[WorkStepKey.TLS_CERT] = 1
                self.render_display(category=WorkCategoryKey.TLS_CA)

                # configure_cluster_tls(
                #     public_ca=public_ca,
                #     private_key=private_key,
                #     secret_name=secret_name,
                #     cm_name=cm_name,
                #     **self._kwargs,
                # )
                sleep(1)
                self._completed_steps[WorkStepKey.TLS_CLUSTER] = 1
                self.render_display(category=WorkCategoryKey.TLS_CA)
            else:
                if not self._render_progress:
                    logger.warning("Skipped TLS config as requested.")

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
                template, parameters = self.build_template(work_kpis=work_kpis)
                sleep(1)

                # deployment_result, deployment_poller = deploy_template(
                #     template=template.content, parameters=parameters, deployment_name=self._work_name, **self._kwargs
                # )
                # work_kpis.update(deployment_result)

                # if self._no_block:
                #     return work_kpis

                # # Pattern needs work, its this way to dynamically update UI
                # self.display.categories[WorkCategoryKey.DEPLOY_AIO][0].title = (
                #     f"[link={deployment_result['deploymentLink']}]"
                #     f"{self.display.categories[WorkCategoryKey.DEPLOY_AIO][0].title}[/link]"
                # )
                # self.render_display(category=WorkCategoryKey.DEPLOY_AIO)

                # terminal_deployment = wait_for_terminal_state(deployment_poller)
                # deployment_result["deploymentState"]["status"] = terminal_deployment.properties.provisioning_state
                # deployment_result["deploymentState"]["correlationId"] = terminal_deployment.properties.correlation_id
                # deployment_result["deploymentState"]["opsVersion"] = template.component_vers
                # deployment_result["deploymentState"]["timestampUtc"]["ended"] = get_timestamp_now_utc()
                # deployment_result["deploymentState"]["resources"] = [
                #     resource.id.split(
                #         f"/subscriptions/{self._subscription_id}/resourceGroups/"
                #         f"{self._kwargs['resource_group_name']}/providers/"
                #     )[1]
                #     for resource in terminal_deployment.properties.output_resources
                # ]

                # work_kpis.update(deployment_result)
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

    def build_template(self, work_kpis: dict) -> Tuple[TemplateVer, dict]:
        # TODO refactor, move out of work
        template = CURRENT_TEMPLATE
        parameters = {}

        for template_pair in [
            ("cluster_name", "clusterName"),
            ("location", "location"),
            ("cluster_location", "clusterLocation"),  # TODO
            ("custom_location_name", "customLocationName"),
            ("simulate_plc", "simulatePLC"),
            ("opcua_discovery_endpoint", "opcuaDiscoveryEndpoint"),
            ("target_name", "targetName"),
            ("dp_instance_name", "dataProcessorInstanceName"),
            ("mq_instance_name", "mqInstanceName"),
            ("mq_frontend_server_name", "mqFrontendServer"),
            ("mq_listener_name", "mqListenerName"),
            ("mq_broker_name", "mqBrokerName"),
            ("mq_authn_name", "mqAuthnName"),
            ("mq_frontend_replicas", "mqFrontendReplicas"),
            ("mq_frontend_workers", "mqFrontendWorkers"),
            ("mq_backend_redundancy_factor", "mqBackendRedundancyFactor"),
            ("mq_backend_workers", "mqBackendWorkers"),
            ("mq_backend_partitions", "mqBackendPartitions"),
            ("mq_mode", "mqMode"),
            ("mq_memory_profile", "mqMemoryProfile"),
            ("mq_service_type", "mqServiceType"),
        ]:
            if template_pair[0] in self._kwargs and self._kwargs[template_pair[0]] is not None:
                parameters[template_pair[1]] = {"value": self._kwargs[template_pair[0]]}

        parameters["dataProcessorCardinality"] = {
            "value": template.parameters["dataProcessorCardinality"]["defaultValue"]
        }
        for template_pair in [
            ("dp_reader_workers", "readerWorker"),
            ("dp_runner_workers", "runnerWorker"),
            ("dp_message_stores", "messageStore"),
        ]:
            if template_pair[0] in self._kwargs and self._kwargs[template_pair[0]] is not None:
                parameters["dataProcessorCardinality"]["value"][template_pair[1]] = self._kwargs[template_pair[0]]

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

        # Covers cluster_namespace
        template.content["variables"]["AIO_CLUSTER_RELEASE_NAMESPACE"] = self._kwargs["cluster_namespace"]

        tls_map = work_kpis.get("tls", {})
        if "aioTrustConfigMap" in tls_map:
            template.content["variables"]["AIO_TRUST_CONFIG_MAP"] = tls_map["aioTrustConfigMap"]
        if "aioTrustSecretName" in tls_map:
            template.content["variables"]["AIO_TRUST_SECRET_NAME"] = tls_map["aioTrustSecretName"]

        mq_insecure = self._kwargs.get("mq_insecure", False)
        if mq_insecure:
            broker_adj = False
            # This solution entirely relies on the form of the "standard" template.
            # Needs re-work after event
            for resource in template.content["resources"]:
                if resource.get("type") == "Microsoft.IoTOperationsMQ/mq/broker":
                    resource["properties"]["encryptInternalTraffic"] = False
                    broker_adj = True

                if broker_adj:
                    break

            from .template import get_insecure_mq_listener

            template.content["resources"].append(get_insecure_mq_listener())

        return template, parameters


def deploy(
    **kwargs,
):
    show_template = kwargs.get("show_template", False)
    if show_template:
        return CURRENT_TEMPLATE.content

    manager = WorkManager(**kwargs)
    return manager.do_work()
