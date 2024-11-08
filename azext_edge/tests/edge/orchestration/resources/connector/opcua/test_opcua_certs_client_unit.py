# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock
import pytest

import responses
from azext_edge.edge.commands_connector import (
    add_connector_opcua_client,
)
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    OPCUA_SPC_NAME,
)
from azext_edge.edge.providers.orchestration.work import IOT_OPS_EXTENSION_TYPE
from .conftest import (
    assemble_resource_map_mock,
    get_mock_spc_record,
    get_mock_secretsync_record,
    get_secret_endpoint,
    get_secretsync_endpoint,
    get_spc_endpoint,
)
from azext_edge.tests.generators import generate_random_string
from azext_edge.tests.helpers import generate_ops_resource


@pytest.mark.parametrize(
    "expected_resources_map, client_app_spc, client_app_secretsync,"
    "public_file_name, private_file_name, expected_secret_sync",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extension": {IOT_OPS_EXTENSION_TYPE: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
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
    expected_resources_map: dict,
    client_app_spc: dict,
    client_app_secretsync: dict,
    public_file_name: str,
    private_file_name: str,
    expected_secret_sync: dict,
    mocked_instance: Mock,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        custom_locations=expected_resources_map["custom locations"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_get_resource_client: Mock = mocker.patch(
        "azext_edge.edge.util.queryable.get_resource_client",
    )
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.read_file_content",
        return_value=file_content,
    )

    if expected_resources_map["resources"]:
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

        # set opcua spc
        mocked_responses.add(
            method=responses.PUT,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
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

    result = add_connector_opcua_client(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
        public_key_file=public_file_name,
        private_key_file=private_file_name,
        application_uri="uri",
        subject_name="subjectname",
        overwrite_secret=True,
    )

    assert (
        mocked_logger.warning.call_args[0][0] == "Please ensure the certificate must be added "
        "to the issuers list if it was issued by a CA."
    )

    if result:
        if not client_app_spc:
            assert (
                mocked_logger.warning.call_args[0][0] == f"Azure Key Vault Secret Provider Class {OPCUA_SPC_NAME} "
                "not found, creating new one..."
            )

        if not client_app_secretsync:
            assert (
                mocked_logger.warning.call_args[0][0] == f"Secret Sync {OPCUA_CLIENT_CERT_SECRET_SYNC_NAME} "
                "not found, creating new one..."
            )
        mocked_instance.get_resource_map().connected_cluster.get_extensions_by_type.assert_called_once_with(
            "microsoft.iotoperations"
        )
        mocked_instance.get_resource_map().connected_cluster.update_aio_extension.assert_called_once_with(
            extension_name=expected_resources_map["extension"][IOT_OPS_EXTENSION_TYPE]["name"],
            properties={
                "configurationSettings": {
                    "connectors.values.securityPki.applicationCert": OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                    "connectors.values.securityPki.subjectName": "subjectname",
                    "connectors.values.securityPki.applicationUri": "uri",
                }
            },
        )


@pytest.mark.parametrize(
    "expected_resources_map, client_app_spc, client_app_secretsync,"
    "public_file_name, private_file_name, expected_error",
    [
        # no default spc
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
            "Please enable secret sync before adding certificate.",
        ),
        # no aio extension
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extension": {},
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
            "IoT Operations extension not found.",
        ),
        # file names not matching
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extension": {IOT_OPS_EXTENSION_TYPE: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            {},
            {},
            "/fake/path/pubkey.der",
            "/fake/path/prikey.pem",
            "Public key file name pubkey and private key file name prikey must match.",
        ),
    ],
)
def test_client_add_errors(
    mocker,
    mocked_cmd,
    mocked_sleep: Mock,
    mocked_logger: Mock,
    expected_resources_map: dict,
    client_app_spc: dict,
    client_app_secretsync: dict,
    public_file_name: str,
    private_file_name: str,
    expected_error: str,
    mocked_instance: Mock,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = "mock-instance"
    rg_name = "mock-rg"

    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        custom_locations=expected_resources_map["custom locations"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_get_resource_client: Mock = mocker.patch(
        "azext_edge.edge.util.queryable.get_resource_client",
    )
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.read_file_content",
        return_value=file_content,
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

        # set opcua spc
        mocked_responses.add(
            method=responses.PUT,
            url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
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

        # set opcua secretsync
        mocked_responses.add(
            method=responses.PUT,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            json=client_app_secretsync,
            status=200,
            content_type="application/json",
        )

    with pytest.raises(Exception) as e:
        add_connector_opcua_client(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            public_key_file=public_file_name,
            private_key_file=private_file_name,
            application_uri="uri",
            subject_name="subjectname",
            overwrite_secret=True,
        )

    assert expected_error in e.value.args[0]
