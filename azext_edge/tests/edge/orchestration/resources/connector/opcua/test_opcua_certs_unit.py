# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
from unittest.mock import Mock
import pytest

import responses
from azext_edge.edge.commands_connector import add_connector_opcua_client, add_connector_opcua_issuer, add_connector_opcua_trust
from azext_edge.edge.providers.orchestration.resource_map import IoTOperationsResource
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    OPCUA_SPC_NAME,
    OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
)
from azext_edge.edge.providers.orchestration.work import IOT_OPS_EXTENSION_TYPE
from azext_edge.tests.edge.orchestration.resources.conftest import get_base_endpoint, get_mock_resource
from azext_edge.tests.generators import generate_random_string

# TODO: Add more tests


@pytest.fixture
def spy_opcua_cert(mocker):
    from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OpcUACerts

    yield {
        "_process_fortos_yaml": mocker.spy(OpcUACerts, "_process_fortos_yaml"),
        "_check_and_update_secret_name": mocker.spy(OpcUACerts, "_check_and_update_secret_name"),
        "_upload_to_key_vault": mocker.spy(OpcUACerts, "_upload_to_key_vault"),
        "_add_secret_to_spc": mocker.spy(OpcUACerts, "_add_secret_to_spc"),
        "_add_secret_to_secret_sync": mocker.spy(OpcUACerts, "_add_secret_to_secret_sync"),
        "_get_cl_resources": mocker.spy(OpcUACerts, "_get_cl_resources"),
    }


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.logger",
    )
    yield patched


@pytest.fixture
def mocked_get_keyvault_client(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.get_keyvault_client"
    )
    yield patched


@pytest.fixture
def mocked_get_ssc_mgmt_client(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.get_ssc_mgmt_client", autospec=True
    )
    yield patched


@pytest.fixture
def mocked_show(mocker):
    mocked_instance = get_mock_resource(
        name="mock-instance",
        properties={
            "description": "AIO Instance description.",
            "provisioningState": "Succeeded",
            "extendedLocation": {"name": "mock-location"},
            "customLocations": [
                {
                    "hostResourceId": "/subscriptions/mock-sub/resourceGroups/mock-rg/"
                    "providers/Microsoft.Kubernetes/connectedClusters/mock-cluster",
                    "namespace": "azure-iot-operations",
                    "displayName": "mock-custom-location",
                    "provisioningState": "Succeeded",
                    "clusterExtensionIds": ["mock-extension-id"],
                    "authentication": {},
                }
            ],
        },
        resource_group_name="mock-rg",
    )
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.Instances.show",
        return_value=mocked_instance,
    )
    yield patched


def mocked_file_open(mocker, file_content: bytes):
    mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch("azext_edge.edge.util.queryable")
    yield patched().get_resource_client


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.Instances",
    )
    yield patched().get_resource_map


@pytest.fixture
def mocked_sleep(mocker):
    patched = mocker.patch("azext_edge.edge.util.az_client.sleep", return_value=None)
    yield patched


def _generate_ops_resource(segments: int = 1) -> IoTOperationsResource:
    resource_id = ""
    for _ in range(segments):
        resource_id = f"{resource_id}/{generate_random_string()}"

    resource = IoTOperationsResource(
        resource_id=resource_id,
        display_name=resource_id.split("/")[-1],
        api_version=generate_random_string(),
    )

    return resource


def get_spc_endpoint(spc_name: str, resource_group_name: str) -> str:
    resource_path = "/azureKeyVaultSecretProviderClasses"
    if spc_name:
        resource_path += f"/{spc_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider="Microsoft.SecretSyncController",
        api_version="2024-08-21-preview",
    )


def get_secretsync_endpoint(secretsync_name: str, resource_group_name: str) -> str:
    resource_path = "/secretSyncs"
    if secretsync_name:
        resource_path += f"/{secretsync_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider="Microsoft.SecretSyncController",
        api_version="2024-08-21-preview",
    )


def get_secret_endpoint(keyvault_name: str, secret_name: Optional[str] = None) -> str:
    resource_path = "/secrets"
    if secret_name:
        resource_path += f"/{secret_name}"

    return f"https://{keyvault_name}.vault.azure.net{resource_path}?api-version=7.4"


def get_mock_spc_record(spc_name: str, resource_group_name: str, objects: Optional[str] = None) -> dict:
    objects = objects or ""
    return get_mock_resource(
        name=spc_name,
        resource_path=f"/azureKeyVaultSecretProviderClasses/{spc_name}",
        properties={
            "provisioningState": "Succeeded",
            "clientId": generate_random_string(),
            "keyvaultName": "mock-keyvault",
            "objects": objects,
            "tenantId": generate_random_string(),
        },
        resource_group_name=resource_group_name,
        qualified_type="Microsoft.SecretSyncController/AzureKeyVaultSecretProviderClasses",
    )


def get_mock_secretsync_record(secretsync_name: str, resource_group_name: str, objects: Optional[str] = None) -> dict:
    objects = objects or ""
    return get_mock_resource(
        name=secretsync_name,
        resource_path=f"/secretSyncs/{secretsync_name}",
        properties={
            "provisioningState": "Succeeded",
            "kubernetesSecretType": "Opaque",
            "secretProviderClassName": "opc-ua-connector",
            "serviceAccountName": "aio-ssc-sa",
            "objectSecretMapping": [],
        },
        resource_group_name=resource_group_name,
        qualified_type="Microsoft.SecretSyncController/secretSyncs",
    )


@pytest.mark.parametrize("file_content", [b"\x00\x01\x02\x03"])
@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync, file_name, secret_name, expected_secret_sync",
    [
        (
            {
                "resources": None,
                "resource sync rules": None,
                "custom locations": None,
                "extensions": None,
                "meta": {
                    "expected_total": 0,
                },
            },
            {},
            {},
            "/fake/path/certificate.crt",
            None,
            {},
        ),
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [_generate_ops_resource()],
                "custom locations": [_generate_ops_resource()],
                "extensions": [_generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
            ),
            "/fake/path/certificate.der",
            "new-secret",
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects="new-secret",
            ),
        ),
    ],
)
def test_trust_add(
    mocker,
    mocked_cmd,
    mocked_sleep: Mock,
    expected_resources_map,
    trust_list_spc,
    trust_list_secretsync,
    file_name,
    file_content,
    secret_name,
    expected_secret_sync,
    mocked_responses: responses,
):

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.read_file_content",
        return_value=file_content,
    )
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    if expected_resources_map["resources"]:
        # get default spc
        mocked_responses.add(
            method=responses.GET,
            url=get_spc_endpoint(spc_name="default-spc", resource_group_name=rg_name),
            json=expected_resources_map["resources"][0],
            status=200,
            content_type="application/json",
        )

    if trust_list_spc:
        # get secrets
        mocked_responses.add(
            method=responses.GET,
            url=get_secret_endpoint(keyvault_name="mock-keyvault"),
            json={
                "value": [
                    {
                        "id": "https://mock-keyvault.vault.azure.net/secrets/mock-secret",
                    }
                ]
            },
            status=200,
            content_type="application/json",
        )

        # set secret
        mocked_responses.add(
            method=responses.PUT,
            url=get_secret_endpoint(keyvault_name="mock-keyvault", secret_name=secret_name),
            json={},
            status=200,
            content_type="application/json",
        )

        # get opcua spc
        mocked_responses.add(
            method=responses.GET,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
            json=trust_list_spc,
            status=200,
            content_type="application/json",
        )

        # set opcua spc
        mocked_responses.add(
            method=responses.PUT,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
            json={},
            status=200,
            content_type="application/json",
        )

        # get opcua secretsync
        mocked_responses.add(
            method=responses.GET,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=trust_list_secretsync,
            status=200,
            content_type="application/json",
        )

        # set opcua secretsync
        mocked_responses.add(
            method=responses.PUT,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=expected_secret_sync,
            status=200,
            content_type="application/json",
        )

    result = None

    try:
        result = add_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file=file_name,
            secret_name=secret_name,
        )
    except Exception:
        # TODO: Add more assertions
        if not expected_resources_map["custom locations"]:
            assert (
                mocked_logger.error.call_args[0][0] == f"Secret sync is not enabled for the instance {instance_name}."
                "Please enable secret sync before adding certificate."
            )
            return

    if result:
        assert result == expected_secret_sync

def _assemble_resource_map_mock(
    resource_map_mock: Mock,
    extension: Optional[dict],
    custom_locations: Optional[List[dict]],
    resources: Optional[List[dict]],
):
    resource_map_mock().custom_locations = custom_locations
    resource_map_mock().get_resources.return_value = resources
    resource_map_mock().connected_cluster.get_extensions_by_type.return_value = extension
    resource_map_mock().connected_cluster.get_aio_resources.return_value = resources

@pytest.mark.parametrize("file_content", [b"\x00\x01\x02\x03"])
@pytest.mark.parametrize(
    "expected_resources_map, issuer_list_spc, issuer_list_secretsync, file_name, secret_name, expected_secret_sync",
    [
        (
            {
                "resources": None,
                "resource sync rules": None,
                "custom locations": None,
                "extensions": None,
                "meta": {
                    "expected_total": 0,
                },
            },
            {},
            {},
            "/fake/path/certificate.crt",
            None,
            {},
        ),
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [_generate_ops_resource()],
                "custom locations": [_generate_ops_resource()],
                "extensions": [_generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
            ),
            "/fake/path/certificate.der",
            "new-secret",
            get_mock_secretsync_record(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects="new-secret",
            ),
        ),
    ],
)
def test_issuer_add(
    mocker,
    mocked_cmd,
    mocked_sleep: Mock,
    expected_resources_map,
    issuer_list_spc,
    issuer_list_secretsync,
    file_name,
    file_content,
    secret_name,
    expected_secret_sync,
    mocked_responses: responses,
):

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.read_file_content",
        return_value=file_content,
    )
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    if expected_resources_map["resources"]:
        # get default spc
        mocked_responses.add(
            method=responses.GET,
            url=get_spc_endpoint(spc_name="default-spc", resource_group_name=rg_name),
            json=expected_resources_map["resources"][0],
            status=200,
            content_type="application/json",
        )

    if issuer_list_spc:
        # get secrets
        mocked_responses.add(
            method=responses.GET,
            url=get_secret_endpoint(keyvault_name="mock-keyvault"),
            json={
                "value": [
                    {
                        "id": "https://mock-keyvault.vault.azure.net/secrets/mock-secret",
                    }
                ]
            },
            status=200,
            content_type="application/json",
        )

        # set secret
        mocked_responses.add(
            method=responses.PUT,
            url=get_secret_endpoint(keyvault_name="mock-keyvault", secret_name=secret_name),
            json={},
            status=200,
            content_type="application/json",
        )

        # get opcua spc
        mocked_responses.add(
            method=responses.GET,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
            json=issuer_list_spc,
            status=200,
            content_type="application/json",
        )

        # set opcua spc
        mocked_responses.add(
            method=responses.PUT,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
            json={},
            status=200,
            content_type="application/json",
        )

        # get opcua secretsync
        mocked_responses.add(
            method=responses.GET,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=issuer_list_secretsync,
            status=200,
            content_type="application/json",
        )

        # set opcua secretsync
        mocked_responses.add(
            method=responses.PUT,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=expected_secret_sync,
            status=200,
            content_type="application/json",
        )

    result = None

    try:
        result = add_connector_opcua_issuer(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file=file_name,
            secret_name=secret_name,
        )
    except Exception:
        # TODO: Add more assertions
        if not expected_resources_map["custom locations"]:
            assert (
                mocked_logger.error.call_args[0][0] == f"Secret sync is not enabled for the instance {instance_name}."
                "Please enable secret sync before adding certificate."
            )
            return

    if result:
        assert result == expected_secret_sync


@pytest.mark.parametrize("file_content", [b"\x00\x01\x02\x03"])
@pytest.mark.parametrize(
    "expected_resources_map, client_app_spc, client_app_secretsync, public_file_name, private_file_name, expected_secret_sync",
    [
        (
            {
                "resources": None,
                "resource sync rules": None,
                "custom locations": None,
                "extension": None,
                "meta": {
                    "expected_total": 0,
                },
            },
            {},
            {},
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            {},
        ),
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [_generate_ops_resource()],
                "custom locations": [_generate_ops_resource()],
                "extension": {
                    IOT_OPS_EXTENSION_TYPE: {"id": "aio-ext-id", "name": "aio-ext-name","properties": {}}
                },
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name="mock-rg"
            ),
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects="new-secret",
            ),
        ),
    ],
)
def test_client_add(
    mocker,
    mocked_cmd,
    mocked_sleep: Mock,
    mocked_logger: Mock,
    expected_resources_map,
    client_app_spc,
    client_app_secretsync,
    public_file_name,
    private_file_name,
    file_content,
    expected_secret_sync,
    mocked_resource_map,
    mocked_responses: responses,
):
    _assemble_resource_map_mock(
        resource_map_mock=mocked_resource_map,
        extension=expected_resources_map["extension"],
        custom_locations=expected_resources_map["custom locations"],
        resources=expected_resources_map["resources"],
    )
    mocked_get_resource_client: Mock = mocker.patch(
        "azext_edge.edge.util.queryable.get_resource_client",
    )
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.read_file_content",
        return_value=file_content,
    )
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    if expected_resources_map["resources"]:
        # get default spc
        mocked_responses.add(
            method=responses.GET,
            url=get_spc_endpoint(spc_name="default-spc", resource_group_name=rg_name),
            json=expected_resources_map["resources"][0],
            status=200,
            content_type="application/json",
        )

    if client_app_spc:
        # get secrets
        mocked_responses.add(
            method=responses.GET,
            url=get_secret_endpoint(keyvault_name="mock-keyvault"),
            json={
                "value": [
                    {
                        "id": "https://mock-keyvault.vault.azure.net/secrets/mock-secret",
                    }
                ]
            },
            status=200,
            content_type="application/json",
        )

        # set secret
        mocked_responses.add(
            method=responses.PUT,
            url=get_secret_endpoint(keyvault_name="mock-keyvault", secret_name="certificate-der"),
            json={},
            status=200,
            content_type="application/json",
        )

        # set secret
        mocked_responses.add(
            method=responses.PUT,
            url=get_secret_endpoint(keyvault_name="mock-keyvault", secret_name="certificate-pem"),
            json={},
            status=200,
            content_type="application/json",
        )

        # get opcua spc
        mocked_responses.add(
            method=responses.GET,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
            json=client_app_spc,
            status=200,
            content_type="application/json",
        )

        # set opcua spc
        mocked_responses.add(
            method=responses.PUT,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
            json={},
            status=200,
            content_type="application/json",
        )

        # get opcua secretsync
        mocked_responses.add(
            method=responses.GET,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=client_app_secretsync,
            status=200,
            content_type="application/json",
        )

        # set opcua secretsync
        mocked_responses.add(
            method=responses.PUT,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=expected_secret_sync,
            status=200,
            content_type="application/json",
        )

    result = None

    try:
        result = add_connector_opcua_client(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            public_key_file=public_file_name,
            private_key_file=private_file_name,
            application_uri="uri",
            subject_name="subjectname",
        )
    except Exception:
        if not expected_resources_map["custom locations"]:
            assert (
                mocked_logger.error.call_args[0][0] == f"Secret sync is not enabled for the instance {instance_name}."
                "Please enable secret sync before adding certificate."
            )
            return

    if result:
        mocked_resource_map().connected_cluster.get_extensions_by_type.assert_called_once_with("microsoft.iotoperations")
        mocked_resource_map().connected_cluster.update_aio_extension.assert_called_once_with(
            extension_name=expected_resources_map["extension"][IOT_OPS_EXTENSION_TYPE]["name"],
            properties={
                "configurationSettings": {
                    "connectors.values.securityPki.applicationCert": OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                    "connectors.values.securityPki.subjectName": "subjectname",
                    "connectors.values.securityPki.applicationUri": "uri"
                }
            }
        )