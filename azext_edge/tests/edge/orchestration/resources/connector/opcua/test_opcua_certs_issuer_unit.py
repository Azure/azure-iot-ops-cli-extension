# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from unittest.mock import Mock
import pytest

import responses
from azext_edge.edge.commands_connector import add_connector_opcua_issuer
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    OPCUA_SPC_NAME,
)
from azext_edge.tests.edge.orchestration.resources.connector.opcua.conftest import (
    get_mock_spc_record,
    get_mock_secretsync_record,
    get_secret_endpoint,
    get_secretsync_endpoint,
    get_spc_endpoint,
)
from azext_edge.tests.generators import generate_random_string
from azext_edge.tests.helpers import generate_ops_resource


@pytest.mark.parametrize(
    "expected_resources_map, issuer_list_spc, issuer_list_secretsync, file_name, secret_name, expected_secret_sync",
    [
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
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
        # adding .crl with corresponding .der or crt
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "sourcePath": "secret1",
                        "targetKey": "certificate.der",
                    }
                ],
            ),
            "/fake/path/certificate.crl",
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
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    issuer_list_spc: dict,
    issuer_list_secretsync: dict,
    file_name: str,
    secret_name: str,
    expected_secret_sync: dict,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )
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

        matched_names = []
        if file_name.endswith("crl") and issuer_list_secretsync:
            file_name = os.path.basename(file_name)
            possible_file_names = [file_name.replace(".crl", ".der"), file_name.replace(".crl", ".crt")]
            matched_names = [
                mapping["targetKey"]
                for mapping in issuer_list_secretsync["properties"]["objectSecretMapping"]
                if mapping["targetKey"] in possible_file_names
            ]

        if not (file_name.endswith("crl") and not matched_names):
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

            if issuer_list_spc:
                # set opcua spc
                mocked_responses.add(
                    method=responses.PUT,
                    url=get_spc_endpoint(spc_name=OPCUA_SPC_NAME, resource_group_name=rg_name),
                    json={},
                    status=200,
                    content_type="application/json",
                )

            if issuer_list_secretsync:
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

    result = add_connector_opcua_issuer(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
        file=file_name,
        secret_name=secret_name,
    )

    if result:
        if not issuer_list_spc:
            assert (
                mocked_logger.warning.call_args[0][0] == f"Azure Key Vault Secret Provider Class {OPCUA_SPC_NAME} "
                "not found, creating new one..."
            )
            return

        if not issuer_list_secretsync:
            assert (
                mocked_logger.warning.call_args[0][0] == f"Secret Sync {OPCUA_ISSUER_LIST_SECRET_SYNC_NAME} "
                "not found, creating new one..."
            )
            return
        assert result == expected_secret_sync


@pytest.mark.parametrize(
    "expected_resources_map, issuer_list_spc, issuer_list_secretsync, file_name, secret_name, expected_error",
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
            "/fake/path/certificate1.crt",
            None,
            "Please enable secret sync before adding certificate.",
        ),
        # adding .crl without corresponding .der or crt
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
            ),
            "/fake/path/certificate2.crl",
            "new-secret",
            "Cannot add .crl certificate2.crl without corresponding .crt or .der file.",
        ),
        # duplicate targetKey in objectSecretMapping
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "targetKey": "certificate3.der",
                    },
                ],
            ),
            "/fake/path/certificate3.der",
            "new-secret",
            "Cannot have duplicate targetKey in objectSecretMapping.",
        ),
        # secret existed
        (
            {
                "resources": [get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg")],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
            ),
            "/fake/path/certificate.der",
            "mock-secret",
            "Secret with name mock-secret already exists in keyvault mock-keyvault. "
            "Please provide a different name via --secret.",
        ),
    ],
)
def test_issuer_add_errors(
    mocker,
    mocked_cmd,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    issuer_list_spc: dict,
    issuer_list_secretsync: dict,
    file_name: str,
    secret_name: str,
    expected_error: str,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )
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

        if not file_name.endswith("crl"):
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

            if secret_name != "mock-secret":
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

                if not file_name.endswith("der"):
                    # set opcua secretsync
                    mocked_responses.add(
                        method=responses.PUT,
                        url=get_secretsync_endpoint(
                            secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME, resource_group_name=rg_name
                        ),
                        json={},
                        status=200,
                        content_type="application/json",
                    )

    with pytest.raises(Exception) as e:
        add_connector_opcua_issuer(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file=file_name,
            secret_name=secret_name,
        )

    assert expected_error in e.value.args[0]
