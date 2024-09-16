# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, List, Optional

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger
from rich import print
from rich.console import Console

from ....util.az_client import (
    ResourceIdContainer,
    get_iotops_mgmt_client,
    get_msi_mgmt_client,
    get_ssc_mgmt_client,
    get_tenant_id,
    parse_resource_id,
    wait_for_terminal_state,
)
from ....util.common import should_continue_prompt, url_safe_hash_phrase
from ....util.queryable import Queryable
from ..common import CUSTOM_LOCATIONS_API_VERSION, KEYVAULT_CLOUD_API_VERSION
from ..permissions import ROLE_DEF_FORMAT_STR, PermissionManager
from ..resource_map import IoTOperationsResourceMap

logger = get_logger(__name__)

console = Console()


SERVICE_ACCOUNT_DATAFLOW = "aio-dataflow"
SERVICE_ACCOUNT_SECRETSYNC = "aio-ssc-sa"
KEYVAULT_ROLE_ID_SECRETS_USER = "4633458b-17de-408a-b874-0445c86b69e6"
KEYVAULT_ROLE_ID_READER = "21090545-7ca7-4776-b22c-e363652d74d2"


def get_user_msg_warn_ra(prefix: str, principal_id: str, scope: str) -> str:
    return (
        f"{prefix}\n\n"
        f"The user-assigned managed identity principal '{principal_id}' needs\n"
        "'Key Vault Secrets User' and 'Key Vault Reader' or equivalent roles against scope:\n"
        f"'{scope}'\n\n"
        "Please handle this step before continuing."
    )


def get_spc_name(instance_name: str) -> str:
    return f"{instance_name}-spc"


def get_fc_name(cluster_name: str, namespace: str, instance_name: str) -> str:
    return f"{cluster_name}-" + url_safe_hash_phrase(f"{cluster_name}-{namespace}-{instance_name}")[:5]


def get_enable_syntax(instanc_name: str, resource_group_name: str) -> str:
    return (
        f"Use 'az iot ops secretsync enable -n {instanc_name} -g {resource_group_name} "
        "--user-assigned /ua/mi/resource/id'."
    )


class Instances(Queryable):
    def __init__(self, cmd, subscription_id: Optional[str] = None):
        # TODO: make sure this works correctly
        # TODO: longer term pattern?
        super().__init__(cmd=cmd, subscriptions=[subscription_id] if subscription_id else None)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.subscriptions[0],
        )
        self.msi_mgmt_client = get_msi_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ssc_mgmt_client = get_ssc_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.permission_manager = PermissionManager(self.default_subscription_id)

    def show(self, name: str, resource_group_name: str, show_tree: Optional[bool] = None) -> Optional[dict]:
        result = self.iotops_mgmt_client.instance.get(instance_name=name, resource_group_name=resource_group_name)

        if show_tree:
            self._show_tree(result)
            return

        return result

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.iotops_mgmt_client.instance.list_by_resource_group(resource_group_name=resource_group_name)

        return self.iotops_mgmt_client.instance.list_by_subscription()

    def _show_tree(self, instance: dict):
        resource_map = self.get_resource_map(instance)
        with console.status("Working..."):
            resource_map.refresh_resource_state()
        print(resource_map.build_tree(category_color="cyan"))

    def _get_associated_cl(self, instance: dict) -> dict:
        return self.resource_client.resources.get_by_id(
            resource_id=instance["extendedLocation"]["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )

    def get_resource_map(self, instance: dict) -> IoTOperationsResourceMap:
        custom_location = self._get_associated_cl(instance)
        resource_id_container = parse_resource_id(custom_location["properties"]["hostResourceId"])

        return IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=resource_id_container.resource_name,
            resource_group_name=resource_id_container.resource_group_name,
            subscription_id=resource_id_container.subscription_id,
            defer_refresh=True,
        )

    def update(
        self,
        name: str,
        resource_group_name: str,
        tags: Optional[dict] = None,
        description: Optional[str] = None,
        **kwargs: dict,
    ) -> dict:
        instance = kwargs.pop("instance", None) or self.show(name=name, resource_group_name=resource_group_name)

        if description:
            instance["properties"]["description"] = description

        if tags or tags == {}:
            instance["tags"] = tags

        with console.status("Working..."):
            poller = self.iotops_mgmt_client.instance.begin_create_or_update(
                instance_name=name,
                resource_group_name=resource_group_name,
                resource=instance,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def remove_mi_user_assigned(
        self,
        name: str,
        resource_group_name: str,
        mi_user_assigned: str,
        federated_credential_name: Optional[str] = None,
        **kwargs,
    ):
        mi_resource_id_container = parse_resource_id(mi_user_assigned)
        instance = self.show(name=name, resource_group_name=resource_group_name)
        cluster_resource = self.get_resource_map(instance).connected_cluster.resource
        custom_location = self._get_associated_cl(instance)

        if not federated_credential_name:
            federated_credential_name = get_fc_name(
                cluster_name=cluster_resource["name"],
                namespace=custom_location["properties"]["namespace"],
                instance_name=instance["name"],
            )
        self.unfederate_msi(mi_resource_id_container, federated_credential_name)

        identity: dict = instance.get("identity", {})
        if not identity:
            raise ValidationError("No identities are associated with the instance.")

        if mi_user_assigned not in identity.get("userAssignedIdentities", {}):
            raise ValidationError(
                f"The identity '{mi_resource_id_container.resource_name}' is not associated with the instance."
            )

        del identity["userAssignedIdentities"][mi_user_assigned]

        # Check if we deleted them all.
        if not identity["userAssignedIdentities"]:
            identity["type"] = "None"

        instance["identity"] = identity
        return self.update(name=name, resource_group_name=resource_group_name, instance=instance, **kwargs)

    def add_mi_user_assigned(
        self,
        name: str,
        resource_group_name: str,
        mi_user_assigned: str,
        federated_credential_name: Optional[str] = None,
        **kwargs,
    ):
        """
        Responsible for federating and building the instance identity object.
        """
        kwargs.pop("usage_type", None)  # TODO - @digimaun, unused atm.
        mi_resource_id_container = parse_resource_id(mi_user_assigned)
        instance = self.show(name=name, resource_group_name=resource_group_name)
        cluster_resource = self.get_resource_map(instance).connected_cluster.resource
        self._ensure_oidc_issuer(cluster_resource)
        custom_location = self._get_associated_cl(instance)
        if not federated_credential_name:
            federated_credential_name = get_fc_name(
                cluster_name=cluster_resource["name"],
                namespace=custom_location["properties"]["namespace"],
                instance_name=instance["name"],
            )
        self.federate_msi(
            mi_resource_id_container,
            oidc_issuer=cluster_resource["properties"]["oidcIssuerProfile"]["issuerUrl"],
            federated_credential_name=federated_credential_name,
            namespace=custom_location["properties"]["namespace"],
        )

        identity: dict = instance.get("identity", {})
        if not identity or identity.get("type") == "None":
            identity["type"] = "UserAssigned"
            identity["userAssignedIdentities"] = {}
        identity["userAssignedIdentities"][mi_user_assigned] = {}

        instance["identity"] = identity
        return self.update(name=name, resource_group_name=resource_group_name, instance=instance, **kwargs)

    def enable_secretsync(
        self,
        name: str,
        resource_group_name: str,
        mi_user_assigned: str,
        keyvault_resource_id: str,
        federated_credential_name: Optional[str] = None,
        spc_name: Optional[str] = None,
        skip_role_assignments: bool = False,
        **kwargs,
    ):
        mi_resource_id_container = parse_resource_id(mi_user_assigned)
        keyvault_resource_id_container = parse_resource_id(keyvault_resource_id)
        with console.status("Working...") as status:
            keyvault: dict = self.resource_client.resources.get_by_id(
                resource_id=keyvault_resource_id_container.resource_id, api_version=KEYVAULT_CLOUD_API_VERSION
            )
            mi_user_assigned: dict = self.msi_mgmt_client.user_assigned_identities.get(
                resource_group_name=mi_resource_id_container.resource_group_name,
                resource_name=mi_resource_id_container.resource_name,
            )
            role_assignment_error = None
            if not skip_role_assignments:
                role_assignment_error = self._attempt_keyvault_role_assignments(
                    keyvault=keyvault, mi_user_assigned=mi_user_assigned
                )

            instance = self.show(name=name, resource_group_name=resource_group_name)
            resource_map = self.get_resource_map(instance)
            cluster_resource = resource_map.connected_cluster.resource
            custom_location = self._get_associated_cl(instance)
            cl_resources = resource_map.connected_cluster.get_aio_resources(custom_location_id=custom_location["id"])
            self._ensure_oidc_issuer(cluster_resource)
            secretsync_spc = self._find_existing_spc(cl_resources)
            if secretsync_spc:
                status.stop()
                logger.warning(
                    f"Instance '{instance['name']}' is already enabled for secret sync.\n"
                    f"Use 'az iot ops secretsync show -n {instance['name']} -g {resource_group_name}' for details."
                )
                return
            if not federated_credential_name:
                federated_credential_name = (
                    get_fc_name(
                        cluster_name=cluster_resource["name"],
                        namespace=custom_location["properties"]["namespace"],
                        instance_name=instance["name"],
                    )
                    + "-ssc"
                )
            self.federate_msi(
                mi_resource_id_container=mi_resource_id_container,
                oidc_issuer=cluster_resource["properties"]["oidcIssuerProfile"]["issuerUrl"],
                federated_credential_name=federated_credential_name,
                namespace=custom_location["properties"]["namespace"],
                service_account_name=SERVICE_ACCOUNT_SECRETSYNC,
            )
            spc_poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
                resource_group_name=resource_group_name,
                azure_key_vault_secret_provider_class_name=spc_name or get_spc_name(instance["name"]),
                resource={
                    "location": cluster_resource["location"],
                    "extendedLocation": instance["extendedLocation"],
                    "properties": {
                        "clientId": mi_user_assigned["properties"]["clientId"],
                        "keyvaultName": keyvault_resource_id_container.resource_name,
                        "tenantId": get_tenant_id(),
                    },
                },
            )
            result_spc = wait_for_terminal_state(spc_poller, **kwargs)
            status.stop()
            if role_assignment_error:
                logger.warning(role_assignment_error)
            return result_spc

    def show_secretsync(self, name: str, resource_group_name: str) -> Optional[dict]:
        with console.status("Working..."):
            instance = self.show(name=name, resource_group_name=resource_group_name)
            resource_map = self.get_resource_map(instance)
            cl_resources = resource_map.connected_cluster.get_aio_resources(
                custom_location_id=instance["extendedLocation"]["name"]
            )
            secretsync_spc = self._find_existing_spc(cl_resources)
            if secretsync_spc:
                return secretsync_spc
        logger.warning(f"No secret provider class detected.\n{get_enable_syntax(name, resource_group_name)}")

    def disable_secretsync(
        self,
        name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            instance = self.show(name=name, resource_group_name=resource_group_name)
            resource_map = self.get_resource_map(instance)
            cl_resources = resource_map.connected_cluster.get_aio_resources(
                custom_location_id=instance["extendedLocation"]["name"]
            )
            secretsync_spc = self._find_existing_spc(cl_resources)
            if secretsync_spc:
                spc_poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_delete(
                    resource_group_name=resource_group_name,
                    azure_key_vault_secret_provider_class_name=secretsync_spc["name"],
                )
                wait_for_terminal_state(spc_poller, **kwargs)
                return
        logger.warning(f"No secret provider class detected.\n{get_enable_syntax(name, resource_group_name)}")

    def _find_existing_spc(self, cl_resources: List[dict]) -> Optional[dict]:
        for resource in cl_resources:
            if resource["type"].lower() == "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses":
                resource_id_container = parse_resource_id(resource["id"])
                return self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
                    resource_group_name=resource_id_container.resource_group_name,
                    azure_key_vault_secret_provider_class_name=resource_id_container.resource_name,
                )

    def _attempt_keyvault_role_assignments(self, keyvault: dict, mi_user_assigned: dict) -> Optional[str]:
        """
        Returns error string is role-assignment fails.
        """
        target_role_ids = [KEYVAULT_ROLE_ID_SECRETS_USER, KEYVAULT_ROLE_ID_READER]
        try:
            for role_id in target_role_ids:
                self.permission_manager.apply_role_assignment(
                    scope=keyvault["id"],
                    principal_id=mi_user_assigned["properties"]["principalId"],
                    role_def_id=ROLE_DEF_FORMAT_STR.format(
                        subscription_id=self.default_subscription_id,
                        role_id=role_id,
                    ),
                )
        except Exception as e:
            return get_user_msg_warn_ra(
                prefix=f"Role assignment failed with:\n{str(e)}.",
                principal_id=mi_user_assigned["properties"]["principalId"],
                scope=keyvault["id"],
            )

    def _ensure_oidc_issuer(self, cluster_resource: dict):
        enabled_oidc = cluster_resource["properties"].get("oidcIssuerProfile", {}).get("enabled", False)
        enabled_wlif = (
            cluster_resource["properties"].get("securityProfile", {}).get("workloadIdentity", {}).get("enabled", False)
        )

        error = f"The connected cluster '{cluster_resource['name']}' is not enabled"
        fix_with = (
            f"Please enable with 'az connectedk8s update -n {cluster_resource['name']} "
            f"-g {parse_resource_id(cluster_resource['id']).resource_group_name}"
        )
        if not enabled_oidc:
            error += " as an oidc issuer"
            fix_with += " --enable-oidc-issuer"
        if not enabled_wlif:
            sep = "" if enabled_oidc else " or"
            error += f"{sep} for workload identity federation"
            fix_with += " --enable-workload-identity"
        error += ".\n"
        error += f"{fix_with}'."

        if any([not enabled_oidc, not enabled_wlif]):
            raise ValidationError(error)

    def federate_msi(
        self,
        mi_resource_id_container: ResourceIdContainer,
        oidc_issuer: str,
        federated_credential_name: str,
        namespace: str = "azure-iot-operations",
        service_account_name: str = SERVICE_ACCOUNT_DATAFLOW,
    ):
        self.msi_mgmt_client.federated_identity_credentials.create_or_update(
            resource_group_name=mi_resource_id_container.resource_group_name,
            resource_name=mi_resource_id_container.resource_name,
            federated_identity_credential_resource_name=federated_credential_name,
            parameters={
                "properties": {
                    "subject": f"system:serviceaccount:{namespace}:{service_account_name}",
                    "audiences": ["api://AzureADTokenExchange"],
                    "issuer": oidc_issuer,
                }
            },
        )

    def unfederate_msi(
        self,
        mi_resource_id_container: ResourceIdContainer,
        federated_credential_name: str,
    ):
        self.msi_mgmt_client.federated_identity_credentials.delete(
            resource_group_name=mi_resource_id_container.resource_group_name,
            resource_name=mi_resource_id_container.resource_name,
            federated_identity_credential_resource_name=federated_credential_name,
        )
