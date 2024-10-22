# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from azure.core.exceptions import ResourceNotFoundError
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
    setup_mock_common_responses,
)
from azext_edge.tests.generators import generate_random_string
from azext_edge.tests.helpers import generate_ops_resource


@pytest.mark.parametrize(
    "expected_resources_map, client_app_spc, client_app_secretsync,"
    "public_file_name, private_file_name, expected_secret_sync",
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
        # no aio extension
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
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
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects="new-secret",
            ),
        ),
        # no opcua spc
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
            "/fake/path/certificate.der",
            "/fake/path/certificate.pem",
            get_mock_secretsync_record(
                secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects="new-secret",
            ),
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
    expected_secret_sync,
    mocked_resource_map,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    assemble_resource_map_mock(
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
        setup_mock_common_responses(
            mocked_responses=mocked_responses,
            spc=client_app_spc,
            secretsync=client_app_secretsync,
            opcua_secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            rg_name=rg_name,
            secret_name="certificate-der",
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
    except Exception as e:
        if isinstance(e, ValueError):
            private_file_name = os.path.basename(private_file_name).replace(".pem", "")
            public_file_name = os.path.basename(public_file_name).replace(".der", "")
            if private_file_name != public_file_name:
                assert e.args[0] == "Public key file pubkey and private key file prikey must match."
                return
        elif isinstance(e, ResourceNotFoundError):
            if not expected_resources_map["custom locations"]:
                assert "Please enable secret sync before adding certificate." in e.args[0]
                return
            if not expected_resources_map["extension"]:
                assert e.args[0] == "IoT Operations extension not found."
                return

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
        mocked_resource_map().connected_cluster.get_extensions_by_type.assert_called_once_with(
            "microsoft.iotoperations"
        )
        mocked_resource_map().connected_cluster.update_aio_extension.assert_called_once_with(
            extension_name=expected_resources_map["extension"][IOT_OPS_EXTENSION_TYPE]["name"],
            properties={
                "configurationSettings": {
                    "connectors.values.securityPki.applicationCert": OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
                    "connectors.values.securityPki.subjectName": "subjectname",
                    "connectors.values.securityPki.applicationUri": "uri",
                }
            },
        )
