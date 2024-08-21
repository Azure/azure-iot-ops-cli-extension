# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import IntEnum
from json import dumps
from time import sleep
from typing import Dict, List, Optional, Tuple, Union
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
from ...util.az_client import wait_for_terminal_state
from ...util.x509 import DEFAULT_EC_ALGO, DEFAULT_VALID_DAYS
from .template import (
    CURRENT_TEMPLATE,
    TemplateVer,
    get_basic_dataflow_profile,
    get_current_template_copy,
)

logger = get_logger(__name__)


class WorkCategoryKey(IntEnum):
    PRE_FLIGHT = 1
    DEPLOY_AIO = 2

class WorkStepKey(IntEnum):
    REG_RP = 1
    ENUMERATE_PRE_FLIGHT = 2
    WHAT_IF = 3


class WorkRecord:
    def __init__(self, title: str):
        self.title = title


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
        self._no_preflight: bool = kwargs.get("no_preflight", False)
        self._cmd = kwargs.get("cmd")
        self._keyvault_resource_id = kwargs.get("keyvault_resource_id")
        if self._keyvault_resource_id:
            self._keyvault_name = self._keyvault_resource_id.split("/")[-1]
        self._template_path = kwargs.get("template_path")
        self._progress_shown = False
        self._render_progress = not self._no_progress
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=self._render_progress)
        self._completed_steps: Dict[int, int] = {}
        self._active_step: int = 0
        self._subscription_id = get_subscription_id(self._cmd.cli_ctx)
        kwargs["subscription_id"] = self._subscription_id  # TODO: temporary
        # TODO: Make cluster target with KPIs
        self._cluster_name: str = kwargs["cluster_name"]
        self._cluster_namespace: str = kwargs["cluster_namespace"]
        self._custom_location_name: str = kwargs["custom_location_name"]
        self._deploy_rsync_rules = not kwargs.get("disable_rsync_rules", False)
        self._connected_cluster = None
        self._kwargs = kwargs

        self._build_display()

    def _build_display(self):
        pre_check_cat_desc = "Pre-Flight"
        self.display.add_category(WorkCategoryKey.PRE_FLIGHT, pre_check_cat_desc, skipped=self._no_preflight)
        self.display.add_step(
            WorkCategoryKey.PRE_FLIGHT, WorkStepKey.REG_RP, "Ensure registered IoT Ops resource providers"
        )
        self.display.add_step(
            WorkCategoryKey.PRE_FLIGHT, WorkStepKey.ENUMERATE_PRE_FLIGHT, "Enumerate pre-flight checks"
        )
        self.display.add_step(WorkCategoryKey.PRE_FLIGHT, WorkStepKey.WHAT_IF, "Verify What-If deployment")

        deployment_moniker = "Custom template" if self._template_path else CURRENT_TEMPLATE.moniker
        self.display.add_category(
            WorkCategoryKey.DEPLOY_AIO,
            f"Deploy IoT Operations - '[cyan]{deployment_moniker}[/cyan]'",
            skipped=self._no_deploy,
        )

    def do_work(self):  # noqa: C901
        from ..edge_api.keyvault import KEYVAULT_API_V1
        from .base import (
            deploy_template,
            throw_if_iotops_deployed,
            verify_arc_cluster_config,
            verify_cluster_and_use_location,
            verify_custom_location_namespace,
            verify_custom_locations_enabled,
        )
        from .host import verify_cli_client_connections
        from .permissions import verify_write_permission_against_rg
        from .rp_namespace import register_providers

        work_kpis = {}

        try:
            # Ensure connection to ARM if needed. Show remediation error message otherwise.
            # TODO - @digimaun - self._keyvault_resource_id
            if any([not self._no_preflight, not self._no_deploy, self._keyvault_resource_id]):
                verify_cli_client_connections()
                # cluster_location uses actual connected cluster location. Same applies to location IF not provided.
                self._connected_cluster = verify_cluster_and_use_location(self._kwargs)
                verify_arc_cluster_config(self._connected_cluster)

            # Pre-check segment
            if (
                WorkCategoryKey.PRE_FLIGHT in self.display.categories
                and not self.display.categories[WorkCategoryKey.PRE_FLIGHT][1]
            ):
                self.render_display(category=WorkCategoryKey.PRE_FLIGHT, active_step=WorkStepKey.REG_RP)

                if not self._keyvault_resource_id and not KEYVAULT_API_V1.is_deployed():
                    raise ValidationError(
                        error_msg="--kv-id is required when the Key Vault CSI driver is not installed."
                    )

                # WorkStepKey.REG_RP
                register_providers(**self._kwargs)

                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.REG_RP,
                    active_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                )

                # WorkStepKey.ENUMERATE_PRE_FLIGHT
                if self._connected_cluster:
                    throw_if_iotops_deployed(self._connected_cluster)
                    verify_custom_locations_enabled(self._cmd)
                    verify_custom_location_namespace(
                        connected_cluster=self._connected_cluster,
                        custom_location_name=self._custom_location_name,
                        namespace=self._cluster_namespace,
                    )

                if self._deploy_rsync_rules:
                    verify_write_permission_against_rg(
                        **self._kwargs,
                    )

                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                    active_step=WorkStepKey.WHAT_IF,
                )

                # WorkStepKey.WHAT_IF
                # Execute What-If deployment to allow RPs to evaluate deployment
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

                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT, completed_step=WorkStepKey.WHAT_IF, active_step=-1
                )
            else:
                if not self._render_progress:
                    logger.warning("Skipped Pre-Flight as requested.")

            # Deployment segment
            if self._no_deploy:
                if not self._render_progress:
                    logger.warning("Skipped deployment of AIO as requested.")

                if work_kpis:
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
                deployment_result["deploymentState"]["opsVersion"] = template.get_component_vers()
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

    def complete_step(
        self, category: WorkCategoryKey, completed_step: WorkStepKey, active_step: Optional[WorkStepKey] = None
    ):
        self._completed_steps[completed_step] = 1
        self.render_display(category, active_step=active_step)

    def render_display(self, category: Optional[WorkCategoryKey] = None, active_step: Optional[WorkStepKey] = None):
        if active_step:
            self._active_step = active_step

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

            active_cat_str = "[cyan]->[/cyan] "
            active_step_str = "[cyan]*[/cyan]"
            complete_str = "[green]:heavy_check_mark:[/green]"
            for c in self.display.categories:
                cat_prefix = active_cat_str if c == category else ""
                content_grid.add_row(
                    cat_prefix,
                    f"{self.display.categories[c][0].title} "
                    f"{'[[dark_khaki]skipped[/dark_khaki]]' if self.display.categories[c][1] else ''}",
                )
                if c in self.display.steps:
                    for s in self.display.steps[c]:
                        if s in self._completed_steps:
                            step_prefix = complete_str
                        elif s == self._active_step:
                            step_prefix = active_step_str
                        else:
                            step_prefix = "-"

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
                self._progress_bar.update(self._task_id, description="Done.")
                sleep(0.5)
            self._live.stop()

    def build_template(self, work_kpis: dict) -> Tuple[TemplateVer, dict]:
        # TODO refactor, move out of work
        safe_cluster_name = self._cluster_name.replace("_", "-")

        template = get_current_template_copy(self._template_path)
        built_in_template_params = template.parameters

        parameters = {}

        for template_pair in [
            ("instance_name", "instanceName"),
            ("instance_description", "instanceDescription"),
            ("cluster_name", "clusterName"),
            ("location", "location"),
            ("cluster_location", "clusterLocation"),
            ("custom_location_name", "customLocationName"),
            ("simulate_plc", "simulatePLC"),
            ("container_runtime_socket", "containerRuntimeSocket"),
            ("kubernetes_distro", "kubernetesDistro"),
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
            ("mq_memory_profile", "mqMemoryProfile"),
            ("mq_service_type", "mqServiceType"),
        ]:
            if (
                template_pair[0] in self._kwargs
                and self._kwargs[template_pair[0]] is not None
                and template_pair[1] in built_in_template_params
            ):
                parameters[template_pair[1]] = {"value": self._kwargs[template_pair[0]]}

        # TODO - @digimaun
        # parameters["mqSecrets"] = {
        #     "value": {
        #         "enabled": True,
        #         "secretProviderClassName": self._cluster_secret_class_name,
        #         "servicePrincipalSecretRef": self._cluster_secret_ref,
        #     }
        # }
        # parameters["opcUaBrokerSecrets"] = {
        #     "value": {"kind": "csi", "csiServicePrincipalSecretRef": self._cluster_secret_ref}
        # }
        parameters["deployResourceSyncRules"] = {"value": self._deploy_rsync_rules}

        # Covers cluster_namespace
        template.content["variables"]["AIO_CLUSTER_RELEASE_NAMESPACE"] = self._kwargs["cluster_namespace"]

        # TODO @digimaun, this section will be deleted soon
        safe_cluster_name = self._cluster_name.replace("_", "-")
        safe_cluster_name = safe_cluster_name.lower()
        template.content["variables"]["OBSERVABILITY"]["targetName"] = f"{safe_cluster_name}-observability"

        tls_map = work_kpis.get("tls", {})
        if "aioTrustConfigMap" in tls_map:
            template.content["variables"]["AIO_TRUST_CONFIG_MAP"] = tls_map["aioTrustConfigMap"]
        if "aioTrustSecretName" in tls_map:
            template.content["variables"]["AIO_TRUST_SECRET_NAME"] = tls_map["aioTrustSecretName"]

        mq_insecure = self._kwargs.get("mq_insecure")
        if mq_insecure:
            # This solution entirely relies on the form of the "standard" template.
            # Needs re-work after event
            default_listener = template.get_resource_defs("Microsoft.IoTOperations/instances/brokers/listeners")
            if default_listener:
                ports: list = default_listener["properties"]["ports"]
                ports.append({"port": 1883})

        mq_broker_config = self._kwargs.get("mq_broker_config")
        if mq_broker_config:
            if "properties" in mq_broker_config:
                mq_broker_config = mq_broker_config["properties"]
            broker: dict = template.get_resource_defs("Microsoft.IoTOperations/instances/brokers")
            broker["properties"] = mq_broker_config

        # Default dataflow profile
        deploy_resources: List[dict] = template.content.get("resources", [])
        df_profile_instances = self._kwargs.get("dataflow_profile_instances", 1)
        deploy_resources.append(get_basic_dataflow_profile(instance_count=df_profile_instances))

        return template, parameters


def deploy(
    **kwargs,
):
    show_template = kwargs.get("show_template", False)
    if show_template:
        return CURRENT_TEMPLATE.content

    manager = WorkManager(**kwargs)
    return manager.do_work()
