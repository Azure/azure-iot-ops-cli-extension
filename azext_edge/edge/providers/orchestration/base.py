# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
from time import sleep
from typing import List, NamedTuple, Optional, Tuple

from azure.cli.core.azclierror import HTTPError
from knack.log import get_logger

from ...util import (
    generate_secret,
    generate_self_signed_cert,
    get_timestamp_now_utc,
    read_file_content,
    get_resource_client,
)
from ..base import (
    create_cluster_namespace,
    create_namespaced_configmap,
    create_namespaced_custom_objects,
    create_namespaced_secret,
    get_cluster_namespace,
)
from ...common import K8sSecretType
from ..edge_api import KEYVAULT_API_V1, KeyVaultResourceKinds
from .components import (
    get_kv_secret_store_yaml,
)

logger = get_logger(__name__)


KEYVAULT_CLOUD_API_VERSION = "2022-07-01"

DEFAULT_POLL_RETRIES = 60
DEFAULT_POLL_WAIT_SEC = 10


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
    **kwargs,
) -> dict:
    resource_client = get_resource_client(subscription_id=subscription_id)
    return wait_for_terminal_state(
        resource_client.resources.begin_create_or_update_by_id(
            resource_id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}/Providers"
            f"/Microsoft.KubernetesConfiguration/extensions/{extension_name}",
            api_version="2022-11-01",
            parameters={
                "identity": {"type": "SystemAssigned"},
                "properties": {
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
    )


def configure_cluster_secrets(
    cluster_namespace: str,
    cluster_secret_ref: str,
    cluster_akv_secret_class_name: str,
    keyvault_secret_name: str,
    sp_record: ServicePrincipal,
    keyvault_resource_id: str,
    **kwargs,
):
    if not get_cluster_namespace(namespace=cluster_namespace):
        create_cluster_namespace(namespace=cluster_namespace)

    aio_akv_sp_secret_key = cluster_secret_ref
    create_namespaced_secret(
        secret_name=aio_akv_sp_secret_key,
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
    ]:
        yaml_configs.append(
            get_kv_secret_store_yaml(
                name=secret_class,
                namespace=cluster_namespace,
                keyvault_name=keyvault_name,
                secret_name=keyvault_secret_name,
                tenantId=sp_record.tenant_id,
            )
        )

    KEYVAULT_API_V1.kinds  # TODO: clunky
    create_namespaced_custom_objects(
        group=KEYVAULT_API_V1.group,
        version=KEYVAULT_API_V1.version,
        plural=KEYVAULT_API_V1._kinds[KeyVaultResourceKinds.SECRET_PROVIDER_CLASS.value],  # TODO: clunky
        namespace=cluster_namespace,
        yaml_objects=yaml_configs,
        delete_first=True,
    )


def prepare_ca(
    tls_ca_path: Optional[str] = None, tls_ca_key_path: Optional[str] = None, tls_ca_dir: Optional[str] = None, **kwargs
) -> Tuple[bytes, bytes, str, str]:
    from ..support.base import normalize_dir

    public_cert = private_key = None
    secret_name = "aio-ca-key-pair"
    cm_name = "aio-ca-trust-bundle"

    if tls_ca_path:
        public_cert = read_file_content(file_path=tls_ca_path, read_as_binary=True)
        if tls_ca_key_path:
            private_key = read_file_content(file_path=tls_ca_key_path, read_as_binary=True)
    else:
        normalized_path = normalize_dir(dir_path=tls_ca_dir)
        test_ca_path = normalized_path.joinpath("aio-test-ca.crt")
        test_pk_path = normalized_path.joinpath("aio-test-private.key")

        public_cert, private_key = generate_self_signed_cert()

        with open(str(test_ca_path), "wb") as f:
            f.write(public_cert)

        with open(str(test_pk_path), "wb") as f:
            f.write(private_key)

        secret_name = f"{secret_name}-test-only"
        cm_name = f"{cm_name}-test-only"

    return public_cert, private_key, secret_name, cm_name


def configure_cluster_tls(
    cluster_namespace: str, public_ca: bytes, private_key: bytes, secret_name: str, cm_name: str, **kwargs
) -> Tuple[str, str, str]:
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
    cm_key = "ca.crt"
    data = {cm_key: public_ca.decode()}
    create_namespaced_configmap(namespace=cluster_namespace, cm_name=cm_name, data=data, delete_first=True)


def prepare_sp(cmd, deployment_name: str, **kwargs) -> ServicePrincipal:
    from datetime import datetime, timedelta, timezone

    from azure.cli.core.util import send_raw_request

    timestamp = datetime.now(timezone.utc) + timedelta(days=30.0)
    timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    sp_app_id = kwargs.get("service_principal_app_id")
    sp_object_id = kwargs.get("service_principal_object_id")
    sp_secret = kwargs.get("service_principal_secret")
    app_reg = {}
    app_created = False

    if sp_object_id:
        existing_sp = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=f"https://graph.microsoft.com/v1.0/servicePrincipals/{sp_object_id}",
        ).json()
        sp_app_id = existing_sp["appId"]
        try:
            app_reg = existing_sp = send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="GET",
                url=f"https://graph.microsoft.com/v1.0/applications/{sp_app_id}",
            ).json()
        except HTTPError as http_error:
            if http_error.response.status_code not in [401, 403]:
                raise http_error

    if not sp_app_id:
        app_reg = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="POST",
            url="https://graph.microsoft.com/v1.0/applications",
            body=json.dumps({"displayName": deployment_name, "signInAudience": "AzureADMyOrg"}),
        ).json()
        app_created = True
        sp_app_id = app_reg["appId"]

    if not sp_object_id or app_created:
        try:
            existing_sp = send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="GET",
                url=f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{sp_app_id}')",
            ).json()
            sp_object_id = existing_sp["id"]
        except HTTPError as http_error:
            if http_error.response.status_code != 404:
                raise http_error
            sp = send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="POST",
                url="https://graph.microsoft.com/v1.0/servicePrincipals",
                body=json.dumps({"appId": sp_app_id}),
            ).json()
            sp_object_id = sp["id"]

    if app_reg:
        existing_resource_access: List[dict] = app_reg["requiredResourceAccess"]
        add_kv_access = True
        add_basic_graph_access = True
        for resource_app in existing_resource_access:
            if resource_app["resourceAppId"] == "cfa8b339-82a2-471a-a3c9-0fc0be7a4093":
                add_kv_access = False
            if resource_app["resourceAppId"] == "00000003-0000-0000-c000-000000000000":
                add_basic_graph_access = False

        if add_kv_access:
            existing_resource_access.append(
                {
                    "resourceAppId": "cfa8b339-82a2-471a-a3c9-0fc0be7a4093",
                    "resourceAccess": [{"id": "f53da476-18e3-4152-8e01-aec403e6edc0", "type": "Scope"}],
                },
            )
        if add_basic_graph_access:
            existing_resource_access.append(
                {
                    "resourceAppId": "00000003-0000-0000-c000-000000000000",
                    "resourceAccess": [{"id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d", "type": "Scope"}],
                },
            )

        if add_kv_access or add_basic_graph_access:
            send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="PATCH",
                url=f"https://graph.microsoft.com/v1.0/myorganization/applications(appId='{sp_app_id}')",
                body=json.dumps({"requiredResourceAccess": existing_resource_access}),
            )

    if not sp_secret:
        add_secret_op = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="POST",
            url=f"https://graph.microsoft.com/v1.0/myorganization/applications(appId='{sp_app_id}')/addPassword",
            body=json.dumps({"passwordCredential": {"displayName": deployment_name, "endDateTime": timestamp_str}}),
        )
        sp_secret = add_secret_op.json()["secretText"]

    sp_record = ServicePrincipal(
        client_id=sp_app_id,
        object_id=sp_object_id,
        secret=sp_secret,
        tenant_id=get_tenant_id(),
        created_app=app_created,
    )
    return sp_record


def prepare_keyvault_access_policy(subscription_id: str, sp_record: ServicePrincipal, **kwargs) -> str:
    keyvault_resource_id = kwargs.get("keyvault_resource_id")
    resource_client = get_resource_client(subscription_id=subscription_id)
    keyvault_resource: dict = resource_client.resources.get_by_id(
        resource_id=keyvault_resource_id, api_version=KEYVAULT_CLOUD_API_VERSION
    ).as_dict()
    vault_uri = keyvault_resource["properties"]["vaultUri"]
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

    return vault_uri


def prepare_keyvault_secret(deployment_name: str, vault_uri: str, **kwargs) -> str:
    from azure.cli.core.util import send_raw_request

    keyvault_secret_name = kwargs.get("keyvault_secret_name")
    cmd = kwargs["cmd"]
    if keyvault_secret_name:
        get_secretver: dict = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=f"{vault_uri}/secrets/{keyvault_secret_name}/versions?api-version=7.4",
            resource="https://vault.azure.net",
        ).json()
        if not get_secretver.get("value"):
            send_raw_request(
                cli_ctx=cmd.cli_ctx,
                method="PUT",
                url=f"{vault_uri}/secrets/{keyvault_secret_name}?api-version=7.4",
                resource="https://vault.azure.net",
                body=json.dumps({"value": generate_secret()}),
            ).json()
    else:
        keyvault_secret_name = deployment_name.replace(".", "-")
        send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="PUT",
            url=f"{vault_uri}/secrets/{keyvault_secret_name}?api-version=7.4",
            resource="https://vault.azure.net",
            body=json.dumps({"value": generate_secret()}),
        ).json()

    return keyvault_secret_name


def get_resource_by_id(resource_id: str, subscription_id: str, api_version: str):
    resource_client = get_resource_client(subscription_id=subscription_id)
    return resource_client.resources.get_by_id(resource_id=resource_id, api_version=api_version)


def get_tenant_id():
    from azure.cli.core._profile import Profile

    profile = Profile()
    sub = profile.get_subscription()
    return sub["tenantId"]


def deploy_template(
    template: dict,
    parameters: dict,
    subscription_id: str,
    resource_group_name: str,
    deployment_name: str,
    cluster_name: str,
    cluster_namespace: str,
    **kwargs,
) -> Tuple[dict, dict]:
    resource_client = get_resource_client(subscription_id=subscription_id)

    deployment_params = {"properties": {"mode": "Incremental", "template": template, "parameters": parameters}}
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


def wait_for_terminal_state(poller) -> dict:
    # resource client does not handle sigint well
    counter = 0
    while counter < DEFAULT_POLL_RETRIES:
        sleep(DEFAULT_POLL_WAIT_SEC)
        counter = counter + 1
        if poller.done():
            break
    return poller.result()
