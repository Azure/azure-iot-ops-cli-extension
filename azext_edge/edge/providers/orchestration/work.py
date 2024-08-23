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

from ...util import get_timestamp_now_utc, url_safe_random_chars
from ...util.az_client import wait_for_terminal_state
from .connected_cluster import ConnectedCluster
from .template import (
    # CURRENT_TEMPLATE,
    TemplateVer,
    get_basic_dataflow_profile,
    get_current_template_copy,
)

logger = get_logger(__name__)


class WorkCategoryKey(IntEnum):
    PRE_FLIGHT = 1
    ENABLE_IOT_OPS = 2
    DEPLOY_IOT_OPS = 3


class WorkStepKey(IntEnum):
    REG_RP = 1
    ENUMERATE_PRE_FLIGHT = 2
    WHAT_IF = 3


class WorkRecord:
    def __init__(self, title: str):
        self.title = title


PROVISIONING_STATE_SUCCESS = "Succeeded"
CONNECTIVITY_STATUS_CONNECTED = "Connected"


class WorkDisplay:
    def __init__(self):
        self._categories: Dict[int, Tuple[WorkRecord, bool]] = {}
        self._steps: Dict[int, Dict[int, str]] = {}
        self._headers: Dict[int, str] = {}

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


class InitTargets:
    def __init__(
        self,
        cluster_name: str,
        resource_group_name: str,
        cluster_namespace: str = "azure-iot-operations",
        location: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        disable_rsync_rules: Optional[bool] = None,
        instance_name: Optional[str] = None,
        instance_description: Optional[str] = None,
        enable_fault_tolerance: Optional[bool] = None,
        **_,
    ):
        self.cluster_name = cluster_name
        self.safe_cluster_name = self._sanitize_k8s_name(self.cluster_name)
        self.resource_group_name = resource_group_name
        self.cluster_namespace = self._sanitize_k8s_name(cluster_namespace)
        self.location = location
        self.custom_location_name = (
            self._sanitize_k8s_name(custom_location_name)
            or f"{self.safe_cluster_name}-{url_safe_random_chars(3).lower()}-ops-cl"
        )
        self.deploy_resource_sync_rules: bool = not disable_rsync_rules
        self.instance_name = self._sanitize_k8s_name(instance_name)
        self.instance_description = instance_description
        self.enable_fault_tolerance = enable_fault_tolerance

    def _sanitize_k8s_name(self, name: str) -> str:
        if not name:
            return name
        sanitized = str(name)
        sanitized = name.lower()
        sanitized = sanitized.replace("_", "-")
        return sanitized


class WorkManager:
    def __init__(self, cmd):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.subscription_id: str = get_subscription_id(cli_ctx=cmd.cli_ctx)

    def _bootstrap_ux(self, show_progress: bool = False):
        self.display = WorkDisplay()
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=show_progress)
        self._progress_bar = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
        )
        self._show_progress = show_progress
        self._progress_shown = False

    def _build_display(self):
        pre_check_cat_desc = "Pre-Flight"
        self.display.add_category(WorkCategoryKey.PRE_FLIGHT, pre_check_cat_desc, skipped=not self._pre_flight)
        self.display.add_step(
            WorkCategoryKey.PRE_FLIGHT, WorkStepKey.REG_RP, "Ensure registered IoT Ops resource providers"
        )
        self.display.add_step(
            WorkCategoryKey.PRE_FLIGHT, WorkStepKey.ENUMERATE_PRE_FLIGHT, "Enumerate pre-flight checks"
        )
        self.display.add_step(WorkCategoryKey.PRE_FLIGHT, WorkStepKey.WHAT_IF, "Verify What-If deployment")

        self.display.add_category(WorkCategoryKey.ENABLE_IOT_OPS, "Install foundation")
        deploy_iot_ops_desc = "Deploy Instance"
        if self._targets.instance_name:
            deploy_iot_ops_desc = f"{deploy_iot_ops_desc} - '{self._targets.instance_name}'"
        self.display.add_category(
            WorkCategoryKey.DEPLOY_IOT_OPS, deploy_iot_ops_desc, skipped=not self._targets.instance_name
        )

    def _process_connected_cluster(self) -> ConnectedCluster:
        connected_cluster = ConnectedCluster(
            cmd=self.cmd,
            subscription_id=self.subscription_id,
            cluster_name=self._targets.cluster_name,
            resource_group_name=self._targets.resource_group_name,
        )

        cluster = connected_cluster.resource
        cluster_properties: Dict[str, Union[str, dict]] = cluster["properties"]
        cluster_validation_tuples = [
            ("provisioningState", PROVISIONING_STATE_SUCCESS),
            ("connectivityStatus", CONNECTIVITY_STATUS_CONNECTED),
        ]
        for v in cluster_validation_tuples:
            if cluster_properties[v[0]].lower() != v[1].lower():
                raise ValidationError(f"The connected cluster {self._targets.cluster_name}'s {v[0]} is not {v[1]}.")

        if not self._targets.location:
            self._targets.location = cluster["location"]

        if self._targets.enable_fault_tolerance and cluster_properties["totalNodeCount"] < 3:
            raise ValidationError("Edge storage accelerator fault tolerance enablement requires at least 3 nodes.")

        return connected_cluster

    def execute_ops_init(self, show_progress: bool = True, block: bool = True, pre_flight: bool = True, **kwargs):
        self._bootstrap_ux(show_progress=show_progress)
        self._work_id = uuid4().hex
        self._work_name = f"aziotops.init.{self._work_id}"
        self._block = block
        self._pre_flight = pre_flight

        self._completed_steps: Dict[int, int] = {}
        self._active_step: int = 0
        self._targets = InitTargets(**kwargs)
        self._build_display()

        # TODO - @digimaun TODO
        self._kwargs = kwargs
        return self._do_work()

    def _do_work(self):  # noqa: C901
        from .base import (
            deploy_template,
            throw_if_iotops_deployed,
            verify_custom_location_namespace,
            verify_custom_locations_enabled,
        )
        from .host import verify_cli_client_connections
        from .permissions import verify_write_permission_against_rg
        from .rp_namespace import register_providers

        work_kpis = {}

        try:
            # Ensure connection to ARM if needed. Show remediation error message otherwise.
            self.render_display()
            verify_cli_client_connections()
            connected_cluster = self._process_connected_cluster()

            return connected_cluster.resource
            # Pre-check segment
            if (
                WorkCategoryKey.PRE_FLIGHT in self.display.categories
                and not self.display.categories[WorkCategoryKey.PRE_FLIGHT][1]
            ):
                # WorkStepKey.REG_RP
                self.render_display(category=WorkCategoryKey.PRE_FLIGHT, active_step=WorkStepKey.REG_RP)
                register_providers(**self._kwargs)
                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.REG_RP,
                    active_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                )

                # WorkStepKey.ENUMERATE_PRE_FLIGHT
                # TODO @digimaun
                if False:
                    throw_if_iotops_deployed(self._connected_cluster)
                    verify_custom_locations_enabled(self.cmd)
                    verify_custom_location_namespace(
                        connected_cluster=self._connected_cluster,
                        custom_location_name=self._targets.custom_location_name,
                        namespace=self._targets.cluster_namespace,
                    )

                if self._targets.deploy_resource_sync_rules:
                    # TODO - @digimaun use permission manager after fixing check access issue
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
                if "status" in pre_flight_result and pre_flight_result["status"].lower() != PROVISIONING_STATE_SUCCESS:
                    raise AzureResponseError(dumps(pre_flight_result, indent=2))

                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT, completed_step=WorkStepKey.WHAT_IF, active_step=-1
                )
            else:
                if not self._show_progress:
                    logger.warning("Skipped Pre-Flight as requested.")

            if (
                WorkCategoryKey.IOT_OPS in self.display.categories
                and not self.display.categories[WorkCategoryKey.IOT_OPS][1]
            ):
                self.render_display(category=WorkCategoryKey.IOT_OPS)
                template, parameters = self.build_template(work_kpis=work_kpis)

                # WorkStepKey.DEPLOY_AIO_MONIKER
                deployment_result, deployment_poller = deploy_template(
                    template=template.content, parameters=parameters, deployment_name=self._work_name, **self._kwargs
                )
                work_kpis.update(deployment_result)

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

        if self._show_progress:
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

        if self._show_progress and not self._live.is_started:
            self._live.start(True)

    def stop_display(self):
        if self._show_progress and self._live.is_started:
            if self._progress_shown:
                self._progress_bar.update(self._task_id, description="Done.")
                sleep(0.5)
            self._live.stop()

    def build_template(self, work_kpis: dict) -> Tuple[TemplateVer, dict]:
        template = get_current_template_copy()
        built_in_template_params = template.parameters

        parameters = {}

        for template_pair in [
            ("instance_name", "instanceName"),
            ("instance_description", "instanceDescription"),
            ("cluster_name", "clusterName"),
            ("location", "location"),
            ("cluster_location", "clusterLocation"),
            ("custom_location_name", "customLocationName"),
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

        parameters["deployResourceSyncRules"] = {"value": self._targets.deploy_resource_sync_rules}

        # Covers cluster_namespace
        template.content["variables"]["AIO_CLUSTER_RELEASE_NAMESPACE"] = self._kwargs["cluster_namespace"]

        tls_map = work_kpis.get("tls", {})
        if "aioTrustConfigMap" in tls_map:
            template.content["variables"]["AIO_TRUST_CONFIG_MAP"] = tls_map["aioTrustConfigMap"]
        if "aioTrustSecretName" in tls_map:
            template.content["variables"]["AIO_TRUST_SECRET_NAME"] = tls_map["aioTrustSecretName"]

        add_insecure_listener = self._kwargs.get("add_insecure_listener")
        if add_insecure_listener:
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
