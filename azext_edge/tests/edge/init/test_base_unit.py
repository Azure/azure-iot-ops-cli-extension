# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import HTTPError, ValidationError
from requests.models import Response

from azext_edge.edge.providers.orchestration.base import ServicePrincipal
from azext_edge.edge.providers.orchestration.common import (
    GRAPH_V1_APP_ENDPOINT,
    GRAPH_V1_ENDPOINT,
    GRAPH_V1_SP_ENDPOINT,
)
from azext_edge.edge.providers.orchestration.connected_cluster import ConnectedCluster

from ...generators import generate_random_string, get_zeroed_subscription

BASE_ZIP_PATH = "azext_edge.edge.providers.orchestration.base"
ZEROED_SUB = get_zeroed_subscription()


# TODO: move fixtues once functions are moved
@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    terminal_result = mocker.Mock()
    terminal_result.as_dict.return_value = generate_random_string()
    terminal_patch = mocker.patch(f"{BASE_ZIP_PATH}.wait_for_terminal_state", autospec=True, return_value=terminal_result)
    yield terminal_patch


@pytest.fixture
def mocked_sleep(mocker):
    yield mocker.patch(f"{BASE_ZIP_PATH}.sleep")


@pytest.fixture
def mocked_get_tenant_id(mocker):
    yield mocker.patch(f"{BASE_ZIP_PATH}.get_tenant_id", return_value=generate_random_string())


@pytest.fixture
def mocked_keyvault_api(mocker, request):
    is_deployed = getattr(request, "param", True)
    api_patch = mocker.patch(f"{BASE_ZIP_PATH}.KEYVAULT_API_V1")
    api_patch.is_deployed.return_value = is_deployed
    api_patch.group = generate_random_string()
    api_patch.version = generate_random_string()
    yield api_patch


@pytest.fixture
def mocked_base_namespace_functions(mocker, request):
    requests = getattr(request, "param", {})
    path = requests.get("path", BASE_ZIP_PATH)
    get_cluster = requests.get("get_cluster_namespace")
    get_cluster_patch = mocker.patch(f"{path}.get_cluster_namespace", return_value=get_cluster)
    create_cluster_patch = mocker.patch(f"{path}.create_cluster_namespace")
    create_secret_patch = mocker.patch(f"{path}.create_namespaced_secret")
    create_configmap_patch = mocker.patch(f"{path}.create_namespaced_configmap")
    create_object_patch = mocker.patch(f"{path}.create_namespaced_custom_objects")
    yield {
        "get_cluster_patch": get_cluster_patch,
        "create_cluster_patch": create_cluster_patch,
        "create_secret_patch": create_secret_patch,
        "create_configmap_patch": create_configmap_patch,
        "create_object_patch": create_object_patch,
    }


@pytest.mark.parametrize(
    "mocked_resource_management_client",
    [{"client_path": BASE_ZIP_PATH, "resources.begin_create_or_update_by_id": {"result": generate_random_string()}}],
    indirect=True,
)
@pytest.mark.parametrize("rotation_poll_interval", ["1h"])
@pytest.mark.parametrize("extension_name", ["akvsecretsprovider"])
def test_provision_akv_csi_driver(
    mocked_resource_management_client, mocked_wait_for_terminal_state, rotation_poll_interval, extension_name
):
    from azext_edge.edge.providers.orchestration.base import (
        KEYVAULT_ARC_EXTENSION_VERSION,
        provision_akv_csi_driver,
    )

    subscription_id = generate_random_string()
    cluster_name = generate_random_string()
    resource_group_name = generate_random_string()
    enable_secret_rotation = generate_random_string()
    result = provision_akv_csi_driver(
        subscription_id=subscription_id,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        enable_secret_rotation=enable_secret_rotation,
        rotation_poll_interval=rotation_poll_interval,
        extension_name=extension_name,
    )

    assert result == mocked_wait_for_terminal_state.return_value.as_dict.return_value
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    mocked_wait_for_terminal_state.assert_called_once_with(poller)

    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    expected_id = (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}/Providers"
        f"/Microsoft.KubernetesConfiguration/extensions/{extension_name}"
    )
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


@pytest.mark.parametrize(
    "mocked_base_namespace_functions",
    [{"get_cluster_namespace": False}, {"get_cluster_namespace": True}],
    indirect=True,
)
def test_configure_cluster_secrets(mocker, mocked_base_namespace_functions, mocked_keyvault_api):
    get_store_patch = mocker.patch(f"{BASE_ZIP_PATH}.get_kv_secret_store_yaml", return_value=generate_random_string())
    from azext_edge.edge.providers.orchestration.base import configure_cluster_secrets

    cluster_namespace = generate_random_string()
    cluster_secret_ref = generate_random_string()
    keyvault_spc_secret_name = generate_random_string()
    keyvault_resource_id = generate_random_string()
    sp_record = mocker.Mock(
        client_id=generate_random_string(), secret=generate_random_string(), tenant_id=generate_random_string()
    )
    configure_cluster_secrets(
        cluster_namespace=cluster_namespace,
        cluster_secret_ref=cluster_secret_ref,
        cluster_akv_secret_class_name=generate_random_string(),
        keyvault_spc_secret_name=keyvault_spc_secret_name,
        keyvault_resource_id=keyvault_resource_id,
        sp_record=sp_record,
    )
    mocked_base_namespace_functions["get_cluster_patch"].assert_called_once()
    expected_call_count = int(not mocked_base_namespace_functions["get_cluster_patch"].return_value)
    assert mocked_base_namespace_functions["create_cluster_patch"].call_count == expected_call_count
    mocked_base_namespace_functions["create_secret_patch"].assert_called_once_with(
        secret_name=cluster_secret_ref,
        namespace=cluster_namespace,
        data={"clientid": sp_record.client_id, "clientsecret": sp_record.secret},
        labels={"secrets-store.csi.k8s.io/used": "true"},
        delete_first=True,
    )
    assert get_store_patch.call_count == 5
    mocked_base_namespace_functions["create_object_patch"].assert_called_once_with(
        group=mocked_keyvault_api.group,
        version=mocked_keyvault_api.version,
        plural="secretproviderclasses",
        namespace=cluster_namespace,
        yaml_objects=[get_store_patch.return_value] * 5,
        delete_first=True,
    )


@pytest.mark.parametrize("mocked_keyvault_api", [False], indirect=True)
def test_configure_cluster_secrets_error(mocked_keyvault_api):
    from azext_edge.edge.providers.orchestration.base import configure_cluster_secrets

    with pytest.raises(ValidationError):
        configure_cluster_secrets(
            cluster_namespace=generate_random_string(),
            cluster_secret_ref=generate_random_string(),
            cluster_akv_secret_class_name=generate_random_string(),
            keyvault_spc_secret_name=generate_random_string(),
            keyvault_resource_id=generate_random_string(),
            sp_record=generate_random_string(),
        )


@pytest.mark.parametrize(
    "mocked_base_namespace_functions",
    [{"get_cluster_namespace": False}, {"get_cluster_namespace": True}],
    indirect=True,
)
def test_configure_cluster_tls(mocked_base_namespace_functions):
    from azext_edge.edge.providers.orchestration.base import configure_cluster_tls

    cluster_namespace = generate_random_string()
    public_ca = bytes(generate_random_string(), "utf-8")
    cm_name = generate_random_string()
    configure_cluster_tls(
        cluster_namespace=cluster_namespace,
        public_ca=public_ca,
        private_key=bytes(generate_random_string(), "utf-8"),
        secret_name=generate_random_string(),
        cm_name=cm_name,
    )
    mocked_base_namespace_functions["get_cluster_patch"].assert_called_once()
    expected_call_count = int(not mocked_base_namespace_functions["get_cluster_patch"].return_value)
    assert mocked_base_namespace_functions["create_cluster_patch"].call_count == expected_call_count
    mocked_base_namespace_functions["create_secret_patch"].assert_called_once()

    mocked_base_namespace_functions["create_configmap_patch"].assert_called_once_with(
        namespace=cluster_namespace, cm_name=cm_name, data={"ca.crt": public_ca.decode()}, delete_first=True
    )


@pytest.mark.parametrize(
    "mocked_send_raw_request",
    [
        {
            "return_value": {
                "appId": generate_random_string(),
                "id": generate_random_string(),
                "secretText": generate_random_string(),
                "requiredResourceAccess": [
                    {"resourceAppId": "cfa8b339-82a2-471a-a3c9-0fc0be7a4093"},
                    {"resourceAppId": "00000003-0000-0000-c000-000000000000"},
                ],
            }
        }
    ],
    ids=["pass everything"],
    indirect=True,
)
@pytest.mark.parametrize("app_id", [None, generate_random_string()])
@pytest.mark.parametrize("object_id", [None, generate_random_string()])
@pytest.mark.parametrize("secret", [None, generate_random_string()])
@pytest.mark.parametrize("secret_valid_days", [365, 100])
def test_prepare_sp(
    mocker,
    mocked_cmd,
    mocked_get_tenant_id,
    mocked_send_raw_request,
    mocked_sleep,
    app_id,
    object_id,
    secret,
    secret_valid_days,
):
    import datetime

    timedelta_spy = mocker.spy(datetime, "timedelta")
    access_patch = mocker.patch(f"{BASE_ZIP_PATH}.ensure_correct_access")
    from azext_edge.edge.providers.orchestration.base import prepare_sp

    deployment_name = generate_random_string()
    sp = prepare_sp(
        mocked_cmd,
        deployment_name,
        service_principal_app_id=app_id,
        service_principal_object_id=object_id,
        service_principal_secret=secret,
        service_principal_secret_valid_days=secret_valid_days,
    )
    raw_request_result = mocked_send_raw_request.return_value.json.return_value
    assert sp.client_id == (app_id or raw_request_result["appId"])
    assert sp.object_id == (object_id or raw_request_result["id"])
    assert sp.secret == (secret or raw_request_result["secretText"])
    assert sp.tenant_id == mocked_get_tenant_id.return_value
    assert sp.created_app is not (app_id or object_id)
    timedelta_spy.assert_called_once_with(days=secret_valid_days)

    # check calls one by one
    call_count = 0
    if not app_id:
        if object_id:
            get_sp_call = mocked_send_raw_request.call_args_list[call_count].kwargs
            assert get_sp_call["method"] == "GET"
            assert get_sp_call["url"] == f"{GRAPH_V1_SP_ENDPOINT}/{sp.object_id}"
            get_app_call = mocked_send_raw_request.call_args_list[call_count + 1].kwargs
            assert get_app_call["method"] == "GET"
            assert get_app_call["url"] == f"{GRAPH_V1_APP_ENDPOINT}(appId='{sp.client_id}')"
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
        mocked_sleep.assert_called_once()
        call_count += 1

    assert mocked_send_raw_request.call_count == call_count


@pytest.mark.parametrize("error_code", [401, 403])
def test_prepare_sp_catches(mocker, mocked_cmd, mocked_get_tenant_id, mocked_send_raw_request, error_code):
    """Test that this function does not error even if there is an http error - there are 3 cases."""
    from azext_edge.edge.providers.orchestration.base import prepare_sp

    app_id = generate_random_string()
    all_result = {
        "appId": app_id,
        "id": generate_random_string(),
        "secretText": generate_random_string(),
        "requiredResourceAccess": [
            {"resourceAppId": "cfa8b339-82a2-471a-a3c9-0fc0be7a4093"},
            {"resourceAppId": "00000003-0000-0000-c000-000000000000"},
        ],
    }

    def custom_responses(**kwargs):
        if kwargs["url"].startswith(f"{GRAPH_V1_APP_ENDPOINT}/"):
            raise HTTPError(error_msg=generate_random_string(), response=mocker.Mock(status_code=error_code))
        request_mock = mocker.Mock()
        request_mock.json.return_value = all_result
        return request_mock

    mocked_send_raw_request.side_effect = custom_responses
    mocker.patch(f"{BASE_ZIP_PATH}.ensure_correct_access")
    sp = prepare_sp(
        mocked_cmd,
        generate_random_string(),
        service_principal_object_id=generate_random_string(),
        service_principal_secret=generate_random_string(),
    )
    assert sp
    mocked_send_raw_request.reset_mock()

    def custom_responses2(**kwargs):
        if kwargs["url"].startswith(f"{GRAPH_V1_SP_ENDPOINT}(appId='"):
            raise HTTPError(error_msg=generate_random_string(), response=mocker.Mock(status_code=404))
        request_mock = mocker.Mock()
        request_mock.json.return_value = all_result
        return request_mock

    mocked_send_raw_request.side_effect = custom_responses2
    sp = prepare_sp(
        mocked_cmd,
        generate_random_string(),
        service_principal_secret=generate_random_string(),
    )
    assert sp
    post_call = mocked_send_raw_request.call_args_list[2].kwargs
    assert post_call["method"] == "POST"
    assert post_call["url"] == f"{GRAPH_V1_SP_ENDPOINT}"
    assert post_call["body"] == json.dumps({"appId": app_id})


@pytest.mark.parametrize("app_id", [None, generate_random_string()])
@pytest.mark.parametrize("object_id", [None, generate_random_string()])
@pytest.mark.parametrize("secret", [None, generate_random_string()])
def test_prepare_sp_error(
    mocker, mocked_cmd, mocked_get_tenant_id, mocked_send_raw_request, app_id, object_id, secret
):
    response = mocker.Mock(status_code=400)
    mocked_send_raw_request.return_value.json.side_effect = HTTPError(
        error_msg=generate_random_string(), response=response
    )
    mocker.patch(f"{BASE_ZIP_PATH}.ensure_correct_access")
    from azext_edge.edge.providers.orchestration.base import prepare_sp

    if not all([app_id, object_id, secret]):
        with pytest.raises(HTTPError):
            prepare_sp(
                mocked_cmd,
                generate_random_string(),
                service_principal_app_id=app_id,
                service_principal_object_id=object_id,
                service_principal_secret=secret,
            )


@pytest.mark.parametrize("key_vault", [False, True])
@pytest.mark.parametrize("ms_graph", [False, True])
def test_ensure_correct_access(mocked_cmd, mocked_send_raw_request, key_vault, ms_graph):
    from azext_edge.edge.providers.orchestration.base import ensure_correct_access

    app_id = generate_random_string()
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
        assert patch_call["url"] == (f"https://graph.microsoft.com/v1.0/myorganization/applications(appId='{app_id}')")
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


@pytest.mark.parametrize("tls_ca_path", [None, generate_random_string()])
@pytest.mark.parametrize("tls_ca_key_path", [None, generate_random_string()])
@pytest.mark.parametrize("tls_ca_dir", [None, generate_random_string()])
def test_prepare_ca(mocker, tls_ca_path, tls_ca_key_path, tls_ca_dir):
    from unittest.mock import mock_open, patch

    file_patch = mocker.patch(f"{BASE_ZIP_PATH}.read_file_content", return_value=generate_random_string())
    path_mock = mocker.Mock()
    path_mock.joinpath.return_value = generate_random_string()
    normalize_dir_patch = mocker.patch("azext_edge.edge.util.normalize_dir", return_value=path_mock)
    cert_patch = mocker.patch(
        f"{BASE_ZIP_PATH}.generate_self_signed_cert", return_value=(generate_random_string(), generate_random_string())
    )

    with patch("builtins.open", mock_open(read_data="data")) as mock_open_file:
        from azext_edge.edge.providers.orchestration.base import prepare_ca

        tls_ca_valid_days = 100
        result = prepare_ca(
            tls_ca_path=tls_ca_path,
            tls_ca_key_path=tls_ca_key_path,
            tls_ca_dir=tls_ca_dir,
            tls_ca_valid_days=tls_ca_valid_days,
        )

    if tls_ca_path:
        assert result[0] == file_patch.return_value
        assert result[1] == (file_patch.return_value if tls_ca_key_path else None)
        assert result[2] == "aio-ca-key-pair"
        assert result[3] == "aio-ca-trust-bundle"
    else:
        assert result[0] == cert_patch.return_value[0]
        assert result[1] == cert_patch.return_value[1]
        assert result[2] == "aio-ca-key-pair-test-only"
        assert result[3] == "aio-ca-trust-bundle-test-only"

    if tls_ca_dir and not tls_ca_path:
        normalize_dir_patch.assert_called_once_with(dir_path=tls_ca_dir)
        assert mock_open_file.call_count == 2
        assert mock_open_file().write.call_count == 2
        mock_open_file.assert_any_call(path_mock.joinpath.return_value, "wb")
        mock_open_file().write.assert_any_call(cert_patch.return_value[0])
        mock_open_file().write.assert_any_call(cert_patch.return_value[1])
    else:
        assert mock_open_file.call_count == 0
        assert mock_open_file().write.call_count == 0
        assert normalize_dir_patch.call_count == 0


@pytest.mark.parametrize(
    "mocked_resource_management_client",
    [
        {
            "client_path": BASE_ZIP_PATH,
            "resources.get_by_id": {"properties": {"result": generate_random_string()}},
        }
    ],
    indirect=True,
)
def test_validate_keyvault_permission_model(mocked_resource_management_client):
    from azext_edge.edge.providers.orchestration.base import (
        validate_keyvault_permission_model,
    )

    result = validate_keyvault_permission_model(
        subscription_id=generate_random_string(),
        keyvault_resource_id=generate_random_string(),
    )
    assert result == mocked_resource_management_client.resources.get_by_id.return_value.as_dict.return_value


@pytest.mark.parametrize(
    "mocked_resource_management_client",
    [
        {
            "client_path": BASE_ZIP_PATH,
            "resources.get_by_id": {"properties": {"enableRbacAuthorization": True}},
        }
    ],
    indirect=True,
)
def test_validate_keyvault_permission_model_error(mocked_resource_management_client):
    from azext_edge.edge.providers.orchestration.base import (
        validate_keyvault_permission_model,
    )

    with pytest.raises(ValidationError):
        validate_keyvault_permission_model(
            subscription_id=generate_random_string(),
            keyvault_resource_id=generate_random_string(),
        )


@pytest.mark.parametrize(
    "mocked_resource_management_client",
    [
        {
            "client_path": BASE_ZIP_PATH,
            "resources.begin_create_or_update_by_id": {"result": generate_random_string()},
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("access_policy", [False, True])
def test_prepare_keyvault_access_policy(mocker, mocked_resource_management_client, mocked_sleep, access_policy):
    from azext_edge.edge.providers.orchestration.base import (
        prepare_keyvault_access_policy,
    )

    sp_record = mocker.Mock(object_id=generate_random_string(), tenant_id=generate_random_string())
    keyvault_resource = {"properties": {"vaultUri": generate_random_string()}}
    if access_policy:
        keyvault_resource["accessPolicies"] = [{"objectId": sp_record.object_id}]
    sp_record = mocker.Mock(object_id=generate_random_string(), tenant_id=generate_random_string())
    result = prepare_keyvault_access_policy(
        subscription_id=generate_random_string(),
        keyvault_resource=keyvault_resource,
        keyvault_resource_id=generate_random_string(),
        sp_record=sp_record,
    )
    assert result == keyvault_resource["properties"]["vaultUri"]
    assert len(keyvault_resource["properties"]["accessPolicies"]) == 1
    if not access_policy:
        mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
        mocked_sleep.assert_called_once()
        assert keyvault_resource["properties"]["accessPolicies"][0]["tenantId"] == sp_record.tenant_id
        assert keyvault_resource["properties"]["accessPolicies"][0]["objectId"] == sp_record.object_id
        assert keyvault_resource["properties"]["accessPolicies"][0]["permissions"]


@pytest.mark.parametrize(
    "mocked_send_raw_request",
    [
        {"return_value": {"value": [{"name": generate_random_string(), "result": generate_random_string()}]}},
        {"return_value": {"name": generate_random_string(), "result": generate_random_string()}},
    ],
    ids=["value", "no value"],
    indirect=True,
)
@pytest.mark.parametrize("secret_name", [None, generate_random_string()])
def test_prepare_keyvault_secret(mocked_cmd, mocked_send_raw_request, secret_name):
    from azext_edge.edge.providers.orchestration.base import prepare_keyvault_secret

    deployment_name = ".".join(generate_random_string())
    vault_uri = generate_random_string()
    result = prepare_keyvault_secret(
        cmd=mocked_cmd, deployment_name=deployment_name, vault_uri=vault_uri, keyvault_spc_secret_name=secret_name
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


@pytest.mark.parametrize(
    "mocked_resource_management_client",
    [
        {
            "client_path": BASE_ZIP_PATH,
            "deployments.begin_create_or_update": {"result": generate_random_string()},
            "deployments.begin_what_if": {"result": generate_random_string()},
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("pre_flight", [True, False])
def test_deploy_template(mocked_resource_management_client, pre_flight):
    from azext_edge.edge.providers.orchestration.base import deploy_template

    template = {generate_random_string(): generate_random_string()}
    parameters = {generate_random_string(): generate_random_string()}
    subscription_id = generate_random_string()
    resource_group_name = generate_random_string()
    deployment_name = generate_random_string()
    cluster_name = generate_random_string()
    cluster_namespace = generate_random_string()
    result, deployment = deploy_template(
        template=template,
        parameters=parameters,
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        deployment_name=deployment_name,
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        pre_flight=pre_flight,
    )
    expected_parameters = {"properties": {"mode": "Incremental", "template": template, "parameters": parameters}}
    if pre_flight:
        assert not result
        mocked_resource_management_client.deployments.begin_what_if.assert_called_once_with(
            resource_group_name=resource_group_name, deployment_name=deployment_name, parameters=expected_parameters
        )
        mocked_resource_management_client.deployments.begin_create_or_update.assert_not_called()
        assert deployment == mocked_resource_management_client.deployments.begin_what_if.return_value
    else:
        link = (
            "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/"
            f"%2Fsubscriptions%2F{subscription_id}%2FresourceGroups%2F{resource_group_name}"
            f"%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F{deployment_name}"
        )
        assert result["deploymentName"] == deployment_name
        assert result["resourceGroup"] == resource_group_name
        assert result["clusterName"] == cluster_name
        assert result["clusterNamespace"] == cluster_namespace
        assert result["deploymentLink"] == link
        assert result["deploymentState"]["timestampUtc"]["started"]
        assert result["deploymentState"]["status"]
        mocked_resource_management_client.deployments.begin_create_or_update.assert_called_once_with(
            resource_group_name=resource_group_name, deployment_name=deployment_name, parameters=expected_parameters
        )
        mocked_resource_management_client.deployments.begin_what_if.assert_not_called()
        assert deployment == mocked_resource_management_client.deployments.begin_create_or_update.return_value


@pytest.mark.parametrize("mocked_connected_cluster_location", ["westus2", "WestUS2"], indirect=True)
@pytest.mark.parametrize("location", [None, generate_random_string()])
def test_verify_cluster_and_use_location(mocked_connected_cluster_location, mocked_cmd, location):
    kwargs = {
        "cmd": mocked_cmd,
        "cluster_location": None,
        "location": location,
        "cluster_name": generate_random_string(),
        "subscription_id": generate_random_string(),
        "resource_group_name": generate_random_string(),
    }
    from azext_edge.edge.providers.orchestration.base import (
        verify_cluster_and_use_location,
    )

    connected_cluster = verify_cluster_and_use_location(kwargs)

    connected_cluster.cluster_name == kwargs["cluster_name"]
    connected_cluster.subscription_id == kwargs["subscription_id"]
    connected_cluster.resource_group_name == kwargs["resource_group_name"]

    mocked_connected_cluster_location.assert_called_once()

    lowered_cluster_location = mocked_connected_cluster_location.return_value.lower()
    assert kwargs["cluster_location"] == lowered_cluster_location

    if location:
        assert kwargs["location"] == location
    else:
        assert kwargs["location"] == lowered_cluster_location


@pytest.mark.parametrize(
    "mocked_connected_cluster_extensions",
    [
        [{"properties": {"extensionType": "microsoft.iotoperations"}}],
        [
            {"properties": {"extensionType": "microsoft.extension"}},
            {"properties": {"extensionType": "Microsoft.IoTOperations.mq"}},
        ],
        [{"properties": {"extensionType": "microsoft.extension"}}],
        [],
    ],
    indirect=True,
)
def test_throw_if_iotops_deployed(mocked_connected_cluster_extensions, mocked_cmd):
    from azext_edge.edge.providers.orchestration.base import (
        IOT_OPERATIONS_EXTENSION_PREFIX,
        ConnectedCluster,
        throw_if_iotops_deployed,
    )

    kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": generate_random_string(),
        "subscription_id": generate_random_string(),
        "resource_group_name": generate_random_string(),
    }

    assert IOT_OPERATIONS_EXTENSION_PREFIX == "microsoft.iotoperations"

    expect_validation_error = False
    for extension in mocked_connected_cluster_extensions.return_value:
        if extension["properties"]["extensionType"].lower().startswith(IOT_OPERATIONS_EXTENSION_PREFIX):
            expect_validation_error = True
            break

    if expect_validation_error:
        with pytest.raises(ValidationError):
            throw_if_iotops_deployed(ConnectedCluster(**kwargs))
        return

    throw_if_iotops_deployed(ConnectedCluster(**kwargs))
    mocked_connected_cluster_extensions.assert_called_once()


@pytest.mark.parametrize(
    "role_bindings",
    [
        None,
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "items": [],
            "kind": "ClusterRoleBindingList",
            "metadata": {"resourceVersion": "1"},
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "items": [{"metadata": {"name": "AzureArc-Microsoft.ExtendedLocation-RP-RoleBinding", "namespace": "az"}}],
            "kind": "ClusterRoleBindingList",
            "metadata": {"resourceVersion": "2"},
        },
    ],
)
def test_verify_custom_locations_enabled(mocker, role_bindings):
    get_binding_patch = mocker.patch(f"{BASE_ZIP_PATH}.get_bindings", return_value=role_bindings)
    from azext_edge.edge.providers.orchestration.base import (
        verify_custom_locations_enabled,
    )

    if not role_bindings or (role_bindings and not role_bindings["items"]):
        with pytest.raises(ValidationError):
            verify_custom_locations_enabled()
            get_binding_patch.assert_called_once()
        return

    verify_custom_locations_enabled()
    get_binding_patch.assert_called_once()


@pytest.mark.parametrize(
    "test_scenario",
    [
        {  # fail no config map
            "failure": True,
            "config_map": None,
        },
        {  # fail config indicates diff cluster
            "failure": "cluster name",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster2",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # fail config indicates diff rg
            "failure": "resource group",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg2",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # fail config indicates diff sub
            "failure": "subscription Id",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": "8757c60a-a398-4c09-adaf-be328caf42d4",
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # success
            "failure": False,
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
    ],
)
def test_verify_arc_cluster_config(mocker, mocked_cmd, test_scenario):
    get_config_map_patch = mocker.patch(f"{BASE_ZIP_PATH}.get_config_map", return_value=test_scenario["config_map"])
    from azext_edge.edge.providers.orchestration.base import verify_arc_cluster_config

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd,
        subscription_id=ZEROED_SUB,
        cluster_name="cluster1",
        resource_group_name="rg1",
    )

    failure = test_scenario["failure"]
    if failure:
        match_str = ""
        if isinstance(failure, str):
            match_str = failure
        with pytest.raises(ValidationError, match=rf".*{match_str}.*"):
            verify_arc_cluster_config(connected_cluster)
            get_config_map_patch.assert_called_once()
        return

    verify_arc_cluster_config(connected_cluster)
    get_config_map_patch.assert_called_once()


@pytest.mark.parametrize("http_error", [None, 401, 403, 500])
def test_eval_secret_via_sp(mocker, mocked_cmd, http_error):

    def assert_mocked_get_token_from_sp_credential():
        mocked_get_token_from_sp_credential.assert_called_once_with(
            tenant_id=sp_record.tenant_id,
            client_id=sp_record.client_id,
            client_secret=sp_record.secret,
            scope="https://vault.azure.net/.default",
        )

    mock_token = generate_random_string()
    mocked_get_token_from_sp_credential: Mock = mocker.patch(
        f"{BASE_ZIP_PATH}.get_token_from_sp_credential", return_value=mock_token
    )
    mocked_send_raw_request: Mock = mocker.patch("azure.cli.core.util.send_raw_request")

    if http_error:
        test_response = Response()
        test_response.status_code = http_error
        mocked_send_raw_request.side_effect = HTTPError(error_msg=generate_random_string(), response=test_response)

    from azext_edge.edge.providers.orchestration.base import eval_secret_via_sp

    vault_uri = generate_random_string()
    kv_spc_secret_name = generate_random_string()
    sp_record = ServicePrincipal(
        client_id=generate_random_string(),
        object_id=generate_random_string(),
        tenant_id=generate_random_string(),
        secret=generate_random_string(),
        created_app=False,
    )

    if http_error:
        with pytest.raises(ValidationError) as ve:
            eval_secret_via_sp(
                cmd=mocked_cmd, vault_uri=vault_uri, keyvault_spc_secret_name=kv_spc_secret_name, sp_record=sp_record
            )
            assert_mocked_get_token_from_sp_credential()
        if http_error in [401, 403]:
            assert "auth failure" in str(ve.value)
        return

    eval_secret_via_sp(
        cmd=mocked_cmd, vault_uri=vault_uri, keyvault_spc_secret_name=kv_spc_secret_name, sp_record=sp_record
    )
    assert_mocked_get_token_from_sp_credential()
    mocked_send_raw_request.assert_called_once_with(
        cli_ctx=mocked_cmd.cli_ctx,
        method="GET",
        headers=[f"Authorization=Bearer {mock_token}"],
        url=f"{vault_uri}/secrets/{kv_spc_secret_name}?api-version=7.4",
    )


@pytest.mark.parametrize(
    "custom_location_name, namespace, get_cl_for_np_return_value",
    [
        ("mycl", "mynamespace", None),
        ("mycl", "mynamespace", {"name": "mycl"}),
        ("mycl", "mynamespace", {"name": "othercl"}),
    ],
)
def test_verify_custom_location_namespace(
    mocker, mocked_cmd, custom_location_name, namespace, get_cl_for_np_return_value
):
    mocked_get_custom_location_for_namespace = mocker.patch(
        "azext_edge.edge.providers.orchestration.connected_cluster.ConnectedCluster.get_custom_location_for_namespace"
    )
    mocked_get_custom_location_for_namespace.return_value = get_cl_for_np_return_value

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd,
        subscription_id=ZEROED_SUB,
        cluster_name="cluster1",
        resource_group_name="rg1",
    )

    from azext_edge.edge.providers.orchestration.base import verify_custom_location_namespace

    if get_cl_for_np_return_value and get_cl_for_np_return_value["name"] != custom_location_name:
        with pytest.raises(ValidationError) as ve:
            verify_custom_location_namespace(
                connected_cluster=connected_cluster, custom_location_name=custom_location_name, namespace=namespace
            )
        assert (
            f"The intended namespace for deployment: {namespace}, is already referenced "
            f"by custom location: {get_cl_for_np_return_value['name']}" in str(ve.value)
        )
        return

    verify_custom_location_namespace(
        connected_cluster=connected_cluster, custom_location_name=custom_location_name, namespace=namespace
    )
