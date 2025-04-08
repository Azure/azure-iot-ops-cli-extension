# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from json import dumps
from pathlib import PurePath, Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from uuid import uuid4

from azure.cli.core.azclierror import AzureResponseError, ValidationError
from knack.log import get_logger
from packaging import version
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table, box

from ....constants import VERSION as CLI_VERSION
from ...util import (
    chunk_list,
    get_timestamp_now_utc,
    should_continue_prompt,
    to_safe_filename,
)
from ...util.az_client import (
    REGISTRY_API_VERSION,
    wait_for_terminal_state,
    get_resource_client,
    get_msi_mgmt_client,
)
from ...util.id_tools import parse_resource_id
from .common import (
    CONTRIBUTOR_ROLE_ID,
    CUSTOM_LOCATIONS_API_VERSION,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_OSM,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    EXTENSION_TYPE_TO_MONIKER_MAP,
    OPS_EXTENSION_DEPS,
    PROVISIONING_STATE_SUCCESS,
)
from .resources import Instances
from .resources.instances import get_fc_name
from .connected_cluster import ConnectedCluster

DEFAULT_CONSOLE = Console()

if TYPE_CHECKING:
    from azure.core.polling import LROPoller


class SummaryMode(Enum):
    SIMPLE = "simple"
    DETAILED = "detailed"


class TemplateMode(Enum):
    NESTED = "nested"
    LINKED = "linked"


class StateResourceKey(Enum):
    CL = "customLocation"
    INSTANCE = "instance"
    BROKER = "broker"
    LISTENER = "listener"
    AUTHN = "authn"
    AUTHZ = "authz"
    PROFILE = "dataflowProfile"
    ENDPOINT = "dataflowEndpoint"
    DATAFLOW = "dataflow"
    ASSET = "asset"
    ASSET_ENDPOINT_PROFILE = "assetEndpointProfile"
    SSC_SPC = "secretProviderClass"
    SSC_SECRETSYNC = "secretSync"
    ROLE_ASSIGNMENT = "roleAssignment"
    FEDERATE = "identityFederation"


class TemplateParams(Enum):
    INSTANCE_NAME = "instanceName"
    CLUSTER_NAME = "clusterName"
    CUSTOM_LOCATION_NAME = "customLocationName"
    SUBSCRIPTION = "subscription"
    RESOURCEGROUP = "resourceGroup"
    SCHEMA_REGISTRY_ID = "schemaRegistryId"
    PRINCIPAL_ID = "principalId"
    RESOURCE_SLUG = "resourceSlug"


TEMPLATE_EXPRESSION_MAP = {
    "instanceName": f"[parameters('{TemplateParams.INSTANCE_NAME.value}')]",
    "instanceNestedName": (f"[concat(parameters('{TemplateParams.INSTANCE_NAME.value}'), " "'{}')]"),
    "clusterName": f"[parameters('{TemplateParams.CLUSTER_NAME.value}')]",
    "clusterId": (
        "[resourceId('Microsoft.Kubernetes/connectedClusters', " f"parameters('{TemplateParams.CLUSTER_NAME.value}'))]"
    ),
    "customLocationName": f"[parameters('{TemplateParams.CUSTOM_LOCATION_NAME.value}')]",
    "customLocationId": (
        "[resourceId('Microsoft.ExtendedLocation/customLocations', "
        f"parameters('{TemplateParams.CUSTOM_LOCATION_NAME.value}'))]"
    ),
    "extensionId": (
        "[concat(resourceId('Microsoft.Kubernetes/connectedClusters', "
        f"parameters('{TemplateParams.CLUSTER_NAME.value}')), "
        "'/providers/Microsoft.KubernetesConfiguration/extensions/{})]"
    ),
    "schemaRegistryId": f"[parameters('{TemplateParams.SCHEMA_REGISTRY_ID.value}')]",
}


def get_resource_id_expr(rtype: str, resource_id: str, for_instance: bool = True) -> str:
    id_meta = parse_resource_id(resource_id)
    initial_seg = f"parameters('{TemplateParams.INSTANCE_NAME.value}')" if for_instance else id_meta["name"]
    target_name = f"'{initial_seg}'"
    if for_instance:
        target_name = f"parameters('{TemplateParams.INSTANCE_NAME.value}')"
    last_child_num = id_meta.get("last_child_num", 0)
    if last_child_num:
        for i in range(1, last_child_num + 1):
            target_name += f", '{id_meta[f'child_name_{i}']}'"

    return f"[resourceId('{rtype}', {target_name})]"


def get_resource_id_by_parts(rtype: str, *args) -> str:
    def _rem_first_last(s: str, c: str):
        first = s.find(c)
        last = s.rfind(c)
        if first == -1 or first == last:
            return s
        return s[:first] + s[first + 1 : last] + s[last + 1 :]

    name_parts = ""
    for arg in args:
        name_parts += f", '{arg}'"
    # TODO: very hacky
    if "concat(" in name_parts:
        name_parts = _rem_first_last(name_parts, "'")
    return f"[resourceId('{rtype}'{name_parts})]"


def get_resource_id_by_param(rtype: str, param: TemplateParams) -> str:
    return f"[resourceId('{rtype}', parameters('{param.value}'))]"


class DeploymentContainer:
    def __init__(
        self,
        name: str,
        api_version: str = "2022-09-01",
        parameters: Optional[dict] = None,
        depends_on: Optional[Union[Iterable[str], str]] = None,
        resource_group: Optional[str] = None,
        subscription: Optional[str] = None,
    ):
        self.name = name
        self.rcontainer_map: Dict[str, "ResourceContainer"] = {}
        self.api_version = api_version
        self.parameters = parameters
        self.depends_on = depends_on
        if isinstance(self.depends_on, str):
            self.depends_on = {self.depends_on}
        self.resource_group = resource_group
        self.subscription = subscription

    def add_resources(
        self,
        key: Union[StateResourceKey, str],
        api_version: str,
        data_iter: Iterable[dict],
        depends_on: Optional[List[Union[StateResourceKey, str]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        if isinstance(key, StateResourceKey):
            key = key.value
        depends_on = process_depends_on(depends_on)

        to_enumerate = list(data_iter)

        count = 0
        for resource in to_enumerate:
            count += 1
            suffix = "" if count <= 1 else f"_{count}"
            target_key = f"{key}{suffix}"

            self.rcontainer_map[target_key] = ResourceContainer(
                api_version=api_version,
                resource_state=resource,
                depends_on=depends_on,
                config=config,
            )

    def get(self):
        result = {
            "type": "Microsoft.Resources/deployments",
            "apiVersion": self.api_version,
            "name": self.name,
            "properties": {
                "mode": "Incremental",
                "template": {
                    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
                    "contentVersion": "1.0.0.0",
                    "resources": [r.get() for r in list(self.rcontainer_map.values())],
                },
            },
        }
        if self.resource_group:
            result["resourceGroup"] = self.resource_group
        if self.subscription:
            # TODO: verify
            # result["subscription"] = self.subscription
            pass
        if self.parameters:
            input_param_map = {}
            template_param_map = {}

            for param in self.parameters:
                target_value = (
                    self.parameters[param]["value"]
                    if "value" in self.parameters[param]
                    else f"[parameters('{param}')]"
                )
                input_param_map[param] = {"value": target_value}
                template_param_map[param] = {"type": self.parameters[param]["type"]}

            result["properties"]["parameters"] = input_param_map
            result["properties"]["template"]["parameters"] = template_param_map
        if self.depends_on:
            result["dependsOn"] = list(self.depends_on)
        return result


class ResourceContainer:
    def __init__(
        self,
        api_version: str,
        resource_state: dict,
        depends_on: Optional[Iterable[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.api_version = api_version
        self.resource_state = resource_state
        if depends_on:
            depends_on = list(depends_on)
        self.depends_on = depends_on
        if not config:
            config = {}
        self.config = config

    def _prune_resource(self):
        filter_keys = {
            "id",
            "systemData",
        }
        self.resource_state = self._prune_resource_keys(filter_keys=filter_keys, resource=self.resource_state)
        filter_keys = {
            "provisioningState",
            "currentVersion",
            "statuses",
            "status",
        }
        self.resource_state["properties"] = self._prune_resource_keys(
            filter_keys=filter_keys, resource=self.resource_state["properties"]
        )

    def _prune_identity(self):
        filter_keys = {"principalId"}
        if "identity" in self.resource_state:
            self.resource_state["identity"] = self._prune_resource_keys(
                filter_keys=filter_keys, resource=self.resource_state["identity"]
            )

    @classmethod
    def _prune_resource_keys(cls, filter_keys: set, resource: dict) -> dict:
        result = {}
        for key in resource:
            if key not in filter_keys:
                result[key] = resource[key]
        return result

    def _apply_cl_ref(self):
        if "extendedLocation" in self.resource_state:
            self.resource_state["extendedLocation"]["name"] = TEMPLATE_EXPRESSION_MAP["customLocationId"]

    def _apply_nested_name(self):
        def __extract_suffix(path: str) -> str:
            return "/" + path.partition("/")[2]

        if "id" in self.resource_state:
            test: Dict[str, Union[str, int]] = parse_resource_id(self.resource_state["id"])
            target_name = test["name"]
            last_child_num = test.get("last_child_num", 0)
            if last_child_num:
                for i in range(1, last_child_num + 1):
                    target_name += f"/{test[f'child_name_{i}']}"
            self.resource_state["name"] = target_name
            if test["type"].lower() == "instances":
                suffix = __extract_suffix(target_name)
                if suffix == "/":
                    self.resource_state["name"] = TEMPLATE_EXPRESSION_MAP["instanceName"]
                else:
                    self.resource_state["name"] = TEMPLATE_EXPRESSION_MAP["instanceNestedName"].format(suffix)

    def get(self):
        apply_nested_name = self.config.get("apply_nested_name", True)
        if apply_nested_name:
            self._apply_nested_name()

        self._apply_cl_ref()
        self._prune_identity()
        self._prune_resource()

        result = {
            "apiVersion": self.api_version,
            **self.resource_state,
        }
        if self.depends_on:
            result["dependsOn"] = self.depends_on
        return result


class InstanceRestore:
    def __init__(
        self,
        cmd,
        instances: Instances,
        from_instance_name: str,
        cluster_resource_id: str,
        template_content: "TemplateContent",
        user_assigned_mis: Optional[List[str]] = None,
        template_mode: Optional[str] = None,
        no_progress: Optional[bool] = None,
    ):
        self.cmd = cmd
        self.instances = instances
        self.template_content = template_content
        self.from_instance_name = from_instance_name
        self.parsed_cluster_id = parse_resource_id(cluster_resource_id)
        self.cluster_name = self.parsed_cluster_id["name"]
        self.resource_group_name = self.parsed_cluster_id["resource_group"]
        self.subscription_id = self.parsed_cluster_id["subscription"]
        self.connected_cluster = ConnectedCluster(
            cmd=self.cmd,
            subscription_id=self.subscription_id,
            cluster_name=self.cluster_name,
            resource_group_name=self.resource_group_name,
        )
        self.resource_client = get_resource_client(subscription_id=self.subscription_id)
        self.msi_client = get_msi_mgmt_client(subscription_id=self.subscription_id)
        self.template_mode = template_mode
        self.user_assigned_mis = user_assigned_mis
        self.no_progress = no_progress

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
                resource_group_name=self.resource_group_name,
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
            resource_group_name=self.resource_group_name,
            deployment_name=deployment_name,
            parameters=deployment_params,
        )

    def _handle_federation(self, use_self_hosted_issuer: Optional[bool] = None):
        if not self.user_assigned_mis:
            return
        cluster_resource = self.connected_cluster.resource
        oidc_issuer = self.instances._ensure_oidc_issuer(
            cluster_resource, use_self_hosted_issuer=use_self_hosted_issuer
        )

        for i in range(len(self.user_assigned_mis)):
            resource_id = parse_resource_id(self.user_assigned_mis[i])
            credentials = list(
                self.msi_client.federated_identity_credentials.list(
                    resource_group_name=resource_id["resource_group"], resource_name=resource_id["name"]
                )
            )
            filtered_creds = []
            for cred in credentials:
                if cred["properties"]["issuer"] != oidc_issuer:
                    filtered_creds.append(cred)

            for cred in filtered_creds:
                if ":aio-" not in cred["properties"]["subject"]:
                    continue

                # TODO: Handle repeats if subject not already handled
                self.msi_client.federated_identity_credentials.create_or_update(
                    resource_group_name=resource_id["resource_group"],
                    resource_name=resource_id["name"],
                    federated_identity_credential_resource_name=get_fc_name(
                        cluster_name=self.cluster_name,
                        oidc_issuer=oidc_issuer,
                        subject=cred["properties"]["subject"],
                    ),
                    parameters={
                        "properties": {
                            "subject": cred["properties"]["subject"],
                            "audiences": cred["properties"]["audiences"],
                            "issuer": oidc_issuer,
                        }
                    },
                )

    def deploy(
        self,
        instance_name: Optional[str] = None,
        use_self_hosted_issuer: Optional[bool] = None,
    ):
        parameters = {
            "clusterName": {"value": self.cluster_name},
        }
        if instance_name:
            parameters["instanceName"] = {"value": instance_name}
        deployment_name = default_bundle_name(self.from_instance_name)

        DEFAULT_CONSOLE.print()

        deployment_work = []
        if self.template_mode == TemplateMode.LINKED.value:
            deployment_work.extend(self.template_content.get_split_content())
        else:
            deployment_work.append(self.template_content.content)
        total_pages = len(deployment_work)

        with DEFAULT_CONSOLE.status("Pre-flight...") as console:
            self._deploy_template(
                content=deployment_work[0],
                parameters=parameters,
                deployment_name=deployment_name,
                what_if=True,
            )
            # TODO
            self._handle_federation(use_self_hosted_issuer)

            for i in range(total_pages):
                status = f"Initiating {deployment_name} {i+1}/{total_pages}"
                console.update(status=status)
                poller = self._deploy_template(
                    content=deployment_work[i],
                    parameters=parameters,
                    deployment_name=f"{deployment_name}_{i+1}",
                )
                deployment_link = self._get_deployment_link(deployment_name=f"{deployment_name}_{i+1}")
                DEFAULT_CONSOLE.print(
                    f"->[link={deployment_link}]Link to {self.cluster_name} deployment {i+1}/{total_pages}[/link]",
                    highlight=False,
                )
                if total_pages > 1:
                    wait_for_terminal_state(poller)

        DEFAULT_CONSOLE.print()

    def _get_deployment_link(self, deployment_name: str) -> str:
        return (
            "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"
            f"%2Fsubscriptions%2F{self.subscription_id}%2FresourceGroups%2F{self.resource_group_name}"
            f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{deployment_name}"
        )


def backup_ops_instance(
    cmd,
    instance_name: str,
    resource_group_name: str,
    summary_mode: Optional[str] = None,
    to_dir: Optional[str] = None,
    template_mode: Optional[str] = None,
    to_instance_name: Optional[str] = None,
    to_cluster_id: Optional[str] = None,
    use_self_hosted_issuer: Optional[bool] = None,
    linked_base_uri: Optional[str] = None,
    no_progress: Optional[bool] = None,
    confirm_yes: Optional[bool] = None,
    **kwargs,
):
    backup_manager = BackupManager(
        cmd=cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        no_progress=no_progress,
    )
    bundle_path = get_bundle_path(instance_name, bundle_dir=to_dir)

    backup_state = backup_manager.analyze_cluster()

    if not no_progress:
        render_upgrade_table(
            backup_state, bundle_path, to_cluster_id, detailed=summary_mode == SummaryMode.DETAILED.value
        )

    if all([not to_dir, not to_cluster_id]):
        return

    should_bail = not should_continue_prompt(confirm_yes=confirm_yes, context="Clone")
    if should_bail:
        return

    template_content = backup_state.get_content()
    template_content.write(bundle_path, template_mode=template_mode, linked_base_uri=linked_base_uri)

    if to_cluster_id:
        restore_client = backup_state.get_restore_client(
            to_cluster_id=to_cluster_id, template_mode=template_mode, no_progress=no_progress
        )
        restore_client.deploy(instance_name=to_instance_name, use_self_hosted_issuer=use_self_hosted_issuer)


def render_upgrade_table(
    backup_state: "BackupState",
    bundle_path: Optional[PurePath] = None,
    to_cluster_id: Optional[str] = None,
    detailed: bool = False,
):
    table = get_default_table(include_name=detailed)
    total = 0
    for rtype in backup_state.resources:
        rtype_len = len(backup_state.resources[rtype])
        total += rtype_len
        row_content = [f"{rtype}", f"{rtype_len}"]
        if detailed:
            row_content.append("\n".join([r["resource_name"] for r in backup_state.resources[rtype]]))
        table.add_row(*row_content)

    table.title += f" of {backup_state.instance_name}\nTotal resources {total}"
    DEFAULT_CONSOLE.print(table)
    # DEFAULT_CONSOLE.print(f"Total resources: {total}\n", highlight=True)

    if bundle_path:
        DEFAULT_CONSOLE.print(f"State will be saved to:\n-> {bundle_path}\n")

    if to_cluster_id:
        parsed_to_cluster_id = parse_resource_id(to_cluster_id)
        DEFAULT_CONSOLE.print(
            f"State will be cloned to connected cluster:\n"
            f"* Name: {parsed_to_cluster_id['name']}\n"
            f"* Resource Group: {parsed_to_cluster_id['resource_group']}\n"
            f"* Subscription: {parsed_to_cluster_id['subscription']}\n",
            highlight=False,
        )


def get_default_table(include_name: bool = False) -> Table:
    table = Table(
        box=box.MINIMAL,
        expand=False,
        title="Capture",
        min_width=79,
        show_footer=True,
    )
    table.add_column("Resource Type")
    table.add_column("#")
    if include_name:
        table.add_column("Name")

    return table


class BackupState:
    def __init__(
        self,
        cmd,
        instance_name: str,
        instances: Instances,
        resources: dict,
        template_gen: "TemplateGen",
        user_assigned_mis: Optional[List[str]] = None,
    ):
        self.cmd = cmd
        self.instance_name = instance_name
        self.instances = instances
        self.resources = resources
        self.template_gen = template_gen
        self.content = self.template_gen.get_content()
        self.user_assigned_mis = user_assigned_mis

    def get_content(self) -> "TemplateContent":
        return self.content

    def get_restore_client(
        self, to_cluster_id: str, template_mode: str, no_progress: Optional[bool] = None
    ) -> "InstanceRestore":
        return InstanceRestore(
            cmd=self.cmd,
            instances=self.instances,
            from_instance_name=self.instance_name,
            cluster_resource_id=to_cluster_id,
            template_content=self.content,
            user_assigned_mis=self.user_assigned_mis,
            template_mode=template_mode,
            no_progress=no_progress,
        )


class BackupManager:
    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: str,
        no_progress: Optional[bool] = None,
    ):
        self.cmd = cmd
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.no_progress = no_progress
        self.instances = Instances(self.cmd)
        self.instance_record = self.instances.show(
            name=self.instance_name, resource_group_name=self.resource_group_name
        )

        self.resource_map = self.instances.get_resource_map(self.instance_record)
        self.resouce_graph = self.resource_map.connected_cluster.resource_graph
        self.rcontainer_map: Dict[str, ResourceContainer] = {}
        self.parameter_map: dict = {}
        self.variable_map: dict = {}
        self.metadata_map: dict = {}
        self.instance_identities: List[str] = []
        self.active_deployment: Dict[StateResourceKey, List[str]] = {}
        self.chunk_size = 800

    def analyze_cluster(self) -> "BackupState":
        with Progress(
            SpinnerColumn("star"),
            *Progress.get_default_columns(),
            "Elapsed:",
            TimeElapsedColumn(),
            transient=True,
            disable=bool(self.no_progress),
            # disable=True,
        ) as progress:
            _ = progress.add_task(f"Analyzing {self.instance_name}...", total=None)
            self._build_parameters(self.instance_record)
            self._build_variables()
            self._build_metadata()

            self._analyze_extensions()
            self._analyze_instance()
            self._analyze_instance_identity()
            self._analyze_instance_resources()
            self._analyze_secretsync()
            self._analyze_assets()

            return BackupState(
                cmd=self.cmd,
                instance_name=self.instance_name,
                instances=self.instances,
                resources=self._enumerate_resources(),
                template_gen=TemplateGen(
                    self.rcontainer_map, self.parameter_map, self.variable_map, self.metadata_map
                ),
                user_assigned_mis=self.instance_identities,
            )

    def _enumerate_resources(self):
        enumerated_map: dict = {}

        def __enumerator(rcontainer_map: Dict[str, ResourceContainer]):
            for resource in rcontainer_map:
                target_rcontainer = rcontainer_map[resource]
                if isinstance(target_rcontainer, ResourceContainer):
                    if "id" not in target_rcontainer.resource_state:
                        continue
                    parsed_id = parse_resource_id(target_rcontainer.resource_state["id"].lower())
                    key = f"{parsed_id['namespace']}/{parsed_id['type']}"
                    if "resource_type" in parsed_id and parsed_id["resource_type"] != parsed_id["type"]:
                        key += f"/{parsed_id['resource_type']}"

                    items: list = enumerated_map.get(key, [])
                    items.append(parsed_id)
                    enumerated_map[key] = items
                if isinstance(target_rcontainer, DeploymentContainer):
                    __enumerator(target_rcontainer.rcontainer_map)

        __enumerator(self.rcontainer_map)
        return enumerated_map

    def _build_parameters(self, instance: dict):
        self.parameter_map.update(build_parameter(name=TemplateParams.CLUSTER_NAME.value))
        self.parameter_map.update(
            build_parameter(name=TemplateParams.INSTANCE_NAME.value, default=self.instance_record["name"])
        )
        self.parameter_map.update(
            build_parameter(
                name=TemplateParams.RESOURCE_SLUG.value,
                default=(
                    "[take(uniqueString(resourceGroup().id, "
                    "parameters('clusterName'), parameters('instanceName')), 5)]"
                ),
            )
        )
        self.parameter_map.update(
            build_parameter(
                name=TemplateParams.CUSTOM_LOCATION_NAME.value,
                default="[format('location-{0}', parameters('resourceSlug'))]",
            )
        )

    def _build_variables(self):
        self.variable_map["aioExtName"] = "[format('azure-iot-operations-{0}', parameters('resourceSlug'))]"

    def _build_metadata(self):
        self.metadata_map["opsCliVersion"] = CLI_VERSION
        self.metadata_map["clonedInstanceId"] = self.instance_record["id"]

    def get_resources_of_type(self, resource_type: str) -> List[dict]:
        return self.resouce_graph.query_resources(
            f"""
            resources
            | where extendedLocation.name =~ '{self.instance_record["extendedLocation"]["name"]}'
            | where type =~ '{resource_type}'
            | project id, name, type, location, extendedLocation, properties
            """
        )["data"]

    def get_identities_by_client_id(self, client_ids: List[str]) -> List[dict]:
        return self.resouce_graph.query_resources(
            f"""
            resources
            | where type =~ "Microsoft.ManagedIdentity/userAssignedIdentities"
            | where properties.clientId in~ ("{'", "'.join(client_ids)}")
            | project id, name, type, properties
            """
        )["data"]

    def _analyze_extensions(self):
        depends_on_map = {
            EXTENSION_TYPE_SSC: [EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_PLATFORM]],
            EXTENSION_TYPE_ACS: [
                EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_PLATFORM],
                EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OSM],
            ],
            EXTENSION_TYPE_OPS: [EXTENSION_TYPE_TO_MONIKER_MAP[ext_type] for ext_type in list(OPS_EXTENSION_DEPS)],
        }
        api_version = (
            self.resource_map.connected_cluster.clusters.extensions.clusterconfig_mgmt_client._config.api_version
        )
        extension_map = self.resource_map.connected_cluster.get_extensions_by_type(
            *list(EXTENSION_TYPE_TO_MONIKER_MAP.keys())
        )
        for extension_type in extension_map:
            extension_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[extension_type]
            depends_on = depends_on_map.get(extension_type)
            extension_map[extension_type]["scope"] = TEMPLATE_EXPRESSION_MAP["clusterId"]
            if extension_moniker == EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS]:
                extension_map[extension_type]["name"] = "[variables('aioExtName')]"

            self._add_resource(
                key=extension_moniker,
                api_version=api_version,
                data=extension_map[extension_type],
                depends_on=depends_on,
                config={"apply_nested_name": False},
            )

    def _analyze_instance(self):
        api_version = self.instances.iotops_mgmt_client._config.api_version
        # TODO - @digimaun, not efficient.
        custom_location = self.instances._get_associated_cl(self.instance_record)
        custom_location["properties"]["hostResourceId"] = TEMPLATE_EXPRESSION_MAP["clusterId"]
        # TODO
        custom_location["name"] = TEMPLATE_EXPRESSION_MAP["customLocationName"]

        cl_extension_ids = []
        cl_monikers = [
            EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_PLATFORM],
            EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_SSC],
            EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS],
        ]
        for moniker in cl_monikers:
            ext_resource = self.rcontainer_map.get(moniker)
            if moniker == EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS]:
                cl_extension_ids.append(TEMPLATE_EXPRESSION_MAP["extensionId"].format("', variables('aioExtName')"))
            else:
                cl_extension_ids.append(
                    TEMPLATE_EXPRESSION_MAP["extensionId"].format(f"{ext_resource.resource_state['name']}'")
                )

        custom_location["properties"]["clusterExtensionIds"] = cl_extension_ids
        custom_location["properties"]["displayName"] = "[parameters('customLocationName')]"

        self._add_resource(
            key=StateResourceKey.CL,
            api_version=CUSTOM_LOCATIONS_API_VERSION,
            data=custom_location,
            config={"apply_nested_name": False},
            depends_on=cl_monikers,
        )
        # self.instance_record["properties"]["schemaRegistryRef"]["resourceId"] = TEMPLATE_EXPRESSION_MAP[
        #     "schemaRegistryId"
        # ]
        self._add_resource(
            key=StateResourceKey.INSTANCE,
            api_version=api_version,
            data=self.instance_record,
            depends_on=StateResourceKey.CL,
        )
        # self._add_resource(
        #     key=StateResourceKey.ROLE_ASSIGNMENT,
        #     api_version="2022-04-01",
        #     data=get_role_assignment(),
        #     depends_on=EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS],
        #     config={"apply_nested_name": False},
        # )
        nested_params = {
            **build_parameter(name=TemplateParams.CLUSTER_NAME.value),
            **build_parameter(name=TemplateParams.INSTANCE_NAME.value),
            **build_parameter(
                name=TemplateParams.PRINCIPAL_ID.value,
                value="[reference('iotOperations', '2023-05-01', 'Full').identity.principalId]",
            ),
            **build_parameter(
                name=TemplateParams.SCHEMA_REGISTRY_ID.value,
                value=self.instance_record["properties"]["schemaRegistryRef"]["resourceId"],
            ),
        }
        parsed_sr_id = parse_resource_id(self.instance_record["properties"]["schemaRegistryRef"]["resourceId"])
        self._add_deployment(
            key=StateResourceKey.ROLE_ASSIGNMENT,
            api_version="2022-04-01",
            data_iter=[get_role_assignment()],
            depends_on=EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_OPS],
            parameters=nested_params,
            resource_group=parsed_sr_id["resource_group"],
            subscription=parsed_sr_id["subscription"],
        )

    def _analyze_instance_resources(self):
        api_version = self.instances.iotops_mgmt_client._config.api_version
        brokers_iter = self.instances.iotops_mgmt_client.broker.list_by_resource_group(
            resource_group_name=self.resource_group_name, instance_name=self.instance_name
        )
        # Let us keep things simple atm
        default_broker = list(brokers_iter)[0]
        self._add_resource(
            key=StateResourceKey.BROKER,
            api_version=api_version,
            data=default_broker,
            depends_on=StateResourceKey.INSTANCE,
        )

        # Initial dependencies
        nested_params = {
            **build_parameter(name=TemplateParams.CUSTOM_LOCATION_NAME.value),
            **build_parameter(name=TemplateParams.INSTANCE_NAME.value),
        }
        broker_resource_id_expr = get_resource_id_expr(rtype=default_broker["type"], resource_id=default_broker["id"])

        # authN
        self._add_deployment(
            key=StateResourceKey.AUTHN,
            api_version=api_version,
            data_iter=self.instances.iotops_mgmt_client.broker_authentication.list_by_resource_group(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                broker_name=default_broker["name"],
            ),
            depends_on=broker_resource_id_expr,
            parameters=nested_params,
        )

        # authZ
        self._add_deployment(
            key=StateResourceKey.AUTHZ,
            api_version=api_version,
            data_iter=self.instances.iotops_mgmt_client.broker_authorization.list_by_resource_group(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                broker_name=default_broker["name"],
            ),
            depends_on=broker_resource_id_expr,
            parameters=nested_params,
        )

        # listener
        listener_depends_on = []
        for active in self.active_deployment:
            if active in [StateResourceKey.AUTHN, StateResourceKey.AUTHZ]:
                listener_depends_on.append(
                    get_resource_id_by_parts("Microsoft.Resources/deployments", self.active_deployment[active][-1])
                )

        self._add_deployment(
            key=StateResourceKey.LISTENER,
            api_version=api_version,
            data_iter=self.instances.iotops_mgmt_client.broker_listener.list_by_resource_group(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                broker_name=default_broker["name"],
            ),
            depends_on=listener_depends_on,
            parameters=nested_params,
        )

        instance_resource_id_expr = get_resource_id_by_param(
            "microsoft.iotoperations/instances", TemplateParams.INSTANCE_NAME
        )

        # endpoint
        self._add_deployment(
            key=StateResourceKey.ENDPOINT,
            api_version=api_version,
            data_iter=self.instances.iotops_mgmt_client.dataflow_endpoint.list_by_resource_group(
                resource_group_name=self.resource_group_name, instance_name=self.instance_name
            ),
            depends_on=instance_resource_id_expr,
            parameters=nested_params,
        )

        # profile
        profile_iter = list(
            self.instances.iotops_mgmt_client.dataflow_profile.list_by_resource_group(
                resource_group_name=self.resource_group_name, instance_name=self.instance_name
            )
        )
        self._add_deployment(
            key=StateResourceKey.PROFILE,
            api_version=api_version,
            data_iter=profile_iter,
            depends_on=instance_resource_id_expr,
            parameters=nested_params,
        )

        # dataflow
        if profile_iter:
            dataflows = []
            for profile in profile_iter:
                dataflows.extend(
                    self.instances.iotops_mgmt_client.dataflow.list_by_profile_resource(
                        resource_group_name=self.resource_group_name,
                        instance_name=self.instance_name,
                        dataflow_profile_name=profile["name"],
                    )
                )

            self._add_deployment(
                key=StateResourceKey.DATAFLOW,
                api_version=api_version,
                data_iter=dataflows,
                depends_on=[
                    get_resource_id_by_parts(
                        "Microsoft.Resources/deployments", self.active_deployment[StateResourceKey.PROFILE][-1]
                    ),
                    get_resource_id_by_parts(
                        "Microsoft.Resources/deployments", self.active_deployment[StateResourceKey.ENDPOINT][-1]
                    ),
                ],
                parameters=nested_params,
            )

    def _analyze_assets(self):
        nested_params = {
            **build_parameter(name=TemplateParams.CUSTOM_LOCATION_NAME.value),
        }
        instance_resource_id_expr = get_resource_id_by_param(
            "microsoft.iotoperations/instances", TemplateParams.INSTANCE_NAME
        )

        asset_endpoints = self.get_resources_of_type(resource_type="microsoft.deviceregistry/assetendpointprofiles")
        self._add_deployment(
            key=StateResourceKey.ASSET_ENDPOINT_PROFILE,
            api_version=REGISTRY_API_VERSION,
            data_iter=asset_endpoints,
            depends_on=[
                instance_resource_id_expr,
                get_resource_id_by_parts(
                    "Microsoft.Resources/deployments",
                    self.active_deployment[StateResourceKey.LISTENER][-1],
                ),
            ],
            parameters=nested_params,
        )

        assets = self.get_resources_of_type(resource_type="microsoft.deviceregistry/assets")
        if assets and asset_endpoints:
            self._add_deployment(
                key=StateResourceKey.ASSET,
                api_version=REGISTRY_API_VERSION,
                data_iter=assets,
                depends_on=get_resource_id_by_parts(
                    "Microsoft.Resources/deployments",
                    self.active_deployment[StateResourceKey.ASSET_ENDPOINT_PROFILE][-1],
                ),
                parameters=nested_params,
            )

    def _analyze_secretsync(self):
        nested_params = {
            **build_parameter(name=TemplateParams.CUSTOM_LOCATION_NAME.value),
        }
        ssc_client = self.instances.ssc_mgmt_client
        ssc_api_version = ssc_client._config.api_version
        instance_resource_id_expr = get_resource_id_by_param(
            "microsoft.iotoperations/instances", TemplateParams.INSTANCE_NAME
        )
        ext_loc_id = self.instance_record["extendedLocation"]["name"].lower()
        ssc_spcs = list(
            ssc_client.azure_key_vault_secret_provider_classes.list_by_resource_group(
                resource_group_name=self.resource_group_name
            )
        )

        ssc_spcs = [spc for spc in ssc_spcs if spc["extendedLocation"]["name"].lower() == ext_loc_id]
        client_ids = [spc["properties"]["clientId"] for spc in ssc_spcs if "clientId" in spc["properties"]]
        self.instance_identities.extend([mid["id"] for mid in self.get_identities_by_client_id(client_ids)])

        self._add_deployment(
            key=StateResourceKey.SSC_SPC,
            api_version=ssc_api_version,
            data_iter=ssc_spcs,
            depends_on=instance_resource_id_expr,
            parameters=nested_params,
        )

        ssc_secretsyncs = list(
            ssc_client.secret_syncs.list_by_resource_group(resource_group_name=self.resource_group_name)
        )
        ssc_secretsyncs = [
            secretsync
            for secretsync in ssc_secretsyncs
            if secretsync["extendedLocation"]["name"].lower() == ext_loc_id
        ]
        if ssc_secretsyncs and ssc_spcs:
            self._add_deployment(
                key=StateResourceKey.SSC_SECRETSYNC,
                api_version=ssc_api_version,
                data_iter=ssc_secretsyncs,
                depends_on=get_resource_id_by_parts(
                    "Microsoft.Resources/deployments", self.active_deployment[StateResourceKey.SSC_SPC][-1]
                ),
                parameters=nested_params,
            )

    def _analyze_instance_identity(self):
        identity: dict = self.instance_record.get("identity", {}).get("userAssignedIdentities", {})
        for rid in identity:
            identity[rid] = {}
            self.instance_identities.append(rid)

    def add_deployment_by_key(self, key: StateResourceKey) -> Tuple[str, str]:
        deployments_by_key = self.active_deployment.get(key, [])
        symbolic_name = f"{key.value}s_{len(deployments_by_key)+1}"
        deployment_name = f"concat(parameters('resourceSlug'), '_{symbolic_name}')"
        deployments_by_key.append(deployment_name)
        self.active_deployment[key] = deployments_by_key
        return symbolic_name, deployment_name

    def _add_deployment(
        self,
        key: StateResourceKey,
        api_version: str,
        data_iter: Iterable,
        depends_on: Optional[Union[str, Iterable[str]]] = None,
        parameters: Optional[dict] = None,
        resource_group: Optional[str] = None,
        subscription: Optional[str] = None,
    ):
        data_iter = list(data_iter)
        if data_iter:
            chunked_list_data = chunk_list(data_iter, self.chunk_size, 750)

            for chunk in chunked_list_data:
                symbolic_name, deployment_name = self.add_deployment_by_key(key)
                # TODO Debug
                # with open(f"./{symbolic_name}.json", mode="w") as myfile:
                #     myfile.write(dumps(chunk))

                deployment_container = DeploymentContainer(
                    name=f"[{deployment_name}]",
                    depends_on=depends_on,
                    parameters=parameters,
                    resource_group=resource_group,
                    subscription=subscription,
                )
                deployment_container.add_resources(
                    key=key,
                    api_version=api_version,
                    data_iter=chunk,
                )
                self.rcontainer_map[symbolic_name] = deployment_container

    def _add_resource(
        self,
        key: Union[StateResourceKey, str],
        api_version: str,
        data: dict,
        depends_on: Optional[Union[Iterable[str], str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        if isinstance(key, StateResourceKey):
            key = key.value
        depends_on = process_depends_on(depends_on)

        self.rcontainer_map[key] = ResourceContainer(
            api_version=api_version,
            resource_state=data,
            depends_on=depends_on,
            config=config,
        )


class TemplateContent:
    def __init__(self, content: dict):
        self.content = content
        self.linked_type_map = {
            "microsoft.deviceregistry/assets": 0,
            "microsoft.deviceregistry/assetendpointprofiles": 0,
        }
        self.copy_params = {"clusterName", "customLocationName", "resourceSlug", "instanceName"}

    def get_split_content(self) -> List[dict]:
        result = [self.content]
        parameters = self.content.get("parameters", {})
        resources: Dict[str, Dict[str, dict]] = self.content.get("resources", {})
        for key in list(resources.keys()):
            if resources[key].get("type", "").lower() != "microsoft.resources/deployments":
                continue
            nested_resources: List[dict] = resources[key]["properties"]["template"].get("resources", [])
            if not nested_resources:
                continue
            nested_type = nested_resources[0].get("type", "").lower()
            if nested_type not in self.linked_type_map:
                continue

            for param in self.copy_params:
                resources[key]["properties"]["template"]["parameters"][param] = parameters[param]

            result.append(resources[key]["properties"].pop("template"))
            del resources[key]
        return result

    def _get_deployments(self, root_dir: str, linked_base_uri: Optional[str] = None) -> List[Tuple[str, dict]]:
        result = []
        resources: Dict[str, Dict[str, dict]] = self.content.get("resources", {})
        if linked_base_uri and root_dir:
            sep = "" if linked_base_uri.endswith("/") else "/"
            root_dir = f"{linked_base_uri}{sep}{root_dir}"
        for key in resources:
            if resources[key].get("type", "").lower() != "microsoft.resources/deployments":
                continue
            nested_resources: List[dict] = resources[key]["properties"]["template"].get("resources", [])
            if not nested_resources:
                continue
            nested_type = nested_resources[0].get("type", "").lower()
            if nested_type not in self.linked_type_map:
                continue

            self.linked_type_map[nested_type] += 1
            kind = nested_type.split("/")[-1]
            linked_name = f"{kind}_{self.linked_type_map[nested_type]}"
            linked_rel_path = f"{root_dir}/{linked_name}.json"

            template_link = {"relativePath": linked_rel_path} if not linked_base_uri else {"uri": linked_rel_path}
            resources[key]["properties"]["templateLink"] = template_link

            result.append((linked_name, resources[key]["properties"]["template"]))
            del resources[key]["properties"]["template"]

        return result

    def write(
        self,
        bundle_path: PurePath,
        template_mode: Optional[str] = None,
        linked_base_uri: Optional[str] = None,
        file_ext: str = "json",
    ):
        if not bundle_path:
            return

        deployments = None
        if template_mode == TemplateMode.LINKED.value:
            deployments = self._get_deployments(bundle_path.name, linked_base_uri)

        template_str = dumps(self.content, indent=2)
        with open(file=f"{bundle_path}.{file_ext}", mode="w") as template_file:
            template_file.write(template_str)

        if deployments:
            Path(bundle_path).mkdir(exist_ok=True)
            for deployment in deployments:
                with open(file=f"{bundle_path.joinpath(deployment[0])}.{file_ext}", mode="w") as template_file:
                    template_file.write(dumps(deployment[1], indent=2))


class TemplateGen:
    def __init__(
        self, rcontainer_map: Dict[str, ResourceContainer], parameter_map: dict, variable_map: dict, metadata_map: dict
    ):
        self.rcontainer_map = rcontainer_map
        self.parameter_map = parameter_map
        self.variable_map = variable_map
        self.metadata_map = metadata_map

    def _prune_template_keys(self, template: dict) -> dict:
        result = {}
        for key in template:
            if not template[key]:
                continue
            result[key] = template[key]
        return result

    def get_content(self) -> "TemplateContent":
        template = self.get_base_format()
        for template_key in self.rcontainer_map:
            template["resources"][template_key] = self.rcontainer_map[template_key].get()
        template["parameters"].update(self.parameter_map)
        template["variables"].update(self.variable_map)
        template["metadata"].update(self.metadata_map)
        template = self._prune_template_keys(template)
        return TemplateContent(content=template)

    def get_base_format(self) -> dict:
        return {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "languageVersion": "2.0",
            "contentVersion": "1.0.0.0",
            "metadata": {},
            "apiProfile": "",
            "definitions": {},
            "parameters": {},
            "variables": {},
            "functions": [],
            "resources": {},
            "outputs": {},
        }


def process_depends_on(
    depends_on: Optional[Union[Iterable[str], str, Iterable[StateResourceKey], StateResourceKey]] = None
) -> Optional[Iterable[str]]:
    if not depends_on:
        return

    result = []
    if isinstance(depends_on, StateResourceKey):
        depends_on = depends_on.value
    if isinstance(depends_on, str):
        result.append(depends_on)
        return result

    if isinstance(depends_on, Iterable):
        for d in depends_on:
            if isinstance(d, StateResourceKey):
                d = d.value
            if isinstance(d, str):
                result.append(d)

    return result


def get_bundle_path(instance_name: str, bundle_dir: Optional[str] = None) -> Optional[PurePath]:
    from ...util import normalize_dir

    if not bundle_dir:
        return

    bundle_dir_pure_path = normalize_dir(bundle_dir)
    bundle_pure_path = bundle_dir_pure_path.joinpath(default_bundle_name(instance_name))
    return bundle_pure_path


def default_bundle_name(instance_name: str) -> str:
    timestamp = get_timestamp_now_utc(format="%Y%m%dT%H%M%S")
    name = f"clone_{to_safe_filename(instance_name)}_{timestamp}_aio"
    return name


def build_parameter(
    name: str,
    type: str = "string",
    metadata: Optional[dict] = None,
    value: Optional[Any] = None,
    default: Optional[Any] = None,
) -> dict:
    result = {
        name: {
            "type": type,
        }
    }
    if metadata:
        result[name]["metadata"] = metadata
    if value:
        result[name]["value"] = value
    if default:
        result[name]["defaultValue"] = default
    return result


def get_role_assignment():
    return {
        "type": "Microsoft.Authorization/roleAssignments",
        "name": (
            f"[guid(parameters('{TemplateParams.INSTANCE_NAME.value}'), "
            f"parameters('{TemplateParams.CLUSTER_NAME.value}'), resourceGroup().id)]"
        ),
        "scope": f"[parameters('{TemplateParams.SCHEMA_REGISTRY_ID.value}')]",
        "properties": {
            "roleDefinitionId": (
                f"[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '{CONTRIBUTOR_ROLE_ID}')]"
            ),
            "principalId": "[parameters('principalId')]",
            "principalType": "ServicePrincipal",
        },
    }
