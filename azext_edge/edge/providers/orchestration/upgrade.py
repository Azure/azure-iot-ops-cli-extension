# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from time import sleep
from typing import Optional

from azure.cli.core.azclierror import (
    ArgumentUsageError,
    AzureResponseError,
    RequiredArgumentMissingError,
    InvalidArgumentValueError
)
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
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
INSTANCE_7_API = "2024-08-15-preview"


def upgrade_ops_resources(
    cmd,
    resource_group_name: str,
    instance_name: Optional[str] = None,
    cluster_name: Optional[str] = None,
    sr_resource_id: Optional[str] = None,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
):
    manager = UpgradeManager(
        cmd=cmd,
        instance_name=instance_name,
        cluster_name=cluster_name,
        sr_resource_id=sr_resource_id,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
    )
    manager.do_work(confirm_yes=confirm_yes)


# TODO: see if dependencies need to be upgraded (broker, opcua etc)
# keeping this separate for easier removal once no longer needed
class UpgradeManager:
    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: Optional[str] = None,
        cluster_name: Optional[str] = None,
        sr_resource_id: Optional[str] = None,
        no_progress: Optional[bool] = None,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id

        self.cmd = cmd
        self.instance_name = instance_name
        self.cluster_name = cluster_name
        self.sr_resource_id = sr_resource_id
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
        self.resource_map = self._get_resource_map()
        # Ensure cluster exists with existing resource_map pattern.
        self.resource_map.connected_cluster.resource
        if not self.cluster_name:
            self.cluster_name = self.resource_map.connected_cluster.cluster_name
        extension_text = self._check_extensions()

        if self.extensions_to_update:
            print("Azure IoT Operations Upgrade")
            print()
            print(Padding("Extensions to update:", (0,0,0,2)))
            print(Padding(extension_text, (0,0,0,4)))

        if self.require_instance_upgrade:
            print(Padding(
                "Old Azure IoT Operations instance version found. Will update the instance to the latest version.",
                (0,0,0,2)
            ))

        if not self.extensions_to_update and not self.require_instance_upgrade:
            print("Nothing to upgrade :)")
            return

        print()
        print("Upgrading may fail and require you to delete and re-create your cluster.")

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        self._process()

    def _check_extensions(self) -> str:
        from .template import M2_ENABLEMENT_TEMPLATE
        version_map = M2_ENABLEMENT_TEMPLATE.content["variables"]["VERSIONS"].copy()
        train_map = M2_ENABLEMENT_TEMPLATE.content["variables"]["TRAINS"].copy()
        self.new_aio_version = "0.0.0-105821624"  # version_map["aio"]
        type_to_key_map = {
            "microsoft.azure.secretstore": "secretSyncController",  # store
            "microsoft.arc.containerstorage": "edgeStorageAccelerator",  # containerstorage
            "microsoft.openservicemesh": "openServiceMesh",  # hash
            "microsoft.iotoperations.platform": "platform",  # hash
            "microsoft.iotoperations": "aio",  # hash
        }
        aio_extensions = self.resource_map.connected_cluster.extensions
        self.extensions_to_update = {}
        for extension in aio_extensions:
            extension_type = extension["properties"]["extensionType"].lower()
            if extension_type not in type_to_key_map:
                continue
            extension_key = type_to_key_map[extension_type]
            current_version = extension["properties"].get("version", "0").replace("-preview", "")
            if all([extension_type == "microsoft.iotoperations", current_version != "0.0.0-105821624"]):
                extension_update = {
                    "properties": {
                        "autoUpgradeMinorVersion": "false",
                        "releaseTrain": "dev",
                        "version": "0.0.0-105821624",
                        "configurationSettings": {"schemaRegistry.image.tag": "0.1.6"}
                    }
                }
            # TODO: packaging
            elif any([extension_type == "microsoft.iotoperations", current_version >= version_map[extension_key].replace("-preview", "")]):
                logger.info(f"Extension {extension['name']} is already up to date.")
                continue
            else:
                extension_update = {
                    "properties" : {
                        "autoUpgradeMinorVersion": "false",
                        "releaseTrain": train_map[extension_key],
                        "version": version_map[extension_key]
                    }
                }
            self.extensions_to_update[extension["name"]] = extension_update

        display_desc = "[dim]"
        for extension, update in self.extensions_to_update.items():
            version = update["properties"]["version"]
            display_desc += f"• {extension}: {version}\n"
        return display_desc[:-1] + ""

    def _get_resource_map(self) -> IoTOperationsResourceMap:
        if not any([self.cluster_name, self.instance_name]):
            raise ArgumentUsageError("Please provide either an instance name or cluster name.")

        if not self.instance_name:
            resource_map = IoTOperationsResourceMap(
                cmd=self.cmd,
                cluster_name=self.cluster_name,
                resource_group_name=self.resource_group_name,
            )
            custom_locations = resource_map.connected_cluster.get_aio_custom_locations()
            # TODO: maybe support multiple instance updates and extension only updates later
            if custom_locations:
                for cl in custom_locations:
                    aio_resources = resource_map.connected_cluster.get_aio_resources(cl["id"])
                    for resource in aio_resources:
                        if resource["type"].lower() == "microsoft.iotoperations/instances":
                            if self.instance_name:
                                raise InvalidArgumentValueError(f"Found more than one IoT Operations instance for cluster {self.cluster_name}. Please choose the instance to upgrade with --instance.")
                            self.instance_name = resource["name"]
            if not self.instance_name:
                raise InvalidArgumentValueError(f"No instances associated with cluster {self.cluster_name} found. Please run init and create instead.")

        self.require_instance_upgrade = True
        # try with 2024-08-15-preview -> it is m2
        try:
            self.instance = self.resource_client.resources.get(
                resource_group_name=self.resource_group_name,
                parent_resource_path="",
                resource_provider_namespace="Microsoft.IoTOperations",
                resource_type="instances",
                resource_name=self.instance_name,
                api_version=INSTANCE_7_API
            )
            return self.instances.get_resource_map(self.instance)
        except HttpResponseError:
            self.require_instance_upgrade = False
        # try with 2024-09-15-preview -> it is m3 already
        try:
            self.instance = self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
            return self.instances.get_resource_map(self.instance)
        except ResourceNotFoundError as e:
            raise e
        except HttpResponseError:
            raise ArgumentUsageError(f"Cannot upgrade instance {self.instance_name}, please delete your instance, including dependencies, and reinstall.")

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
        if self.require_instance_upgrade:
            # keep the schema reg id
            extension_type = "microsoft.iotoperations"
            aio_extension = self.resource_map.connected_cluster.get_extensions_by_type(extension_type)

            extension_props = aio_extension[extension_type]["properties"]
            if not self.sr_resource_id:
                self.sr_resource_id = extension_props["configurationSettings"].get("schemaRegistry.values.resourceId")

            # m3 extensions should not have the reg id
            if not self.sr_resource_id:
                raise RequiredArgumentMissingError(
                    "Cannot determine the schema registry id from installed extensions, please provide the schema "
                    "registry id via `--sr-id`."
                )

            # prep the instance
            self.instance.pop("systemData", None)
            inst_props = self.instance["properties"]
            inst_props["schemaRegistryRef"] = {"resourceId": self.sr_resource_id}
            inst_props["version"] = self.new_aio_version
            inst_props.pop("schemaRegistryNamespace", None)
            inst_props.pop("components", None)

        result = None
        try:
            # Do the upgrade, the schema reg id may get lost
            if self.extensions_to_update:
                self._render_display("[yellow]Updating extensions...")
            import pdb; pdb.set_trace()
            for extension in self.extensions_to_update:
                logger.info(f"Updating extension {extension}.")
                updated = self.resource_map.connected_cluster.clusters.extensions.update(
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
            import pdb; pdb.set_trace()
            if self.require_instance_upgrade:
                # update the instance
                self._render_display("[yellow]Updating instance...")
                result = wait_for_terminal_state(
                        self.instances.iotops_mgmt_client.instance.begin_create_or_update(
                            resource_group_name=self.resource_group_name,
                            instance_name=self.instance_name,
                            resource=self.instance
                    )
                )
        finally:
            self._stop_display()

        # TODO make sure nothing else is needed
        return result
