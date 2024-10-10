# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import IntEnum
from json import dumps
from time import sleep
from typing import TYPE_CHECKING, Dict, Optional, Tuple, Union
from uuid import uuid4

from azure.cli.core.azclierror import AzureResponseError, ValidationError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich import print
from rich.console import NewLine
from rich.live import Live
from rich.padding import Padding
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.style import Style
from rich.table import Table

from ...util.az_client import (
    REGISTRY_API_VERSION,
    get_resource_client,
    parse_resource_id,
    wait_for_terminal_state,
)
from .permissions import ROLE_DEF_FORMAT_STR, PermissionManager
from .resource_map import IoTOperationsResourceMap
from .targets import InitTargets

logger = get_logger(__name__)

if TYPE_CHECKING:
    from azure.core.polling import LROPoller


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
    def __init__(self, title: str, description: Optional[str] = None):
        self.title = title
        self.description = description


PROVISIONING_STATE_SUCCESS = "Succeeded"
CONNECTIVITY_STATUS_CONNECTED = "Connected"
IOT_OPS_EXTENSION_TYPE = "microsoft.iotoperations"
IOT_OPS_PLAT_EXTENSION_TYPE = "microsoft.iotoperations.platform"
SECRET_SYNC_EXTENSION_TYPE = "microsoft.azure.secretstore"
CONTRIBUTOR_ROLE_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"


# TODO - @digimaun - make common
def get_user_msg_warn_ra(prefix: str, principal_id: str, scope: str) -> str:
    return (
        f"{prefix}\n\n"
        f"The IoT Operations arc extension with principal Id '{principal_id}' needs\n"
        "'Contributor' or equivalent roles against scope:\n"
        f"'{scope}'\n\n"
        "Please handle this step before continuing."
    )


class WorkDisplay:
    def __init__(self):
        self._categories: Dict[int, Tuple[WorkRecord, bool]] = {}
        self._steps: Dict[int, Dict[int, str]] = {}
        self._headers: Dict[int, str] = {}

    def add_category(self, category: WorkCategoryKey, title: str, skipped: bool = False):
        self._categories[category] = (WorkRecord(title), skipped)
        self._steps[category] = {}

    def add_step(self, category: WorkCategoryKey, step: WorkStepKey, title: str, description: Optional[str] = None):
        self._steps[category][step] = WorkRecord(title, description)

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
        self.resource_client = get_resource_client(subscription_id=self.subscription_id)
        self.permission_manager = PermissionManager(subscription_id=self.subscription_id)

    def _bootstrap_ux(self, show_progress: bool = False):
        self._display = WorkDisplay()
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

    def _format_enablement_desc(self) -> str:
        version_map = self._targets.get_extension_versions()
        display_desc = "[dim]"
        for ver in version_map:
            display_desc += f"• {ver}: {version_map[ver]}\n"
        return display_desc[:-1] + ""

    def _format_instance_desc(self) -> str:
        instance_config = {"resource sync": "enabled" if self._targets.deploy_resource_sync_rules else "disabled"}
        display_desc = ""
        for c in instance_config:
            display_desc += f"• {c}: {instance_config[c]}\n"
        return display_desc[:-1] + ""

    def _build_display(self):
        pre_check_cat_desc = "Pre-Flight"
        self._display.add_category(WorkCategoryKey.PRE_FLIGHT, pre_check_cat_desc, skipped=not self._pre_flight)
        self._display.add_step(WorkCategoryKey.PRE_FLIGHT, WorkStepKey.REG_RP, "Ensure registered resource providers")
        self._display.add_step(
            WorkCategoryKey.PRE_FLIGHT, WorkStepKey.ENUMERATE_PRE_FLIGHT, "Enumerate pre-flight checks"
        )

        if self._apply_foundation:
            self._display.add_category(WorkCategoryKey.ENABLE_IOT_OPS, "Enablement")
            self._display.add_step(
                WorkCategoryKey.ENABLE_IOT_OPS, WorkStepKey.WHAT_IF_ENABLEMENT, "What-If evaluation"
            )
            self._display.add_step(
                WorkCategoryKey.ENABLE_IOT_OPS,
                WorkStepKey.DEPLOY_ENABLEMENT,
                "Install foundation layer",
                self._format_enablement_desc(),
            )

        if self._targets.instance_name:
            self._display.add_category(WorkCategoryKey.DEPLOY_IOT_OPS, "Deploy IoT Operations")
            self._display.add_step(WorkCategoryKey.DEPLOY_IOT_OPS, WorkStepKey.WHAT_IF_INSTANCE, "What-If evaluation")
            self._display.add_step(
                WorkCategoryKey.DEPLOY_IOT_OPS,
                WorkStepKey.DEPLOY_INSTANCE,
                f"Create instance [cyan]{self._targets.instance_name}",
                self._format_instance_desc(),
            )

    def _process_connected_cluster(self):
        connected_cluster = self._resource_map.connected_cluster
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
            raise ValidationError("Arc Container Storage fault tolerance enablement requires at least 3 nodes.")

    def _deploy_template(
        self,
        content: dict,
        parameters: dict,
        deployment_name: str,
        what_if: bool = False,
    ) -> Optional["LROPoller"]:
        deployment_params = {"properties": {"mode": "Incremental", "template": content, "parameters": parameters}}
        if what_if:
            what_if_poller = self.resource_client.deployments.begin_what_if(
                resource_group_name=self._targets.resource_group_name,
                deployment_name=deployment_name,
                parameters=deployment_params,
            )
            terminal_what_if_deployment = wait_for_terminal_state(what_if_poller)
            if (
                "status" in terminal_what_if_deployment
                and terminal_what_if_deployment["status"].lower() != PROVISIONING_STATE_SUCCESS.lower()
            ):
                raise AzureResponseError(dumps(terminal_what_if_deployment, indent=2))
            return

        return self.resource_client.deployments.begin_create_or_update(
            resource_group_name=self._targets.resource_group_name,
            deployment_name=deployment_name,
            parameters=deployment_params,
        )

    def execute_ops_init(
        self,
        apply_foundation: bool = True,
        show_progress: bool = True,
        pre_flight: bool = True,
        **kwargs,
    ):
        self._bootstrap_ux(show_progress=show_progress)
        self._work_id = uuid4().hex
        self._work_format_str = f"aziotops.{{op}}.{self._work_id}"
        self._apply_foundation = apply_foundation
        self._pre_flight = pre_flight

        self._completed_steps: Dict[int, int] = {}
        self._active_step: int = 0
        self._targets = InitTargets(subscription_id=self.subscription_id, **kwargs)
        self._extension_map = None
        self._resource_map = IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=self._targets.cluster_name,
            resource_group_name=self._targets.resource_group_name,
            defer_refresh=True,
        )
        self._build_display()

        return self._do_work()

    def _do_work(self):  # noqa: C901
        from .base import (
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
            self._process_connected_cluster()

            # Pre-Flight workflow
            if self._pre_flight:
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
                        connected_cluster=self._resource_map.connected_cluster,
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
                )

            # Enable IoT Ops workflow
            if self._apply_foundation:
                enablement_work_name = self._work_format_str.format(op="enablement")
                self.render_display(
                    category=WorkCategoryKey.ENABLE_IOT_OPS, active_step=WorkStepKey.WHAT_IF_ENABLEMENT
                )
                enablement_content, enablement_parameters = self._targets.get_ops_enablement_template()
                self._deploy_template(
                    content=enablement_content,
                    parameters=enablement_parameters,
                    deployment_name=enablement_work_name,
                    what_if=True,
                )
                self.complete_step(
                    category=WorkCategoryKey.ENABLE_IOT_OPS,
                    completed_step=WorkStepKey.WHAT_IF_ENABLEMENT,
                    active_step=WorkStepKey.DEPLOY_ENABLEMENT,
                )
                enablement_poller = self._deploy_template(
                    content=enablement_content,
                    parameters=enablement_parameters,
                    deployment_name=enablement_work_name,
                )
                enablement_deploy_link = (
                    "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"
                    f"%2Fsubscriptions%2F{self.subscription_id}%2FresourceGroups%2F{self._targets.resource_group_name}"
                    f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{enablement_work_name}"
                )
                # Pattern needs work, it is this way to dynamically update UI
                self._display.categories[WorkCategoryKey.ENABLE_IOT_OPS][0].title = (
                    f"[link={enablement_deploy_link}]"
                    f"{self._display.categories[WorkCategoryKey.ENABLE_IOT_OPS][0].title}[/link]"
                )
                self.render_display(category=WorkCategoryKey.ENABLE_IOT_OPS)
                _ = wait_for_terminal_state(enablement_poller)

                self._extension_map = self._resource_map.connected_cluster.get_extensions_by_type(
                    IOT_OPS_EXTENSION_TYPE, IOT_OPS_PLAT_EXTENSION_TYPE, SECRET_SYNC_EXTENSION_TYPE
                )

                self.complete_step(
                    category=WorkCategoryKey.ENABLE_IOT_OPS, completed_step=WorkStepKey.DEPLOY_ENABLEMENT
                )

                if self._show_progress:
                    self._resource_map.refresh_resource_state()
                    resource_tree = self._resource_map.build_tree()
                    self.stop_display()
                    print(resource_tree)
                    return
                # TODO @digimaun - work_kpis
                return work_kpis

            # Deploy IoT Ops workflow
            if self._targets.instance_name:
                # Ensure schema registry exists.
                self.resource_client.resources.get_by_id(
                    resource_id=self._targets.schema_registry_resource_id,
                    api_version=REGISTRY_API_VERSION,
                )
                if not self._extension_map:
                    self._extension_map = self._resource_map.connected_cluster.get_extensions_by_type(
                        IOT_OPS_EXTENSION_TYPE, IOT_OPS_PLAT_EXTENSION_TYPE, SECRET_SYNC_EXTENSION_TYPE
                    )
                    # TODO - @digmaun revisit
                    if any(not v for v in self._extension_map.values()):
                        raise ValidationError(
                            "Foundational service installation not detected. "
                            "Instance deployment will not continue. Please run init."
                        )

                instance_work_name = self._work_format_str.format(op="instance")
                self.render_display(category=WorkCategoryKey.DEPLOY_IOT_OPS, active_step=WorkStepKey.WHAT_IF_INSTANCE)
                instance_content, instance_parameters = self._targets.get_ops_instance_template(
                    cl_extension_ids=[self._extension_map[ext]["id"] for ext in self._extension_map],
                    ops_extension_config=self._extension_map[IOT_OPS_EXTENSION_TYPE]["properties"][
                        "configurationSettings"
                    ],
                )
                role_assignment_error = None
                try:
                    schema_registry_id_parts = parse_resource_id(self._targets.schema_registry_resource_id)
                    self.permission_manager.apply_role_assignment(
                        scope=self._targets.schema_registry_resource_id,
                        principal_id=self._extension_map[IOT_OPS_EXTENSION_TYPE]["identity"]["principalId"],
                        role_def_id=ROLE_DEF_FORMAT_STR.format(
                            subscription_id=schema_registry_id_parts.subscription_id,
                            role_id=CONTRIBUTOR_ROLE_ID,
                        ),
                    )
                except Exception as e:
                    role_assignment_error = get_user_msg_warn_ra(
                        prefix=f"Role assignment failed with:\n{str(e)}.",
                        principal_id=self._extension_map[IOT_OPS_EXTENSION_TYPE]["identity"]["principalId"],
                        scope=self._targets.schema_registry_resource_id,
                    )
                self._deploy_template(
                    content=instance_content,
                    parameters=instance_parameters,
                    deployment_name=instance_work_name,
                    what_if=True,
                )
                if role_assignment_error:
                    logger.warning(role_assignment_error)
                self.complete_step(
                    category=WorkCategoryKey.DEPLOY_IOT_OPS,
                    completed_step=WorkStepKey.WHAT_IF_INSTANCE,
                    active_step=WorkStepKey.DEPLOY_INSTANCE,
                )
                instance_poller = self._deploy_template(
                    content=instance_content,
                    parameters=instance_parameters,
                    deployment_name=instance_work_name,
                )
                instance_deploy_link = (
                    "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"
                    f"%2Fsubscriptions%2F{self.subscription_id}%2FresourceGroups%2F{self._targets.resource_group_name}"
                    f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{instance_work_name}"
                )
                # Pattern needs work, it is this way to dynamically update UI
                self._display.categories[WorkCategoryKey.DEPLOY_IOT_OPS][0].title = (
                    f"[link={instance_deploy_link}]"
                    f"{self._display.categories[WorkCategoryKey.DEPLOY_IOT_OPS][0].title}[/link]"
                )
                self.render_display(category=WorkCategoryKey.DEPLOY_IOT_OPS)
                _ = wait_for_terminal_state(instance_poller)
                self.complete_step(
                    category=WorkCategoryKey.DEPLOY_IOT_OPS,
                    completed_step=WorkStepKey.DEPLOY_INSTANCE,
                )

                if self._show_progress:
                    self._resource_map.refresh_resource_state()
                    resource_tree = self._resource_map.build_tree()
                    self.stop_display()
                    print(resource_tree)
                    return
                # TODO @digimaun - work_kpis
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
            header_grid.add_row(
                "[light_slate_gray]Azure IoT Operations",
                style=Style(bold=True),
            )
            header_grid.add_row(f"Workflow Id: [dark_orange3]{self._work_id}")
            header_grid.add_row(NewLine(1))

            content_grid = Table.grid(expand=False)
            content_grid.add_column(max_width=3)
            content_grid.add_column(max_width=64)

            active_cat_str = "[cyan]->[/cyan] "
            active_step_str = "[cyan]*[/cyan]"
            complete_str = "[green]:heavy_check_mark:[/green]"
            for c in self._display.categories:
                cat_prefix = active_cat_str if c == category else ""
                content_grid.add_row(
                    cat_prefix,
                    f"{self._display.categories[c][0].title} "
                    f"{'[[dark_khaki]skipped[/dark_khaki]]' if self._display.categories[c][1] else ''}",
                )
                if c in self._display.steps:
                    for s in self._display.steps[c]:
                        if s in self._completed_steps:
                            step_prefix = complete_str
                        elif s == self._active_step:
                            step_prefix = active_step_str
                        else:
                            step_prefix = "-"

                        content_grid.add_row(
                            "",
                            Padding(
                                f"{step_prefix} {self._display.steps[c][s].title} ",
                                (0, 0, 0, 2),
                            ),
                        )
                        if self._display.steps[c][s].description:
                            content_grid.add_row(
                                "",
                                Padding(
                                    self._display.steps[c][s].description,
                                    (0, 0, 0, 4),
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
