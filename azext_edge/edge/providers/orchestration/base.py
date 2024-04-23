# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import logging
from time import sleep
from typing import TYPE_CHECKING, List, NamedTuple, Optional, Tuple

from azure.cli.core.azclierror import HTTPError, ValidationError
from knack.log import get_logger

from ...common import K8sSecretType
from ...util import (
    generate_secret,
    generate_self_signed_cert,
    get_timestamp_now_utc,
    read_file_content,
)
from ...util.az_client import (
    get_resource_client,
    get_tenant_id,
    get_token_from_sp_credential,
    wait_for_terminal_state,
)
from ..base import (
    create_cluster_namespace,
    create_namespaced_configmap,
    create_namespaced_custom_objects,
    create_namespaced_secret,
    get_cluster_namespace,
)
from ..edge_api import KEYVAULT_API_V1
from ..k8s.cluster_role_binding import get_bindings
from ..k8s.config_map import get_config_map
from .common import (
    ARC_CONFIG_MAP,
    ARC_NAMESPACE,
    DEFAULT_SERVICE_PRINCIPAL_SECRET_DAYS,
    EXTENDED_LOCATION_ROLE_BINDING,
    GRAPH_V1_APP_ENDPOINT,
    GRAPH_V1_ENDPOINT,
    GRAPH_V1_SP_ENDPOINT,
)
from .components import (
    get_kv_secret_store_yaml,
)
from .connected_cluster import ConnectedCluster

logger = get_logger(__name__)

if TYPE_CHECKING:
    from requests.models import Response


EXTENSION_API_VERSION = "2022-11-01"  # TODO: fun testing with newer api
IOT_OPERATIONS_EXTENSION_PREFIX = "microsoft.iotoperations"

# TODO: pull out into keyvault file (with other related funcs)
KEYVAULT_CLOUD_API_VERSION = "2022-07-01"
KEYVAULT_DATAPLANE_API_VERSION = "7.4"
KEYVAULT_ARC_EXTENSION_VERSION = "1.5.2"

PROPAGATION_DELAY_SEC = 20


class ServicePrincipal(NamedTuple):
    client_id: str
    object_id: str
    tenant_id: str
    secret: str
    created_app: bool


def provision_akv_csi_driver(
    subscription_id: str,
    cluster_name: str,
    resource_group_name: str,
    enable_secret_rotation: str,
    rotation_poll_interval: str = "1h",
    extension_name: str = "akvsecretsprovider",
    **kwargs,  # TODO: someday remove all kwargs from the smaller funcs
) -> dict:
    resource_client = get_resource_client(subscription_id=subscription_id)
    return wait_for_terminal_state(
        resource_client.resources.begin_create_or_update_by_id(
            resource_id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}/Providers"
            f"/Microsoft.KubernetesConfiguration/extensions/{extension_name}",
            api_version=EXTENSION_API_VERSION,
            parameters={
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "autoUpgradeMinorVersion": False,
                    "version": KEYVAULT_ARC_EXTENSION_VERSION,
                    "extensionType": "microsoft.azurekeyvaultsecretsprovider",
                    "configurationSettings": {
                        "secrets-store-csi-driver.enableSecretRotation": enable_secret_rotation,
                        "secrets-store-csi-driver.rotationPollInterval": rotation_poll_interval,
                        "secrets-store-csi-driver.syncSecret.enabled": "false",
                    },
                    "configurationProtectedSettings": {},
                },
            },
        )
    ).as_dict()


def configure_cluster_secrets(
    cluster_namespace: str,
    cluster_secret_ref: str,
    cluster_akv_secret_class_name: str,
    keyvault_spc_secret_name: str,
    keyvault_resource_id: str,
    sp_record: ServicePrincipal,
    **kwargs,
):
    if not KEYVAULT_API_V1.is_deployed():
        raise ValidationError(
            f"The API {KEYVAULT_API_V1.as_str()} "
            "is not available on the cluster the local kubeconfig is configured for.\n"
            "Please ensure the local kubeconfig matches the target cluster intended for deployment."
        )

    if not get_cluster_namespace(namespace=cluster_namespace):
        create_cluster_namespace(namespace=cluster_namespace)

    create_namespaced_secret(
        secret_name=cluster_secret_ref,
        namespace=cluster_namespace,
        data={"clientid": sp_record.client_id, "clientsecret": sp_record.secret},
        labels={"secrets-store.csi.k8s.io/used": "true"},
        delete_first=True,
    )

    yaml_configs = []
    keyvault_split = keyvault_resource_id.split("/")
    keyvault_name = keyvault_split[-1]

    for secret_class in [
        cluster_akv_secret_class_name,
        "aio-opc-ua-broker-client-certificate",
        "aio-opc-ua-broker-user-authentication",
        "aio-opc-ua-broker-trust-list",
        "aio-opc-ua-broker-issuer-list",
    ]:
        yaml_configs.append(
            get_kv_secret_store_yaml(
                name=secret_class,
                namespace=cluster_namespace,
                keyvault_name=keyvault_name,
                secret_name=keyvault_spc_secret_name,
                tenantId=sp_record.tenant_id,
            )
        )

    create_namespaced_custom_objects(
        group=KEYVAULT_API_V1.group,
        version=KEYVAULT_API_V1.version,
        plural="secretproviderclasses",  # TODO
        namespace=cluster_namespace,
        yaml_objects=yaml_configs,
        delete_first=True,
    )


def prepare_ca(
    tls_ca_path: Optional[str] = None,
    tls_ca_key_path: Optional[str] = None,
    tls_ca_dir: Optional[str] = None,
    tls_ca_valid_days: Optional[int] = None,
    **kwargs,
) -> Tuple[bytes, bytes, str, str]:
    from ...util import normalize_dir

    public_cert = private_key = None
    secret_name = "aio-ca-key-pair"
    cm_name = "aio-ca-trust-bundle"

    if tls_ca_path:
        public_cert = read_file_content(file_path=tls_ca_path, read_as_binary=True)
        if tls_ca_key_path:
            private_key = read_file_content(file_path=tls_ca_key_path, read_as_binary=True)
    else:
        public_cert, private_key = generate_self_signed_cert(tls_ca_valid_days)
        secret_name = f"{secret_name}-test-only"
        cm_name = f"{cm_name}-test-only"

        if tls_ca_dir:
            normalized_path = normalize_dir(dir_path=tls_ca_dir)
            test_ca_path = normalized_path.joinpath("aio-test-ca.crt")
            test_pk_path = normalized_path.joinpath("aio-test-private.key")

            with open(str(test_ca_path), "wb") as f:
                f.write(public_cert)

            with open(str(test_pk_path), "wb") as f:
                f.write(private_key)

    return public_cert, private_key, secret_name, cm_name


def configure_cluster_tls(
    cluster_namespace: str, public_ca: bytes, private_key: bytes, secret_name: str, cm_name: str, **kwargs
):
    from base64 import b64encode

    if not get_cluster_namespace(namespace=cluster_namespace):
        create_cluster_namespace(namespace=cluster_namespace)

    data = {}
    data["tls.crt"] = b64encode(public_ca).decode()
    data["tls.key"] = b64encode(private_key).decode()

    create_namespaced_secret(
        secret_name=secret_name,
        namespace=cluster_namespace,
        secret_type=K8sSecretType.tls,
        data=data,
        delete_first=True,
    )
    data = {"ca.crt": public_ca.decode()}
    create_namespaced_configmap(namespace=cluster_namespace, cm_name=cm_name, data=data, delete_first=True)


def prepare_sp(cmd, deployment_name: str, **kwargs) -> ServicePrincipal:
    from datetime import datetime, timedelta, timezone

    from azure.cli.core.util import send_raw_request

    sp_app_id = kwargs.get("service_principal_app_id")
    sp_object_id = kwargs.get("service_principal_object_id")
    sp_secret = kwargs.get("service_principal_secret")
    sp_secret_valid_days = kwargs.get("service_principal_secret_valid_days", DEFAULT_SERVICE_PRINCIPAL_SECRET_DAYS)

    timestamp = datetime.now(timezone.utc) + timedelta(days=sp_secret_valid_days)
    timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    app_reg = {}
    app_created = False

    if all([sp_app_id, sp_object_id, sp_secret]):
        return ServicePrincipal(
            client_id=sp_app_id,
            object_id=sp_object_id,
            secret=sp_secret,
            tenant_id=get_tenant_id(),
            created_app=app_created,
        )

    if sp_object_id and not sp_app_id:
        existing_sp = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=f"{GRAPH_V1_SP_ENDPOINT}/{sp_object_id}",
        ).json()
        sp_app_id = existing_sp["appId"]
        app_reg = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=f"{GRAPH_V1_APP_ENDPOINT}(appId='{sp_app_id}')",
        ).json()

    if not sp_app_id:
        app_reg = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="POST",
            url=GRAPH_V1_APP_ENDPOINT,
            body=json.dumps({"displayName": deployment_name, "signInAudience": "AzureADMyOrg"}),
        ).json()
        app_created = True
        sp_app_id = app_reg["appId"]

    if not sp_object_id or app_created:
        try:
            existing_sp = send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="GET",
                url=f"{GRAPH_V1_SP_ENDPOINT}(appId='{sp_app_id}')",
            ).json()
            sp_object_id = existing_sp["id"]
        except HTTPError as http_error:
            if http_error.response.status_code != 404:
                raise http_error
            sp = send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="POST",
                url=GRAPH_V1_SP_ENDPOINT,
                body=json.dumps({"appId": sp_app_id}),
            ).json()
            sp_object_id = sp["id"]

    if app_reg:
        ensure_correct_access(cmd, sp_app_id, app_reg["requiredResourceAccess"])

    if not sp_secret:
        add_secret_op = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="POST",
            url=f"{GRAPH_V1_ENDPOINT}/myorganization/applications(appId='{sp_app_id}')/addPassword",
            body=json.dumps({"passwordCredential": {"displayName": deployment_name, "endDateTime": timestamp_str}}),
        )
        sp_secret = add_secret_op.json()["secretText"]
        sleep(PROPAGATION_DELAY_SEC)

    return ServicePrincipal(
        client_id=sp_app_id,
        object_id=sp_object_id,
        secret=sp_secret,
        tenant_id=get_tenant_id(),
        created_app=app_created,
    )


def ensure_correct_access(cmd, sp_app_id: str, existing_resource_access: List[dict]):
    from azure.cli.core.util import send_raw_request

    permission_map = {
        # keyvault to have full access to akv service
        "cfa8b339-82a2-471a-a3c9-0fc0be7a4093": "f53da476-18e3-4152-8e01-aec403e6edc0",
        # ms graph to Sign in and read user profile
        "00000003-0000-0000-c000-000000000000": "e1fe6dd8-ba31-4d61-89e7-88639da4683d",
    }
    for resource_app in existing_resource_access:
        if resource_app["resourceAppId"] in permission_map:
            permission_map.pop(resource_app["resourceAppId"], None)

    for app, permission in permission_map.items():
        existing_resource_access.append(
            {
                "resourceAppId": app,
                "resourceAccess": [{"id": permission, "type": "Scope"}],
            },
        )

    if permission_map:
        send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="PATCH",
            url=f"{GRAPH_V1_ENDPOINT}/myorganization/applications(appId='{sp_app_id}')",
            body=json.dumps({"requiredResourceAccess": existing_resource_access}),
        )


def validate_keyvault_permission_model(subscription_id: str, keyvault_resource_id: str, **kwargs) -> dict:
    resource_client = get_resource_client(subscription_id=subscription_id)
    keyvault_resource: dict = resource_client.resources.get_by_id(
        resource_id=keyvault_resource_id, api_version=KEYVAULT_CLOUD_API_VERSION
    ).as_dict()
    kv_properties = keyvault_resource["properties"]
    if "enableRbacAuthorization" in kv_properties and kv_properties["enableRbacAuthorization"] is True:
        raise ValidationError(
            "Target Key Vault must be configured for access policy based permission model. "
            "Rbac is not currently supported."
        )
    return keyvault_resource


def prepare_keyvault_access_policy(
    subscription_id: str, keyvault_resource: dict, keyvault_resource_id: str, sp_record: ServicePrincipal, **kwargs
) -> str:
    resource_client = get_resource_client(subscription_id=subscription_id)
    vault_uri: str = keyvault_resource["properties"]["vaultUri"]
    if vault_uri[-1] == "/":
        vault_uri = vault_uri[:-1]

    keyvault_access_policies: List[dict] = keyvault_resource["properties"].get("accessPolicies", [])

    add_access_policy = True
    for access_policy in keyvault_access_policies:
        if "objectId" in access_policy and access_policy["objectId"] == sp_record.object_id:
            add_access_policy = False

    if add_access_policy:
        keyvault_access_policies.append(
            {
                "tenantId": sp_record.tenant_id,
                "objectId": sp_record.object_id,
                # "applicationId": sp_record.client_id, # @digimaun - including turns into compound assignment.
                "permissions": {"secrets": ["get", "list"], "keys": [], "certificates": [], "storage": []},
            }
        )
        keyvault_resource["properties"]["accessPolicies"] = keyvault_access_policies
        resource_client.resources.begin_create_or_update_by_id(
            resource_id=f"{keyvault_resource_id}/accessPolicies/add",
            api_version=KEYVAULT_CLOUD_API_VERSION,
            parameters={"properties": {"accessPolicies": keyvault_access_policies}},
        ).result()
        sleep(PROPAGATION_DELAY_SEC)

    return vault_uri


def prepare_keyvault_secret(
    cmd, deployment_name: str, vault_uri: str, keyvault_spc_secret_name: Optional[str] = None, **kwargs
) -> str:
    from azure.cli.core.util import send_raw_request

    url = vault_uri + "/secrets/{0}{1}?api-version={2}"
    if keyvault_spc_secret_name:
        get_secret_version: dict = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=url.format(keyvault_spc_secret_name, "/versions", KEYVAULT_DATAPLANE_API_VERSION),
            resource="https://vault.azure.net",
        ).json()
        if not get_secret_version.get("value"):
            send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="PUT",
                url=url.format(keyvault_spc_secret_name, "", KEYVAULT_DATAPLANE_API_VERSION),
                resource="https://vault.azure.net",
                body=json.dumps({"value": generate_secret()}),
            ).json()
    else:
        keyvault_spc_secret_name = deployment_name.replace(".", "-")
        send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="PUT",
            url=url.format(keyvault_spc_secret_name, "", KEYVAULT_DATAPLANE_API_VERSION),
            resource="https://vault.azure.net",
            body=json.dumps({"value": generate_secret()}),
        ).json()

    return keyvault_spc_secret_name


def eval_secret_via_sp(cmd, vault_uri: str, keyvault_spc_secret_name: str, sp_record: ServicePrincipal):
    from azure.cli.core.util import send_raw_request

    identity_logger = logging.getLogger("azure.identity")
    identity_logger_level = identity_logger.level
    identity_logger.setLevel(logging.ERROR)

    auth_token = get_token_from_sp_credential(
        tenant_id=sp_record.tenant_id,
        client_id=sp_record.client_id,
        client_secret=sp_record.secret,
        scope="https://vault.azure.net/.default",
    )
    identity_logger.setLevel(identity_logger_level)

    kv_secret_url = vault_uri + "/secrets/{0}?api-version={1}"
    try:
        send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            headers=[f"Authorization=Bearer {auth_token}"],  # Expected header format :)
            url=kv_secret_url.format(keyvault_spc_secret_name, KEYVAULT_DATAPLANE_API_VERSION),
        )
    except HTTPError as e:
        error_response: Response = e.response
        http_error_msg = str(e)
        if error_response.status_code in [401, 403]:
            custom_error_msg = (
                f"{http_error_msg}\n\n"
                "The error indicates an auth failure to fetch the default SPC secret from Key Vault. "
                "If no access policy exists for the service principal used to setup the CSI driver"
                "init will create a suitable access policy given the logged-in principal "
                "has permission to do so."
            )
            raise ValidationError(error_msg=custom_error_msg)
        raise ValidationError(error_msg=http_error_msg)


def deploy_template(
    template: dict,
    parameters: dict,
    subscription_id: str,
    resource_group_name: str,
    deployment_name: str,
    cluster_name: str,
    cluster_namespace: str,
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
        "deploymentName": deployment_name,
        "resourceGroup": resource_group_name,
        "clusterName": cluster_name,
        "clusterNamespace": cluster_namespace,
        "deploymentLink": deploy_link,
        "deploymentState": {"timestampUtc": {"started": get_timestamp_now_utc()}, "status": deployment.status()},
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


def verify_custom_locations_enabled():
    target_bindings = get_bindings(field_selector=f"metadata.name=={EXTENDED_LOCATION_ROLE_BINDING}")
    if not target_bindings or (target_bindings and not target_bindings.get("items")):
        raise ValidationError(
            "The custom-locations feature is required but not enabled on the cluster. For guidance refer to:\n"
            "https://aka.ms/ArcK8sCustomLocationsDocsEnableFeature"
        )


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
