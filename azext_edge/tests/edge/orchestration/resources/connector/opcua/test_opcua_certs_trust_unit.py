# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from unittest.mock import Mock
from azext_edge.edge.providers.orchestration.resources.instances import SECRET_SYNC_RESOURCE_TYPE, SPC_RESOURCE_TYPE
import pytest

import responses
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from azext_edge.edge.commands_connector import (
    add_connector_opcua_trust,
    remove_connector_opcua_trust,
    show_connector_opcua_trust,
)
from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_OPS
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_SPC_NAME,
    OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
)
from azext_edge.tests.edge.orchestration.resources.connector.opcua.conftest import (
    assemble_resource_map_mock,
    build_mock_cert,
    generate_ssc_object_string,
    get_mock_spc_record,
    get_mock_secretsync_record,
    get_secret_endpoint,
    get_secretsync_endpoint,
    get_spc_endpoint,
    setup_mock_common_responses,
)
from azext_edge.tests.generators import generate_random_string


@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync, file_name, secret_name, expected_secret_sync",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
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
    mocked_cl_resources: Mock,
    mocked_logger: Mock,
    mocked_read_file_content: Mock,
    mocked_decode_certificate: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    trust_list_spc: dict,
    trust_list_secretsync: dict,
    file_name: str,
    secret_name: str,
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
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_cl_resources.return_value = expected_resources_map["resources"]
    mocked_read_file_content.return_value = file_content

    if expected_resources_map["resources"]:
        mocked_instance.get_default_spc.return_value = expected_resources_map["resources"][0]

    if trust_list_spc:
        setup_mock_common_responses(
            mocked_responses=mocked_responses,
            spc=trust_list_spc,
            secretsync=trust_list_secretsync,
            opcua_secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            rg_name=rg_name,
            secret_name=secret_name,
            spc_name="default-spc",
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


def test_trust_add_opcua_disabled(
    mocked_cmd,
    mocked_instance: Mock,
):
    """Verify trust_add raises ValidationError when opcua.mode is Disabled."""
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    mocked_instance.show.return_value = {
        "extendedLocation": {"name": "mock-cl", "type": "CustomLocations"},
        "location": "eastus",
        "properties": {"features": {"opcua": {"mode": "Disabled"}}},
    }

    with pytest.raises(ValidationError) as exc_info:
        add_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file="/fake/path/certificate.der",
        )

    exc_str = str(exc_info.value)
    assert "OPC UA connector is disabled" in exc_str
    assert instance_name in exc_str
    assert "az iot ops update" in exc_str
    assert "opcua.mode=Stable" in exc_str


@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync,"
    "file_name, secret_name, mocked_cert, expected_error_type, expected_error_text",
    [
        # invalid secret name
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
            ),
            "/fake/path/certificate.der",
            "mock_secret",
            [build_mock_cert()],
            InvalidArgumentValueError,
            "Secret name mock_secret is invalid. Secret name must be alphanumeric and can contain hyphens. "
            "Please provide a valid secret name via --secret-name.",
        ),
        # expired certificate
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(spc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=["mock-secret"],
            ),
            "/fake/path/certificate.der",
            "new-secret",
            [build_mock_cert(expired=True)],
            InvalidArgumentValueError,
            "Certificate in file 'certificate.der' is expired. Please provide a valid certificate.",
        ),
        # more than one certificate in .crt file
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(spc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=["mock-secret"],
            ),
            "/fake/path/certificate.crt",
            "new-secret",
            [build_mock_cert(), build_mock_cert()],
            InvalidArgumentValueError,
            "Multiple certificates detected in file 'certificate.crt' in PEM format. "
            "Please provide a file with only one PEM certificate.",
        ),
    ],
)
def test_trust_add_content_error(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_read_file_content: Mock,
    mocked_decode_certificate: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    trust_list_spc: dict,
    trust_list_secretsync: dict,
    file_name: str,
    secret_name: str,
    mocked_cert: list,
    mocked_instance: Mock,
    expected_error_type: Exception,
    expected_error_text: str,
    mocked_responses: responses,
):
    file_content = b"\x00\x01\x02\x03"
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    mocked_cl_resources.return_value = expected_resources_map["resources"]
    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        resources=expected_resources_map["resources"],
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_read_file_content.return_value = file_content
    mocked_decode_certificate.return_value = mocked_cert

    if expected_resources_map["resources"]:
        # get default spc
        mocked_instance.get_default_spc.return_value = expected_resources_map["resources"][0]

    if trust_list_spc and not ("expired" in expected_error_text) and not (
        "PEM" in expected_error_text
    ):

        setup_mock_common_responses(
            mocked_responses=mocked_responses,
            spc=trust_list_spc,
            secretsync=trust_list_secretsync,
            opcua_secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            rg_name=rg_name,
            secret_name=secret_name,
        )

    with pytest.raises(expected_error_type) as e:
        add_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file=file_name,
            secret_name=secret_name,
            overwrite_secret=True,
        )
    assert expected_error_text in e.value.args[0]


@pytest.mark.parametrize(
    "expected_resources_map, file_name, expected_error_type, expected_error_text",
    [
        # invalid format for .der file
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            "/fake/path/certificate.der",
            InvalidArgumentValueError,
            "Failed to decode certificate data. Ensure the data is in DER format. Error: error parsing "
            "asn1 value: ParseError { kind: UnexpectedTag { actual: Tag { value: 0, constructed: false, "
            "class: Universal } } }",
        ),
        # invalid format for .crt file
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            "/fake/path/certificate.crt",
            InvalidArgumentValueError,
            "Failed to decode certificate data. Ensure the data is in PEM format. Error: Unable to load "
            "PEM file. See https://cryptography.io/en/latest/faq/#why-can-t-i-import-my-pem-file for more "
            "details. MalformedFraming",
        ),
    ],
)
def test_trust_add_format_error(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_read_file_content: Mock,
    mocked_sleep: Mock,
    mocked_instance: Mock,
    expected_resources_map: dict,
    file_name: str,
    expected_error_type: Exception,
    expected_error_text: str,
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
    mocked_cl_resources.return_value = expected_resources_map["resources"]
    mocked_read_file_content.return_value = file_content

    if expected_resources_map["resources"]:
        # get default spc
        mocked_instance.get_default_spc.return_value = expected_resources_map["resources"][0]

    with pytest.raises(expected_error_type) as e:
        add_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
            file=file_name,
            secret_name="new-secret",
            overwrite_secret=True,
        )
    assert expected_error_text in e.value.args[0]


@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync,"
    "certificate_names, expected_secret_sync, include_secrets",
    [
        (
            {
                "resources": [
                    get_mock_spc_record(
                        spc_name="default-spc",
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert-der"]),
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
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(
                spc_name="default-spc",
                resource_group_name="mock-rg",
                objects=generate_ssc_object_string(["cert-der"]),
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
            False,
        ),
        (
            {
                "resources": [
                    get_mock_spc_record(
                        spc_name="default-spc",
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert-der", "cert2-der"]),
                    ),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {
                                "sourcePath": "cert-der",
                                "targetKey": "cert.der"
                            },
                            {
                                "sourcePath": "cert2-der",
                                "targetKey": "cert2.der"
                            },
                        ],
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(
                spc_name="default-spc",
                resource_group_name="mock-rg",
                objects=generate_ssc_object_string(["cert-der", "cert2-der"]),
            ),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "sourcePath": "cert-der",
                        "targetKey": "cert.der"
                    },
                    {
                        "sourcePath": "cert2-der",
                        "targetKey": "cert2.der"
                    },
                ],
            ),
            ["cert.der"],
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "sourcePath": "cert2-der",
                        "targetKey": "cert2.der"
                    },
                ],
            ),
            True,
        ),
        # warning no keyvault secret found
        (
            {
                "resources": [
                    get_mock_spc_record(
                        spc_name="default-spc",
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert3-der"]),
                    ),
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                        resource_group_name="mock-rg",
                        objects=[
                            {
                                "sourcePath": "cert3-der",
                                "targetKey": "cert3.der"
                            },
                        ],
                    ),
                ],
                "extension": {EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
            },
            get_mock_spc_record(
                spc_name="default-spc",
                resource_group_name="mock-rg",
                objects=generate_ssc_object_string(["cert3-der"]),
            ),
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name="mock-rg",
                objects=[
                    {
                        "sourcePath": "cert3-der",
                        "targetKey": "cert3.der"
                    },
                ],
            ),
            ["cert3.der"],
            None,
            False,
        ),
    ],
)
def test_trust_remove(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    mocked_instance: Mock,
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
    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension=expected_resources_map["extension"],
        resources=expected_resources_map["resources"],
        ssc=trust_list_secretsync,
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_cl_resources.return_value = expected_resources_map["resources"]

    mocked_instance.get_default_spc.return_value = expected_resources_map["resources"][0]

    mapping = trust_list_secretsync.get("properties", {}).get("objectSecretMapping", [])
    if len(mapping) == 1:
        # delete opcua secretsync
        mocked_responses.add(
            method=responses.DELETE,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name=rg_name,
            ),
            status=204,
        )
    else:
        # set opcua secretsync
        mocked_responses.add(
            method=responses.PUT,
            url=get_secretsync_endpoint(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
                resource_group_name=rg_name,
            ),
            json=expected_secret_sync,
            status=200,
            content_type="application/json",
        )

    # set opcua spc
    mocked_responses.add(
        method=responses.PUT,
        url=get_spc_endpoint(spc_name="default-spc", resource_group_name=rg_name),
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

        if "cert3.der" not in certificate_names:
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

    result = remove_connector_opcua_trust(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
        certificate_names=certificate_names,
        confirm_yes=True,
        force=True,
        include_secrets=include_secrets,
    )

    if "cert3.der" in certificate_names and include_secrets:
        assert (
            mocked_logger.warning.call_args[0][0] == "Secret cert3-der "
            "not found in keyvault mock-keyvault. Skipping removal..."
        )

    assert result == expected_secret_sync


@pytest.mark.parametrize(
    "expected_resources_map, trust_list_spc, trust_list_secretsync,"
    "certificate_names, include_secrets, expected_error_type, expected_error_text",
    [
        # no available certificate names
        (
            {
                "resources": [
                    get_mock_secretsync_record(
                        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
                    ),
                ],
            },
            {},
            get_mock_secretsync_record(
                secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME, resource_group_name="mock-rg"
            ),
            ["thisshouldnotwork"],
            False,
            InvalidArgumentValueError,
            "Please provide valid certificate name(s) to remove.",
        ),
    ],
)
def test_trust_remove_error(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_sleep: Mock,
    expected_resources_map: dict,
    trust_list_spc: dict,
    trust_list_secretsync: dict,
    certificate_names: list,
    include_secrets: bool,
    expected_error_type: Exception,
    expected_error_text: str,
    mocked_instance: Mock,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension={EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
        resources=expected_resources_map["resources"],
        ssc=trust_list_secretsync,
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_cl_resources.return_value = expected_resources_map["resources"]

    if trust_list_spc:
        # get opcua spc
        mocked_instance.get_default_spc.return_value = expected_resources_map["resources"][0]

    with pytest.raises(expected_error_type) as e:
        remove_connector_opcua_trust(
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
                        spc_name="default-spc",
                        resource_group_name="mock-rg",
                        objects=generate_ssc_object_string(["cert-der"]),
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
    mocked_cl_resources: Mock,
    mocked_sleep: Mock,
    mocked_instance: Mock,
    expected_resources_map: dict,
    expected_secretsync: dict,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension={EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
        resources=expected_resources_map["resources"],
        ssc=expected_secretsync,
    )
    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_cl_resources.return_value = expected_resources_map["resources"]

    result = show_connector_opcua_trust(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group=rg_name,
    )
    assert result == expected_secretsync


@pytest.mark.parametrize(
    "expected_resources_map, expected_error",
    [
        # only spc
        (
            {
                "resources": [
                    get_mock_spc_record(spc_name="default-spc", resource_group_name="mock-rg"),
                ],
            },
            "Secretsync resource aio-opc-ua-broker-trust-list not found.",
        ),
    ],
)
def test_trust_show_error(
    mocker,
    mocked_cmd,
    mocked_cl_resources: Mock,
    mocked_sleep: Mock,
    mocked_instance: Mock,
    expected_resources_map: dict,
    expected_error: str,
):
    instance_name = generate_random_string()
    rg_name = "mock-rg"
    assemble_resource_map_mock(
        resource_map_mock=mocked_instance.get_resource_map,
        extension={EXTENSION_TYPE_OPS: {"id": "aio-ext-id", "name": "aio-ext-name", "properties": {}}},
        resources=expected_resources_map["resources"],
    )
    mocked_instance.get_resource_map().connected_cluster.get_cl_resources_by_type.return_value = {
        SPC_RESOURCE_TYPE: expected_resources_map["resources"],
        SECRET_SYNC_RESOURCE_TYPE: [{}],
    }

    mocked_instance.find_existing_resources.return_value = expected_resources_map["resources"]
    mocked_cl_resources.return_value = expected_resources_map["resources"]

    with pytest.raises(Exception) as e:
        show_connector_opcua_trust(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group=rg_name,
        )
    assert e.value.args[0] == expected_error


def test_trust_add_accepts_expiration_parameter(mocker):
    """Test that the trust add command accepts and passes through the expiration_date parameter."""
    from azext_edge.edge.commands_connector import add_connector_opcua_trust

    # Mock the OpcUACerts class
    mock_opcua_certs = mocker.patch('azext_edge.edge.commands_connector.OpcUACerts')
    mock_instance = mock_opcua_certs.return_value
    mock_instance.trust_add.return_value = {"status": "success"}

    # Test with expiration_date parameter
    expiration_date = "2026-12-31T23:59:59Z"
    add_connector_opcua_trust(
        cmd=mocker.MagicMock(),
        instance_name="test-instance",
        resource_group="test-rg",
        file="/fake/cert.der",
        expiration_date=expiration_date,
    )

    # Verify trust_add was called with expiration_date
    mock_instance.trust_add.assert_called_once()
    call_kwargs = mock_instance.trust_add.call_args[1]
    assert 'expiration_date' in call_kwargs, "expiration_date parameter should be passed to trust_add"
    assert call_kwargs['expiration_date'] == expiration_date, "expiration_date value should match"

    # Test without expiration_date parameter (should default to None)
    mock_instance.trust_add.reset_mock()
    add_connector_opcua_trust(
        cmd=mocker.MagicMock(),
        instance_name="test-instance",
        resource_group="test-rg",
        file="/fake/cert.der",
    )

    call_kwargs = mock_instance.trust_add.call_args[1]
    assert 'expiration_date' in call_kwargs, "expiration_date parameter should be passed to trust_add"
    assert call_kwargs['expiration_date'] is None, "expiration_date should be None when not provided"
