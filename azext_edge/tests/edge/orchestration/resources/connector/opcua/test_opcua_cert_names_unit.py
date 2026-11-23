# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace

import pytest
import responses
import yaml
from azure.cli.core.azclierror import AzureResponseError, InvalidArgumentValueError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge import commands_connector
from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_OPS
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    OpcUACerts,
)
from azext_edge.edge.providers.orchestration.resources.instances import SECRET_SYNC_RESOURCE_TYPE
from azext_edge.edge.util.az_client import OperationTimeoutError
from .conftest import (
    assemble_resource_map_mock,
    build_mock_cert,
    generate_ssc_object_string,
    get_mock_secretsync_record,
    get_mock_spc_record,
    get_secret_endpoint,
    get_secretsync_endpoint,
    get_spc_endpoint,
    setup_mock_common_responses,
)
from .int.helpers import certificate_sync_name


@pytest.mark.parametrize("kind,setting", [
    ("trust", "trustedCerts"), ("issuer", "issuerCerts"), ("client", "applicationCert"),
])
def test_per_instance_names_isolate_certificate_lifecycle(
    kind, setting, mocked_cmd, mocked_instance, mocked_responses,
    mocked_read_file_content, mocked_decode_certificate,
):
    mocked_read_file_content.return_value = b"\x00\x01\x02\x03"
    mocked_decode_certificate.side_effect = lambda *_args, **_kwargs: [build_mock_cert()]
    names = []
    for instance in ("instance-a", "instance-b"):
        sync_name = certificate_sync_name(instance, kind)
        names.append(sync_name)
        assert len(sync_name) <= 24
        files = ["certificate.der", "certificate.pem"] if kind == "client" else ["certificate.der"]
        record = get_mock_secretsync_record(sync_name, "mock-rg", objects=[
            {"sourcePath": name.replace(".", "-"), "targetKey": name} for name in files
        ])
        spc = get_mock_spc_record("default-spc", "mock-rg")
        extension = {"name": "aio-ext", "properties": {"configurationSettings": {"unrelated": "preserved"}}}
        assemble_resource_map_mock(
            mocked_instance.get_resource_map, {EXTENSION_TYPE_OPS: extension}, [], ssc=record,
        )
        cluster = mocked_instance.get_resource_map().connected_cluster
        cluster.connected = True
        cluster.get_cl_resources_by_type.return_value = {SECRET_SYNC_RESOURCE_TYPE: []}
        mocked_instance.get_default_spc.return_value = spc
        setup_mock_common_responses(
            mocked_responses, spc, record, sync_name, "mock-rg", "certificate-der", "default-spc",
        )
        if kind == "client":
            mocked_responses.add(
                responses.PUT, get_secret_endpoint("mock-keyvault", secret_name="certificate-pem"), json={},
            )
        order = []

        def update_reference(**kwargs):
            settings = kwargs["properties"]["configurationSettings"]
            extension["properties"]["configurationSettings"].update(settings)
            order.append("reference")
            return extension

        cluster.update_aio_extension.side_effect = update_reference

        def create_sync(request):
            body = json.loads(request.body)
            assert body["properties"]["secretProviderClassName"] == "default-spc"
            order.append("sync")
            return 200, {"Content-Type": "application/json"}, json.dumps(record)

        endpoint = get_secretsync_endpoint(sync_name, "mock-rg")
        mocked_responses.add_callback(responses.PUT, endpoint, callback=create_sync)
        common = {
            "cmd": mocked_cmd, "instance_name": instance, "resource_group": "mock-rg", "secret_sync_name": sync_name,
        }
        inputs = (
            {"public_key_file": "/fake/certificate.der", "private_key_file": "/fake/certificate.pem"}
            if kind == "client" else {"file": "/fake/certificate.der"}
        )
        result = getattr(commands_connector, f"add_connector_opcua_{kind}")(**common, **inputs)
        assert result == (extension if kind == "client" else record)
        settings = extension["properties"]["configurationSettings"]
        assert settings[f"connectors.values.securityPki.{setting}"] == sync_name
        assert settings["unrelated"] == "preserved"
        assert order == (["sync", "reference"] if kind == "client" else ["reference", "sync"])
        cluster.get_cl_resources_by_type.return_value = {SECRET_SYNC_RESOURCE_TYPE: [record]}
        shown = getattr(commands_connector, f"show_connector_opcua_{kind}")(**common)
        assert shown["name"] == sync_name
        mocked_responses.add(responses.DELETE, endpoint, status=204)
        mocked_responses.add(responses.GET, get_secretsync_endpoint("", "mock-rg"), json={"value": []})
        getattr(commands_connector, f"remove_connector_opcua_{kind}")(
            **common, certificate_names=files, confirm_yes=True,
        )
        if kind == "client":
            assert settings["connectors.values.securityPki.applicationCert"] == ""
        else:
            default = OPCUA_TRUST_LIST_SECRET_SYNC_NAME if kind == "trust" else OPCUA_ISSUER_LIST_SECRET_SYNC_NAME
            assert settings[f"connectors.values.securityPki.{setting}"] == default

    assert len(set(names)) == 2
    deleted = [call.request.url.split("?")[0].rsplit("/", 1)[-1] for call in mocked_responses.calls
               if call.request.method == "DELETE"]
    assert deleted == names


@pytest.mark.parametrize("kind,setting", [("trust", "trustedCerts"), ("issuer", "issuerCerts")])
@pytest.mark.parametrize("failure", ["http", "timeout", "rollback"])
def test_list_add_failure_handles_reference_safely(
    kind, setting, failure, mocked_cmd, mocked_instance, mocked_responses,
    mocked_read_file_content, mocked_decode_certificate, mocker, caplog,
):
    mocked_read_file_content.return_value = b"\x00\x01\x02\x03"
    mocked_decode_certificate.side_effect = lambda *_args, **_kwargs: [build_mock_cert()]
    record = get_mock_secretsync_record("new-list", "mock-rg")
    spc = get_mock_spc_record("default-spc", "mock-rg")
    key = f"connectors.values.securityPki.{setting}"
    settings = {key: "active-list", "unrelated": "preserved"}
    assemble_resource_map_mock(
        mocked_instance.get_resource_map,
        {EXTENSION_TYPE_OPS: {"name": "aio-ext", "properties": {"configurationSettings": settings}}},
        [], ssc=record,
    )
    cluster = mocked_instance.get_resource_map().connected_cluster
    cluster.get_cl_resources_by_type.return_value = {SECRET_SYNC_RESOURCE_TYPE: []}
    mocked_instance.get_default_spc.return_value = spc
    setup_mock_common_responses(
        mocked_responses, spc, record, "new-list", "mock-rg", "certificate-der", "default-spc",
    )

    attempted_references = []

    def update_reference(**kwargs):
        reference = kwargs["properties"]["configurationSettings"][key]
        attempted_references.append(reference)
        if failure == "rollback" and reference == "active-list":
            raise AzureResponseError("Rollback failed.")
        settings.update(kwargs["properties"]["configurationSettings"])

    cluster.update_aio_extension.side_effect = update_reference
    timeout = OperationTimeoutError("SecretSync is still running.")
    if failure == "timeout":
        mocker.patch.object(OpcUACerts, "_add_secrets_to_secret_sync", side_effect=timeout)
    else:
        mocked_responses.add(
            responses.PUT, get_secretsync_endpoint("new-list", "mock-rg"),
            status=403, json={"error": {"code": "Forbidden"}},
        )

    expected_error = OperationTimeoutError if failure == "timeout" else HttpResponseError
    with pytest.raises(expected_error) as caught:
        getattr(commands_connector, f"add_connector_opcua_{kind}")(
            mocked_cmd, "instance-a", "mock-rg", file="/fake/certificate.der", secret_sync_name="new-list",
        )
    if failure == "timeout":
        assert caught.value is timeout
    assert attempted_references == (["new-list"] if failure == "timeout" else ["new-list", "active-list"])
    expected_reference = "active-list" if failure == "http" else "new-list"
    assert settings == {key: expected_reference, "unrelated": "preserved"}
    if failure == "rollback":
        assert "Failed to restore the previous certificate reference" in caplog.text


@pytest.mark.parametrize("reference", [
    "shared", "unshared", "other-spc", "other-location", "no-replacements", "new-sync", "lookup-error",
])
def test_client_rotation_preserves_only_peer_sources_in_same_spc_and_location(
    reference, mocked_cmd, mocked_instance, mocked_responses, mocked_read_file_content, mocked_decode_certificate,
):
    mocked_read_file_content.return_value = b"\x00\x01\x02\x03"
    mocked_decode_certificate.side_effect = lambda *_args, **_kwargs: [build_mock_cert()]
    record = get_mock_secretsync_record("client-sync", "mock-rg", objects=[
        {"sourcePath": "shared-der", "targetKey": "shared.der"},
        {"sourcePath": "old-pem", "targetKey": "old.pem"},
    ])
    record["properties"]["secretProviderClassName"] = "default-spc"
    record["extendedLocation"] = {"name": "mock-cl"}
    if reference == "no-replacements":
        record["properties"]["objectSecretMapping"] = []
    peer = get_mock_secretsync_record("peer-sync", "mock-rg", objects=[
        {"sourcePath": "shared-der", "targetKey": "shared.der"},
    ])
    peer["properties"]["secretProviderClassName"] = "other-spc" if reference == "other-spc" else "default-spc"
    peer["extendedLocation"] = {"name": "other-cl" if reference == "other-location" else "MOCK-CL"}
    spc = get_mock_spc_record(
        "default-spc", "mock-rg", objects=generate_ssc_object_string(["shared-der", "old-pem", "unrelated"]),
    )
    extension = {"name": "aio-ext", "properties": {"configurationSettings": {}}}
    assemble_resource_map_mock(
        mocked_instance.get_resource_map, {EXTENSION_TYPE_OPS: extension}, [], ssc=record,
    )
    cluster = mocked_instance.get_resource_map().connected_cluster
    if reference == "new-sync":
        cluster.get_cl_resources_by_type.return_value = {SECRET_SYNC_RESOURCE_TYPE: []}
    mocked_instance.get_default_spc.return_value = spc
    setup_mock_common_responses(
        mocked_responses, spc, record, "client-sync", "mock-rg", "certificate-der", "default-spc",
    )
    mocked_responses.add(
        responses.PUT, get_secret_endpoint("mock-keyvault", secret_name="certificate-pem"), json={},
    )
    endpoint = get_secretsync_endpoint("", "mock-rg")
    if reference not in {"no-replacements", "new-sync"}:
        if reference == "lookup-error":
            mocked_responses.add(responses.GET, endpoint, status=403, json={"error": {"code": "Forbidden"}})
        else:
            next_page = endpoint + "&$skiptoken=second"
            mocked_responses.add(responses.GET, endpoint, json={"value": [record], "nextLink": next_page})
            mocked_responses.add(
                responses.GET, next_page, json={"value": [] if reference == "unshared" else [peer]},
            )
    mocked_responses.add(responses.PUT, get_secretsync_endpoint("client-sync", "mock-rg"), json=record)
    arguments = {
        "cmd": mocked_cmd, "instance_name": "instance-a", "resource_group": "mock-rg",
        "public_key_file": "/fake/certificate.der", "private_key_file": "/fake/certificate.pem",
        "secret_sync_name": "client-sync",
    }
    if reference == "lookup-error":
        mocked_responses.remove(responses.PUT, get_spc_endpoint("default-spc", "mock-rg"))
        mocked_responses.remove(responses.PUT, get_secretsync_endpoint("client-sync", "mock-rg"))
        with pytest.raises(HttpResponseError):
            commands_connector.add_connector_opcua_client(**arguments)
        cluster.update_aio_extension.assert_not_called()
        assert not any(
            call.request.method == "PUT" and "Microsoft.SecretSyncController" in call.request.url
            for call in mocked_responses.calls
        )
        return
    commands_connector.add_connector_opcua_client(**arguments)
    spc_call = next(call for call in mocked_responses.calls
                    if call.request.url == get_spc_endpoint("default-spc", "mock-rg"))
    objects = yaml.safe_load(json.loads(spc_call.request.body)["properties"]["objects"])["array"]
    sources = {yaml.safe_load(item)["objectName"] for item in objects}
    expected = {"unrelated", "certificate-der", "certificate-pem"}
    if reference in {"shared", "no-replacements", "new-sync"}:
        expected.add("shared-der")
    if reference in {"no-replacements", "new-sync"}:
        expected.add("old-pem")
        assert not any(call.request.url == endpoint for call in mocked_responses.calls)
    assert sources == expected
    sync_call = next(call for call in mocked_responses.calls
                     if call.request.url == get_secretsync_endpoint("client-sync", "mock-rg"))
    assert json.loads(sync_call.request.body)["properties"]["objectSecretMapping"] == [
        {"sourcePath": "certificate-der", "targetKey": "certificate.der"},
        {"sourcePath": "certificate-pem", "targetKey": "certificate.pem"},
    ]
    cluster.update_aio_extension.assert_called_once()


@pytest.mark.parametrize("kind,setting,default", [
    ("trust", "trustedCerts", OPCUA_TRUST_LIST_SECRET_SYNC_NAME),
    ("issuer", "issuerCerts", OPCUA_ISSUER_LIST_SECRET_SYNC_NAME),
])
@pytest.mark.parametrize("custom_reference", [False, True])
def test_default_list_add_restores_custom_reference_without_redeploying_defaults(
    kind, setting, default, custom_reference, mocked_cmd, mocked_instance, mocked_responses,
    mocked_read_file_content, mocked_decode_certificate, mocked_logger,
):
    mocked_read_file_content.return_value = b"\x00\x01\x02\x03"
    mocked_decode_certificate.side_effect = lambda *_args, **_kwargs: [build_mock_cert()]
    record = get_mock_secretsync_record(default, "mock-rg")
    spc = get_mock_spc_record("default-spc", "mock-rg")
    settings = {"unrelated": "preserved"}
    key = f"connectors.values.securityPki.{setting}"
    if custom_reference:
        settings[key] = "custom-list"
    assemble_resource_map_mock(
        mocked_instance.get_resource_map,
        {EXTENSION_TYPE_OPS: {"name": "aio-ext", "properties": {"configurationSettings": settings}}},
        [], ssc=record,
    )
    cluster = mocked_instance.get_resource_map().connected_cluster
    cluster.get_cl_resources_by_type.return_value = {SECRET_SYNC_RESOURCE_TYPE: []}
    mocked_instance.get_default_spc.return_value = spc
    setup_mock_common_responses(
        mocked_responses, spc, record, default, "mock-rg", "certificate-der", "default-spc",
    )
    mocked_responses.add(responses.PUT, get_secretsync_endpoint(default, "mock-rg"), json=record)
    getattr(commands_connector, f"add_connector_opcua_{kind}")(
        mocked_cmd, "instance-a", "mock-rg", file="/fake/certificate.der",
    )
    if custom_reference:
        cluster.update_aio_extension.assert_called_once_with(
            extension_name="aio-ext", properties={"configurationSettings": {key: default}},
        )
    else:
        cluster.update_aio_extension.assert_not_called()
    assert "No changes detected in IoT Operations extension. Skipping update..." not in [
        call.args[0] for call in mocked_logger.warning.call_args_list
    ]
    assert settings["unrelated"] == "preserved"


@pytest.mark.parametrize("kind,setting", [
    ("trust", "trustedCerts"), ("issuer", "issuerCerts"), ("client", "applicationCert"),
])
def test_removing_old_named_certificate_preserves_active_reference(
    mocker, mocked_cmd, mocked_instance, mocked_responses, kind, setting,
):
    record = get_mock_secretsync_record("old-certificate", "mock-rg", objects=[
        {"sourcePath": "old-der", "targetKey": "old.der"},
    ])
    key = f"connectors.values.securityPki.{setting}"
    settings = {key: "current-certificate"}
    assemble_resource_map_mock(
        mocked_instance.get_resource_map,
        {EXTENSION_TYPE_OPS: {"name": "aio-ext", "properties": {"configurationSettings": settings}}},
        [record], ssc=record,
    )
    mocked_instance.get_default_spc.return_value = get_mock_spc_record("default-spc", "mock-rg")
    mocker.patch.object(OpcUACerts, "_remove_secrets_from_spc")
    mocked_responses.add(responses.DELETE, get_secretsync_endpoint("old-certificate", "mock-rg"), status=204)
    mocked_responses.add(responses.GET, get_secretsync_endpoint("", "mock-rg"), json={"value": []})
    getattr(commands_connector, f"remove_connector_opcua_{kind}")(
        mocked_cmd, "instance-a", "mock-rg", ["old.der"], confirm_yes=True, secret_sync_name="old-certificate",
    )
    mocked_instance.get_resource_map().connected_cluster.update_aio_extension.assert_not_called()
    assert settings[key] == "current-certificate"


@pytest.mark.parametrize("reference", ["shared", "only-shared", "other-spc", "other-location", "lookup-error"])
def test_removing_certificate_preserves_authoritatively_shared_sources(
    mocker, mocked_cmd, mocked_instance, mocked_responses, reference,
):
    record = get_mock_secretsync_record("old-sync", "mock-rg", objects=[
        {"sourcePath": "shared-der", "targetKey": "shared.der"},
        {"sourcePath": "old-der", "targetKey": "old.der"},
    ])
    if reference == "only-shared":
        record["properties"]["objectSecretMapping"] = record["properties"]["objectSecretMapping"][:1]
    certificate_names = [mapping["targetKey"] for mapping in record["properties"]["objectSecretMapping"]]
    other = get_mock_secretsync_record("current-sync", "mock-rg", objects=[
        {"sourcePath": "shared-der", "targetKey": "shared.der"},
    ])
    other["properties"]["secretProviderClassName"] = "other-spc" if reference == "other-spc" else "default-spc"
    other["extendedLocation"] = {"name": "other-cl" if reference == "other-location" else "mock-cl"}
    spc = get_mock_spc_record("default-spc", "mock-rg")
    settings = {"connectors.values.securityPki.trustedCerts": "current-sync"}
    assemble_resource_map_mock(
        mocked_instance.get_resource_map,
        {EXTENSION_TYPE_OPS: {"name": "aio-ext", "properties": {"configurationSettings": settings}}},
        [record], ssc=record,
    )
    mocked_instance.get_default_spc.return_value = spc
    provider = OpcUACerts(mocked_cmd, resource_group_name="mock-rg", instance_name="instance-a")
    update_spc = mocker.patch.object(provider, "_remove_secrets_from_spc")
    delete_secret = mocker.patch.object(provider, "_begin_delete_secret")
    purge_secret = mocker.patch.object(provider.keyvault_client, "purge_deleted_secret")
    list_secrets = mocker.patch.object(provider, "_get_secret_names", return_value=[
        "https://mock-keyvault.vault.azure.net/secrets/shared-der",
        "https://mock-keyvault.vault.azure.net/secrets/old-der",
    ])
    inventory = get_secretsync_endpoint("", "mock-rg")
    if reference == "lookup-error":
        mocked_responses.add(responses.GET, inventory, status=403, json={"error": {"code": "Forbidden"}})
        with pytest.raises(HttpResponseError):
            provider.remove("old-sync", certificate_names, confirm_yes=True, include_secrets=True)
        update_spc.assert_not_called()
        delete_secret.assert_not_called()
        purge_secret.assert_not_called()
        assert all(call.request.method == "GET" for call in mocked_responses.calls)
        return
    next_page = inventory + "&$skiptoken=second"
    mocked_responses.add(responses.GET, inventory, json={"value": [record], "nextLink": next_page})
    mocked_responses.add(responses.GET, next_page, json={"value": [other]})
    mocked_responses.add(responses.DELETE, get_secretsync_endpoint("old-sync", "mock-rg"), status=204)
    provider.remove(
        "old-sync", certificate_names, confirm_yes=True, include_secrets=True, certificate_type="trust",
    )
    expected = [] if reference == "only-shared" else ["old-der"] if reference == "shared" else ["shared-der", "old-der"]
    if expected:
        update_spc.assert_called_once_with(secrets=expected, spc=spc, resource_group="mock-rg")
    else:
        update_spc.assert_not_called()
        list_secrets.assert_not_called()
    assert [call.args[1] for call in delete_secret.call_args_list] == expected
    assert [call.kwargs["secret_name"] for call in purge_secret.call_args_list] == expected
    mocked_instance.get_resource_map().connected_cluster.update_aio_extension.assert_not_called()


@pytest.mark.parametrize("kind", ["trust", "issuer", "client"])
@pytest.mark.parametrize("operation", ["add", "show", "remove"])
def test_certificate_commands_parse_custom_secret_sync_names(mocker, tmp_path, kind, operation):
    from azure.cli.core import AzCli
    from azure.cli.core.commands import AzCliCommandInvoker
    from azure.cli.core.parser import AzCliCommandParser
    from knack.arguments import ignore_type
    from knack.cli import CLI
    from azext_edge import OpsExtensionCommandsLoader

    cli = AzCli.__new__(AzCli)
    CLI.__init__(cli, cli_name="az", config_dir=str(tmp_path))
    cli.cloud = mocker.Mock(profile="latest")
    cli.cloud.endpoints.resource_manager = "https://management.azure.com/"
    cli.local_context = SimpleNamespace(is_on=False)
    cli.data["completer_active"] = False
    invoker = AzCliCommandInvoker.__new__(AzCliCommandInvoker)
    invoker.cli_ctx = cli
    invoker.data = {}
    cli.invocation = invoker
    loader = OpsExtensionCommandsLoader(cli)
    invoker.commands_loader = loader
    mocker.patch("azext_edge.edge.util.version_check.check_latest")
    loader.load_command_table([])
    name = f"iot ops connector opcua {kind} {operation}"
    loader.command_name = name
    invoker.data["command_string"] = name
    command = loader.command_table[name]
    command.load_arguments()
    loader.load_arguments(name)
    command.update_argument("cmd", ignore_type)
    loader._update_command_definitions()
    parser = AzCliCommandParser(cli_ctx=cli, cli_help=mocker.Mock(), prog="az")
    parser.load_command_table(loader)
    args = ["--instance", "instance-a", "-g", "mock-rg", "--secret-sync-name", "per-instance-secret"]
    if operation == "add":
        args += (
            ["--public-key-file", "cert.der", "--private-key-file", "cert.pem"]
            if kind == "client" else ["--certificate-file", "cert.der"]
        )
    elif operation == "remove":
        args += ["--certificate-names", "cert.der"]
    assert parser.parse_args(name.split() + args).secret_sync_name == "per-instance-secret"
    expected_default = {
        "trust": "aio-opc-ua-broker-trust-list",
        "issuer": "aio-opc-ua-broker-issuer-list",
        "client": "aio-opc-ua-broker-client-certificate",
    }[kind]
    assert parser.parse_args(name.split() + args[:4] + args[6:]).secret_sync_name == expected_default
    provider = mocker.patch.object(commands_connector, "OpcUACerts")
    for invalid in ("INVALID_NAME", "", "a..b", "-a", "a-", "a" * 254):
        with pytest.raises(InvalidArgumentValueError, match="Kubernetes Secret name"):
            parser.parse_args(name.split() + args[:4] + [f"--secret-sync-name={invalid}"] + args[6:])
    provider.assert_not_called()
    assert parser.parse_args(name.split() + args[:5] + ["valid.name-1"] + args[6:]).secret_sync_name == "valid.name-1"
