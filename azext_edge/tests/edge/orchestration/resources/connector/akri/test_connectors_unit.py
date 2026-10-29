# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from types import SimpleNamespace

import pytest
import responses
from azure.cli.core.azclierror import AzureResponseError, InvalidArgumentValueError, ValidationError

from azext_edge.edge.commands_connector import list_connectors, show_connector
from azext_edge.edge.providers.orchestration.resources.connectors import (
    Connectors, connector_list_table, connector_show_table, require_preview_instance, sorted_connector_versions,
    CONNECTOR_DISCOVERY_REQUIREMENT, MARKETPLACE_URL, get_first_party_connectors, metadata_supports_runtime,
)
from azext_edge.edge.providers.orchestration.runtime import RuntimeContext, RuntimeIssue, RuntimeIssueCode
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_commands import RuntimeTarget, get_runtime_notice_targets
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel


MODULE = "azext_edge.edge.providers.orchestration.resources.connectors"
INSTANCE_ID = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.IoTOperations/instances/aio"
REFERENCE = "example.azurecr.io/purchased/sse-metadata:1.0.0"


def test_connector_versions_use_semantic_order():
    assert sorted_connector_versions([
        "1.9.0", "latest", "1.10.0", "1.10.0", "1.10.0-preview.2", "invalid", "2.0.0",
    ]) == ["2.0.0", "1.10.0", "1.10.0-preview.2", "1.9.0"]


@pytest.mark.parametrize("runtime,minimum,maximum,expected", [
    ("1.5.0", "1.5.0", None, True),
    ("1.4.9", "1.5.0", None, False),
    ("2.0.0", "1.5.0", None, True),
    ("1.6.0", "1.5.0", "1.6.0", True),
    ("1.6.1", "1.5.0", "1.6.0", False),
    ("1.6.0-preview.19", "1.6.0", None, False),
    ("1.6.0-preview.19", "1.6.0-preview.2", "1.6.0", True),
    ("1.9.99", "1.5.0", "1.*.*", True),
    ("2.0.0-preview.1", "1.5.0", "1.*.*", False),
    ("1.6.99", "1.5.0", "1.6.*", True),
    ("1.7.0-preview.1", "1.5.0", "1.6.*", False),
    ("1.4.9", "1.5.0", "1.*.*", False),
    ("2.0.0", "1.5.0", "*.*.*", True),
])
def test_metadata_runtime_compatibility(runtime, minimum, maximum, expected):
    requirements = {"aioMinVersion": minimum}
    if maximum is not None:
        requirements["aioMaxVersion"] = maximum
    assert metadata_supports_runtime({"aioMetadata": requirements}, runtime) is expected


@pytest.mark.parametrize("requirements", [
    None, {}, [], {"aioMinVersion": ""}, {"aioMinVersion": 42},
    {"aioMinVersion": "latest"}, {"aioMinVersion": "1.5.*"},
    *({"aioMinVersion": "1.5.0", "aioMaxVersion": maximum} for maximum in [
        None, "", 42, "invalid", "1.*.0", "1.*", "01.*.*", "1.4.9", "1.4.*", "0.*.*",
    ]),
])
def test_invalid_compatibility_metadata_is_not_a_match(requirements):
    with pytest.raises(ValidationError, match="compatibility"):
        metadata_supports_runtime({"aioMetadata": requirements}, "1.6.0")


@pytest.mark.parametrize("runtime", [None, "", "latest", "1.6", 42])
def test_invalid_runtime_is_not_a_match(runtime):
    with pytest.raises(ValidationError, match="target AIO runtime version"):
        metadata_supports_runtime({"aioMetadata": {"aioMinVersion": "1.0.0"}}, runtime)


def test_registry_tag_pagination(mocker):
    from azext_edge.edge.util.oci_client import OciRegistryClient

    client = OciRegistryClient()
    mocker.patch.object(client, "_get_auth_headers", return_value={})
    get = mocker.patch.object(client, "get", side_effect=[
        mocker.Mock(status_code=200, headers={"Link": '</v2/connectors/rest-metadata/tags/list?last=1>; rel="next"'},
                    json=lambda: {"name": "connectors/rest-metadata", "tags": ["1.0.0", "1.0.0"]}),
        mocker.Mock(status_code=200, headers={},
                    json=lambda: {"name": "connectors/rest-metadata", "tags": ["2.0.0"]}),
    ])
    assert client.list_tags("mcr.microsoft.com/connectors/rest-metadata") == ["1.0.0", "2.0.0"]
    assert get.call_args.args[0] == "https://mcr.microsoft.com/v2/connectors/rest-metadata/tags/list?last=1"
    assert get.call_args.kwargs["permit_redirects"] is False


@pytest.mark.parametrize("status", [200, 302])
def test_registry_tags_use_pipeline_transport_without_redirects(mocker, status):
    from azext_edge.edge.util.oci_client import OciRegistryClient

    with responses.RequestsMock() as requests_mock, OciRegistryClient() as client:
        mocker.patch.object(client, "_get_auth_headers", return_value={"Authorization": "Bearer test-token"})
        requests_mock.add(
            responses.GET, "https://mcr.microsoft.com/v2/connectors/rest-metadata/tags/list",
            status=status, headers={"Location": "https://other.example/tags"} if status == 302 else {},
            json={"name": "connectors/rest-metadata", "tags": ["1.0.0"]},
        )
        if status == 200:
            assert client.list_tags("mcr.microsoft.com/connectors/rest-metadata") == ["1.0.0"]
        else:
            with pytest.raises(ValidationError, match="HTTP 302"):
                client.list_tags("mcr.microsoft.com/connectors/rest-metadata")
        assert len(requests_mock.calls) == 1


@pytest.mark.parametrize("token_response,authorized", [
    ({"token": "public-token"}, True),
    ({"access_token": "public-token"}, True),
    ({"token": "", "access_token": "public-token"}, True),
    ({}, False),
])
def test_anonymous_registry_token_fallback(mocker, token_response, authorized):
    from azext_edge.edge.util.oci_client import OciRegistryClient

    oci_module = "azext_edge.edge.util.oci_client"
    cmd = SimpleNamespace(cli_ctx=SimpleNamespace(data={"tenant_id": "test-tenant"}))
    mocker.patch(f"{oci_module}.CloudConfig", return_value=SimpleNamespace(
        acr_suffix=".azurecr.io", arm_endpoint_scope="https://management.azure.com/.default",
    ))
    mocker.patch(f"{oci_module}.AZURE_CLI_CREDENTIAL.get_token", return_value=SimpleNamespace(token="arm-token"))
    logger = mocker.patch(f"{oci_module}.logger")
    registry = "https://example.azurecr.io"
    manifest = {"config": {"mediaType": "application/vnd.oci.image.config.v1+json"}, "layers": []}
    with responses.RequestsMock() as requests_mock, OciRegistryClient() as client:
        requests_mock.add(responses.POST, f"{registry}/oauth2/exchange", status=401)
        requests_mock.add(
            responses.GET, f"{registry}/v2/", status=401,
            headers={"WWW-Authenticate": f'Bearer realm="{registry}/oauth2/token",service="example.azurecr.io"'},
        )
        requests_mock.add(
            responses.GET, f"{registry}/oauth2/token", json=token_response,
            match=[responses.matchers.query_param_matcher({
                "service": "example.azurecr.io", "scope": "repository:purchased/sse-metadata:pull",
            })],
        )
        requests_mock.add(
            responses.GET, f"{registry}/v2/purchased/sse-metadata/manifests/1.0.0",
            status=200 if authorized else 401,
            json=manifest if authorized else {"errors": [{"code": "UNAUTHORIZED"}]},
        )

        if authorized:
            assert client.fetch_manifest(REFERENCE, cmd=cmd) == manifest
            assert requests_mock.calls[-1].request.headers.get("Authorization") == "Bearer public-token"
        else:
            with pytest.raises(ValidationError, match="401"):
                client.fetch_manifest(REFERENCE, cmd=cmd)
            assert "Authorization" not in requests_mock.calls[-1].request.headers
        logger.warning.assert_called_once_with("ACR exchange failed with status code: 401")
        assert len(requests_mock.calls) == 4


@pytest.mark.parametrize("link", [
    '<https://other.example/v2/connectors/rest-metadata/tags/list>; rel="next"',
    '</v2/other/tags/list>; rel="next"',
    '</v2/connectors/rest-metadata/tags/list>; rel="next"',
])
def test_registry_tag_pagination_rejects_unsafe_or_repeated_links(mocker, link):
    from azext_edge.edge.util.oci_client import OciRegistryClient

    client = OciRegistryClient()
    mocker.patch.object(client, "_get_auth_headers", return_value={"Authorization": "Bearer secret"})
    get = mocker.patch.object(client, "get", return_value=mocker.Mock(
        status_code=200, headers={"Link": link},
        json=lambda: {"name": "connectors/rest-metadata", "tags": []},
    ))
    with pytest.raises(ValidationError):
        client.list_tags("mcr.microsoft.com/connectors/rest-metadata")
    get.assert_called_once()


@pytest.mark.parametrize("page", [
    None, {}, {"name": "wrong", "tags": []}, {"name": "connectors/rest-metadata", "tags": [42]},
])
def test_registry_tag_listing_rejects_invalid_responses(mocker, page):
    from azext_edge.edge.util.oci_client import OciRegistryClient

    client = OciRegistryClient()
    mocker.patch.object(client, "_get_auth_headers", return_value={})
    mocker.patch.object(client, "get", return_value=mocker.Mock(status_code=200, headers={}, json=lambda: page))
    with pytest.raises(ValidationError):
        client.list_tags("mcr.microsoft.com/connectors/rest-metadata")


@pytest.fixture
def discovery(mocker):
    cmd = mocker.Mock()
    cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com/"
    cmd.cli_ctx.only_show_errors = False
    cmd.cli_ctx.invocation.data = {"output": "json"}
    cmd.cli_ctx.config.getboolean.return_value = False
    cmd.cli_ctx.config.get.return_value = "json"
    mocker.patch(f"{MODULE}.sys.stdout.isatty", return_value=False)
    mocker.patch(f"{MODULE}.sys.stderr.isatty", return_value=False)
    guard = mocker.patch(f"{MODULE}.require_preview_instance", return_value=INSTANCE_ID)
    registry = mocker.patch(f"{MODULE}.get_oci_client").return_value
    registry.list_tags.return_value = ["1.0.0"]
    metadata = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.ConnectorTemplates.fetch_metadata",
        return_value={
            "name": "rest", "version": "1.0.0",
            "aioMetadata": {"aioMinVersion": "1.0.0"},
            "imageConfigurationSettings": {"imageName": "azureiotoperations/akri-connectors/rest"},
            "inboundEndpoints": [{"endpointType": "Microsoft.Http", "version": "1.0"}],
        },
    )
    mocker.patch(f"{MODULE}.get_subscription_id", return_value="sub")
    request = mocker.patch(f"{MODULE}.send_raw_request")
    request.return_value.json.return_value = {"value": []}
    return SimpleNamespace(cmd=cmd, guard=guard, request=request, registry=registry, metadata=metadata)


@pytest.mark.parametrize("status", [200, 403])
def test_discovery_keeps_shared_oci_client_usable(mocker, status):
    from azext_edge.edge.util.oci_client import OciRegistryClient, get_oci_client

    repository = "azureiotoperations/akri-connectors/rest-metadata"
    manifest = {"config": {"mediaType": "application/vnd.oci.image.config.v1+json"}, "layers": []}
    with responses.RequestsMock() as requests_mock, OciRegistryClient() as client:
        mocker.patch("azext_edge.edge.util.oci_client._oci_client", client)
        mocker.patch.object(client, "_get_auth_headers", return_value={})
        mocker.patch(f"{MODULE}.FIRST_PARTY_CONNECTOR_NAMES", ("rest",))
        requests_mock.add(
            responses.GET, f"https://mcr.microsoft.com/v2/{repository}/tags/list",
            status=status, json={"name": repository, "tags": []},
        )
        requests_mock.add(
            responses.GET, f"https://mcr.microsoft.com/v2/{repository}/manifests/1.0.0", json=manifest,
        )
        for _ in range(2):
            if status == 200:
                entries = get_first_party_connectors(None, "1.6.0-preview.49")
                assert isinstance(entries, tuple) and not entries
            else:
                with pytest.raises(ValidationError, match="HTTP 403"):
                    get_first_party_connectors(None, "1.6.0-preview.49")

        assert get_oci_client() is client
        assert get_oci_client().fetch_manifest(f"mcr.microsoft.com/{repository}:1.0.0") == manifest
        assert len(requests_mock.calls) == 3


def test_first_party_references_follow_registry_versions(discovery):
    discovery.registry.list_tags.return_value = ["9.9.0", "9.10.0", "latest"]
    result = list_connectors(discovery.cmd, "aio", "rg")
    assert result[0] == {
        "name": "rest", "source": "FirstParty",
        "metadataRef": "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:9.10.0",
    }
    assert [entry["name"] for entry in result] == ["rest", "media", "mqtt", "sse", "onvif"]
    discovery.request.assert_called_once()
    assert discovery.registry.list_tags.call_count == 5
    assert discovery.metadata.call_count == 5
    discovery.registry.list_tags.assert_any_call(
        "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata", cmd=discovery.cmd,
    )


def test_incompatible_latest_uses_older_compatible_version(discovery):
    discovery.registry.list_tags.return_value = ["1.9.0", "1.10.0", "1.8.0"]
    discovery.metadata.side_effect = lambda cmd, reference: {
        **discovery.metadata.return_value,
        "aioMetadata": {"aioMinVersion": "1.6.0" if reference.endswith(":1.10.0") else "1.5.0"}
    }
    result = list_connectors(discovery.cmd, "aio", "rg")
    assert len(result) == 5
    assert all(entry["metadataRef"].endswith(":1.9.0") for entry in result)
    assert discovery.metadata.call_count == 10
    assert all(not call.args[1].endswith(":1.8.0") for call in discovery.metadata.call_args_list)


def test_registry_versions_are_refreshed_each_invocation(discovery):
    provider = Connectors(discovery.cmd)
    assert all(entry["metadataRef"].endswith(":1.0.0") for entry in provider.list("aio", "rg"))
    discovery.registry.list_tags.return_value = ["1.0.0", "1.1.0-preview.1"]
    result = provider.list("aio", "rg")
    assert len(result) == 5
    assert all(entry["metadataRef"].endswith(":1.1.0-preview.1") for entry in result)
    assert discovery.registry.list_tags.call_count == 10


@pytest.mark.parametrize("tags", [[], ["latest"], ["1.0.0"]])
def test_no_compatible_first_party_versions_preserves_purchases(discovery, tags):
    discovery.registry.list_tags.return_value = tags
    discovery.metadata.return_value["aioMetadata"] = {"aioMinVersion": "2.0.0"}
    discovery.request.return_value.json.return_value = {"value": [
        {"name": "purchase", "properties": {
            "applicationMetadataRef": REFERENCE, "applicationSource": "marketplace", "applicationType": "connector",
        }}
    ]}
    assert list_connectors(discovery.cmd, "aio", "rg") == [
        {"name": "purchase", "source": "Marketplace", "metadataRef": REFERENCE}
    ]
    assert discovery.metadata.call_count == (5 if tags == ["1.0.0"] else 0)


@pytest.mark.parametrize("field", [
    "name", "version", "imageConfigurationSettings", "inboundEndpoints", "imageConfigurationSettings.imageName",
])
@pytest.mark.parametrize("missing", [True, False])
def test_compatible_first_party_metadata_must_pass_template_validation(discovery, mocker, field, missing):
    metadata = discovery.metadata.return_value
    target = metadata
    key = field
    if "." in field:
        parent, key = field.split(".")
        target = metadata[parent]
        target["imagePullPolicy"] = "IfNotPresent"
    if missing:
        target.pop(key)
    else:
        target[key] = None
    discovery.registry.list_tags.return_value = ["1.0.0", "2.0.0"]
    hint = mocker.patch(f"{MODULE}.logger.warning")

    assert metadata_supports_runtime(metadata, "1.6.0-preview.49")
    with pytest.raises(ValidationError, match=field) as error:
        list_connectors(discovery.cmd, "aio", "rg")
    assert "rest-metadata:2.0.0" in str(error.value)
    discovery.metadata.assert_called_once()
    discovery.registry.list_tags.assert_called_once()
    hint.assert_not_called()


def test_missing_compatibility_fails_without_trying_older_version(discovery, mocker):
    discovery.registry.list_tags.return_value = ["1.0.0", "2.0.0"]
    discovery.metadata.return_value = {}
    hint = mocker.patch(f"{MODULE}.logger.warning")
    with pytest.raises(ValidationError, match="rest-metadata:2.0.0"):
        list_connectors(discovery.cmd, "aio", "rg")
    discovery.metadata.assert_called_once()
    hint.assert_not_called()


def test_metadata_download_failure_is_not_incompatibility(discovery, mocker):
    discovery.registry.list_tags.return_value = ["1.0.0", "2.0.0"]
    failure = ValidationError("Metadata download failed")
    discovery.metadata.side_effect = failure
    hint = mocker.patch(f"{MODULE}.logger.warning")
    with pytest.raises(ValidationError) as error:
        list_connectors(discovery.cmd, "aio", "rg")
    assert error.value is failure
    discovery.metadata.assert_called_once()
    hint.assert_not_called()


def test_registry_failure_is_not_partial_success(discovery, mocker):
    failure = ValidationError("Registry unavailable")
    discovery.registry.list_tags.side_effect = failure
    hint = mocker.patch(f"{MODULE}.logger.warning")
    with pytest.raises(ValidationError) as error:
        list_connectors(discovery.cmd, "aio", "rg")
    assert error.value is failure
    hint.assert_not_called()


def test_list_combines_definitions_without_fetching_marketplace_metadata(discovery, mocker):
    collection = f"https://management.azure.com{INSTANCE_ID}/aioApplicationDefinitions"
    api_version = get_runtime_catalog().get(RuntimeChannel.PREVIEW).iotops_api_version
    next_link = f"{collection}?api-version={api_version}&$skiptoken=page2"
    discovery.request.side_effect = [
        mocker.Mock(json=lambda: {"value": [{"name": "purchase-1", "properties": {
            "applicationMetadataRef": REFERENCE, "imageDetails": {"imageName": "not-the-metadata"},
            "applicationSource": "marketplace", "applicationType": "connector",
        }}], "nextLink": next_link}),
        mocker.Mock(json=lambda: {"value": [{"name": "purchase-2", "properties": {
            "applicationMetadataRef": REFERENCE, "applicationSource": "Marketplace", "applicationType": "Connector",
        }}]}),
    ]
    result = list_connectors(discovery.cmd, "aio", "rg")
    assert len(result) == 7
    assert all(entry["source"] == "FirstParty" for entry in result[:5])
    assert result[-2:] == [
        {"name": "purchase-1", "source": "Marketplace", "metadataRef": REFERENCE},
        {"name": "purchase-2", "source": "Marketplace", "metadataRef": REFERENCE},
    ]
    discovery.guard.assert_called_once_with(discovery.cmd, "aio", "rg")
    assert discovery.request.call_args_list[1].kwargs["url"] == next_link
    assert discovery.metadata.call_count == 5
    assert all(call.args[1].startswith("mcr.microsoft.com/") for call in discovery.metadata.call_args_list)
    assert list(connector_list_table(result)[0]) == ["Name", "Source", "MetadataRef"]


@pytest.mark.parametrize("source,application_type", [
    ("userdefined", "aioApplication"), ("userdefined", "connector"), ("marketplace", "aioApplication"),
    (None, "connector"), ("marketplace", None), (42, "connector"), ("marketplace", []),
])
@pytest.mark.parametrize("has_reference", [False, True])
def test_list_skips_unrelated_application_definitions(discovery, source, application_type, has_reference):
    properties = {"applicationSource": source, "applicationType": application_type}
    if has_reference:
        properties["applicationMetadataRef"] = REFERENCE
    unrelated = {"name": "application", "properties": properties}
    purchase = {"name": "purchase", "properties": {
        "applicationSource": "marketplace", "applicationType": "connector", "applicationMetadataRef": REFERENCE,
    }}
    discovery.registry.list_tags.return_value = []
    discovery.request.return_value.json.return_value = {"value": [unrelated, purchase]}

    assert list_connectors(discovery.cmd, "aio", "rg") == [
        {"name": "purchase", "source": "Marketplace", "metadataRef": REFERENCE},
    ]
    discovery.request.return_value.json.return_value = {"value": [unrelated, {"properties": {}}]}
    result = list_connectors(discovery.cmd, "aio", "rg")
    assert isinstance(result, list) and not result
    discovery.metadata.assert_not_called()


def test_live_marketplace_definition_reference_is_preserved(discovery):
    reference = (
        "arcmktplaceprod.azurecr.io/est_iot_akrimarketplaceconnectors_poc1778863100388/"
        "com.microsoft.akri.sse-connector/images/sse-metadata:1.3.6-1.3.2"
    )
    discovery.request.return_value.json.return_value = {"value": [{
        "id": f"{INSTANCE_ID}/aioApplicationDefinitions/akrimktconnsse",
        "name": "akrimktconnsse",
        "type": "microsoft.iotoperations/instances/aioapplicationdefinitions",
        "properties": {
            "aioMetadata": {"aioMaxVersion": "1.*", "aioMinVersion": "1.0"},
            "applicationMetadataRef": reference,
            "applicationSource": "marketplace",
            "applicationType": "connector",
            "imageDetails": {"imageName": "com.microsoft.akri.sse-connector/images/sse-image"},
            "provisioningState": "Succeeded",
        },
    }]}

    result = list_connectors(discovery.cmd, "aio", "rg")

    assert result[-1] == {"name": "akrimktconnsse", "source": "Marketplace", "metadataRef": reference}
    api_version = get_runtime_catalog().get(RuntimeChannel.PREVIEW).iotops_api_version
    discovery.request.assert_called_once_with(
        cli_ctx=discovery.cmd.cli_ctx, method="GET",
        url=f"https://management.azure.com{INSTANCE_ID}/aioApplicationDefinitions?api-version={api_version}",
    )
    assert discovery.metadata.call_count == 5
    assert all(call.args[1].startswith("mcr.microsoft.com/") for call in discovery.metadata.call_args_list)


def test_empty_definitions_keep_first_party(discovery):
    assert len(list_connectors(discovery.cmd, "aio", "rg")) == 5


@pytest.mark.parametrize("page", [None, {}, {"value": None}, {"value": [{}]}, {"value": [None]}])
def test_invalid_definition_response_is_not_empty_success(discovery, page):
    discovery.request.return_value.json.return_value = page
    with pytest.raises(AzureResponseError):
        list_connectors(discovery.cmd, "aio", "rg")


@pytest.mark.parametrize("reference", [None, "akri-connectors/rest-metadata:0.5.0", "https://user:secret@host/path"])
def test_invalid_definition_reference_is_not_reconstructed(discovery, reference):
    discovery.request.return_value.json.return_value = {"value": [
        {"name": "purchase", "properties": {
            "applicationMetadataRef": reference, "applicationSource": "marketplace", "applicationType": "connector",
        }}
    ]}
    with pytest.raises(AzureResponseError, match="fully qualified applicationMetadataRef") as error:
        list_connectors(discovery.cmd, "aio", "rg")
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
def test_discovery_errors_are_preserved(discovery, status):
    failure = AzureResponseError(f"Service error {status}")
    discovery.request.side_effect = failure
    with pytest.raises(AzureResponseError) as error:
        list_connectors(discovery.cmd, "aio", "rg")
    assert error.value is failure


@pytest.mark.parametrize("next_link", ["https://evil.example/profiles", "/other/collection", 42, {}, False])
def test_unsafe_pagination_rejected(discovery, next_link):
    discovery.request.return_value.json.return_value = {"value": [], "nextLink": next_link}
    with pytest.raises(AzureResponseError, match="nextLink"):
        list_connectors(discovery.cmd, "aio", "rg")
    discovery.request.assert_called_once()


def test_preview_failure_does_not_query_definitions(discovery):
    discovery.guard.side_effect = ValidationError("Requires preview runtime")
    with pytest.raises(ValidationError, match="preview"):
        list_connectors(discovery.cmd, "aio", "rg")
    discovery.request.assert_not_called()
    discovery.registry.list_tags.assert_not_called()
    discovery.metadata.assert_not_called()


@pytest.fixture(params=[False, True], ids=["stable", "preview"])
def connector_runtime(request):
    identity = get_runtime_catalog().for_create(use_preview=request.param).identity
    return RuntimeContext(
        instance_id=INSTANCE_ID, custom_location_id="location", cluster_id="cluster", extension_id="extension",
        identity=identity, requested_version=identity.version, provisioning_state="Succeeded",
    )


def test_preview_requirement_uses_shared_runtime_contract(mocker, connector_runtime):
    prefix = "azext_edge.edge.providers.orchestration"
    instances = mocker.patch(f"{prefix}.resources.instances.Instances")
    record = {"id": INSTANCE_ID}
    instances.return_value.show.return_value = record
    instances.return_value.get_runtime_context.return_value = connector_runtime
    cmd = SimpleNamespace()
    if connector_runtime.identity.channel == RuntimeChannel.PREVIEW:
        assert require_preview_instance(cmd, "aio", "rg") == INSTANCE_ID
    else:
        with pytest.raises(ValidationError, match="preview"):
            require_preview_instance(cmd, "aio", "rg")
    instances.return_value.show.assert_called_once_with(name="aio", resource_group_name="rg")
    instances.return_value.get_runtime_context.assert_called_once_with(
        record, get_runtime_catalog().qualification_identities, allow_unbundled_integration=True,
    )
    assert "runtime_context" not in vars(cmd)


def test_preview_requirement_reuses_and_validates_command_runtime(mocker, connector_runtime):
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    cmd = SimpleNamespace(runtime_context=connector_runtime)
    if connector_runtime.identity.channel == RuntimeChannel.PREVIEW:
        assert require_preview_instance(cmd, "aio", "rg") == INSTANCE_ID
    else:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            require_preview_instance(cmd, "aio", "rg")
    instances.assert_not_called()


@pytest.mark.parametrize("operation", ["list", "show"])
def test_unready_runtime_fails_before_discovery(mocker, mocked_cmd, connector_runtime, operation):
    from dataclasses import replace

    mocked_cmd.runtime_context = replace(connector_runtime, readiness_issues=(
        RuntimeIssue(RuntimeIssueCode.CLUSTER_CONNECTIVITY, "cluster", "disconnected"),
    ))
    request = mocker.patch(f"{MODULE}.send_raw_request")
    registry = mocker.patch(f"{MODULE}.get_first_party_connectors")
    fetch = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.ConnectorTemplates.fetch_metadata",
    )
    with pytest.raises(ValidationError, match="not ready"):
        if operation == "show":
            show_connector(mocked_cmd, REFERENCE, "aio", "rg")
        else:
            list_connectors(mocked_cmd, "aio", "rg")
    request.assert_not_called()
    registry.assert_not_called()
    fetch.assert_not_called()


def test_discovery_follows_cli_preview_profile_updates(discovery, mocker):
    catalog = mocker.patch("azext_edge.edge.providers.orchestration.runtime_catalog.get_runtime_catalog")
    profile = catalog.return_value.get.return_value
    discovery.registry.list_tags.return_value = ["1.9.0", "1.10.0"]
    discovery.metadata.side_effect = lambda cmd, reference: {
        **discovery.metadata.return_value,
        "aioMetadata": {
            "aioMinVersion": "1.6.0-preview.49" if reference.endswith(":1.10.0") else "1.6.0-preview.1",
        },
    }
    for runtime_version, api_version, connector_version in (
        ("1.6.0-preview.43", "2026-09-01-preview", "1.9.0"),
        ("1.6.0-preview.49", "2026-09-03-preview", "1.10.0"),
    ):
        profile.identity = SimpleNamespace(version=runtime_version)
        profile.iotops_api_version = api_version
        discovery.request.reset_mock()

        result = list_connectors(discovery.cmd, "aio", "rg")

        assert len(result) == 5
        assert all(entry["metadataRef"].endswith(f":{connector_version}") for entry in result)
        discovery.request.assert_called_once_with(
            cli_ctx=discovery.cmd.cli_ctx, method="GET",
            url=f"https://management.azure.com{INSTANCE_ID}/aioApplicationDefinitions?api-version={api_version}",
        )
    assert catalog.return_value.get.call_args_list == [mocker.call(RuntimeChannel.PREVIEW)] * 2


def test_missing_preview_profile_fails_before_discovery(discovery, mocker):
    from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeProfileCatalog

    stable = get_runtime_catalog().get(RuntimeChannel.STABLE)
    mocker.patch(
        "azext_edge.edge.providers.orchestration.runtime_catalog.get_runtime_catalog",
        return_value=RuntimeProfileCatalog([stable]),
    )
    with pytest.raises(ValidationError, match="No reviewed preview runtime profile"):
        list_connectors(discovery.cmd, "aio", "rg")
    discovery.request.assert_not_called()
    discovery.registry.list_tags.assert_not_called()


def test_definition_api_version_and_cloud_are_scoped_to_discovery(discovery, mocker):
    catalog = mocker.patch("azext_edge.edge.providers.orchestration.runtime_catalog.get_runtime_catalog")
    discovery.cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.usgovcloudapi.net/"
    discovery.registry.list_tags.return_value = []
    provider = Connectors(discovery.cmd, api_version="2026-11-01-preview")
    result = provider.list("aio", "rg")
    assert isinstance(result, list) and not result
    discovery.request.assert_called_once_with(
        cli_ctx=discovery.cmd.cli_ctx, method="GET",
        url=(
            f"https://management.usgovcloudapi.net{INSTANCE_ID}"
            "/aioApplicationDefinitions?api-version=2026-11-01-preview"
        ),
    )
    catalog.assert_called_once_with()
    catalog.return_value.get.assert_called_once_with(RuntimeChannel.PREVIEW)


def test_invalid_json_response_is_not_empty_success(discovery):
    discovery.request.return_value.json.side_effect = ValueError("invalid")
    with pytest.raises(AzureResponseError, match="invalid JSON"):
        list_connectors(discovery.cmd, "aio", "rg")


def test_repeated_pagination_fails(discovery):
    collection = f"https://management.azure.com{INSTANCE_ID}/aioApplicationDefinitions"
    api_version = get_runtime_catalog().get(RuntimeChannel.PREVIEW).iotops_api_version
    discovery.request.return_value.json.return_value = {
        "value": [], "nextLink": f"{collection}?api-version={api_version}"
    }
    with pytest.raises(AzureResponseError, match="repeated"):
        list_connectors(discovery.cmd, "aio", "rg")
    discovery.request.assert_called_once()


def test_later_page_failure_does_not_return_partial_results(discovery, mocker):
    collection = f"https://management.azure.com{INSTANCE_ID}/aioApplicationDefinitions"
    api_version = get_runtime_catalog().get(RuntimeChannel.PREVIEW).iotops_api_version
    discovery.request.side_effect = [
        mocker.Mock(json=lambda: {
            "value": [{"name": "purchase", "properties": {
                "applicationMetadataRef": REFERENCE, "applicationSource": "marketplace", "applicationType": "connector",
            }}],
            "nextLink": f"{collection}?api-version={api_version}&$skiptoken=next",
        }),
        AzureResponseError("Denied"),
    ]
    hint = mocker.patch(f"{MODULE}.logger.warning")
    with pytest.raises(AzureResponseError, match="Denied"):
        list_connectors(discovery.cmd, "aio", "rg")
    hint.assert_not_called()


@pytest.mark.parametrize("operation", ["list", "show"])
def test_mismatched_instance_fails_before_discovery(discovery, operation):
    discovery.guard.return_value = INSTANCE_ID.replace("/sub/", "/other-subscription/")
    with pytest.raises(ValidationError, match="does not match"):
        if operation == "show":
            show_connector(discovery.cmd, REFERENCE, "aio", "rg")
        else:
            list_connectors(discovery.cmd, "aio", "rg")
    discovery.request.assert_not_called()
    discovery.metadata.assert_not_called()


@pytest.mark.parametrize("tags", [[], ["1.0.0"]])
def test_interactive_hint_for_populated_and_empty_results(discovery, mocker, tags):
    mocker.patch(f"{MODULE}.sys.stdout.isatty", return_value=True)
    mocker.patch(f"{MODULE}.sys.stderr.isatty", return_value=True)
    discovery.registry.list_tags.return_value = tags
    hint = mocker.patch(f"{MODULE}.logger.warning")
    list_connectors(discovery.cmd, "aio", "rg")
    hint.assert_called_once()
    assert "Purchase additional connectors" in hint.call_args.args[0]


@pytest.mark.parametrize("setting", ["stdout_pipe", "stderr_pipe", "only_errors", "output_none", "config_none"])
def test_hint_suppression(discovery, mocker, setting):
    mocker.patch(f"{MODULE}.sys.stdout.isatty", return_value=setting != "stdout_pipe")
    mocker.patch(f"{MODULE}.sys.stderr.isatty", return_value=setting != "stderr_pipe")
    if setting == "only_errors":
        discovery.cmd.cli_ctx.only_show_errors = True
    if setting == "output_none":
        discovery.cmd.cli_ctx.invocation.data["output"] = "none"
    if setting == "config_none":
        discovery.cmd.cli_ctx.invocation.data = {}
        discovery.cmd.cli_ctx.config.get.return_value = "none"
    hint = mocker.patch(f"{MODULE}.logger.warning")
    list_connectors(discovery.cmd, "aio", "rg")
    hint.assert_not_called()


def test_explicit_output_overrides_config_for_hint(discovery, mocker):
    mocker.patch(f"{MODULE}.sys.stdout.isatty", return_value=True)
    mocker.patch(f"{MODULE}.sys.stderr.isatty", return_value=True)
    discovery.cmd.cli_ctx.config.get.return_value = "none"
    discovery.cmd.cli_ctx.invocation.data["output"] = "table"
    hint = mocker.patch(f"{MODULE}.logger.warning")
    list_connectors(discovery.cmd, "aio", "rg")
    hint.assert_called_once()


@pytest.fixture
def connector_commands(mocker, tmp_path):
    from copy import copy
    from azure.cli.core import AzCli
    from azure.cli.core.commands import AzCliCommandInvoker
    from azure.cli.core.parser import AzCliCommandParser
    from knack.arguments import ignore_type
    from knack.cli import CLI
    from knack.events import EVENT_INVOKER_POST_PARSE_ARGS, EVENT_INVOKER_PRE_PARSE_ARGS
    from azext_edge import OpsExtensionCommandsLoader

    cli = AzCli.__new__(AzCli)
    CLI.__init__(cli, cli_name="az", config_dir=str(tmp_path))
    cli.cloud = mocker.Mock(profile="latest")
    cli.cloud.endpoints.resource_manager = "https://management.azure.com/"
    cli.local_context = SimpleNamespace(is_on=False)
    cli.data["subscription_id"] = "sub"
    cli.data["completer_active"] = False
    invoker = AzCliCommandInvoker.__new__(AzCliCommandInvoker)
    invoker.cli_ctx = cli
    invoker.data = {}
    cli.invocation = invoker
    loader = OpsExtensionCommandsLoader(cli)
    mocker.patch("azext_edge.edge.util.version_check.check_latest")
    mocker.patch("azure.cli.core._profile.Profile.get_raw_token", side_effect=AssertionError("authentication"))
    invoker.commands_loader = loader
    loader.load_command_table([])
    loader.cmd_to_loader_map = {name: [loader] for name in loader.command_table}
    for name in ("iot ops connector list", "iot ops connector show", "iot ops connector template create"):
        loader.command_name = name
        invoker.data["command_string"] = name
        command = loader.command_table[name]
        command.load_arguments()
        loader.load_arguments(name)
        command.update_argument("cmd", ignore_type)
    loader._update_command_definitions()

    def execute(name, arguments, render_help=False):
        from azure.cli.core._help import AzCliHelp

        invoker.data["command_string"] = name
        cli.data["runtime_notice_targets"] = get_runtime_notice_targets(loader.command_table)
        global_parser = AzCliCommandParser.create_global_parser(cli_ctx=cli)
        cli_help = AzCliHelp(cli) if render_help else mocker.Mock()
        if not render_help:
            cli_help.get_examples.return_value = []
        invoker.parser = AzCliCommandParser(
            cli_ctx=cli, cli_help=cli_help, prog="az", parents=[global_parser],
        )
        invoker.parser.load_command_table(loader)
        args = name.split() + arguments
        cli.raise_event(EVENT_INVOKER_PRE_PARSE_ARGS, args=args)
        namespace = invoker.parser.parse_args(args)
        cli.raise_event(EVENT_INVOKER_POST_PARSE_ARGS, command=name, args=namespace)
        job = copy(loader.command_table[name])
        namespace.cmd = namespace._cmd = job
        invoker._validation(namespace)
        return job(invoker._filter_params(namespace))

    return SimpleNamespace(loader=loader, execute=execute)


def test_command_registration_and_required_arguments(connector_commands):
    loader = connector_commands.loader
    listing = loader.command_table["iot ops connector list"]
    showing = loader.command_table["iot ops connector show"]
    creation = loader.command_table["iot ops connector template create"]
    assert listing.arguments["instance"].options_list == ["--instance", "-i"]
    assert listing.arguments["resource_group"].options_list == ["--resource-group", "-g"]
    assert listing.arguments["instance"].options["required"]
    assert listing.arguments["resource_group"].options["required"]
    assert showing.arguments["connector_metadata_ref"].options_list == ["--connector-metadata-ref", "--ref"]
    assert showing.arguments["connector_metadata_ref"].options["required"]
    assert showing.arguments["instance"].options_list == ["--instance", "-i"]
    assert showing.arguments["resource_group"].options_list == ["--resource-group", "-g"]
    assert showing.arguments["instance"].options["required"]
    assert showing.arguments["resource_group"].options["required"]
    assert listing.preview_info and showing.preview_info
    assert listing.runtime_requirement is CONNECTOR_DISCOVERY_REQUIREMENT
    assert listing.runtime_requirement.channels == {RuntimeChannel.PREVIEW}
    assert listing.runtime_target == RuntimeTarget(
        instance_name="instance", resource_group_name="resource_group", allow_unbundled_integration=True,
    )
    assert showing.runtime_requirement is CONNECTOR_DISCOVERY_REQUIREMENT
    assert showing.runtime_target == listing.runtime_target
    assert creation.runtime_requirement is None
    assert "use_preview" not in listing.arguments
    assert "use_preview" not in showing.arguments
    notices = get_runtime_notice_targets(loader.command_table)
    assert "iot ops connector list" in notices
    assert "iot ops connector show" in notices
    assert "iot ops connector template create" not in notices
    assert not getattr(creation, "preview_info", None)
    assert creation.arguments["connector_metadata_ref"].options["required"]


def test_list_command_validates_runtime_once_before_discovery(mocker, connector_commands, connector_runtime):
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    instances.return_value.get_runtime_context.return_value = connector_runtime
    request = mocker.patch(f"{MODULE}.send_raw_request")
    request.return_value.json.return_value = {"value": []}
    registry = mocker.patch(f"{MODULE}.get_first_party_connectors", return_value=())

    if connector_runtime.identity.channel == RuntimeChannel.PREVIEW:
        assert connector_commands.execute("iot ops connector list", ["-i", "aio", "-g", "rg"]) == []
        request.assert_called_once()
        registry.assert_called_once_with(mocker.ANY, connector_runtime.identity.version)
    else:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            connector_commands.execute("iot ops connector list", ["-i", "aio", "-g", "rg"])
        request.assert_not_called()
        registry.assert_not_called()
    instances.return_value.show.assert_called_once_with(name="aio", resource_group_name="rg")
    instances.return_value.get_runtime_context.assert_called_once()
    assert "runtime_context" not in vars(connector_commands.loader.command_table["iot ops connector list"])


@pytest.mark.parametrize("operation", ["list", "show"])
@pytest.mark.parametrize("entry_point", ["command", "provider"])
@pytest.mark.parametrize("version,train,error", [
    ("1.6.0-preview.32", "integration", None),
    ("1.6.0-preview.43", "integration", None),
    ("1.6.0-preview.60", "integration", None),
    ("1.6.0-preview.43", "preview", None),
    ("1.5.7", "stable", "requires a preview runtime"),
    ("1.5.7", "integration", "requires a preview runtime"),
    ("1.6.0-preview.43", "unknown", "no supported runtime profile mapping"),
    (None, "integration", "Unable to validate AIO runtime version"),
    ("", "integration", "Unable to validate AIO runtime version"),
    ("invalid", "integration", "Unable to validate AIO runtime version"),
    ("1.6.1-preview.43", "integration", "conflicts with the preview runtime profile"),
])
def test_discovery_uses_installed_channel_and_cli_profile(
    mocker, connector_commands, operation, entry_point, version, train, error,
):
    from azext_edge.edge.providers.orchestration.runtime_profiles import resolve_runtime_identity

    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    record = {"id": INSTANCE_ID}
    instances.return_value.show.return_value = record

    def discover(instance, qualification_identities, *, allow_unbundled_integration=False):
        identity = resolve_runtime_identity(
            version, train, qualification_identities, allow_unbundled_integration=allow_unbundled_integration,
        )
        return RuntimeContext(
            instance_id=instance["id"], custom_location_id="location", cluster_id="cluster", extension_id="extension",
            identity=identity, requested_version=version, provisioning_state="Succeeded",
        )

    instances.return_value.get_runtime_context.side_effect = discover
    request = mocker.patch(f"{MODULE}.send_raw_request")
    request.return_value.json.return_value = {"value": []}
    registry = mocker.patch(f"{MODULE}.get_first_party_connectors", return_value=())
    metadata = {"name": "sse", "version": "1.0.0"}
    fetch = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.ConnectorTemplates.fetch_metadata",
        return_value=metadata,
    )

    def execute():
        name = f"iot ops connector {operation}"
        if entry_point == "command":
            arguments = ["-i", "aio", "-g", "rg"]
            if operation == "show":
                arguments.extend(["--ref", REFERENCE])
            return connector_commands.execute(name, arguments)
        cmd = connector_commands.loader.command_table[name]
        if operation == "show":
            return show_connector(cmd, REFERENCE, "aio", "rg")
        return list_connectors(cmd, "aio", "rg")

    if error:
        with pytest.raises(ValidationError, match=error):
            execute()
        request.assert_not_called()
        registry.assert_not_called()
        fetch.assert_not_called()
    elif operation == "list":
        assert execute() == []
        request.assert_called_once_with(
            cli_ctx=mocker.ANY, method="GET",
            url=f"https://management.azure.com{INSTANCE_ID}/aioApplicationDefinitions?api-version=2026-11-01-preview",
        )
        registry.assert_called_once_with(mocker.ANY, "1.6.0-preview.59")
        fetch.assert_not_called()
    else:
        assert execute() == {"metadataRef": REFERENCE, "metadata": metadata}
        fetch.assert_called_once_with(mocker.ANY, REFERENCE)
        request.assert_not_called()
        registry.assert_not_called()
    instances.return_value.get_runtime_context.assert_called_once_with(
        record, get_runtime_catalog().qualification_identities, allow_unbundled_integration=True,
    )
    assert get_runtime_catalog().get(RuntimeChannel.PREVIEW).identity.version == "1.6.0-preview.59"


@pytest.mark.parametrize("name", [
    "iot ops connector list", "iot ops connector show", "iot ops connector template create",
])
def test_connector_help_is_offline(mocker, connector_commands, name, caplog):
    from azext_edge.edge.providers.orchestration.runtime_commands import PREVIEW_RUNTIME_NOTICE

    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    registry = mocker.patch(f"{MODULE}.get_oci_client")
    with pytest.raises(SystemExit) as result:
        connector_commands.execute(name, ["--help"])
    assert result.value.code == 0
    assert caplog.messages.count(PREVIEW_RUNTIME_NOTICE) == int(name != "iot ops connector template create")
    instances.assert_not_called()
    registry.assert_not_called()


@pytest.mark.parametrize("operation", ["list", "show"])
def test_connector_help_rendering(mocker, connector_commands, operation, capsys):
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    registry = mocker.patch(f"{MODULE}.get_oci_client")
    name = f"iot ops connector {operation}"
    with pytest.raises(SystemExit) as result:
        connector_commands.execute(name, ["--help"], render_help=True)
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert name in output
    assert "--instance" in output and "--resource-group" in output
    assert all(len(line) <= 100 for line in output.splitlines())
    if operation == "list":
        assert MARKETPLACE_URL in output
        assert "bundled preview runtime" in output
    else:
        assert "--connector-metadata-ref" in output
        assert "Running connector list first is not required." in output
    instances.assert_not_called()
    registry.assert_not_called()


def test_show_command_independently_validates_runtime_once(mocker, connector_commands, connector_runtime):
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    instances.return_value.get_runtime_context.return_value = connector_runtime
    metadata = {"name": "sse", "version": "1.0.0"}
    fetch = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.ConnectorTemplates.fetch_metadata",
        return_value=metadata,
    )
    arguments = ["-i", "aio", "-g", "rg", "--ref", REFERENCE]
    if connector_runtime.identity.channel == RuntimeChannel.PREVIEW:
        assert connector_commands.execute("iot ops connector show", arguments) == {
            "metadataRef": REFERENCE, "metadata": metadata,
        }
        fetch.assert_called_once_with(mocker.ANY, REFERENCE)
    else:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            connector_commands.execute("iot ops connector show", arguments)
        fetch.assert_not_called()
    instances.return_value.show.assert_called_once_with(name="aio", resource_group_name="rg")
    instances.return_value.get_runtime_context.assert_called_once()
    assert "runtime_context" not in vars(connector_commands.loader.command_table["iot ops connector show"])


@pytest.mark.parametrize("arguments", [
    ["--ref", REFERENCE], ["-i", "aio", "--ref", REFERENCE],
    ["-g", "rg", "--ref", REFERENCE], ["-i", "aio", "-g", "rg"],
])
def test_show_requires_instance_resource_group_and_reference(mocker, connector_commands, arguments, caplog):
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    fetch = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.ConnectorTemplates.fetch_metadata",
    )
    with pytest.raises(SystemExit) as error:
        connector_commands.execute("iot ops connector show", arguments)
    assert error.value.code == 2
    assert "required" in caplog.text
    instances.assert_not_called()
    fetch.assert_not_called()


@pytest.mark.parametrize("reference", ["", "rest-metadata:1", "registry/path-metadata:1", "user:secret@host/repo:tag"])
@pytest.mark.parametrize("entry_point", ["command", "provider"])
def test_show_rejects_invalid_references_without_echoing_credentials(
    discovery, reference, entry_point, mocker, connector_commands,
):
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    with pytest.raises(InvalidArgumentValueError) as error:
        if entry_point == "command":
            connector_commands.execute("iot ops connector show", ["-i", "aio", "-g", "rg", "--ref", reference])
        else:
            show_connector(discovery.cmd, reference, "aio", "rg")
    assert "secret" not in str(error.value)
    instances.assert_not_called()
    discovery.guard.assert_not_called()
    discovery.request.assert_not_called()
    discovery.registry.list_tags.assert_not_called()
    discovery.metadata.assert_not_called()


def test_show_connector_preserves_metadata_for_preview_instance(discovery):
    reference = "example.azurecr.io/connectors/rest-metadata:1.0.0"
    metadata = {"name": "rest", "version": "1.0.0", "extra": {"preserved": True}}
    discovery.metadata.return_value = metadata
    result = show_connector(discovery.cmd, reference, "aio", "rg")

    assert result == {"metadataRef": reference, "metadata": metadata}
    discovery.guard.assert_called_once_with(discovery.cmd, "aio", "rg")
    discovery.metadata.assert_called_once_with(discovery.cmd, reference)
    assert connector_show_table(result) == {"Name": "rest", "Version": "1.0.0", "MetadataRef": reference}
    assert list(connector_show_table(result)) == ["Name", "Version", "MetadataRef"]


def test_show_connector_rejects_non_object_metadata(discovery):
    discovery.metadata.return_value = []
    with pytest.raises(ValidationError, match="JSON object"):
        show_connector(discovery.cmd, "example.azurecr.io/connectors/rest-metadata:1.0.0", "aio", "rg")
