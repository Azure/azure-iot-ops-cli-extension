# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
# TODO - @digimaun


from enum import IntEnum
from json import dumps
from time import sleep
from typing import Dict, Optional, Tuple, Union
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
from .connected_cluster import ConnectedCluster
from .targets import InitTargets
from .template import TemplateVer

logger = get_logger(__name__)


class WorkCategoryKey(IntEnum):
    PRE_FLIGHT = 1
    ENABLE_IOT_OPS = 2
    DEPLOY_IOT_OPS = 3


class WorkStepKey(IntEnum):
    REG_RP = 1
    ENUMERATE_PRE_FLIGHT = 2
    WHAT_IF_ENABLEMENT = 3
    DEPLOY_ENABLEMENT = 4
    WHAT_IF_INSTANCE = 5
    DEPLOY_INSTANCE = 6


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
        self.display.add_step(WorkCategoryKey.PRE_FLIGHT, WorkStepKey.REG_RP, "Ensure registered resource providers")
        self.display.add_step(
            WorkCategoryKey.PRE_FLIGHT, WorkStepKey.ENUMERATE_PRE_FLIGHT, "Enumerate pre-flight checks"
        )

        self.display.add_category(WorkCategoryKey.ENABLE_IOT_OPS, "Enablement")
        self.display.add_step(WorkCategoryKey.ENABLE_IOT_OPS, WorkStepKey.WHAT_IF_ENABLEMENT, "What-If evaluation")
        self.display.add_step(
            WorkCategoryKey.ENABLE_IOT_OPS, WorkStepKey.DEPLOY_ENABLEMENT, "Install foundation layer"
        )

        create_instance_desc = "Create instance"
        if self._targets.instance_name:
            create_instance_desc = f"{create_instance_desc}: [cyan]{self._targets.instance_name}[/cyan]"
        self.display.add_category(
            WorkCategoryKey.DEPLOY_IOT_OPS, "Deploy IoT Operations", skipped=not self._targets.instance_name
        )
        self.display.add_step(WorkCategoryKey.DEPLOY_IOT_OPS, WorkStepKey.WHAT_IF_INSTANCE, "What-If evaluation")
        self.display.add_step(WorkCategoryKey.DEPLOY_IOT_OPS, WorkStepKey.DEPLOY_INSTANCE, create_instance_desc)

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

        return self._do_work()

    def _do_work(self):  # noqa: C901
        from .base import (
            deploy_template,
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

            # Pre-check segment
            if (
                WorkCategoryKey.PRE_FLIGHT in self.display.categories
                and not self.display.categories[WorkCategoryKey.PRE_FLIGHT][1]
            ):
                # WorkStepKey.REG_RP
                self.render_display(category=WorkCategoryKey.PRE_FLIGHT, active_step=WorkStepKey.REG_RP)
                register_providers(self.subscription_id)
                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.REG_RP,
                    active_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                )

                # WorkStepKey.ENUMERATE_PRE_FLIGHT
                # TODO @digimaun - cluster checks
                if False:
                    verify_custom_locations_enabled(self.cmd)
                    verify_custom_location_namespace(
                        connected_cluster=self._connected_cluster,
                        custom_location_name=self._targets.custom_location_name,
                        namespace=self._targets.cluster_namespace,
                    )

                if self._targets.deploy_resource_sync_rules and self._targets.instance_name:
                    # TODO - @digimaun use permission manager after fixing check access issue
                    verify_write_permission_against_rg(
                        subscription_id=self.subscription_id, resource_group_name=self._targets.resource_group_name
                    )

                self.complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                    active_step=WorkStepKey.WHAT_IF_ENABLEMENT,
                )

                # # WorkStepKey.WHAT_IF_ENABLEMENT
                # # Execute What-If deployment to allow RPs to evaluate deployment
                # template, parameters = self.build_template(work_kpis=work_kpis)
                # deployment_result, deployment_poller = deploy_template(
                #     template=template.content,
                #     parameters=parameters,
                #     deployment_name=self._work_name,
                #     pre_flight=True,
                #     **self._kwargs,
                # )
                # terminal_deployment = wait_for_terminal_state(deployment_poller)
                # pre_flight_result: Dict[str, Union[dict, str]] = terminal_deployment.as_dict()
                # if "status" in pre_flight_result and pre_flight_result["status"].lower() != PROVISIONING_STATE_SUCCESS:
                #     raise AzureResponseError(dumps(pre_flight_result, indent=2))

                # self.complete_step(
                #     category=WorkCategoryKey.PRE_FLIGHT, completed_step=WorkStepKey.WHAT_IF, active_step=-1
                # )
            else:
                if not self._show_progress:
                    logger.warning("Skipped Pre-Flight as requested.")

            return connected_cluster.resource

            if (
                WorkCategoryKey.ENABLE_IOT_OPS in self.display.categories
                and not self.display.categories[WorkCategoryKey.ENABLE_IOT_OPS][1]
            ):
                self.render_display(category=WorkCategoryKey.ENABLE_IOT_OPS)
                content, parameters = self._targets.get_ops_enablement_template(work_kpis=work_kpis)

                # WorkStepKey.DEPLOY_AIO_MONIKER
                deployment_result, deployment_poller = deploy_template(
                    template=content, parameters=parameters, deployment_name=self._work_name, **self._kwargs
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
