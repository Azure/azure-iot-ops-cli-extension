# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import Mock
import pytest

import responses
from cryptography import x509
from cryptography.x509.oid import NameOID
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OPCUA_SPC_NAME
from azext_edge.tests.edge.orchestration.resources.conftest import get_base_endpoint, get_mock_resource
from azext_edge.tests.generators import generate_random_string


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.logger",
    )
    yield patched


@pytest.fixture
def mocked_instance(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.Instances",
    )
    yield patched()


@pytest.fixture
def mocked_sleep(mocker):
    patched = mocker.patch("azext_edge.edge.util.az_client.sleep", return_value=None)
    yield patched


@pytest.fixture
def mocked_cl_resources(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
    )
    yield patched


@pytest.fixture
def mocked_read_file_content(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.read_file_content",
    )
    yield patched


def build_mock_cert(
    subject_name: str = "subjectname",
    uri: str = "uri",
    expired: bool = False,
    ca_cert: bool = False,
    version: str = "V1",
):
    mock_cert = Mock(spec=x509.Certificate)

    # Set up a mock subject and issuer
    mock_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, subject_name),
        ]
    )
    mock_cert.subject = mock_subject

    # Set up a mock for subject alternative names extension
    mock_san_extension = Mock(spec=x509.SubjectAlternativeName)
    mock_san_general_names = [
        x509.DNSName("www.example.com"),
        x509.UniformResourceIdentifier(uri),
    ]
    mock_san_extension.value = mock_san_general_names
    mock_cert.extensions.get_extension_for_oid.return_value = mock_san_extension

    if expired:
        # Set up a mock for not valid after
        mock_cert.not_valid_after_utc = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        # Set up a mock for not valid after
        mock_cert.not_valid_after_utc = datetime.now(timezone.utc) + timedelta(days=1)

    if ca_cert:
        # Set up a mock for basic constraints
        mock_basic_constraints = Mock(spec=x509.BasicConstraints)
        mock_value = Mock()
        mock_value.ca = True
        mock_value.path_length = None

        # assign the mock value to the correct attribute
        mock_basic_constraints.value = mock_value
        mock_cert.extensions.get_extension_for_oid.return_value = mock_basic_constraints

    # Set up a mock for version
    if version == "V1":
        mock_cert.version = x509.Version.v1
    elif version == "V3":
        mock_cert.version = x509.Version.v3

    return mock_cert


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch(
        "azext_edge.edge.util.queryable.get_resource_client",
    )
    yield patched


@pytest.fixture
def mocked_decode_certificate(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.decode_x509_files",
        return_value=[build_mock_cert()],
    )
    yield patched


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


def get_secret_endpoint(
    keyvault_name: str,
    deleted: bool = False,
    secret_name: Optional[str] = None,
) -> str:
    resource_path = "/deletedsecrets" if deleted else "/secrets"
    if secret_name:
        resource_path += f"/{secret_name}"

    return f"https://{keyvault_name}.vault.azure.net{resource_path}?api-version=7.5"


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


def get_mock_secretsync_record(secretsync_name: str, resource_group_name: str, objects: Optional[dict] = None) -> dict:
    objects = objects or []
    return get_mock_resource(
        name=secretsync_name,
        resource_path=f"/secretSyncs/{secretsync_name}",
        properties={
            "provisioningState": "Succeeded",
            "kubernetesSecretType": "Opaque",
            "secretProviderClassName": "opc-ua-connector",
            "serviceAccountName": "aio-ssc-sa",
            "objectSecretMapping": objects,
        },
        resource_group_name=resource_group_name,
        qualified_type="Microsoft.SecretSyncController/secretSyncs",
    )


def setup_mock_common_responses(
    mocked_responses: responses,
    spc: dict,
    secretsync: dict,
    opcua_secretsync_name: str,
    rg_name: str,
    secret_name: str,
):
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

    if secret_name != "mock-secret" and secret_name != "mock_secret":
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
            json=spc,
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
            url=get_secretsync_endpoint(secretsync_name=opcua_secretsync_name, resource_group_name=rg_name),
            json=secretsync,
            status=200,
            content_type="application/json",
        )


def assemble_resource_map_mock(
    resource_map_mock: Mock,
    extension: Optional[dict],
    resources: Optional[List[dict]],
):
    resource_map_mock().connected_cluster.get_extensions_by_type.return_value = extension
    resource_map_mock().connected_cluster.get_aio_resources.return_value = resources


def generate_ssc_object_string(names: List[str]):
    object_string = "array:\n"
    for name in names:
        object_string += f"    - |\n      objectEncoding: hex\n      objectName: {name}\n      objectType: secret\n"
    return object_string
