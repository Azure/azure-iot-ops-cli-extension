# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from rich.console import Console
from typing import TYPE_CHECKING, Dict, Iterable, Optional
from knack.log import get_logger

from ....common import IdentityType
from ....util.az_client import get_registry_refresh_mgmt_client, get_resource_client, wait_for_terminal_state
from ....util.common import should_continue_prompt
from ....util.queryable import Queryable

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistryrefreshmgmt.operations import NamespacesOperations
    from ....vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)


class Namespaces(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_refresh_mgmt_client(
            subscription_id=self.default_subscription_id
        )
        self.resource_mgmt_client = get_resource_client(
            subscription_id=self.default_subscription_id
        )
        self.ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def create(
        self,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        mi_system_identity: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        if not location:
            location = self.get_resource_group(name=resource_group_name)["location"]

        namespace_body = {
            "identity": _build_identity(system=mi_system_identity),
            "location": location,
            "properties": {},
            "tags": tags,
        }
        with console.status(f"Creating {namespace_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name,
                namespace_name,
                resource=namespace_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(self, namespace_name: str, resource_group_name: str, confirm_yes: bool = False, **kwargs):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        with console.status(f"Deleting {namespace_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, namespace_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()

    def update(
        self,
        namespace_name: str,
        resource_group_name: str,
        # Note for now, keep this here but will be moved once user identities are supported
        mi_system_identity: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        update_payload = {}
        if tags:
            update_payload["tags"] = tags

        if mi_system_identity is not None:
            update_payload["identity"] = _build_identity(system=mi_system_identity)

        with console.status(f"Updating {namespace_name}..."):
            poller = self.ops.begin_update(
                resource_group_name,
                namespace_name,
                update_payload
            )
            return wait_for_terminal_state(poller, **kwargs)


def _build_identity(system: bool = False) -> dict:
    if system:
        identity_type = IdentityType.system_assigned.value
    else:
        identity_type = IdentityType.none.value
        logger.warning("An identity type was not specified. The namespace may not function as expected.")

    return {"type": identity_type}
