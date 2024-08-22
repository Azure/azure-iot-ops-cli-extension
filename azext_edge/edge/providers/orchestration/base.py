# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Tuple

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger

from ...util import (
    get_timestamp_now_utc,
)
from ...util.az_client import (
    get_resource_client,
)
from ..k8s.cluster_role_binding import get_bindings
from ..k8s.config_map import get_config_map
from .common import (
    ARC_CONFIG_MAP,
    ARC_NAMESPACE,
    CUSTOM_LOCATIONS_RP_APP_ID,
    EXTENDED_LOCATION_ROLE_BINDING,
    GRAPH_V1_SP_ENDPOINT,
)
from .connected_cluster import ConnectedCluster

logger = get_logger(__name__)

IOT_OPERATIONS_EXTENSION_PREFIX = "microsoft.iotoperations"


# TODO - @digimaun - potentially can reuse
# def configure_cluster_secrets(
#     cluster_namespace: str,
#     cluster_secret_ref: str,
#     cluster_akv_secret_class_name: str,
#     keyvault_spc_secret_name: str,
#     keyvault_resource_id: str,
#     sp_record: ServicePrincipal,
#     **kwargs,
# ):
#     if not KEYVAULT_API_V1.is_deployed():
#         raise ValidationError(
#             f"The API {KEYVAULT_API_V1.as_str()} "
#             "is not available on the cluster the local kubeconfig is configured for.\n"
#             "Please ensure the local kubeconfig matches the target cluster intended for deployment."
#         )

#     if not get_cluster_namespace(namespace=cluster_namespace):
#         create_cluster_namespace(namespace=cluster_namespace)

#     create_namespaced_secret(
#         secret_name=cluster_secret_ref,
#         namespace=cluster_namespace,
#         data={"clientid": sp_record.client_id, "clientsecret": sp_record.secret},
#         labels={"secrets-store.csi.k8s.io/used": "true"},
#         delete_first=True,
#     )

#     yaml_configs = []
#     keyvault_split = keyvault_resource_id.split("/")
#     keyvault_name = keyvault_split[-1]

#     for secret_class in [
#         cluster_akv_secret_class_name,
#         "aio-opc-ua-broker-client-certificate",
#         "aio-opc-ua-broker-user-authentication",
#         "aio-opc-ua-broker-trust-list",
#         "aio-opc-ua-broker-issuer-list",
#     ]:
#         yaml_configs.append(
#             get_kv_secret_store_yaml(
#                 name=secret_class,
#                 namespace=cluster_namespace,
#                 keyvault_name=keyvault_name,
#                 secret_name=keyvault_spc_secret_name,
#                 tenantId=sp_record.tenant_id,
#             )
#         )

#     create_namespaced_custom_objects(
#         group=KEYVAULT_API_V1.group,
#         version=KEYVAULT_API_V1.version,
#         plural="secretproviderclasses",  # TODO
#         namespace=cluster_namespace,
#         yaml_objects=yaml_configs,
#         delete_first=True,
#     )


def deploy_template(
    template: dict,
    parameters: dict,
    subscription_id: str,
    resource_group_name: str,
    deployment_name: str,
    cluster_name: str,
    cluster_namespace: str,
    instance_name: str,
    pre_flight: bool = False,
    **kwargs,
) -> Tuple[dict, dict]:
    resource_client = get_resource_client(subscription_id=subscription_id)

    deployment_params = {"properties": {"mode": "Incremental", "template": template, "parameters": parameters}}
    if pre_flight:
        return {}, resource_client.deployments.begin_what_if(
            resource_group_name=resource_group_name,
            deployment_name=deployment_name,
            parameters=deployment_params,
        )

    deployment = resource_client.deployments.begin_create_or_update(
        resource_group_name=resource_group_name,
        deployment_name=deployment_name,
        parameters=deployment_params,
    )

    deploy_link = (
        "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"
        f"%2Fsubscriptions%2F{subscription_id}%2FresourceGroups%2F{resource_group_name}"
        f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{deployment_name}"
    )

    result = {
        "clusterName": cluster_name,
        "clusterNamespace": cluster_namespace,
        "deploymentLink": deploy_link,
        "deploymentName": deployment_name,
        "deploymentState": {"timestampUtc": {"started": get_timestamp_now_utc()}, "status": deployment.status()},
        "instanceName": instance_name,
        "resourceGroup": resource_group_name,
        "subscriptionId": subscription_id,
    }
    return result, deployment


def verify_cluster_and_use_location(kwargs: dict) -> ConnectedCluster:
    # TODO: Note kwargs is not expanded to keep as mutable dict until next TODO resolved.
    # TODO: Use intermediate object to store KPIs / refactor out of kwargs.
    location = kwargs["location"]
    cluster_name = kwargs["cluster_name"]
    subscription_id = kwargs["subscription_id"]
    resource_group_name = kwargs["resource_group_name"]

    from .connected_cluster import ConnectedCluster

    connected_cluster = ConnectedCluster(
        cmd=kwargs["cmd"],
        subscription_id=subscription_id,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
    )
    connected_cluster_location = connected_cluster.location.lower()

    kwargs["cluster_location"] = connected_cluster_location
    if not location:
        kwargs["location"] = connected_cluster_location

    return connected_cluster


def throw_if_iotops_deployed(connected_cluster: ConnectedCluster):
    connected_cluster_extensions = connected_cluster.extensions
    for extension in connected_cluster_extensions:
        if "properties" in extension and "extensionType" in extension["properties"]:
            if extension["properties"]["extensionType"].lower().startswith(IOT_OPERATIONS_EXTENSION_PREFIX):
                raise ValidationError(
                    "Detected existing IoT Operations deployment. "
                    "Remove IoT Operations or use a different connected cluster to continue.\n"
                )


def verify_custom_locations_enabled(cmd):
    from azure.cli.core.util import send_raw_request

    target_bindings = get_bindings(field_selector=f"metadata.name=={EXTENDED_LOCATION_ROLE_BINDING}")
    if not target_bindings or (target_bindings and not target_bindings.get("items")):
        raise ValidationError(
            "The custom-locations feature is required but not enabled on the cluster. For guidance refer to:\n"
            "https://aka.ms/ArcK8sCustomLocationsDocsEnableFeature"
        )

    # See if we can verify the RP OID.
    try:
        cl_sp_response = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=f"{GRAPH_V1_SP_ENDPOINT}(appId='{CUSTOM_LOCATIONS_RP_APP_ID}')",
        ).json()
        cl_oid = cl_sp_response["id"].lower()
    except Exception:
        # If not, bail without throwing.
        return

    # We are expecting one binding. Field selector pattern is used due to AKS-EE issue.
    target_binding: dict = target_bindings["items"][0]
    for subject in target_binding.get("subjects", []):
        if "name" in subject and subject["name"].lower() == cl_oid:
            return

    raise ValidationError(f"Invalid OID used for custom locations feature enablement. Use '{cl_oid}'.")


def verify_arc_cluster_config(connected_cluster: ConnectedCluster):
    connect_config_map = get_config_map(name=ARC_CONFIG_MAP, namespace=ARC_NAMESPACE)
    if not connect_config_map:
        raise ValidationError(
            "Unable to verify cluster arc config. Please ensure the target cluster is arc-enabled and a "
            "corresponding kubeconfig context exists locally. "
        )

    connect_data_map: dict = connect_config_map.get("data", {})

    evaluations: Tuple[str, str, str] = [
        (connected_cluster.cluster_name, connect_data_map.get("AZURE_RESOURCE_NAME"), "cluster name"),
        (connected_cluster.resource_group_name, connect_data_map.get("AZURE_RESOURCE_GROUP"), "resource group"),
        (connected_cluster.subscription_id, connect_data_map.get("AZURE_SUBSCRIPTION_ID"), "subscription Id"),
    ]

    for evaluation in evaluations:
        cloud_value = evaluation[0].lower()
        arc_config_value = evaluation[1].lower()
        description = evaluation[2]
        if arc_config_value != cloud_value:
            raise ValidationError(
                f"The cluster-side arc config uses {arc_config_value} for {description}, "
                f"while the cloud target is {cloud_value}.\n"
                "Please ensure the local kubeconfig is up-to-date with the intended cluster for deployment."
            )


def verify_custom_location_namespace(connected_cluster: ConnectedCluster, custom_location_name: str, namespace: str):
    custom_location_ref = connected_cluster.get_custom_location_for_namespace(namespace=namespace)
    if custom_location_ref and custom_location_ref["name"] != custom_location_name:
        raise ValidationError(
            f"The intended namespace for deployment: {namespace}, is already referenced by "
            f"custom location: {custom_location_ref['name']}.\n"
            "A namespace can only be referenced by a single custom location. "
            "Please choose a different namespace via --cluster-namespace."
        )
