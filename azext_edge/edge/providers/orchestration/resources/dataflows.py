# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.console import Console

from ....util.common import should_continue_prompt
from ....util.az_client import get_iotops_mgmt_client, wait_for_terminal_state
from ....util.queryable import Queryable
from .instances import Instances
from .reskit import GetInstanceExtLoc, get_file_config

logger = get_logger(__name__)

console = Console()

if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        DataflowEndpointOperations,
        DataflowOperations,
        DataflowProfileOperations,
    )

console = Console()


class DataFlowProfiles(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.ops: "DataflowProfileOperations" = self.iotops_mgmt_client.dataflow_profile
        self.instances = Instances(cmd=cmd)
        self.dataflows = DataFlows(self.iotops_mgmt_client.dataflow, self.instances.get_ext_loc)

    def create(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        profile_instances: int = 1,
        log_level: str = "info",
        **kwargs,
    ):

        resource = {
            "properties": {
                "diagnostics": {
                    "logs": {"level": log_level},
                },
                "instanceCount": profile_instances,
            },
            "extendedLocation": self.instances.get_ext_loc(
                name=instance_name, resource_group_name=resource_group_name
            ),
        }

        with console.status(f"Creating {name}..."):
            poller = self.ops.begin_create_or_update(
                instance_name=instance_name,
                dataflow_profile_name=name,
                resource_group_name=resource_group_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def update(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        profile_instances: Optional[int] = None,
        log_level: Optional[str] = None,
        **kwargs,
    ):
        # get the existing dataflow profile
        original_profile = self.show(
            name=name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

        # update the properties
        if profile_instances:
            properties = original_profile.setdefault("properties", {})
            properties["instanceCount"] = profile_instances
        if log_level:
            properties = original_profile.setdefault("properties", {})
            diagnostics = properties.setdefault("diagnostics", {})
            logs = diagnostics.setdefault("logs", {})
            logs["level"] = log_level

        with console.status(f"Updating {name}..."):
            poller = self.ops.begin_create_or_update(
                instance_name=instance_name,
                dataflow_profile_name=name,
                resource_group_name=resource_group_name,
                resource=original_profile,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ) -> dict:
        dataflows = self.dataflows.list(
            dataflow_profile_name=name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
        dataflows = list(dataflows)

        if name == "default":
            logger.warning("Deleting the 'default' dataflow profile may cause disruptions.")

        if dataflows:
            console.print("Deleting this dataflow profile will also affect the associated dataflows:")
            for dataflow in dataflows:
                console.print(f"\t- {dataflow['name']}")

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status(f"Deleting {name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=name,
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)


class DataFlows:
    def __init__(self, ops: "DataflowOperations", get_ext_loc: GetInstanceExtLoc):
        self.ops = ops
        self.get_ext_loc = get_ext_loc

    def show(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
    ) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
            dataflow_name=name,
        )

    def list(self, dataflow_profile_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_profile_resource(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
        )


class DataFlowEndpoints(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "DataflowEndpointOperations" = self.iotops_mgmt_client.dataflow_endpoint
        self.instances = Instances(self.cmd)

    def apply(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        config_file: str,
        **kwargs
    ) -> dict:
        resource = {}
        endpoint_config = get_file_config(config_file)
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
        resource["extendedLocation"] = self.instance["extendedLocation"]
        resource["properties"] = endpoint_config

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                dataflow_endpoint_name=name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: bool = False,
        **kwargs
    ):
        should_bail = not should_continue_prompt(
            confirm_yes=confirm_yes,
        )
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=name,
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)
