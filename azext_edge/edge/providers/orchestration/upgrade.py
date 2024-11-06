# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from time import sleep
from typing import List, Optional, OrderedDict

from azure.cli.core.azclierror import (
    ArgumentUsageError,
    AzureResponseError,
    CLIInternalError,
)
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich import print
from rich.console import NewLine
from rich.live import Live
from rich.padding import Padding
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table

from ...util.az_client import get_resource_client, wait_for_terminal_state
from ...util.common import should_continue_prompt
from .resource_map import IoTOperationsResourceMap
from .resources import Instances

logger = get_logger(__name__)
INSTANCE_MIN_VERSION = "1.0.6"

INSTANCE_UPGRADE_ERROR = (
    "Cannot upgrade instance {0}, please delete your instance, including dependencies, and reinstall."
)


def upgrade_ops_resources(
    cmd,
    resource_group_name: str,
    instance_name: Optional[str] = None,
    cluster_name: Optional[str] = None,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
):
    manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
    )
    return manager.do_work(confirm_yes=confirm_yes)


# keeping this separate for easier removal once no longer needed
class UpgradeManager:
    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: Optional[str] = None,
        cluster_name: Optional[str] = None,
        no_progress: Optional[bool] = None,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.instance_name = instance_name
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.instances = Instances(self.cmd)
        self.subscription_id = get_subscription_id(cli_ctx=cmd.cli_ctx)
        self.resource_client = get_resource_client(self.subscription_id)

        self._render_progress = not no_progress
        self._live = Live(None, transient=False, refresh_per_second=8, auto_refresh=self._render_progress)
        self._progress_bar = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=False,
        )
        self._progress_shown = False

    def do_work(self, confirm_yes: Optional[bool] = None):
        from .template import M3_INSTANCE_TEMPLATE
        self.new_aio_version = M3_INSTANCE_TEMPLATE.content["variables"]["VERSIONS"]["iotOperations"]
        # get the resource map from the instance (checks if update is needed for instance/too old)
        self.resource_map = self._get_resource_map()
        # Ensure cluster exists with existing resource_map pattern.
        self.resource_map.connected_cluster.resource
        self.cluster_name = self.resource_map.connected_cluster.cluster_name
        current_version = self.instance["properties"]["version"]

        # get the extensions to update, populate the expected patches
        extension_text = self._check_extensions()

        if not self.extensions_to_update:
            print("[green]Nothing to upgrade :)[/green]")
            return

        if self._render_progress:
            print("Azure IoT Operations Upgrade")
            print()
            if self.extensions_to_update:
                print(Padding("Extensions to update:", (0, 0, 0, 2)))
                print(Padding(extension_text, (0, 0, 0, 4)))
                # if the aio extension is updated, the instance will be too
                if "azure-iot-operations" in extension_text:
                    print(Padding(
                        f"Azure IoT Operations instance version {current_version} found. Will update the instance to "
                        f"version {self.new_aio_version}.",
                        (0, 0, 0, 2)
                    ))

            print()
            print("[yellow]Upgrading may fail and require you to delete and re-create your cluster.[/yellow]")

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes, context="Upgrade")
        if should_bail:
            return

        # do the work - get the schema reg id if needed, do the updates
        return self._process()

    def _check_extensions(self) -> str:
        from .template import M3_ENABLEMENT_TEMPLATE, M3_INSTANCE_TEMPLATE
        version_map = M3_ENABLEMENT_TEMPLATE.content["variables"]["VERSIONS"].copy()
        version_map.update(M3_INSTANCE_TEMPLATE.content["variables"]["VERSIONS"].copy())
        train_map = M3_ENABLEMENT_TEMPLATE.content["variables"]["TRAINS"].copy()
        train_map.update(M3_INSTANCE_TEMPLATE.content["variables"]["TRAINS"].copy())

        # note that the secret store type changes but somehow it all works out :)
        # the order is determined by depends on in the template
        type_to_key_map = OrderedDict([
            ("microsoft.iotoperations.platform", "platform"),
            ("microsoft.openservicemesh", "openServiceMesh"),
            ("microsoft.azure.secretstore", "secretStore"),
            ("microsoft.arc.containerstorage", "containerStorage"),
            ("microsoft.iotoperations", "iotOperations"),
        ])
        # order the extension list with the same order as above map
        aio_extensions: List[dict] = self.resource_map.connected_cluster.extensions
        type_to_aio_extensions = {ext["properties"]["extensionType"].lower(): ext for ext in aio_extensions}
        ordered_aio_extensions = OrderedDict({
            ext_type: type_to_aio_extensions[ext_type] for ext_type in type_to_key_map
        })
        # make sure order is kept
        self.extensions_to_update = OrderedDict()

        # package import can be wack
        try:
            from packaging import version
        except ImportError:
            raise CLIInternalError("Cannot parse extension versions.")
        for extension_type, extension in ordered_aio_extensions.items():
            extension_key = type_to_key_map[extension_type]
            current_version = extension["properties"].get("version", "0")
            current_train = extension["properties"].get("releaseTrain", "").lower()

            extension_update = {
                "properties" : {
                    "autoUpgradeMinorVersion": "false",
                    "releaseTrain": train_map[extension_key],
                    "version": version_map[extension_key],
                },
                "currentVersion": current_version
            }

            try:
                if all([
                    version.parse(current_version) >= version.parse(version_map[extension_key]),
                    train_map[extension_key].lower() == current_train
                ]):
                    logger.info(f"Extension {extension['name']} is already up to date.")
                    continue
                self.extensions_to_update[extension["name"]] = extension_update
            except version.InvalidVersion:
                raise CLIInternalError(f"Cannot parse extension versions for {extension['name']}.")

        # text to print (ordered)
        display_desc = "[dim]"
        for extension, update in self.extensions_to_update.items():
            new_version = update["properties"]["version"]
            old_version = update.pop("currentVersion")
            display_desc += f"• {extension}: {old_version} -> {new_version}\n"
        return display_desc[:-1] + ""

    def _get_resource_map(self) -> IoTOperationsResourceMap:
        api_spec_error = "HttpResponsePayloadAPISpecValidationFailed"
        try:
            from packaging import version
        except ImportError:
            raise CLIInternalError("Cannot parse extension versions.")

        # try with current
        try:
            self.instance = self.instances.show(
                name=self.instance_name,
                resource_group_name=self.resource_group_name
            )
            if version.parse(INSTANCE_MIN_VERSION) > version.parse(self.instance["properties"]["version"]):
                raise ArgumentUsageError(INSTANCE_UPGRADE_ERROR.format(self.instance_name))
            return self.instances.get_resource_map(self.instance)
        except version.InvalidVersion:
            raise CLIInternalError(f"Cannot parse version for {self.instance}.")
        except HttpResponseError as e:
            if api_spec_error in e.message:
                raise ArgumentUsageError(INSTANCE_UPGRADE_ERROR.format(self.instance_name))
            raise e

    def _render_display(self, description: str):
        if self._render_progress:
            grid = Table.grid(expand=False)
            grid.add_column()
            grid.add_row(NewLine(1))
            grid.add_row(description)
            grid.add_row(NewLine(1))
            grid.add_row(self._progress_bar)

            if not self._progress_shown:
                self._task_id = self._progress_bar.add_task(description="Work.", total=None)
                self._progress_shown = True
            self._live.update(grid, refresh=True)

            if not self._live.is_started:
                self._live.start(True)

    def _stop_display(self):
        if self._render_progress and self._live.is_started:
            if self._progress_shown:
                self._progress_bar.update(self._task_id, description="Done.")
                sleep(0.5)
            self._live.stop()

    def _process(self):
        result = None
        try:
            # Do the extension upgrade, try to keep the sr resource id
            if self.extensions_to_update:
                self._render_display("[yellow]Updating extensions...")
            for extension in self.extensions_to_update:
                logger.info(f"Updating extension {extension}.")
                logger.info(f"Extension PATCH body: {self.extensions_to_update[extension]}")
                updated = self.resource_map.connected_cluster.clusters.extensions.update_cluster_extension(
                    resource_group_name=self.resource_group_name,
                    cluster_name=self.cluster_name,
                    extension_name=extension,
                    update_payload=self.extensions_to_update[extension]
                )
                # check for hidden errors
                for status in updated["properties"].get("statuses", []):
                    if status["code"] == "InstallationFailed":
                        raise AzureResponseError(
                            f"Updating extension {extension} failed with the error message: {status['message']}"
                        )
            else:
                result = self.instances.show(
                    resource_group_name=self.resource_group_name,
                    name=self.instance_name,
                )
        finally:
            self._stop_display()
        return result
