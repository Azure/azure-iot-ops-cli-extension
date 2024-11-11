# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from unittest.mock import Mock
import pytest

import responses
from azext_edge.edge.commands_connector import add_connector_opcua_trust, remove_connector_opcua_trust, show_connector_opcua_trust
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_SPC_NAME,
    OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
)
from azext_edge.tests.edge.orchestration.resources.connector.opcua.conftest import (
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
    "expected_resources_map, trust_list_spc, trust_list_secretsync, file_name, secret_name, expected_secret_sync",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_spc_record(spc_name=OPCUA_SPC_NAME, resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
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
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    trust_list_spc: dict,
    trust_list_secretsync: dict,
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

    if trust_list_spc:
        setup_mock_common_responses(
            mocked_responses=mocked_responses,
            spc=trust_list_spc,
            secretsync=trust_list_secretsync,
            opcua_secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            rg_name=rg_name,
            secret_name=secret_name,
        )

        matched_target_key = False
        mapping = trust_list_secretsync["properties"]["objectSecretMapping"]

        if mapping:
            matched_target_key = mapping[0]["targetKey"] == os.path.basename(file_name)

        if not matched_target_key:
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

    result = add_connector_opcua_trust(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
        file=file_name,
        secret_name=secret_name,
        overwrite_secret=True,
    )

    if result:
        if not trust_list_spc:
            assert (
                mocked_logger.warning.call_args[0][0] == f"Azure Key Vault Secret Provider Class {OPCUA_SPC_NAME} "
                "not found, creating new one..."
            )
            return

        if not trust_list_secretsync:
            assert (
                mocked_logger.warning.call_args[0][0] == f"Secret Sync {OPCUA_TRUST_LIST_SECRET_SYNC_NAME} "
                "not found, creating new one..."
            )
            return
        assert result == expected_secret_sync


@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync, file_name, secret_name, expected_error",
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
        # invalid secret name
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
                "meta": {
                    "expected_total": 4,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(spc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
            ),
            "/fake/path/certificate.der",
            "mock_secret",
            "Secret name mock_secret is invalid. Secret name must be alphanumeric and can contain hyphens. "
            "Please provide a valid secret name via --secret-name.",
        ),
    ],
)
def test_trust_add_error(
    mocker,
    mocked_cmd,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    trust_list_spc: dict,
    trust_list_secretsync: dict,
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

    if trust_list_spc:

        setup_mock_common_responses(
            mocked_responses=mocked_responses,
            spc=trust_list_spc,
            secretsync=trust_list_secretsync,
            opcua_secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            rg_name=rg_name,
            secret_name=secret_name,
        )

    with pytest.raises(Exception) as e:
        add_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file=file_name,
            secret_name=secret_name,
            overwrite_secret=True,
        )
    assert expected_error in e.value.args[0]


@pytest.mark.parametrize("include_secrets", [False, True])
@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync, certificate_names, expected_secret_sync",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(
                        spc_name=OPCUA_SPC_NAME,
                        resource_group_name="mock-rg",
                        objects="array:\n    - |\n      objectEncoding: hex\n      objectName: cert-der\n      objectType: secret\n",
                    ),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {
                                "sourcePath": "cert-der",
                                "targetKey": "cert.der"
                            },
                        ],
                    ),
                ],
                "resource sync rules": [generate_ops_resource()],
                "custom locations": [generate_ops_resource()],
                "extensions": [generate_ops_resource()],
                "meta": {
                    "expected_total": 2,
                    "resource_batches": 1,
                },
            },
            get_mock_spc_record(
                spc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects="array:\n    - |\n      objectEncoding: hex\n      objectName: cert-der\n      objectType: secret\n",
            ),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "sourcePath": "cert-der",
                        "targetKey": "cert.der"
                    },
                ],
            ),
            ["cert.der"],
            None,
        ),
    ],
)
def test_trust_remove(
    mocker,
    mocked_cmd,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    trust_list_spc: dict,
    trust_list_secretsync: dict,
    certificate_names: list,
    include_secrets: bool,
    expected_secret_sync: dict,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )

    # get opcua secretsync
    mocked_responses.add(
        method=responses.GET,
        url=get_secretsync_endpoint(
            secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            resource_group_name=rg_name
        ),
        json=trust_list_secretsync,
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

    # delete opcua secretsync
    mocked_responses.add(
        method=responses.DELETE,
        url=get_secretsync_endpoint(
            secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name=rg_name
        ),
        json={},
        status=204,
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

        # purge secret
        mocked_responses.add(
            method=responses.DELETE,
            url=get_secret_endpoint(
                keyvault_name="mock-keyvault",
                secret_name="cert-der",
                deleted=True,
            ),
            json={},
            status=204,
            content_type="application/json",
        )

    result = remove_connector_opcua_trust(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
        certificate_names=certificate_names,
        confirm_yes=True,
        force=True,
        include_secrets=include_secrets,
    )

    if result:
        assert result == expected_secret_sync


@pytest.mark.parametrize(
    "expected_resources_map, expected_secretsync",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(
                        spc_name=OPCUA_SPC_NAME,
                        resource_group_name="mock-rg",
                        objects="array:\n    - |\n      objectEncoding: hex\n      objectName: cert-der\n      objectType: secret\n",
                    ),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {
                                "sourcePath": "cert-der",
                                "targetKey": "cert.der"
                            },
                        ],
                    ),
                ],
            },
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "sourcePath": "cert-der",
                        "targetKey": "cert.der"
                    },
                ],
            ),
        ),
    ],
)
def test_trust_show(
    mocker,
    mocked_cmd,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    expected_secretsync: dict,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )

    # get opcua secretsync
    mocked_responses.add(
        method=responses.GET,
        url=get_secretsync_endpoint(
            secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            resource_group_name=rg_name
        ),
        json=expected_secretsync,
        status=200,
        content_type="application/json",
    )

    result = show_connector_opcua_trust(
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
            "Secretsync resource aio-opc-ua-broker-trust-list not found.",
        ),
    ],
)
def test_trust_show_error(
    mocker,
    mocked_cmd,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    expected_error: str,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"

    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector.opcua.certs.OpcUACerts._get_cl_resources",
        return_value=expected_resources_map["resources"],
    )

    with pytest.raises(Exception) as e:
        show_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
        )
    assert e.value.args[0] == expected_error
