# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock
import pytest

import responses
from azure.core.exceptions import ResourceNotFoundError
from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.commands_connector import (
    add_connector_opcua_client,
    remove_connector_opcua_client,
    show_connector_opcua_client,
)
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    OPCUA_SPC_NAME,
)
from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_OPS
from .conftest import (
    assemble_resource_map_mock,
    generate_ssc_object_string,
    get_mock_spc_record,
    get_mock_secretsync_record,
    get_secret_endpoint,
    get_secretsync_endpoint,
    get_spc_endpoint,
    build_mock_cert,
)
from azext_edge.tests.generators import generate_random_string


# TODO: Resturcture parameters into dict
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
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
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
    mocked_read_file_content: Mock,
    mocked_load_x509_cert: Mock,
    mocked_sleep: Mock,
    mocked_logger: Mock,
    expected_resources_map: dict,
    client_app_spc: dict,
    client_app_secretsync: dict,
    public_file_name: str,
    private_file_name: str,
    expected_secret_sync: dict,
    mocked_get_resource_client: Mock,
    mocked_instance: Mock,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}
    mocked_read_file_content.return_value = file_content

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

    warnings = [call[0][0] for call in mocked_logger.warning.call_args_list]

    assert (
        "If this certificate was issued by a CA, then please "
        "ensure that the CA certificate is added to issuer list." in warnings
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
            extension_name=expected_resources_map["extension"][EXTENSION_TYPE_OPS]["name"],
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
    "public_file_name, private_file_name, subject_name, uri, cert_subject_name,"
    "cert_uri, expected_error_type, expected_error_text",
    [
        # no default spc
        (
            {
                "resources": None,
                "extension": None,
            },
            {},
            {},
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            "subjectname",
            "uri",
            "subjectname",
            "uri",
            ResourceNotFoundError,
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
                "extension": {},
            },
            get_mock_spc_record(spc_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name="mock-rg"
            ),
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            "subjectname",
            "uri",
            "subjectname",
            "uri",
            ResourceNotFoundError,
            "IoT Operations extension not found.",
        ),
        # file names not matching
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            {},
            {},
            "/fake/path/pubkey.der",
            "/fake/path/prikey.pem",
            "subjectname",
            "uri",
            "subjectname",
            "uri",
            InvalidArgumentValueError,
            "Public key file name pubkey and private key file name prikey must match.",
        ),
        # subject name not found
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            {},
            {},
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            " ",
            "uri",
            " ",
            "uri",
            InvalidArgumentValueError,
            "Not able to extract subject name from the certificate. "
            "Please provide the correct subject name in certificate via --public-key-file.",
        ),
        # uri not found
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            {},
            {},
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            "subjectname",
            " ",
            "subjectname",
            " ",
            InvalidArgumentValueError,
            "Not able to extract application URI from the certificate. "
            "Please provide the correct application URI in certificate via --public-key-file.",
        ),
        # subject name provided not matching cert
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            {},
            {},
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            "subjectnamenotmatch",
            "uri",
            "subjectname",
            "uri",
            InvalidArgumentValueError,
            "Given --subject-name subjectnamenotmatch does not match certificate subject name subjectname. "
            "Please provide the correct subject name via --subject-name or correct certificate using --public-key-file."
        ),
        # uri provided not matching cert
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            {},
            {},
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            "subjectname",
            "urinotmatch",
            "subjectname",
            "uri",
            InvalidArgumentValueError,
            "Given --application-uri urinotmatch does not match certificate application URI uri. "
            "Please provide the correct application URI via --application-uri or correct certificate "
            "using --public-key-file."
        ),
    ],
)
def test_client_add_errors(
    mocker,
    mocked_cmd,
    mocked_read_file_content: Mock,
    mocked_load_x509_cert: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    client_app_spc: dict,
    client_app_secretsync: dict,
    public_file_name: str,
    private_file_name: str,
    subject_name: str,
    uri: str,
    cert_subject_name: str,
    cert_uri: str,
    expected_error_text: str,
    expected_error_type: Exception,
    mocked_get_resource_client: Mock,
    mocked_instance: Mock,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = "mock-instance"
    rg_name = "mock-rg"

    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}
    mocked_read_file_content.return_value = file_content
    mocked_load_x509_cert.return_value = build_mock_cert(subject_name=cert_subject_name, uri=cert_uri)

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

    with pytest.raises(expected_error_type) as e:
        add_connector_opcua_client(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            public_key_file=public_file_name,
            private_key_file=private_file_name,
            application_uri=uri,
            subject_name=subject_name,
            overwrite_secret=True,
        )

    assert expected_error_text in e.value.args[0]


@pytest.mark.parametrize("include_secrets", [False, True])
@pytest.mark.parametrize(
    "expected_resources_map, client_list_spc, client_list_secretsync, certificate_names, expected_secret_sync",
    [
        (
            {
                "resources": [
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {"sourcePath": "cert-der", "targetKey": "cert.der"},
                        ],
                    ),
                    get_mock_spc_record(
                        spc_name=OPCUA_SPC_NAME,
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert-der"]),
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(
                spc_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=generate_ssc_object_string(["cert-der"]),
            ),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {"sourcePath": "cert-der", "targetKey": "cert.der"},
                ],
            ),
            ["cert.der"],
            None,
        ),
        (
            {
                "resources": [
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {"sourcePath": "cert-der", "targetKey": "cert.der"},
                            {"sourcePath": "cert-pem", "targetKey": "cert.pem"},
                        ],
                    ),
                    get_mock_spc_record(
                        spc_name=OPCUA_SPC_NAME,
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert-der", "cert-pem"]),
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(
                spc_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=generate_ssc_object_string(["cert-der", "cert-pem"]),
            ),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {"sourcePath": "cert-der", "targetKey": "cert.der"},
                    {"sourcePath": "cert-pem", "targetKey": "cert.pem"},
                ],
            ),
            ["cert.der", "cert.pem"],
            None,
        ),
    ],
)
def test_client_remove(
    mocker,
    mocked_cmd,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    client_list_spc: dict,
    client_list_secretsync: dict,
    certificate_names: list,
    include_secrets: bool,
    expected_secret_sync: dict,
    mocked_get_resource_client: Mock,
    mocked_instance: Mock,
    mocked_responses: responses,
):
    instance_name = "mock-instance"
    rg_name = "mock-rg"

    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.side_effect = [
        [client_list_secretsync],
        [client_list_spc],
    ]
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}

    mapping = client_list_secretsync.get("properties", {}).get("objectSecretMapping", [])
    if len(certificate_names) < len(mapping):
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
    else:
        # delete opcua secretsync
        mocked_responses.add(
            method=responses.DELETE,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name=rg_name
            ),
            status=204,
        )

    # set opcua spc
    mocked_responses.add(
        method=responses.PUT,
        url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
        json={},
        status=200,
        content_type="application/json",
    )

    if include_secrets:
        # get secrets
        mocked_responses.add(
            method=responses.GET,
            url=get_secret_endpoint(keyvault_name="mock-keyvault"),
            json={
                "value": [
                    {
                        "id": "https://mock-keyvault.vault.azure.net/secrets/cert-der",
                    }
                ]
            },
            status=200,
            content_type="application/json",
        )

        # delete secret
        mocked_responses.add(
            method=responses.DELETE,
            url=get_secret_endpoint(keyvault_name="mock-keyvault", secret_name="cert-der"),
            status=200,
            json={},
            content_type="application/json",
        )

        # get deleted secret
        mocked_responses.add(
            method=responses.GET,
            url=get_secret_endpoint(
                keyvault_name="mock-keyvault",
                secret_name="cert-der",
                deleted=True,
            ),
            status=200,
            json={},
            content_type="application/json",
        )

        # purge secret
        mocked_responses.add(
            method=responses.DELETE,
            url=get_secret_endpoint(
                keyvault_name="mock-keyvault",
                secret_name="cert-der",
                deleted=True,
            ),
            status=204,
        )

    remove_connector_opcua_client(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
        certificate_names=certificate_names,
        confirm_yes=True,
        force=True,
        include_secrets=include_secrets,
    )

    if len(certificate_names) == len(mapping):
        mocked_instance.get_resource_map().connected_cluster.get_extensions_by_type.assert_called_once_with(
            "microsoft.iotoperations"
        )
        mocked_instance.get_resource_map().connected_cluster.update_aio_extension.assert_called_once_with(
            extension_name=expected_resources_map["extension"][EXTENSION_TYPE_OPS]["name"],
            properties={
                "configurationSettings": {
                    "connectors.values.securityPki.applicationCert": "",
                    "connectors.values.securityPki.subjectName": "",
                    "connectors.values.securityPki.applicationUri": "",
                }
            },
        )


@pytest.mark.parametrize(
    "expected_resources_map, client_list_spc, client_list_secretsync,"
    "certificate_names, include_secrets, expected_error_type, expected_error_text",
    [
        # target secretsync resource not found
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg"),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            [get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg")],
            [],
            ["cert.der"],
            False,
            ResourceNotFoundError,
            "Secretsync resource aio-opc-ua-broker-client-certificate not found.",
        ),
        # no valid certificate names
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {"sourcePath": "cert-der", "targetKey": "cert.der"},
                        ],
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            [get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg")],
            [
                get_mock_secretsync_record(
                    secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                    resource_group_name="mock-rg",
                    objects=[
                        {"sourcePath": "cert-der", "targetKey": "cert.der"},
                    ],
                )
            ],
            ["thiswontwork"],
            False,
            InvalidArgumentValueError,
            "Please provide valid certificate name(s) to remove.",
        ),
        # no target spc resource found
        (
            {
                "resources": [
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {"sourcePath": "cert-der", "targetKey": "cert.der"},
                        ],
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            [],
            [
                get_mock_secretsync_record(
                    secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                    resource_group_name="mock-rg",
                    objects=[
                        {"sourcePath": "cert-der", "targetKey": "cert.der"},
                    ],
                )
            ],
            ["cert.der"],
            False,
            ResourceNotFoundError,
            "Secret Provider Class resource opc-ua-connector not found.",
        ),
    ],
)
def test_client_remove_error(
    mocker,
    mocked_cmd,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    client_list_spc: dict,
    client_list_secretsync: dict,
    certificate_names: list,
    include_secrets: bool,
    mocked_get_resource_client: Mock,
    mocked_instance: Mock,
    expected_error_type: Exception,
    expected_error_text: str,
):
    instance_name = "mock-instance"
    rg_name = "mock-rg"

    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.side_effect = [
        client_list_secretsync,
        client_list_spc,
    ]
    mocked_get_resource_client().resources.get_by_id.return_value = {"id": "mock-id"}

    with pytest.raises(expected_error_type) as e:
        remove_connector_opcua_client(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            certificate_names=certificate_names,
            confirm_yes=True,
            force=True,
            include_secrets=include_secrets,
        )

    assert expected_error_text in e.value.args[0]


@pytest.mark.parametrize(
    "expected_resources_map, expected_secretsync",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(
                        spc_name=OPCUA_SPC_NAME,
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert-der"]),
                    ),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {"sourcePath": "cert-der", "targetKey": "cert.der"},
                        ],
                    ),
                ],
            },
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {"sourcePath": "cert-der", "targetKey": "cert.der"},
                ],
            ),
        ),
    ],
)
def test_client_show(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    expected_secretsync: dict,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    mocked_cl_resources.return_value = expected_resources_map["resources"]

    # get opcua secretsync
    mocked_responses.add(
        method=responses.GET,
        url=get_secretsync_endpoint(secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, resource_group_name=rg_name),
        json=expected_secretsync,
        status=200,
        content_type="application/json",
    )

    result = show_connector_opcua_client(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
    )
    assert result == expected_secretsync


@pytest.mark.parametrize(
    "expected_resources_map, expected_error",
    [
        (
            {
                "resources": None,
            },
            "No custom location resources found associated with the IoT Operations deployment.",
        ),
        # only spc
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg"),
                ],
            },
            "Secretsync resource aio-opc-ua-broker-client-certificate not found.",
        ),
    ],
)
def test_client_show_error(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    expected_error: str,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    mocked_cl_resources.return_value = expected_resources_map["resources"]

    with pytest.raises(Exception) as e:
        show_connector_opcua_client(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
        )
    assert e.value.args[0] == expected_error
