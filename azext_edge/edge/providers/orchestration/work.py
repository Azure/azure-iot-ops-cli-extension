# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import IntEnum
from json import dumps
from time import sleep
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple, Union
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
    REGISTRY_PREVIEW_API_VERSION,
    get_resource_client,
    parse_resource_id,
    wait_for_terminal_state,
)
from ...util.common import insert_newlines
from .common import (
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    OPS_EXTENSION_DEPS,
    ClusterConnectStatus,
)
from .permissions import ROLE_DEF_FORMAT_STR, PermissionManager, PrincipalType
from .resource_map import IoTOperationsResourceMap
from .resources.custom_locations import CustomLocations
from .targets import InitTargets, InstancePhase

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
    DEPLOY_INSTANCE = 5
    DEPLOY_RESOURCES = 6


class WorkRecord:
    def __init__(self, title: str, description: Optional[str] = None):
        self.title = title
        self.description = description


PROVISIONING_STATE_SUCCESS = "Succeeded"

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

    def add_category(
        self, category: WorkCategoryKey, title: str, skipped: bool = False, description: Optional[str] = None
    ):
        self._categories[category] = (WorkRecord(title, description), skipped)
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
        self.custom_locations = CustomLocations(self.cmd)

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
        for moniker in version_map:
            display_desc += f"• {moniker}: {version_map[moniker]['version']} {version_map[moniker]['train']}\n"
        return display_desc[:-1]

    def _format_instance_desc(self) -> str:
        version_map = self._targets.get_extension_versions(False)
        display_desc = "[dim]"
        for moniker in version_map:
            display_desc += f"v{version_map[moniker]['version']} {version_map[moniker]['train']}\n"
        return display_desc[:-1]

    def _format_instance_config_desc(self) -> str:
        instance_config = {"resource sync": "enabled" if self._targets.deploy_resource_sync_rules else "disabled"}
        display_desc = ""
        for c in instance_config:
            display_desc += f"• {c}: {instance_config[c]}\n"
        return display_desc[:-1]

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
            self._display.add_category(
                WorkCategoryKey.DEPLOY_IOT_OPS, "Deploy IoT Operations", False, self._format_instance_desc()
            )
            self._display.add_step(
                WorkCategoryKey.DEPLOY_IOT_OPS,
                WorkStepKey.DEPLOY_INSTANCE,
                f"Create instance [cyan]{self._targets.instance_name}",
                self._format_instance_config_desc(),
            )
            self._display.add_step(
                WorkCategoryKey.DEPLOY_IOT_OPS,
                WorkStepKey.DEPLOY_RESOURCES,
                "Apply default resources",
            )

    def _process_connected_cluster(self):
        connected_cluster = self._resource_map.connected_cluster
        cluster = connected_cluster.resource
        cluster_properties: Dict[str, Union[str, dict]] = cluster["properties"]
        cluster_validation_tuples = [
            ("provisioningState", PROVISIONING_STATE_SUCCESS),
            ("connectivityStatus", ClusterConnectStatus.CONNECTED.value),
        ]
        for v in cluster_validation_tuples:
            if cluster_properties[v[0]].lower() != v[1].lower():
                raise ValidationError(f"The connected cluster {self._targets.cluster_name}'s {v[0]} is not {v[1]}.")

        if not self._targets.location:
            self._targets.location = cluster["location"]

        if self._targets.enable_fault_tolerance and cluster_properties["totalNodeCount"] < 3:
            raise ValidationError("Arc Container Storage fault tolerance enablement requires at least 3 nodes.")

    def _process_extension_dependencies(self):
        missing_exts = []
        bad_provisioning_state = []
        dependencies = self.ops_extension_dependencies
        for ext in dependencies:
            ext_attr = dependencies.get(ext)
            if not ext_attr:
                missing_exts.append(ext)
                continue

            ext_provisioning_state: str = ext_attr.get("properties", {}).get("provisioningState")
            if ext_provisioning_state.lower() != PROVISIONING_STATE_SUCCESS.lower():
                bad_provisioning_state.append(ext)

        if missing_exts:
            raise ValidationError(
                "Foundational service(s) not detected on the cluster:\n\n"
                + "\n".join(missing_exts)
                + "\n\nInstance deployment will not continue. Please run 'az iot ops init'."
            )

        if bad_provisioning_state:
            raise ValidationError(
                "Foundational service(s) with non-successful provisioning state detected on the cluster:\n\n"
                + "\n".join(bad_provisioning_state)
                + "\n\nInstance deployment will not continue. Please run 'az iot ops init'."
            )

        # validate trust config in platform extension matches trust settings in create
        platform_extension_config = dependencies[EXTENSION_TYPE_PLATFORM]["properties"]["configurationSettings"]
        is_user_trust = platform_extension_config.get("installCertManager", "").lower() != "true"
        if is_user_trust and not self._targets.trust_settings:
            raise ValidationError(
                "Cluster was enabled with user-managed trust configuration, "
                "--trust-settings arguments are required to create an instance on this cluster."
            )
        elif not is_user_trust and self._targets.trust_settings:
            raise ValidationError(
                "Cluster was enabled with system cert-manager, "
                "trust settings (--trust-settings) are not applicable to this cluster."
            )

    def _apply_sr_role_assignment(self) -> Optional[str]:
        ops_ext = self.ops_extension
        if not ops_ext:
            raise ValidationError("IoT Operations extension not detected. Please run 'az iot ops create'.")
        # TODO - add non-success provisioningState
        ops_ext_principal_id = ops_ext.get("identity", {}).get("principalId")
        if not ops_ext_principal_id:
            raise ValidationError(
                "Unable to determine the IoT Operations system-managed identity principal Id.\n"
                "Please re-deploy via 'az iot ops create'."
            )

        try:
            schema_registry_id_parts = parse_resource_id(self._targets.schema_registry_resource_id)
            self.permission_manager.apply_role_assignment(
                scope=self._targets.schema_registry_resource_id,
                principal_id=ops_ext_principal_id,
                role_def_id=ROLE_DEF_FORMAT_STR.format(
                    subscription_id=schema_registry_id_parts.subscription_id,
                    role_id=CONTRIBUTOR_ROLE_ID,
                ),
                principal_type=PrincipalType.SERVICE_PRINCIPAL.value,
            )
        except HttpResponseError as e:
            self._warnings.append(
                get_user_msg_warn_ra(
                    prefix=f"Role assignment failed with:\n{str(e)}",
                    principal_id=ops_ext_principal_id,
                    scope=self._targets.schema_registry_resource_id,
                )
            )

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
        self._resource_map = IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=self._targets.cluster_name,
            resource_group_name=self._targets.resource_group_name,
            defer_refresh=True,
        )
        self._result_payload = {}
        self._warnings: List[str] = []
        self._ops_ext_dependencies = None
        self._ops_ext = None
        self._build_display()

        return self._do_work()

    def _do_work(self):
        from .host import verify_cli_client_connections
        from .permissions import verify_write_permission_against_rg
        from .rp_namespace import register_providers

        try:
            # Ensure connection to ARM if needed. Show remediation error message otherwise.
            self._render_display()
            verify_cli_client_connections()
            self._process_connected_cluster()

            # Pre-Flight workflow
            if self._pre_flight:
                # WorkStepKey.REG_RP
                self._render_display(category=WorkCategoryKey.PRE_FLIGHT, active_step=WorkStepKey.REG_RP)
                register_providers(self.subscription_id)
                self._complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.REG_RP,
                    active_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                )

                # WorkStepKey.ENUMERATE_PRE_FLIGHT
                if self._targets.deploy_resource_sync_rules and self._targets.instance_name:
                    # TODO - @digimaun use permission manager after fixing check access issue
                    verify_write_permission_against_rg(
                        subscription_id=self.subscription_id, resource_group_name=self._targets.resource_group_name
                    )
                self._complete_step(
                    category=WorkCategoryKey.PRE_FLIGHT,
                    completed_step=WorkStepKey.ENUMERATE_PRE_FLIGHT,
                )

            # Enable IoT Ops workflow
            if self._apply_foundation:
                enablement_work_name = self._work_format_str.format(op="enablement")
                self._render_display(
                    category=WorkCategoryKey.ENABLE_IOT_OPS, active_step=WorkStepKey.WHAT_IF_ENABLEMENT
                )
                enablement_content, enablement_parameters = self._targets.get_ops_enablement_template()
                self._deploy_template(
                    content=enablement_content,
                    parameters=enablement_parameters,
                    deployment_name=enablement_work_name,
                    what_if=True,
                )
                self._complete_step(
                    category=WorkCategoryKey.ENABLE_IOT_OPS,
                    completed_step=WorkStepKey.WHAT_IF_ENABLEMENT,
                    active_step=WorkStepKey.DEPLOY_ENABLEMENT,
                )
                enablement_poller = self._deploy_template(
                    content=enablement_content,
                    parameters=enablement_parameters,
                    deployment_name=enablement_work_name,
                )
                # Pattern needs work, it is this way to dynamically update UI
                self._display.categories[WorkCategoryKey.ENABLE_IOT_OPS][0].title = (
                    f"[link={self._get_deployment_link(enablement_work_name)}]"
                    f"{self._display.categories[WorkCategoryKey.ENABLE_IOT_OPS][0].title}[/link]"
                )
                self._render_display(category=WorkCategoryKey.ENABLE_IOT_OPS)
                _ = wait_for_terminal_state(enablement_poller)

                self._complete_step(
                    category=WorkCategoryKey.ENABLE_IOT_OPS, completed_step=WorkStepKey.DEPLOY_ENABLEMENT
                )

            # Deploy IoT Ops workflow
            if self._targets.instance_name:
                # Ensure schema registry exists.
                self.resource_client.resources.get_by_id(
                    resource_id=self._targets.schema_registry_resource_id,
                    api_version=REGISTRY_PREVIEW_API_VERSION,
                )
                self._process_extension_dependencies()
                dependency_ext_ids = [
                    self.ops_extension_dependencies[ext]["id"] for ext in [EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_SSC]
                ]
                self._render_display(category=WorkCategoryKey.DEPLOY_IOT_OPS, active_step=WorkStepKey.DEPLOY_INSTANCE)
                self._create_or_update_custom_location(
                    extension_ids=[self.ops_extension_dependencies[EXTENSION_TYPE_PLATFORM]["id"]]
                )
                instance_content, instance_parameters = self._targets.get_ops_instance_template(
                    cl_extension_ids=dependency_ext_ids,
                    phase=InstancePhase.EXT,
                )
                instance_work_name = self._work_format_str.format(op="extension")
                wait_for_terminal_state(
                    self._deploy_template(
                        content=instance_content,
                        parameters=instance_parameters,
                        deployment_name=instance_work_name,
                    )
                )
                self._create_or_update_custom_location(extension_ids=dependency_ext_ids + [self.ops_extension["id"]])
                instance_work_name = self._work_format_str.format(op="instance")
                instance_content, instance_parameters = self._targets.get_ops_instance_template(
                    cl_extension_ids=dependency_ext_ids,
                    phase=InstancePhase.INSTANCE,
                )
                wait_for_terminal_state(
                    self._deploy_template(
                        content=instance_content,
                        parameters=instance_parameters,
                        deployment_name=instance_work_name,
                    )
                )
                self._complete_step(
                    category=WorkCategoryKey.DEPLOY_IOT_OPS,
                    completed_step=WorkStepKey.DEPLOY_INSTANCE,
                    active_step=WorkStepKey.DEPLOY_RESOURCES,
                )
                instance_content, instance_parameters = self._targets.get_ops_instance_template(
                    cl_extension_ids=dependency_ext_ids, phase=InstancePhase.RESOURCES
                )
                instance_work_name = self._work_format_str.format(op="resources")
                instance_poller = self._deploy_template(
                    content=instance_content,
                    parameters=instance_parameters,
                    deployment_name=instance_work_name,
                )
                # Pattern needs work, it is this way to dynamically update UI
                self._display.categories[WorkCategoryKey.DEPLOY_IOT_OPS][0].title = (
                    f"[link={self._get_deployment_link(instance_work_name)}]"
                    f"{self._display.categories[WorkCategoryKey.DEPLOY_IOT_OPS][0].title}[/link]"
                )
                self._render_display(category=WorkCategoryKey.DEPLOY_IOT_OPS)
                wait_for_terminal_state(instance_poller)
                self._apply_sr_role_assignment()

                self._complete_step(
                    category=WorkCategoryKey.DEPLOY_IOT_OPS,
                    completed_step=WorkStepKey.DEPLOY_INSTANCE,
                )

            return self._get_user_result()
        except HttpResponseError as e:
            # TODO: repeated error messages.
            raise AzureResponseError(e.message)
        except KeyboardInterrupt:
            return
        finally:
            self._stop_display()

    def _complete_step(
        self, category: WorkCategoryKey, completed_step: WorkStepKey, active_step: Optional[WorkStepKey] = None
    ):
        self._completed_steps[completed_step] = 1
        self._render_display(category, active_step=active_step)

    def _render_display(self, category: Optional[WorkCategoryKey] = None, active_step: Optional[WorkStepKey] = None):
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
                if self._display.categories[c][0].description:
                    content_grid.add_row(
                        "",
                        Padding(
                            self._display.categories[c][0].description,
                            (0, 0, 0, 4),
                        ),
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

    def _stop_display(self):
        if self._show_progress and self._live.is_started:
            if self._progress_shown:
                self._progress_bar.update(self._task_id, description="Done.")
                sleep(0.5)
            self._live.stop()

    @property
    def ops_extension_dependencies(self) -> Dict[str, Optional[dict]]:
        if not self._ops_ext_dependencies:
            self._ops_ext_dependencies = self._resource_map.connected_cluster.get_extensions_by_type(
                *OPS_EXTENSION_DEPS
            )
        return self._ops_ext_dependencies

    @property
    def ops_extension(self) -> Optional[dict]:
        if not self._ops_ext:
            self._ops_ext = self._resource_map.connected_cluster.get_extensions_by_type(EXTENSION_TYPE_OPS)[
                EXTENSION_TYPE_OPS
            ]
        return self._ops_ext

    def _get_user_result(self) -> Optional[dict]:
        if self._show_progress:
            self._resource_map.refresh_resource_state()
            resource_tree = self._resource_map.build_tree()
            self._stop_display()
            print(resource_tree)

        if self._warnings:
            for w in self._warnings:
                logger.warning(w + "\n")

        # TODO @digimaun - work kpis
        return self._result_payload

    def _get_deployment_link(self, deployment_name: str) -> str:
        return (
            "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"
            f"%2Fsubscriptions%2F{self.subscription_id}%2FresourceGroups%2F{self._targets.resource_group_name}"
            f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{deployment_name}"
        )

    def _create_or_update_custom_location(self, extension_ids: Iterable[str]) -> dict:
        try:
            return self.custom_locations.create(
                name=self._targets.custom_location_name,
                resource_group_name=self._targets.resource_group_name,
                host_resource_id=self._resource_map.connected_cluster.resource_id,
                namespace=self._targets.cluster_namespace,
                display_name=self._targets.custom_location_name,
                location=self._targets.location,
                cluster_extension_ids=extension_ids,
                tags=self._targets.tags,
            )
        except HttpResponseError as http_exc:
            if http_exc.error.code == "UnauthorizedNamespaceError":
                explain = (
                    "[IoT Ops explanation]\n\nThis error generally happens for two reasons.\n"
                    "- The arc custom locations feature was not enabled.\n"
                    "- The arc custom locations feature was not enabled with the correct OID.\n\n"
                    "To resolve the issue, re-run create after applying the instructions at the aka.ms "
                    "link provided in the error."
                )
                cl_error_prefix = "Custom Locations Error:\n"
                raise ValidationError(
                    f"{insert_newlines(f'{cl_error_prefix}{http_exc.error.message}', 140)}\n\n{explain}"
                )
            raise http_exc
