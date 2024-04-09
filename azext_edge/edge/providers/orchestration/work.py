# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import IntEnum
from json import dumps
from time import sleep
from typing import Dict, Tuple, Union
from uuid import uuid4

from azure.cli.core.azclierror import AzureResponseError, ValidationError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import NewLine
from rich.live import Live
from rich.padding import Padding
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.style import Style
from rich.table import Table

from ...util import get_timestamp_now_utc
from ...util.x509 import DEFAULT_EC_ALGO, DEFAULT_VALID_DAYS
from .template import CURRENT_TEMPLATE, TemplateVer, get_current_template_copy

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
    KV_CLOUD_TEST = 5
    KV_CSI_DEPLOY = 6
    KV_CSI_CLUSTER = 7
    TLS_CERT = 8
    TLS_CLUSTER = 9

    REG_RP = 10
    EVAL_LOGIN_PERM = 11
    DEPLOY_AIO_MONIKER = 12


class WorkRecord:
    def __init__(self, title: str):
        self.title = title


CLUSTER_SECRET_REF = "aio-akv-sp"
CLUSTER_SECRET_CLASS_NAME = "aio-default-spc"

PRE_FLIGHT_SUCCESS_STATUS = "succeeded"


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
        self._no_preflight: bool = kwargs.get("no_preflight", False)
        self._cmd = kwargs.get("cmd")
        self._keyvault_resource_id = kwargs.get("keyvault_resource_id")
        if self._keyvault_resource_id:
            self._keyvault_name = self._keyvault_resource_id.split("/")[-1]
        self._keyvault_sat_secret_name = kwargs["keyvault_spc_secret_name"]
        self._sp_app_id = kwargs.get("service_principal_app_id")
        self._sp_obj_id = kwargs.get("service_principal_object_id")
        self._tls_ca_path = kwargs.get("tls_ca_path")
        self._tls_ca_key_path = kwargs.get("tls_ca_key_path")
        self._tls_ca_valid_days = kwargs.get("tls_ca_valid_days", DEFAULT_VALID_DAYS)
        self._tls_insecure = kwargs.get("tls_insecure", False)
        self._template_path = kwargs.get("template_path")
        self._progress_shown = False
        self._render_progress = not self._no_progress
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=self._render_progress)
        self._completed_steps: Dict[int, int] = {}
        self._subscription_id = get_subscription_id(self._cmd.cli_ctx)
        kwargs["subscription_id"] = self._subscription_id  # TODO: temporary
        self._cluster_secret_ref = CLUSTER_SECRET_REF
        self._cluster_secret_class_name = CLUSTER_SECRET_CLASS_NAME
        # TODO: Make cluster target with KPIs
        self._cluster_namespace = kwargs.get("cluster_namespace")
        self._custom_location_name = kwargs.get("custom_location_name")
        self._deploy_rsync_rules = not kwargs.get("disable_rsync_rules", False)
        self._connected_cluster = None
        self._kwargs = kwargs

        self._build_display()

    def _build_display(self):
        pre_check_cat_desc = "Pre-Flight"
        self.display.add_category(WorkCategoryKey.PRE_CHECK, pre_check_cat_desc, skipped=self._no_preflight)
        self.display.add_step(
            WorkCategoryKey.PRE_CHECK, WorkStepKey.REG_RP, "Ensure registered IoT Ops resource providers"
        )
        self.display.add_step(WorkCategoryKey.PRE_CHECK, WorkStepKey.EVAL_LOGIN_PERM, "Verify pre-flight deployment")

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

        self.display.add_step(
            WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_AP, description="Configure access policy"
        )

        kv_cloud_sec_desc = f"Ensure secret name '[green]{self._keyvault_sat_secret_name}[/green]' for service account"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_SEC, description=kv_cloud_sec_desc)

        kv_sp_test_desc = "Test SP access"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_TEST, description=kv_sp_test_desc)

        kv_csi_deploy_desc = "Deploy driver to cluster"
        self.display.add_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_DEPLOY, description=kv_csi_deploy_desc)

        kv_csi_configure_desc = "Configure driver"
        self.display.add_step(
            WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_CLUSTER, description=kv_csi_configure_desc
        )

        # TODO @digimaun - MQ insecure mode
        self.display.add_category(WorkCategoryKey.TLS_CA, "TLS", self._no_tls)
        if self._tls_ca_path:
            tls_ca_desc = f"User provided CA '[green]{self._tls_ca_path}[/green]'"
        else:
            tls_ca_desc = (
                f"Generate test CA using '[green]{DEFAULT_EC_ALGO.name}[/green]' "
                f"valid for '[green]{self._tls_ca_valid_days}[/green]' days"
            )

        self.display.add_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CERT, tls_ca_desc)
        self.display.add_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CLUSTER, "Configure cluster for tls")

        self.display.add_category(WorkCategoryKey.DEPLOY_AIO, "Deploy IoT Operations", skipped=self._no_deploy)
        deployment_moniker = "Custom template" if self._template_path else CURRENT_TEMPLATE.moniker
        self.display.add_step(
            WorkCategoryKey.DEPLOY_AIO,
            WorkStepKey.DEPLOY_AIO_MONIKER,
            f"[cyan]{deployment_moniker}[/cyan]",
        )

    def do_work(self):  # noqa: C901
        from ..edge_api.keyvault import KEYVAULT_API_V1
        from .base import (
            configure_cluster_secrets,
            configure_cluster_tls,
            deploy_template,
            eval_secret_via_sp,
            prepare_ca,
            prepare_keyvault_access_policy,
            prepare_keyvault_secret,
            prepare_sp,
            provision_akv_csi_driver,
            throw_if_iotops_deployed,
            validate_keyvault_permission_model,
            verify_arc_cluster_config,
            verify_cluster_and_use_location,
            verify_custom_location_namespace,
            verify_custom_locations_enabled,
            wait_for_terminal_state,
        )
        from .host import verify_cli_client_connections
        from .permissions import verify_write_permission_against_rg
        from .rp_namespace import register_providers

        work_kpis = {}

        try:
            # Ensure connection to ARM if needed. Show remediation error message otherwise.
            if any([not self._no_preflight, not self._no_deploy, self._keyvault_resource_id]):
                verify_cli_client_connections(include_graph=bool(self._keyvault_resource_id))
                # cluster_location uses actual connected cluster location. Same applies to location IF not provided.
                self._connected_cluster = verify_cluster_and_use_location(self._kwargs)
                verify_arc_cluster_config(self._connected_cluster)

            # Always run this check
            if not self._keyvault_resource_id and not KEYVAULT_API_V1.is_deployed():
                raise ValidationError(error_msg="--kv-id is required when the Key Vault CSI driver is not installed.")

            # Pre-check segment
            if (
                WorkCategoryKey.PRE_CHECK in self.display.categories
                and not self.display.categories[WorkCategoryKey.PRE_CHECK][1]
            ):
                self.render_display(category=WorkCategoryKey.PRE_CHECK)

                # WorkStepKey.REG_RP
                register_providers(**self._kwargs)

                self.complete_step(WorkCategoryKey.PRE_CHECK, WorkStepKey.REG_RP)

                # WorkStepKey.EVAL_LOGIN_PERM -- rest of pre-flight checks are under this step.
                if self._connected_cluster:
                    throw_if_iotops_deployed(self._connected_cluster)
                    verify_custom_locations_enabled()
                    verify_custom_location_namespace(
                        connected_cluster=self._connected_cluster,
                        custom_location_name=self._custom_location_name,
                        namespace=self._cluster_namespace,
                    )

                if self._deploy_rsync_rules:
                    verify_write_permission_against_rg(
                        **self._kwargs,
                    )

                # Use pre-flight deployment as a shortcut to evaluate permissions
                template, parameters = self.build_template(work_kpis=work_kpis)
                deployment_result, deployment_poller = deploy_template(
                    template=template.content,
                    parameters=parameters,
                    deployment_name=self._work_name,
                    pre_flight=True,
                    **self._kwargs,
                )
                terminal_deployment = wait_for_terminal_state(deployment_poller)
                pre_flight_result: Dict[str, Union[dict, str]] = terminal_deployment.as_dict()
                if "status" in pre_flight_result and pre_flight_result["status"].lower() != PRE_FLIGHT_SUCCESS_STATUS:
                    raise AzureResponseError(dumps(pre_flight_result, indent=2))

                self.complete_step(WorkCategoryKey.PRE_CHECK, WorkStepKey.EVAL_LOGIN_PERM)
            else:
                if not self._render_progress:
                    logger.warning("Skipped Pre-Flight as requested.")

            # CSI driver segment
            if self._keyvault_resource_id:
                work_kpis["csiDriver"] = {}
                if (
                    WorkCategoryKey.CSI_DRIVER in self.display.categories
                    and not self.display.categories[WorkCategoryKey.CSI_DRIVER][1]
                ):
                    self.render_display(category=WorkCategoryKey.CSI_DRIVER)

                    # WorkStepKey.KV_CLOUD_PERM_MODEL
                    keyvault_resource = validate_keyvault_permission_model(**self._kwargs)

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_PERM_MODEL)

                    # WorkStepKey.SP
                    sp_record = prepare_sp(deployment_name=self._work_name, **self._kwargs)
                    if sp_record.created_app:
                        self.display.steps[WorkCategoryKey.CSI_DRIVER][
                            WorkStepKey.SP
                        ].title = f"Created app '[green]{sp_record.client_id}[/green]'"
                        self.render_display(category=WorkCategoryKey.CSI_DRIVER)
                    work_kpis["csiDriver"]["spAppId"] = sp_record.client_id
                    work_kpis["csiDriver"]["spObjectId"] = sp_record.object_id
                    work_kpis["csiDriver"]["keyVaultId"] = self._keyvault_resource_id

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.SP)

                    # WorkCategoryKey.KV_CLOUD_AP
                    vault_uri = prepare_keyvault_access_policy(
                        keyvault_resource=keyvault_resource,
                        sp_record=sp_record,
                        **self._kwargs,
                    )

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_AP)

                    # WorkStepKey.KV_CLOUD_SEC
                    keyvault_spc_secret_name = prepare_keyvault_secret(
                        deployment_name=self._work_name,
                        vault_uri=vault_uri,
                        **self._kwargs,
                    )
                    work_kpis["csiDriver"]["kvSatSecretName"] = keyvault_spc_secret_name

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_SEC)

                    # WorkStepKey.KV_CLOUD_TEST
                    eval_secret_via_sp(
                        cmd=self._cmd,
                        vault_uri=vault_uri,
                        keyvault_spc_secret_name=keyvault_spc_secret_name,
                        sp_record=sp_record,
                    )

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CLOUD_TEST)

                    # WorkStepKey.KV_CSI_DEPLOY
                    enable_secret_rotation = not self._kwargs.get("disable_secret_rotation", False)
                    enable_secret_rotation = "true" if enable_secret_rotation else "false"
                    work_kpis["csiDriver"]["rotationPollInterval"] = self._kwargs.get("rotation_poll_interval")
                    work_kpis["csiDriver"]["enableSecretRotation"] = enable_secret_rotation

                    akv_csi_driver_result = provision_akv_csi_driver(
                        enable_secret_rotation=enable_secret_rotation, **self._kwargs
                    )
                    work_kpis["csiDriver"]["version"] = akv_csi_driver_result["properties"]["version"]

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_DEPLOY)

                    # WorkStepKey.KV_CSI_CLUSTER
                    configure_cluster_secrets(
                        cluster_secret_ref=self._cluster_secret_ref,
                        cluster_akv_secret_class_name=self._cluster_secret_class_name,
                        sp_record=sp_record,
                        **self._kwargs,
                    )

                    self.complete_step(WorkCategoryKey.CSI_DRIVER, WorkStepKey.KV_CSI_CLUSTER)
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

                # WorkStepKey.TLS_CERT
                public_ca, private_key, secret_name, cm_name = prepare_ca(**self._kwargs)
                work_kpis["tls"]["aioTrustConfigMap"] = cm_name
                work_kpis["tls"]["aioTrustSecretName"] = secret_name

                self.complete_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CERT)

                configure_cluster_tls(
                    public_ca=public_ca,
                    private_key=private_key,
                    secret_name=secret_name,
                    cm_name=cm_name,
                    **self._kwargs,
                )

                self.complete_step(WorkCategoryKey.TLS_CA, WorkStepKey.TLS_CLUSTER)
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

                # WorkStepKey.DEPLOY_AIO_MONIKER
                deployment_result, deployment_poller = deploy_template(
                    template=template.content, parameters=parameters, deployment_name=self._work_name, **self._kwargs
                )
                work_kpis.update(deployment_result)

                if self._no_block:
                    return work_kpis

                # Pattern needs work, it is this way to dynamically update UI
                self.display.categories[WorkCategoryKey.DEPLOY_AIO][0].title = (
                    f"[link={deployment_result['deploymentLink']}]"
                    f"{self.display.categories[WorkCategoryKey.DEPLOY_AIO][0].title}[/link]"
                )
                self.render_display(category=WorkCategoryKey.DEPLOY_AIO)

                terminal_deployment = wait_for_terminal_state(deployment_poller)
                deployment_result["deploymentState"]["status"] = terminal_deployment.properties.provisioning_state
                deployment_result["deploymentState"]["correlationId"] = terminal_deployment.properties.correlation_id
                deployment_result["deploymentState"]["opsVersion"] = template.component_vers
                deployment_result["deploymentState"]["timestampUtc"]["ended"] = get_timestamp_now_utc()
                deployment_result["deploymentState"]["resources"] = [
                    resource.id.split(
                        f"/subscriptions/{self._subscription_id}/resourceGroups/"
                        f"{self._kwargs['resource_group_name']}/providers/"
                    )[1]
                    for resource in terminal_deployment.properties.output_resources
                ]
                work_kpis.update(deployment_result)

                self.complete_step(WorkCategoryKey.DEPLOY_AIO, WorkStepKey.DEPLOY_AIO_MONIKER)

                return work_kpis

        except HttpResponseError as e:
            # TODO: repeated error messages.
            raise AzureResponseError(e.message)
        except KeyboardInterrupt:
            return
        finally:
            self.stop_display()

    def complete_step(self, category: WorkCategoryKey, completed_step: WorkStepKey):
        self._completed_steps[completed_step] = 1
        self.render_display(category)

    def render_display(self, category: WorkCategoryKey = None):
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
        template = get_current_template_copy(self._template_path)
        parameters = {}

        for template_pair in [
            ("cluster_name", "clusterName"),
            ("location", "location"),
            ("cluster_location", "clusterLocation"),
            ("custom_location_name", "customLocationName"),
            ("simulate_plc", "simulatePLC"),
            ("opcua_discovery_endpoint", "opcuaDiscoveryEndpoint"),
            ("container_runtime_socket", "containerRuntimeSocket"),
            ("kubernetes_distro", "kubernetesDistro"),
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
        parameters["deployResourceSyncRules"] = {"value": self._deploy_rsync_rules}

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
