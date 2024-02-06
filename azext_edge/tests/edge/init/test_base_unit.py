# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest
from azure.cli.core.azclierror import HTTPError, ValidationError
from azext_edge.edge.providers.orchestration.common import (
    GRAPH_V1_ENDPOINT, GRAPH_V1_SP_ENDPOINT, GRAPH_V1_APP_ENDPOINT
)

from ...generators import generate_generic_id

BASE_PATH = "azext_edge.edge.providers.orchestration.base"


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "client_path": BASE_PATH,
    "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
}], indirect=True)
@pytest.mark.parametrize("rotation_poll_interval", ["1h"])
@pytest.mark.parametrize("extension_name", ["akvsecretsprovider"])
def test_provision_akv_csi_driver(mocker, mocked_resource_management_client, rotation_poll_interval, extension_name):
    terminal_result = mocker.Mock()
    terminal_result.as_dict.return_value = generate_generic_id()
    terminal_patch = mocker.patch(f"{BASE_PATH}.wait_for_terminal_state", autospec=True, return_value=terminal_result)
    from azext_edge.edge.providers.orchestration.base import provision_akv_csi_driver, KEYVAULT_ARC_EXTENSION_VERSION
    subscription_id = generate_generic_id()
    cluster_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    enable_secret_rotation = generate_generic_id()
    result = provision_akv_csi_driver(
        subscription_id=subscription_id,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        enable_secret_rotation=enable_secret_rotation,
        rotation_poll_interval=rotation_poll_interval,
        extension_name=extension_name
    )

    assert result == terminal_result.as_dict.return_value
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    terminal_patch.assert_called_once_with(poller)

    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    expected_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"\
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}/Providers"\
        f"/Microsoft.KubernetesConfiguration/extensions/{extension_name}"
    assert call_kwargs["resource_id"] == expected_id
    assert call_kwargs["api_version"] == "2022-11-01"

    params = call_kwargs["parameters"]
    assert params["identity"] == {"type": "SystemAssigned"}
    assert params["properties"]["autoUpgradeMinorVersion"] is False
    assert params["properties"]["version"] == KEYVAULT_ARC_EXTENSION_VERSION
    assert params["properties"]["configurationProtectedSettings"] == {}
    config_settings = params["properties"]["configurationSettings"]
    assert config_settings["secrets-store-csi-driver.enableSecretRotation"] == enable_secret_rotation
    assert config_settings["secrets-store-csi-driver.rotationPollInterval"] == rotation_poll_interval
    assert config_settings["secrets-store-csi-driver.syncSecret.enabled"] == "false"


@pytest.mark.parametrize("get_cluster", [False, True])
def test_configure_cluster_secrets(mocker, get_cluster):
    api_patch = mocker.patch(f"{BASE_PATH}.KEYVAULT_API_V1")
    api_patch.is_deployed.return_value = True
    api_patch.group = generate_generic_id()
    api_patch.version = generate_generic_id()
    get_cluster_patch = mocker.patch(f"{BASE_PATH}.get_cluster_namespace", return_value=get_cluster)
    create_cluster_patch = mocker.patch(f"{BASE_PATH}.create_cluster_namespace")
    create_secret_patch = mocker.patch(f"{BASE_PATH}.create_namespaced_secret")
    get_store_patch = mocker.patch(f"{BASE_PATH}.get_kv_secret_store_yaml", return_value=generate_generic_id())
    create_object_patch = mocker.patch(f"{BASE_PATH}.create_namespaced_custom_objects")
    from azext_edge.edge.providers.orchestration.base import configure_cluster_secrets
    cluster_namespace = generate_generic_id()
    cluster_secret_ref = generate_generic_id()
    keyvault_sat_secret_name = generate_generic_id()
    keyvault_resource_id = generate_generic_id()
    sp_record = mocker.Mock(
        client_id=generate_generic_id(), secret=generate_generic_id(), tenant_id=generate_generic_id()
    )
    configure_cluster_secrets(
        cluster_namespace=cluster_namespace,
        cluster_secret_ref=cluster_secret_ref,
        cluster_akv_secret_class_name=generate_generic_id(),
        keyvault_sat_secret_name=keyvault_sat_secret_name,
        keyvault_resource_id=keyvault_resource_id,
        sp_record=sp_record
    )
    get_cluster_patch.assert_called_once()
    assert create_cluster_patch.call_count == int(not get_cluster)
    create_secret_patch.assert_called_once_with(
        secret_name=cluster_secret_ref,
        namespace=cluster_namespace,
        data={"clientid": sp_record.client_id, "clientsecret": sp_record.secret},
        labels={"secrets-store.csi.k8s.io/used": "true"},
        delete_first=True,
    )
    assert get_store_patch.call_count == 5
    create_object_patch.assert_called_once_with(
        group=api_patch.group,
        version=api_patch.version,
        plural="secretproviderclasses",
        namespace=cluster_namespace,
        yaml_objects=[get_store_patch.return_value] * 5,
        delete_first=True
    )


def test_configure_cluster_secrets_error(mocker):
    api_patch = mocker.patch(f"{BASE_PATH}.KEYVAULT_API_V1")
    api_patch.is_deployed.return_value = False
    from azext_edge.edge.providers.orchestration.base import configure_cluster_secrets
    with pytest.raises(ValidationError):
        configure_cluster_secrets(
            cluster_namespace=generate_generic_id(),
            cluster_secret_ref=generate_generic_id(),
            cluster_akv_secret_class_name=generate_generic_id(),
            keyvault_sat_secret_name=generate_generic_id(),
            keyvault_resource_id=generate_generic_id(),
            sp_record=generate_generic_id()
        )


@pytest.mark.parametrize("get_cluster", [False, True])
def test_configure_cluster_tls(mocker, get_cluster):
    get_cluster_patch = mocker.patch(f"{BASE_PATH}.get_cluster_namespace", return_value=get_cluster)
    create_cluster_patch = mocker.patch(f"{BASE_PATH}.create_cluster_namespace")
    create_secret_patch = mocker.patch(f"{BASE_PATH}.create_namespaced_secret")
    create_configmap_patch = mocker.patch(f"{BASE_PATH}.create_namespaced_configmap")
    from azext_edge.edge.providers.orchestration.base import configure_cluster_tls
    cluster_namespace = generate_generic_id()
    public_ca = bytes(generate_generic_id(), 'utf-8')
    cm_name = generate_generic_id()
    configure_cluster_tls(
        cluster_namespace=cluster_namespace,
        public_ca=public_ca,
        private_key=bytes(generate_generic_id(), 'utf-8'),
        secret_name=generate_generic_id(),
        cm_name=cm_name
    )
    get_cluster_patch.assert_called_once()
    assert create_cluster_patch.call_count == int(not get_cluster)
    create_secret_patch.assert_called_once()

    create_configmap_patch.assert_called_once_with(
        namespace=cluster_namespace,
        cm_name=cm_name,
        data={"ca.crt": public_ca.decode()},
        delete_first=True
    )


@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "return_value": {
            "appId": generate_generic_id(),
            "id": generate_generic_id(),
            "secretText": generate_generic_id(),
            "requiredResourceAccess": [
                {"resourceAppId": "cfa8b339-82a2-471a-a3c9-0fc0be7a4093"},
                {"resourceAppId": "00000003-0000-0000-c000-000000000000"},
            ]
        }
    }
], ids=["pass everything"], indirect=True)
@pytest.mark.parametrize("app_id", [None, generate_generic_id()])
@pytest.mark.parametrize("object_id", [None, generate_generic_id()])
@pytest.mark.parametrize("secret", [None, generate_generic_id()])
@pytest.mark.parametrize("secret_valid_days", [365, 100])
def test_prepare_sp(mocker, mocked_cmd, mocked_send_raw_request, app_id, object_id, secret, secret_valid_days):
    tenant_patch = mocker.patch(f"{BASE_PATH}.get_tenant_id", return_value=generate_generic_id())
    access_patch = mocker.patch(f"{BASE_PATH}.ensure_correct_access")
    from azext_edge.edge.providers.orchestration.base import prepare_sp
    deployment_name = generate_generic_id()
    sp = prepare_sp(
        mocked_cmd,
        deployment_name,
        service_principal_app_id=app_id,
        service_principal_object_id=object_id,
        service_principal_secret=secret,
        service_principal_secret_valid_days=secret_valid_days
    )
    raw_request_result = mocked_send_raw_request.return_value.json.return_value
    assert sp.client_id == (app_id or raw_request_result["appId"])
    assert sp.object_id == (object_id or raw_request_result["id"])
    assert sp.secret == (secret or raw_request_result["secretText"])
    assert sp.tenant_id == tenant_patch.return_value
    assert sp.created_app is not (app_id or object_id)

    # check calls one by one
    call_count = 0
    if not app_id:
        if object_id:
            get_sp_call = mocked_send_raw_request.call_args_list[call_count].kwargs
            assert get_sp_call["method"] == "GET"
            assert get_sp_call["url"] == f"{GRAPH_V1_SP_ENDPOINT}/{sp.object_id}"
            get_app_call = mocked_send_raw_request.call_args_list[call_count + 1].kwargs
            assert get_app_call["method"] == "GET"
            assert get_app_call["url"] == f"{GRAPH_V1_APP_ENDPOINT}/{sp.client_id}"
            call_count += 2
        else:
            post_sp_call = mocked_send_raw_request.call_args_list[call_count].kwargs
            assert post_sp_call["method"] == "POST"
            assert post_sp_call["url"] == f"{GRAPH_V1_APP_ENDPOINT}"
            assert post_sp_call["body"] == json.dumps(
                {"displayName": deployment_name, "signInAudience": "AzureADMyOrg"}
            )
            access_patch.assert_called_once()
            call_count += 1
    if not object_id:
        get_sp_call = mocked_send_raw_request.call_args_list[call_count].kwargs
        assert get_sp_call["method"] == "GET"
        assert get_sp_call["url"] == f"{GRAPH_V1_SP_ENDPOINT}(appId='{sp.client_id}')"
        call_count += 1
        # exception case here
    if not secret:
        post_call = mocked_send_raw_request.call_args_list[call_count].kwargs
        assert post_call["method"] == "POST"
        assert post_call["url"] == (
            f"{GRAPH_V1_ENDPOINT}/myorganization/applications(appId='{sp.client_id}')/addPassword"
        )
        body = json.loads(post_call["body"])
        assert body["passwordCredential"]["displayName"] == deployment_name
        assert body["passwordCredential"]["endDateTime"]
        call_count += 1

    assert mocked_send_raw_request.call_count == call_count


@pytest.mark.parametrize("error_code", [401, 403])
def test_prepare_sp_catches(mocker, mocked_cmd, mocked_send_raw_request, error_code):
    """Test that this function does not error even if there is an http error - there are 3 cases."""
    from azext_edge.edge.providers.orchestration.base import prepare_sp
    app_id = generate_generic_id()
    all_result = {
        "appId": app_id,
        "id": generate_generic_id(),
        "secretText": generate_generic_id(),
        "requiredResourceAccess": [
            {"resourceAppId": "cfa8b339-82a2-471a-a3c9-0fc0be7a4093"},
            {"resourceAppId": "00000003-0000-0000-c000-000000000000"},
        ]
    }

    def custom_responses(**kwargs):
        if kwargs["url"].startswith(f"{GRAPH_V1_APP_ENDPOINT}/"):
            raise HTTPError(error_msg=generate_generic_id(), response=mocker.Mock(status_code=error_code))
        request_mock = mocker.Mock()
        request_mock.json.return_value = all_result
        return request_mock

    mocked_send_raw_request.side_effect = custom_responses
    mocker.patch(f"{BASE_PATH}.get_tenant_id", return_value=generate_generic_id())
    mocker.patch(f"{BASE_PATH}.ensure_correct_access")
    sp = prepare_sp(
        mocked_cmd,
        generate_generic_id(),
        service_principal_object_id=generate_generic_id(),
        service_principal_secret=generate_generic_id(),
    )
    assert sp
    mocked_send_raw_request.reset_mock()

    def custom_responses2(**kwargs):
        if kwargs["url"].startswith(f"{GRAPH_V1_SP_ENDPOINT}(appId='"):
            raise HTTPError(error_msg=generate_generic_id(), response=mocker.Mock(status_code=404))
        request_mock = mocker.Mock()
        request_mock.json.return_value = all_result
        return request_mock

    mocked_send_raw_request.side_effect = custom_responses2
    sp = prepare_sp(
        mocked_cmd,
        generate_generic_id(),
        service_principal_secret=generate_generic_id(),
    )
    assert sp
    post_call = mocked_send_raw_request.call_args_list[2].kwargs
    assert post_call["method"] == "POST"
    assert post_call["url"] == f"{GRAPH_V1_SP_ENDPOINT}"
    assert post_call["body"] == json.dumps({"appId": app_id})


@pytest.mark.parametrize("app_id", [None, generate_generic_id()])
@pytest.mark.parametrize("object_id", [None, generate_generic_id()])
@pytest.mark.parametrize("secret", [None, generate_generic_id()])
def test_prepare_sp_error(mocker, mocked_cmd, mocked_send_raw_request, app_id, object_id, secret):
    response = mocker.Mock(status_code=400)
    mocked_send_raw_request.return_value.json.side_effect = HTTPError(
        error_msg=generate_generic_id(), response=response
    )
    mocker.patch(f"{BASE_PATH}.get_tenant_id", return_value=generate_generic_id())
    mocker.patch(f"{BASE_PATH}.ensure_correct_access")
    from azext_edge.edge.providers.orchestration.base import prepare_sp
    if not all([app_id, object_id, secret]):
        with pytest.raises(HTTPError):
            prepare_sp(
                mocked_cmd,
                generate_generic_id(),
                service_principal_app_id=app_id,
                service_principal_object_id=object_id,
                service_principal_secret=secret,
            )


@pytest.mark.parametrize("key_vault", [False, True])
@pytest.mark.parametrize("ms_graph", [False, True])
def test_ensure_correct_access(mocked_cmd, mocked_send_raw_request, key_vault, ms_graph):
    from azext_edge.edge.providers.orchestration.base import ensure_correct_access
    app_id = generate_generic_id()
    resource_access = []
    if key_vault:
        resource_access.append({"resourceAppId": "cfa8b339-82a2-471a-a3c9-0fc0be7a4093"})
    if ms_graph:
        resource_access.append({"resourceAppId": "00000003-0000-0000-c000-000000000000"})
    ensure_correct_access(mocked_cmd, app_id, resource_access)

    if key_vault and ms_graph:
        mocked_send_raw_request.assert_not_called()
    else:
        mocked_send_raw_request.assert_called_once()
        patch_call = mocked_send_raw_request.call_args.kwargs
        assert patch_call["method"] == "PATCH"
        assert patch_call["url"] == (
            f"https://graph.microsoft.com/v1.0/myorganization/applications(appId='{app_id}')"
        )
        body = json.loads(patch_call["body"])["requiredResourceAccess"]
        id_map = {app["resourceAppId"]: app.get("resourceAccess") for app in body}
        if not key_vault:
            assert "cfa8b339-82a2-471a-a3c9-0fc0be7a4093" in id_map
            scope = id_map["cfa8b339-82a2-471a-a3c9-0fc0be7a4093"][0]
            assert scope["type"] == "Scope"
            assert scope["id"] == "f53da476-18e3-4152-8e01-aec403e6edc0"
        if not ms_graph:
            assert "00000003-0000-0000-c000-000000000000" in id_map
            scope = id_map["00000003-0000-0000-c000-000000000000"][0]
            assert scope["type"] == "Scope"
            assert scope["id"] == "e1fe6dd8-ba31-4d61-89e7-88639da4683d"


@pytest.mark.parametrize("tls_ca_path", [None, generate_generic_id()])
@pytest.mark.parametrize("tls_ca_key_path", [None, generate_generic_id()])
def test_prepare_ca(mocker, tls_ca_path, tls_ca_key_path):
    file_patch = mocker.patch(f"{BASE_PATH}.read_file_content", return_value=generate_generic_id())
    path_mock = mocker.Mock()
    path_mock.joinpath.return_value = generate_generic_id()
    normalize_patch = mocker.patch(
        "azext_edge.edge.providers.support.base.normalize_dir", return_value=path_mock
    )
    cert_patch = mocker.patch(
        f"{BASE_PATH}.generate_self_signed_cert", return_value=(generate_generic_id(), generate_generic_id())
    )
    open_patch = mocker.patch("builtins.open", autospec=True)

    from azext_edge.edge.providers.orchestration.base import prepare_ca
    tls_ca_dir = generate_generic_id()
    tls_ca_valid_days = 100
    result = prepare_ca(
        tls_ca_path=tls_ca_path,
        tls_ca_key_path=tls_ca_key_path,
        tls_ca_dir=tls_ca_dir,
        tls_ca_valid_days=tls_ca_valid_days
    )
    if tls_ca_path:
        assert result[0] == file_patch.return_value
        assert result[1] == (file_patch.return_value if tls_ca_key_path else None)
        assert result[2] == "aio-ca-key-pair"
        assert result[3] == "aio-ca-trust-bundle"
    else:
        assert result[0] == cert_patch.return_value[0]
        assert result[1] == cert_patch.return_value[1]
        normalize_patch.assert_called_once_with(dir_path=tls_ca_dir)
        assert open_patch.called is True
        assert result[2] == "aio-ca-key-pair-test-only"
        assert result[3] == "aio-ca-trust-bundle-test-only"


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "client_path": BASE_PATH,
    "resources.get_by_id": {"properties": {"result": generate_generic_id()}},
}], indirect=True)
def test_validate_keyvault_permission_model(mocked_resource_management_client):
    from azext_edge.edge.providers.orchestration.base import validate_keyvault_permission_model
    result = validate_keyvault_permission_model(
        subscription_id=generate_generic_id(),
        keyvault_resource_id=generate_generic_id(),
    )
    assert result == mocked_resource_management_client.resources.get_by_id.return_value.as_dict.return_value


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "client_path": BASE_PATH,
    "resources.get_by_id": {"properties": {"enableRbacAuthorization": True}},
}], indirect=True)
def test_validate_keyvault_permission_model_error(mocked_resource_management_client):
    from azext_edge.edge.providers.orchestration.base import validate_keyvault_permission_model
    with pytest.raises(ValidationError):
        validate_keyvault_permission_model(
            subscription_id=generate_generic_id(),
            keyvault_resource_id=generate_generic_id(),
        )


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "client_path": BASE_PATH,
    "resources.begin_create_or_update_by_id": {"result": generate_generic_id()},
}], indirect=True)
@pytest.mark.parametrize("access_policy", [False, True])
def test_prepare_keyvault_access_policy(mocker, mocked_resource_management_client, access_policy):
    from azext_edge.edge.providers.orchestration.base import prepare_keyvault_access_policy
    sp_record = mocker.Mock(object_id=generate_generic_id(), tenant_id=generate_generic_id())
    keyvault_resource = {"properties": {"vaultUri": generate_generic_id()}}
    if access_policy:
        keyvault_resource["accessPolicies"] = [{
            "objectId": sp_record.object_id
        }]
    sp_record = mocker.Mock(object_id=generate_generic_id(), tenant_id=generate_generic_id())
    result = prepare_keyvault_access_policy(
        subscription_id=generate_generic_id(),
        keyvault_resource=keyvault_resource,
        keyvault_resource_id=generate_generic_id(),
        sp_record=sp_record
    )
    assert result == keyvault_resource["properties"]["vaultUri"]
    assert len(keyvault_resource["properties"]["accessPolicies"]) == 1
    if not access_policy:
        mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
        assert keyvault_resource["properties"]["accessPolicies"][0]["tenantId"] == sp_record.tenant_id
        assert keyvault_resource["properties"]["accessPolicies"][0]["objectId"] == sp_record.object_id
        assert keyvault_resource["properties"]["accessPolicies"][0]["permissions"]


@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "return_value": {
            "value": [{"name": generate_generic_id(), "result": generate_generic_id()}]
        }
    },
    {
        "return_value": {"name": generate_generic_id(), "result": generate_generic_id()}
    }
], ids=["value", "no value"], indirect=True)
@pytest.mark.parametrize("secret_name", [None, generate_generic_id()])
def test_prepare_keyvault_secret(mocked_cmd, mocked_send_raw_request, secret_name):
    from azext_edge.edge.providers.orchestration.base import prepare_keyvault_secret
    deployment_name = ".".join(generate_generic_id())
    vault_uri = generate_generic_id()
    result = prepare_keyvault_secret(
        cmd=mocked_cmd,
        deployment_name=deployment_name,
        vault_uri=vault_uri,
        keyvault_sat_secret_name=secret_name
    )
    if secret_name:
        get_kwargs = mocked_send_raw_request.call_args_list[0].kwargs
        assert get_kwargs["method"] == "GET"
        assert get_kwargs["url"] == f"{vault_uri}/secrets/{secret_name}/versions?api-version=7.4"
        assert get_kwargs["resource"] == "https://vault.azure.net"
    if not mocked_send_raw_request.return_value.json.return_value.get("value") or not secret_name:
        if not secret_name:
            secret_name = deployment_name.replace(".", "-")
        put_kwargs = mocked_send_raw_request.call_args_list[-1].kwargs
        assert put_kwargs["method"] == "PUT"
        assert put_kwargs["url"] == f"{vault_uri}/secrets/{secret_name}?api-version=7.4"
        assert put_kwargs["resource"] == "https://vault.azure.net"
        assert put_kwargs["body"]
    assert result == secret_name


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "client_path": BASE_PATH,
    "deployments.begin_create_or_update": {"result": generate_generic_id()},
    "deployments.begin_what_if": {"result": generate_generic_id()}
}], indirect=True)
@pytest.mark.parametrize("pre_flight", [True, False])
def test_deploy_template(mocked_resource_management_client, pre_flight):
    from azext_edge.edge.providers.orchestration.base import deploy_template
    template = {generate_generic_id(): generate_generic_id()}
    parameters = {generate_generic_id(): generate_generic_id()}
    subscription_id = generate_generic_id()
    resource_group_name = generate_generic_id()
    deployment_name = generate_generic_id()
    cluster_name = generate_generic_id()
    cluster_namespace = generate_generic_id()
    result, deployment = deploy_template(
        template=template,
        parameters=parameters,
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        deployment_name=deployment_name,
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        pre_flight=pre_flight
    )
    expected_parameters = {"properties": {
        "mode": "Incremental", "template": template, "parameters": parameters
    }}
    if pre_flight:
        assert result == {}
        mocked_resource_management_client.deployments.begin_what_if.assert_called_once_with(
            resource_group_name=resource_group_name,
            deployment_name=deployment_name,
            parameters=expected_parameters
        )
        mocked_resource_management_client.deployments.begin_create_or_update.assert_not_called()
        assert deployment == mocked_resource_management_client.deployments.begin_what_if.return_value
    else:
        link = "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"\
            f"%2Fsubscriptions%2F{subscription_id}%2FresourceGroups%2F{resource_group_name}"\
            f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{deployment_name}"
        assert result["deploymentName"] == deployment_name
        assert result["resourceGroup"] == resource_group_name
        assert result["clusterName"] == cluster_name
        assert result["clusterNamespace"] == cluster_namespace
        assert result["deploymentLink"] == link
        assert result["deploymentState"]["timestampUtc"]["started"]
        assert result["deploymentState"]["status"]
        mocked_resource_management_client.deployments.begin_create_or_update.assert_called_once_with(
            resource_group_name=resource_group_name,
            deployment_name=deployment_name,
            parameters=expected_parameters
        )
        mocked_resource_management_client.deployments.begin_what_if.assert_not_called()
        assert deployment == mocked_resource_management_client.deployments.begin_create_or_update.return_value


@pytest.mark.parametrize("cluster_location", [None, generate_generic_id()])
@pytest.mark.parametrize("location", [None, generate_generic_id()])
def test_process_default_location(mocker, cluster_location, location):
    cluster = mocker.patch("azext_edge.edge.providers.orchestration.connected_cluster.ConnectedCluster", autospec=True)
    cluster.return_value.location = generate_generic_id()
    kwargs = {
        "cluster_location": cluster_location,
        "location": location,
        "cluster_name": generate_generic_id(),
        "subscription_id": generate_generic_id(),
        "resource_group_name": generate_generic_id()
    }
    from azext_edge.edge.providers.orchestration.base import process_default_location
    process_default_location(kwargs)
    if cluster_location and location:
        cluster.assert_not_called()
    else:
        cluster.assert_called_once()
        assert kwargs["cluster_location"] == (cluster_location or cluster.return_value.location)
        assert kwargs["location"] == (location or cluster.return_value.location)


def test_get_tenant_id(mocker):
    tenant_id = generate_generic_id()
    profile_patch = mocker.patch("azure.cli.core._profile.Profile", autospec=True)
    profile_patch.return_value.get_subscription.return_value = {"tenantId": tenant_id}
    from azext_edge.edge.providers.orchestration.base import get_tenant_id
    result = get_tenant_id()
    assert result == tenant_id


@pytest.mark.parametrize("done", [True, False])
def test_wait_for_terminal_state(mocker, done):
    # could be fixture with param
    sleep_patch = mocker.patch(f"{BASE_PATH}.sleep")
    poll_num = 10
    mocker.patch(f"{BASE_PATH}.DEFAULT_POLL_RETRIES", poll_num)

    poller = mocker.Mock()
    poller.done.return_value = done
    poller.result.return_value = generate_generic_id()

    from azext_edge.edge.providers.orchestration.base import wait_for_terminal_state

    result = wait_for_terminal_state(poller)
    assert result == poller.result.return_value
    assert sleep_patch.call_count == (1 if done else poll_num)
