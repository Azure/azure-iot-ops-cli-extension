# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from types import SimpleNamespace

import pytest
from azure.cli.core import get_default_cli
from azure.cli.core.azclierror import CLIInternalError
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError, ServiceRequestError
from knack.util import CLIError

from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    OpcUACerts,
)
from .int import helpers
from .int import test_opcua_certs_client_int as client_tests
from .int import test_opcua_certs_issuer_int as issuer_tests
from .int import test_opcua_certs_trust_int as trust_tests


SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
LOCATION = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test-rg/"
    "providers/Microsoft.ExtendedLocation/customLocations/current"
)
OLD_LOCATION = LOCATION.replace("/current", "/previous")
NAME = OPCUA_TRUST_LIST_SECRET_SYNC_NAME


def resource(location=LOCATION):
    return {"extendedLocation": {"name": location}}


@pytest.mark.parametrize("remaining", [[], [{"sourcePath": "another-secret"}]])
def test_certificate_removal_waits_for_resource_graph(mocker, remaining):
    stale = {
        "name": NAME, "resourceGroup": "test-rg", "extendedLocation": {"name": LOCATION},
        "properties": {"objectSecretMapping": [{"sourcePath": "trusttest-der"}]},
    }
    fresh = {**stale, "properties": {"objectSecretMapping": remaining}}
    command = mocker.patch.object(helpers, "run", return_value=[fresh])
    sleep = mocker.patch.object(helpers, "sleep")
    helpers.assert_ssc_secret_not_exists([stale], LOCATION, "test-rg", "trusttest.der", NAME, "test-instance")
    command.assert_called_once_with("az iot ops secretsync list -i test-instance -g test-rg")
    sleep.assert_called_once_with(helpers.SECRETSYNC_RETRY_INTERVAL)


@pytest.mark.parametrize("response", ["stale", "foreign", "absent", None, CLIInternalError("read failed")])
def test_certificate_removal_never_masks_persistent_or_invalid_results(mocker, response):
    stale = {
        "name": NAME, "resourceGroup": "test-rg", "extendedLocation": {"name": LOCATION},
        "properties": {"objectSecretMapping": [{"sourcePath": "trusttest-der"}]},
    }
    mocker.patch.object(helpers, "SECRETSYNC_MAX_RETRIES", 2)
    sleep = mocker.patch.object(helpers, "sleep")
    command = mocker.patch.object(helpers, "run")
    if isinstance(response, Exception):
        command.side_effect = response
    else:
        command.return_value = {
            "stale": [stale], "foreign": [{**stale, "extendedLocation": {"name": OLD_LOCATION}}],
            "absent": [], None: None,
        }[response]
    if response == "absent":
        helpers.assert_ssc_secret_not_exists([stale], LOCATION, "test-rg", "trusttest.der", NAME, "test-instance")
    else:
        with pytest.raises(CLIInternalError if isinstance(response, Exception) else AssertionError):
            helpers.assert_ssc_secret_not_exists(
                [stale], LOCATION, "test-rg", "trusttest.der", NAME, "test-instance",
            )
    assert command.call_count == sleep.call_count == (2 if response == "stale" else 1)


@pytest.fixture
def cleanup_context(mocker):
    settings = SimpleNamespace(env=SimpleNamespace(azext_edge_rg="test-rg", azext_edge_instance="test-instance"))
    mocker.patch.object(helpers, "run_json", return_value=resource())
    cli = mocker.patch.object(helpers, "get_default_cli")
    cli.return_value = mocker.MagicMock(spec=get_default_cli())
    cli.return_value.cloud.endpoints.resource_manager = "https://management.usgovcloudapi.net/"
    ssc_factory = mocker.patch.object(helpers, "get_ssc_mgmt_client")
    owner_factory = mocker.patch.object(helpers, "get_resource_client")
    sleep = mocker.patch.object(helpers, "sleep")
    logger = mocker.patch.object(helpers, "logger")
    command = mocker.patch.object(helpers, "run")
    certs = mocker.patch.object(helpers, "OpcUACerts", autospec=True)
    certs.return_value.extended_location = {"name": LOCATION}
    ssc = ssc_factory.return_value
    ssc.secret_syncs.get.side_effect = ResourceNotFoundError("missing")
    ssc.secret_syncs.begin_delete.return_value.done.return_value = True
    return SimpleNamespace(
        settings=settings, ssc=ssc, ssc_factory=ssc_factory, owner_factory=owner_factory,
        owner=owner_factory.return_value, sleep=sleep, logger=logger, command=command, certs=certs, cli=cli,
    )


def test_missing_secretsync_needs_no_cleanup(cleanup_context):
    ctx = cleanup_context
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()
    ctx.owner_factory.assert_not_called()
    ctx.ssc_factory.assert_called_once_with(
        subscription_id=SUBSCRIPTION, endpoint="https://management.usgovcloudapi.net/",
    )


@pytest.mark.parametrize("kind", ["trust", "issuer", "client"])
def test_per_instance_cleanup_resets_its_certificate_reference(cleanup_context, kind):
    ctx = cleanup_context
    name = helpers.certificate_sync_name("test-instance", kind)
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, name, certificate_type=kind)
    ctx.ssc.secret_syncs.get.side_effect = [resource(), ResourceNotFoundError("deleted")]
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_called_once_with(
        resource_group_name="test-rg", secret_sync_name=name,
    )
    ctx.certs.return_value._reset_certificate_reference.assert_called_once_with(name, kind)
    ctx.logger.warning.assert_not_called()


@pytest.mark.parametrize("name", [OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, OPCUA_TRUST_LIST_SECRET_SYNC_NAME])
def test_orphan_is_deleted_and_absence_verified_before_tests(cleanup_context, name):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [
        resource(OLD_LOCATION), resource(OLD_LOCATION), ResourceNotFoundError("deleted"),
        ResourceNotFoundError("still absent"),
    ]
    ctx.owner.resources.get_by_id.side_effect = ResourceNotFoundError("custom location deleted")

    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, name)
    poller = ctx.ssc.secret_syncs.begin_delete.return_value
    poller.wait.assert_called_once_with(timeout=120)
    poller.result.assert_called_once_with()
    ctx.ssc.secret_syncs.begin_delete.assert_called_once_with(
        resource_group_name="test-rg", secret_sync_name=name,
    )
    ctx.owner.resources.get_by_id.assert_called_once_with(
        OLD_LOCATION, api_version=helpers.CUSTOM_LOCATIONS_API_VERSION,
    )
    assert ctx.ssc.secret_syncs.get.call_count == 3
    ctx.sleep.assert_called_once_with(helpers.SECRETSYNC_RETRY_INTERVAL)
    cleanup()
    assert ctx.ssc.secret_syncs.begin_delete.call_count == 1
    ctx.command.assert_not_called()
    ctx.certs.assert_not_called()


def test_orphan_owner_read_preserves_referenced_subscription(cleanup_context):
    ctx = cleanup_context
    other_subscription = "11111111-1111-1111-1111-111111111111"
    owner = OLD_LOCATION.replace(SUBSCRIPTION, other_subscription)
    ctx.ssc.secret_syncs.get.side_effect = [resource(owner), ResourceNotFoundError("deleted")]
    ctx.owner.resources.get_by_id.side_effect = ResourceNotFoundError("missing owner")
    helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    ctx.owner_factory.assert_called_once_with(
        subscription_id=other_subscription, endpoint="https://management.usgovcloudapi.net/",
    )


@pytest.mark.parametrize("owner", [LOCATION, LOCATION.upper(), OLD_LOCATION])
def test_live_owner_is_never_deleted(cleanup_context, owner):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [resource(owner)]
    with pytest.raises(CLIInternalError, match="clean test instance|another custom location"):
        helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()


@pytest.mark.parametrize("invalid", [
    {}, {"extendedLocation": None}, {"extendedLocation": []}, resource("not-an-arm-id"),
    resource(LOCATION + "/children/child"),
    resource(LOCATION.replace("Microsoft.ExtendedLocation", "Microsoft.Other")),
])
def test_invalid_owner_does_not_authorize_deletion(cleanup_context, invalid):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [invalid]
    with pytest.raises(CLIInternalError, match="invalid custom location"):
        helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()
    ctx.owner_factory.assert_not_called()


@pytest.mark.parametrize("error", [HttpResponseError("forbidden"), ServiceRequestError("network unavailable")])
def test_owner_lookup_error_is_not_treated_as_an_orphan(cleanup_context, error):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [resource(OLD_LOCATION)]
    ctx.owner.resources.get_by_id.side_effect = error
    with pytest.raises(type(error)):
        helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()


@pytest.mark.parametrize("name", [OPCUA_TRUST_LIST_SECRET_SYNC_NAME, OPCUA_ISSUER_LIST_SECRET_SYNC_NAME])
def test_teardown_deletes_only_current_instance_resource(cleanup_context, name):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [
        ResourceNotFoundError("not created yet"), resource(LOCATION.upper()), ResourceNotFoundError("deleted"),
    ]
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, name)
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_called_once_with(
        resource_group_name="test-rg", secret_sync_name=name,
    )
    ctx.command.assert_not_called()
    ctx.certs.assert_not_called()


def client_resource():
    return {
        **resource(),
        "properties": {"objectSecretMapping": [
            {"sourcePath": "clienttest-der", "targetKey": "clienttest.der"},
            {"sourcePath": "clienttest-pem", "targetKey": "clienttest.pem"},
        ]},
    }


def test_client_teardown_rolls_back_extension_without_touching_spc(cleanup_context, mocker):
    ctx = cleanup_context
    connected_cluster = mocker.Mock()
    provider = ctx.certs.return_value
    provider.resource_map = SimpleNamespace(connected_cluster=connected_cluster)
    connected_cluster.get_extensions_by_type.return_value = {"microsoft.iotoperations": {
        "name": "aio-extension",
        "properties": {"configurationSettings": {
            "connectors.values.securityPki.applicationCert": OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            "connectors.values.securityPki.subjectName": "test-subject",
            "connectors.values.securityPki.applicationUri": "urn:test",
            "unrelated.setting": "preserve",
        }},
    }}

    def rollback(**kwargs):
        assert ctx.ssc.secret_syncs.get.call_count == 4
        return OpcUACerts._update_client_secret_to_extension(provider, **kwargs)

    provider._update_client_secret_to_extension.side_effect = rollback
    provider._reset_certificate_reference.side_effect = (
        lambda *args: OpcUACerts._reset_certificate_reference(provider, *args)
    )
    provider._update_extension_configuration.side_effect = (
        lambda *args, **kwargs: OpcUACerts._update_extension_configuration(provider, *args, **kwargs)
    )
    ctx.ssc.secret_syncs.get.side_effect = [
        ResourceNotFoundError("not created yet"), client_resource(), resource(), ResourceNotFoundError("deleted"),
    ]
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, OPCUA_CLIENT_CERT_SECRET_SYNC_NAME)
    ctx.settings.env.azext_edge_instance = "different-instance"
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_called_once_with(
        resource_group_name="test-rg", secret_sync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    )
    assert ctx.certs.call_args.kwargs["cmd"].cli_ctx is ctx.cli.return_value
    assert ctx.certs.call_args.kwargs["instance_name"] == "test-instance"
    assert ctx.certs.call_args.kwargs["resource_group_name"] == "test-rg"
    connected_cluster.update_aio_extension.assert_called_once_with(
        extension_name="aio-extension",
        properties={"configurationSettings": {
            "connectors.values.securityPki.applicationCert": "",
            "connectors.values.securityPki.subjectName": "",
            "connectors.values.securityPki.applicationUri": "",
        }},
    )
    provider.remove.assert_not_called()
    provider._remove_secrets_from_spc.assert_not_called()
    assert ctx.ssc.azure_key_vault_secret_provider_classes.mock_calls == []
    ctx.command.assert_not_called()
    assert ctx.ssc.secret_syncs.get.call_count == 4
    ctx.sleep.assert_called_once_with(helpers.SECRETSYNC_RETRY_INTERVAL)
    ctx.logger.warning.assert_not_called()


@pytest.mark.parametrize("phase", ["initialize", "delete", "verify", "rollback"])
@pytest.mark.parametrize("error", [
    CLIInternalError("cleanup failed"), CLIError("login unavailable"),
    HttpResponseError("forbidden"), TimeoutError("timed out"),
])
def test_client_teardown_failure_is_warning_only(cleanup_context, phase, error):
    ctx = cleanup_context
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, OPCUA_CLIENT_CERT_SECRET_SYNC_NAME)
    ctx.ssc.secret_syncs.get.side_effect = [client_resource(), ResourceNotFoundError("deleted")]
    if phase == "initialize":
        ctx.certs.side_effect = error
    elif phase == "delete":
        ctx.ssc.secret_syncs.begin_delete.side_effect = error
    elif phase == "verify":
        ctx.ssc.secret_syncs.get.side_effect = [client_resource(), error]
    else:
        ctx.certs.return_value._reset_certificate_reference.side_effect = error
    cleanup()
    ctx.logger.warning.assert_called_once()
    ctx.command.assert_not_called()
    if phase != "rollback":
        ctx.certs.return_value._reset_certificate_reference.assert_not_called()


@pytest.mark.parametrize("properties", [
    None, {}, {"objectSecretMapping": []}, {"objectSecretMapping": [None]},
    {"objectSecretMapping": [{"targetKey": ""}]}, {"objectSecretMapping": [{"targetKey": None}]},
])
def test_client_teardown_does_not_inspect_or_modify_spc_mappings(cleanup_context, properties):
    ctx = cleanup_context
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, OPCUA_CLIENT_CERT_SECRET_SYNC_NAME)
    ctx.ssc.secret_syncs.get.side_effect = [
        {**resource(), "properties": properties}, ResourceNotFoundError("deleted"),
    ]
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_called_once_with(
        resource_group_name="test-rg", secret_sync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    )
    ctx.certs.return_value._reset_certificate_reference.assert_called_once_with(
        OPCUA_CLIENT_CERT_SECRET_SYNC_NAME, "client",
    )
    ctx.certs.return_value._remove_secrets_from_spc.assert_not_called()
    ctx.logger.warning.assert_not_called()
    ctx.command.assert_not_called()


def test_client_teardown_ownership_change_preserves_other_deployment(cleanup_context):
    ctx = cleanup_context
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, OPCUA_CLIENT_CERT_SECRET_SYNC_NAME)
    ctx.ssc.secret_syncs.get.side_effect = [{**client_resource(), **resource(OLD_LOCATION)}]
    cleanup()
    ctx.command.assert_not_called()
    ctx.certs.assert_not_called()
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()
    ctx.logger.warning.assert_called_once()


def test_client_teardown_instance_move_preserves_resources(cleanup_context):
    ctx = cleanup_context
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, OPCUA_CLIENT_CERT_SECRET_SYNC_NAME)
    ctx.ssc.secret_syncs.get.side_effect = [client_resource()]
    ctx.certs.return_value.extended_location = {"name": OLD_LOCATION}
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()
    ctx.certs.return_value._update_client_secret_to_extension.assert_not_called()
    ctx.logger.warning.assert_called_once()


def test_teardown_ownership_change_is_warning_only(cleanup_context):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [ResourceNotFoundError("missing"), resource(OLD_LOCATION)]
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    cleanup()
    ctx.ssc.secret_syncs.begin_delete.assert_not_called()
    ctx.logger.warning.assert_called_once()
    assert "ownership changed" in str(ctx.logger.warning.call_args)


@pytest.mark.parametrize("phase", ["get", "delete", "poll", "verify"])
@pytest.mark.parametrize("error", [
    HttpResponseError("forbidden"), ServiceRequestError("network unavailable"), TimeoutError("timed out"),
])
def test_teardown_failure_is_warning_only(cleanup_context, phase, error):
    ctx = cleanup_context
    cleanup = helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    ctx.ssc.secret_syncs.get.side_effect = [resource(), ResourceNotFoundError("deleted")]
    poller = ctx.ssc.secret_syncs.begin_delete.return_value
    if phase == "get":
        ctx.ssc.secret_syncs.get.side_effect = error
    elif phase == "delete":
        ctx.ssc.secret_syncs.begin_delete.side_effect = error
    elif phase == "poll":
        poller.result.side_effect = error
    else:
        ctx.ssc.secret_syncs.get.side_effect = [resource(), error]
    cleanup()
    ctx.logger.warning.assert_called_once()


def test_deletion_must_finish_before_tests_can_run(cleanup_context):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = [resource(OLD_LOCATION)]
    ctx.owner.resources.get_by_id.side_effect = ResourceNotFoundError("missing")
    ctx.ssc.secret_syncs.begin_delete.return_value.done.return_value = False
    with pytest.raises(TimeoutError, match="Timed out deleting"):
        helpers.prepare_opcua_secretsync(ctx.settings, NAME)
    assert ctx.ssc.secret_syncs.get.call_count == 1


def test_persistent_resource_exhausts_bounded_deletion_check(cleanup_context):
    ctx = cleanup_context
    ctx.ssc.secret_syncs.get.side_effect = None
    ctx.ssc.secret_syncs.get.return_value = resource()
    with pytest.raises(TimeoutError, match="still exists"):
        helpers._delete_opcua_secretsync(ctx.ssc, "test-rg", NAME)
    assert ctx.ssc.secret_syncs.get.call_count == helpers.SECRETSYNC_MAX_RETRIES
    assert ctx.sleep.call_count == helpers.SECRETSYNC_MAX_RETRIES - 1


@pytest.mark.parametrize("module,fixture_name,kind", [
    (client_tests, "opcua_certs_client_test_setup", "client"),
    (issuer_tests, "opcua_certs_issuer_test_setup", "issuer"),
    (trust_tests, "opcua_certs_trust_test_setup", "trust"),
])
def test_setup_failure_still_registers_cleanup(mocker, module, fixture_name, kind):
    settings = SimpleNamespace(env=SimpleNamespace(azext_edge_rg="test-rg", azext_edge_instance="test-instance"))
    request = mocker.Mock()
    mocker.patch.object(module, "ensure_env_vars")
    vault_cleanup = mocker.Mock()

    def provision_vault(_settings, fixture_request):
        fixture_request.addfinalizer(vault_cleanup)
        return "/vault", "vault"

    mocker.patch.object(module, "ensure_key_vault", side_effect=provision_vault)
    mocker.patch.object(module, "ensure_managed_identity", side_effect=CLIInternalError("setup failed"))
    prepare = mocker.patch.object(module, "prepare_opcua_secretsync")
    fixture = getattr(module, fixture_name).__wrapped__(settings, [], request)
    with pytest.raises(CLIInternalError, match="setup failed"):
        next(fixture)
    assert request.addfinalizer.call_count == 2
    prepare.assert_called_once_with(
        settings, helpers.certificate_sync_name("test-instance", kind), certificate_type=kind,
    )
    finalizers = [call.args[0] for call in request.addfinalizer.call_args_list]
    for finalizer in reversed(finalizers):
        finalizer()
    prepare.return_value.assert_called_once_with()
    vault_cleanup.assert_called_once_with()
