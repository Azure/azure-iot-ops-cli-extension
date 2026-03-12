# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Unit tests for connector template commands."""

from typing import Dict, Optional
from copy import deepcopy
import pytest
import responses

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ValidationError,
)
from azext_edge.edge.util.az_client import parse_resource_id
from azext_edge.edge.commands_connector import (
    create_connector_template,
    update_connector_template,
    show_connector_template,
    delete_connector_template,
    list_connector_templates,
)
from azext_edge.edge.providers.orchestration.resources.connector_templates import (
    ConnectorTemplates,
    DEFAULT_LOG_LEVEL,
)

from ....generators import generate_random_string, get_zeroed_subscription


# Path for mocking
CONNECTOR_TEMPLATES_PATH = "azext_edge.edge.providers.orchestration.resources.connector_templates"


# =====================
# Fixtures
# =====================


@pytest.fixture()
def mocked_get_resource_client(mocker):
    """Mock the resource client to prevent isodate import issues."""
    patched = mocker.patch(
        "azext_edge.edge.util.queryable.get_resource_client",
    )
    yield patched


@pytest.fixture()
def mocked_get_extended_location(mocker):
    """Mock get_extended_location to prevent actual API calls."""
    result = {
        "type": "CustomLocation",
        "name": generate_random_string(),
        "cluster_location": generate_random_string(),
        "namespace": parse_resource_id(
            f"/subscriptions/{get_zeroed_subscription()}/resourceGroups/{generate_random_string()}"
            f"/providers/Microsoft.DeviceRegistry/namespaces/{generate_random_string()}"
        )
    }
    mock = mocker.patch(
        "azext_edge.edge.providers.adr.helpers.get_extended_location",
        return_value=result,
        autospec=True
    )
    mock.original_return_value = deepcopy(result)
    yield mock


@pytest.fixture()
def mocked_get_iotops_mgmt_client(mocker, mocked_get_resource_client, mocked_instances):
    """Mock the IoT Operations management client via Instances."""
    # Return a mock that exposes the iotops_mgmt_client from mocked_instances
    mock = mocker.MagicMock()
    mock.return_value = mocked_instances.iotops_mgmt_client
    yield mock


@pytest.fixture()
def mocked_fetch_connector_metadata(mocker):
    """Mock the _fetch_connector_metadata method."""
    sample_metadata = {
        "name": "test-connector",
        "version": "1.0.0",
        "imageConfigurationSettings": {
            "imageName": "test/connector",
            "tag": "1.0.0",
        },
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.Http",
                "version": "1.0",
            }
        ],
        "aioMetadata": {
            "aioMinVersion": "1.0.0",
            "aioMaxVersion": "2.0.0",
        },
        "recommendedReplicas": 2,
    }
    mock = mocker.patch(
        f"{CONNECTOR_TEMPLATES_PATH}.ConnectorTemplates._fetch_connector_metadata",
        return_value=sample_metadata,
    )
    yield mock


@pytest.fixture()
def mocked_wait_for_terminal_state(mocker):
    """Mock wait_for_terminal_state function."""
    mock = mocker.patch(
        f"{CONNECTOR_TEMPLATES_PATH}.wait_for_terminal_state",
    )
    yield mock


@pytest.fixture()
def mocked_should_continue_prompt(mocker):
    """Mock should_continue_prompt function."""
    mock = mocker.patch(
        f"{CONNECTOR_TEMPLATES_PATH}.should_continue_prompt",
        return_value=True,
    )
    yield mock


@pytest.fixture()
def mocked_instances(mocker, mocked_get_resource_client):
    """Mock the Instances class for secret sync validation and iotops_mgmt_client."""
    mock_instances = mocker.MagicMock()
    # Set up a mock iotops_mgmt_client on the instances mock
    mock_instances.iotops_mgmt_client = mocker.MagicMock()
    mocker.patch(
        f"{CONNECTOR_TEMPLATES_PATH}.Instances",
        return_value=mock_instances,
    )
    yield mock_instances


# =====================
# Helper Functions
# =====================


def get_connector_template_id(
    template_name: str,
    resource_group: str,
    instance_name: str,
    subscription: Optional[str] = None,
) -> str:
    """Generate connector template resource ID."""
    subscription = subscription or get_zeroed_subscription()
    return (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.IoTOperations/instances/{instance_name}"
        f"/akriConnectorTemplates/{template_name}"
    )


def get_connector_template_mgmt_uri(
    template_name: Optional[str] = None,
    resource_group: Optional[str] = None,
    instance_name: Optional[str] = None,
    subscription: Optional[str] = None,
) -> str:
    """Generate management API URL for connector template."""
    subscription = subscription or get_zeroed_subscription()
    base = f"https://management.azure.com/subscriptions/{subscription}"
    if resource_group:
        base += f"/resourceGroups/{resource_group}"
    base += f"/providers/Microsoft.IoTOperations/instances/{instance_name}"
    if template_name:
        base += f"/akriConnectorTemplates/{template_name}"
    else:
        base += "/akriConnectorTemplates"
    return base


def get_instance_mgmt_uri(
    instance_name: str,
    resource_group: str,
    subscription: Optional[str] = None,
) -> str:
    """Generate management API URL for IoT Operations instance."""
    subscription = subscription or get_zeroed_subscription()
    return (
        f"https://management.azure.com/subscriptions/{subscription}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.IoTOperations/instances/{instance_name}"
    )


def get_sample_metadata(
    name: str = "test-connector",
    version: str = "1.0.0",
    endpoint_type: str = "Microsoft.Http",
) -> dict:
    """Generate sample connector metadata."""
    return {
        "name": name,
        "version": version,
        "imageConfigurationSettings": {
            "imageName": "azureiotoperations/akri-connectors/test",
            "tag": version,
        },
        "inboundEndpoints": [
            {
                "endpointType": endpoint_type,
                "version": "1.0",
            }
        ],
        "aioMetadata": {
            "aioMinVersion": "1.0.0",
            "aioMaxVersion": "2.0.0",
        },
        "recommendedReplicas": 2,
    }


def get_sample_connector_template_record(
    template_name: str,
    resource_group: str,
    instance_name: str,
    version: str = "1.0.0",
    endpoint_type: str = "Microsoft.Http",
    replicas: int = 1,
    provisioning_state: str = "Succeeded",
) -> dict:
    """Generate sample connector template resource."""
    return {
        "id": get_connector_template_id(template_name, resource_group, instance_name),
        "name": template_name,
        "type": "Microsoft.IoTOperations/instances/akriConnectorTemplates",
        "systemData": {
            "createdAt": "2025-01-01T00:00:00Z",
            "lastModifiedAt": "2025-01-01T00:00:00Z",
        },
        "properties": {
            "provisioningState": provisioning_state,
            "connectorMetadataRef": f"mcr.microsoft.com/test/connector-metadata:{version}",
            "deviceInboundEndpointTypes": [
                {
                    "endpointType": endpoint_type,
                    "version": "1.0",
                }
            ],
            "runtimeConfiguration": {
                "runtimeConfigurationType": "ManagedConfiguration",
                "managedConfigurationSettings": {
                    "managedConfigurationType": "ImageConfiguration",
                    "imageConfigurationSettings": {
                        "imageName": "test/connector",
                        "replicas": replicas,
                        "tagDigestSettings": {
                            "tagDigestType": "Tag",
                            "tag": version,
                        },
                        "registrySettings": {
                            "registrySettingsType": "ContainerRegistry",
                            "containerRegistrySettings": {
                                "registry": "mcr.microsoft.com",
                            },
                        },
                    },
                },
            },
            "diagnostics": {
                "logs": {
                    "level": "info",
                },
            },
            "aioMetadata": {
                "aioMinVersion": "1.0.0",
                "aioMaxVersion": "2.0.0",
            },
        },
        "extendedLocation": {
            "name": generate_random_string(),
            "type": "CustomLocation",
        },
    }


# =====================
# Helper Method Tests
# =====================


class TestIsClearSignal:
    """Tests for _is_clear_signal static method."""

    def test_none_returns_false(self):
        assert ConnectorTemplates._is_clear_signal(None) is False

    def test_empty_string_returns_true(self):
        assert ConnectorTemplates._is_clear_signal("") is True

    def test_non_empty_string_returns_false(self):
        assert ConnectorTemplates._is_clear_signal("test") is False

    def test_empty_list_returns_true(self):
        assert ConnectorTemplates._is_clear_signal([]) is True

    def test_list_with_empty_string_returns_true(self):
        assert ConnectorTemplates._is_clear_signal([""]) is True

    def test_list_with_values_returns_false(self):
        assert ConnectorTemplates._is_clear_signal(["test"]) is False

    def test_other_types_return_false(self):
        assert ConnectorTemplates._is_clear_signal(123) is False
        assert ConnectorTemplates._is_clear_signal({}) is False


class TestSplitImageReference:
    """Tests for _split_image_reference method."""

    def test_mcr_reference(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        registry, image_name = provider._split_image_reference(
            "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6"
        )
        assert registry == "mcr.microsoft.com"
        assert image_name == "azureiotoperations/akri-connectors/rest"

    def test_acr_reference(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        registry, image_name = provider._split_image_reference(
            "myacr.azurecr.io/connectors/test-metadata:1.0.0"
        )
        assert registry == "myacr.azurecr.io"
        assert image_name == "connectors/test"

    def test_handles_exception(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        # Invalid format - should return fallback
        registry, image_name = provider._split_image_reference("invalid")
        assert registry == ""
        assert image_name == "invalid"


class TestIsValidVersionUpgrade:
    """Tests for _is_valid_version_upgrade method."""

    def test_patch_upgrade_allowed(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert provider._is_valid_version_upgrade("1.0.5", "1.0.6") is True

    def test_minor_upgrade_allowed(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert provider._is_valid_version_upgrade("1.0.6", "1.1.0") is True

    def test_major_upgrade_blocked(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert provider._is_valid_version_upgrade("1.0.6", "2.0.0") is False

    def test_downgrade_blocked(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert provider._is_valid_version_upgrade("1.0.6", "1.0.5") is False

    def test_same_version_allowed(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert provider._is_valid_version_upgrade("1.0.6", "1.0.6") is True

    def test_short_versions_rejected(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        # Versions must be in full semver format (major.minor.patch)
        assert provider._is_valid_version_upgrade("1.0", "1.1") is False
        assert provider._is_valid_version_upgrade("1", "2") is False

    def test_invalid_version_format(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert provider._is_valid_version_upgrade("invalid", "1.0.0") is False
        assert provider._is_valid_version_upgrade("1.0.0", "invalid") is False


class TestValidateMetadata:
    """Tests for _validate_metadata method."""

    def test_valid_metadata_passes(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        # Should not raise
        provider._validate_metadata(metadata, "test-ref")

    def test_missing_name_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        del metadata["name"]
        with pytest.raises(ValidationError) as exc:
            provider._validate_metadata(metadata, "test-ref")
        assert "name" in str(exc.value)

    def test_missing_version_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        del metadata["version"]
        with pytest.raises(ValidationError) as exc:
            provider._validate_metadata(metadata, "test-ref")
        assert "version" in str(exc.value)

    def test_missing_image_config_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        del metadata["imageConfigurationSettings"]
        with pytest.raises(ValidationError) as exc:
            provider._validate_metadata(metadata, "test-ref")
        assert "imageConfigurationSettings" in str(exc.value)

    def test_missing_inbound_endpoints_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        del metadata["inboundEndpoints"]
        with pytest.raises(ValidationError) as exc:
            provider._validate_metadata(metadata, "test-ref")
        assert "inboundEndpoints" in str(exc.value)

    def test_missing_image_name_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        del metadata["imageConfigurationSettings"]["imageName"]
        with pytest.raises(ValidationError) as exc:
            provider._validate_metadata(metadata, "test-ref")
        assert "imageName" in str(exc.value)


class TestParseSecrets:
    """Tests for _parse_secrets method."""

    def test_empty_list_returns_empty(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert not provider._parse_secrets([])
        assert not provider._parse_secrets(None)

    def test_valid_secret_parsed(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretRef=my-secret", "secretKey=password", "secretAlias=dbPassword"]]
        result = provider._parse_secrets(secrets)
        assert len(result) == 1
        assert result[0]["secretRef"] == "my-secret"
        assert result[0]["secretKey"] == "password"
        assert result[0]["secretAlias"] == "dbPassword"

    def test_flat_list_format(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        # Single secret as flat list (alternative input style)
        secrets = ["secretRef=my-secret", "secretKey=password", "secretAlias=dbPassword"]
        result = provider._parse_secrets(secrets)
        assert len(result) == 1
        assert result[0]["secretRef"] == "my-secret"

    def test_quoted_string_format(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        # User wrapped in quotes
        secrets = [["secretRef=my-secret secretKey=password secretAlias=dbPassword"]]
        result = provider._parse_secrets(secrets)
        assert len(result) == 1
        assert result[0]["secretRef"] == "my-secret"

    def test_missing_secret_ref_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretKey=password", "secretAlias=dbPassword"]]
        with pytest.raises(RequiredArgumentMissingError) as exc:
            provider._parse_secrets(secrets)
        assert "secretRef" in str(exc.value)

    def test_missing_secret_key_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretRef=my-secret", "secretAlias=dbPassword"]]
        with pytest.raises(RequiredArgumentMissingError) as exc:
            provider._parse_secrets(secrets)
        assert "secretKey" in str(exc.value)

    def test_missing_secret_alias_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretRef=my-secret", "secretKey=password"]]
        with pytest.raises(RequiredArgumentMissingError) as exc:
            provider._parse_secrets(secrets)
        assert "secretAlias" in str(exc.value)

    def test_invalid_secret_ref_format_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretRef=invalid!ref", "secretKey=password", "secretAlias=dbPassword"]]
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._parse_secrets(secrets)
        assert "secretRef" in str(exc.value)

    def test_invalid_secret_key_format_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretRef=my-secret", "secretKey=invalid!key", "secretAlias=dbPassword"]]
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._parse_secrets(secrets)
        assert "secretKey" in str(exc.value)

    def test_invalid_secret_alias_format_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [["secretRef=my-secret", "secretKey=password", "secretAlias=invalid!alias"]]
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._parse_secrets(secrets)
        assert "secretAlias" in str(exc.value)

    def test_duplicate_alias_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [
            ["secretRef=my-secret", "secretKey=password1", "secretAlias=sameAlias"],
            ["secretRef=my-secret", "secretKey=password2", "secretAlias=sameAlias"],
        ]
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._parse_secrets(secrets)
        assert "Duplicate secretAlias" in str(exc.value)

    def test_duplicate_secret_key_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [
            ["secretRef=my-secret", "secretKey=sameKey", "secretAlias=alias1"],
            ["secretRef=my-secret", "secretKey=sameKey", "secretAlias=alias2"],
        ]
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._parse_secrets(secrets)
        assert "Duplicate secretKey" in str(exc.value)

    def test_different_secret_refs_fail(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        secrets = [
            ["secretRef=secret1", "secretKey=key1", "secretAlias=alias1"],
            ["secretRef=secret2", "secretKey=key2", "secretAlias=alias2"],
        ]
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._parse_secrets(secrets)
        assert "same secretRef" in str(exc.value)


class TestParseStorageVolumes:
    """Tests for _parse_storage_volumes method."""

    def test_empty_list_returns_empty(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        assert not provider._parse_storage_volumes([])
        assert not provider._parse_storage_volumes(None)

    def test_valid_volume_parsed(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        volumes = ["claimName=myPVC mountPath=/data"]
        result = provider._parse_storage_volumes(volumes)
        assert len(result) == 1
        assert result[0]["claimName"] == "myPVC"
        assert result[0]["mountPath"] == "/data"

    def test_missing_claim_name_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        volumes = ["mountPath=/data"]
        with pytest.raises(RequiredArgumentMissingError) as exc:
            provider._parse_storage_volumes(volumes)
        assert "claimName" in str(exc.value)

    def test_missing_mount_path_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        volumes = ["claimName=myPVC"]
        with pytest.raises(RequiredArgumentMissingError) as exc:
            provider._parse_storage_volumes(volumes)
        assert "mountPath" in str(exc.value)


class TestExtractTemplateSummary:
    """Tests for _extract_template_summary method."""

    def test_extracts_all_fields(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        template = get_sample_connector_template_record(
            template_name="test-template",
            resource_group="test-rg",
            instance_name="test-instance",
            version="1.0.0",
            endpoint_type="Microsoft.Http",
            replicas=3,
        )
        summary = provider._extract_template_summary(template)

        assert summary["name"] == "test-template"
        assert summary["connectorType"] == "Microsoft.Http"
        assert summary["version"] == "1.0"
        assert summary["replicas"] == 3
        assert summary["provisioningState"] == "Succeeded"
        assert "createdAt" in summary
        assert "lastModifiedAt" in summary

    def test_handles_missing_fields(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        template = {"name": "test", "properties": {}}
        summary = provider._extract_template_summary(template)

        assert summary["name"] == "test"
        assert summary["connectorType"] == ""
        assert summary["version"] == ""
        assert summary["replicas"] == 1  # default
        assert summary["provisioningState"] == ""


# =====================
# FetchConnectorMetadata Tests
# =====================


class TestFetchConnectorMetadata:
    """Tests for _fetch_connector_metadata method."""

    def test_empty_metadata_ref_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        with pytest.raises(RequiredArgumentMissingError):
            provider._fetch_connector_metadata("")

    def test_invalid_format_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._fetch_connector_metadata("invalid-format")
        assert "Expected format" in str(exc.value)

    def test_invalid_format_no_tag_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        with pytest.raises(InvalidArgumentValueError):
            provider._fetch_connector_metadata("mcr.microsoft.com/test/connector-metadata")


# =====================
# Build Template Properties Tests
# =====================


class TestBuildTemplateProperties:
    """Tests for _build_template_properties method."""

    def test_basic_properties(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        metadata_ref = "mcr.microsoft.com/test/connector-metadata:1.0.0"

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref=metadata_ref,

            replicas=3,
            log_level="debug",
            image_pull_policy="Always",
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref=None,
        )

        assert properties["connectorMetadataRef"] == metadata_ref
        assert properties["diagnostics"]["logs"]["level"] == "debug"

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        image_config = managed_config["imageConfigurationSettings"]
        assert image_config["replicas"] == 3
        assert image_config["imagePullPolicy"] == "Always"

    def test_with_private_registry(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        """Test that private registry uses ContainerRegistry type."""
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        metadata_ref = "myacr.azurecr.io/test/connector-metadata:1.0.0"

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref=metadata_ref,
            replicas=None,
            log_level=None,
            image_pull_policy=None,
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref=None,
        )

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        image_config = managed_config["imageConfigurationSettings"]
        registry_settings = image_config["registrySettings"]

        assert registry_settings["registrySettingsType"] == "ContainerRegistry"
        assert registry_settings["containerRegistrySettings"]["registry"] == "myacr.azurecr.io"

    def test_with_image_pull_secrets(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        metadata_ref = "mcr.microsoft.com/test/connector-metadata:1.0.0"

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref=metadata_ref,

            replicas=None,
            log_level=None,
            image_pull_policy=None,
            image_pull_secrets=["secret1", "secret2"],
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref=None,
        )

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        image_config = managed_config["imageConfigurationSettings"]
        registry_settings = image_config["registrySettings"]

        assert registry_settings["registrySettingsType"] == "ContainerRegistry"
        pull_secrets = registry_settings["containerRegistrySettings"]["imagePullSecrets"]
        assert len(pull_secrets) == 2
        assert pull_secrets[0]["secretRef"] == "secret1"

    def test_invalid_image_pull_policy_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()

        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._build_template_properties(
                metadata=metadata,
                connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

                replicas=None,
                log_level=None,
                image_pull_policy="InvalidPolicy",
                image_pull_secrets=None,
                allocation_policy=None,
                bucket_size=None,
                secrets=None,
                storage_volumes=None,
                connector_config=None,
                trust_settings_secret_ref=None,
            )
        assert "image pull policy" in str(exc.value).lower()

    def test_image_pull_policy_case_insensitive(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

            replicas=None,
            log_level=None,
            image_pull_policy="always",  # lowercase
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref=None,
        )

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        image_config = managed_config["imageConfigurationSettings"]
        assert image_config["imagePullPolicy"] == "Always"  # normalized

    def test_invalid_allocation_policy_fails(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()

        with pytest.raises(InvalidArgumentValueError) as exc:
            provider._build_template_properties(
                metadata=metadata,
                connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

                replicas=None,
                log_level=None,
                image_pull_policy=None,
                image_pull_secrets=None,
                allocation_policy="InvalidPolicy",
                bucket_size=None,
                secrets=None,
                storage_volumes=None,
                connector_config=None,
                trust_settings_secret_ref=None,
            )
        assert "allocation policy" in str(exc.value).lower()

    def test_with_connector_config(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

            replicas=None,
            log_level=None,
            image_pull_policy=None,
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=["key1=value1", "key2=value2"],
            trust_settings_secret_ref=None,
        )

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        assert "additionalConfiguration" in managed_config
        assert managed_config["additionalConfiguration"]["key1"] == "value1"
        assert managed_config["additionalConfiguration"]["key2"] == "value2"

    def test_with_trust_settings(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

            replicas=None,
            log_level=None,
            image_pull_policy=None,
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref="my-trust-secret",
        )

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        assert managed_config["trustSettings"]["trustListSecretRef"] == "my-trust-secret"

    def test_uses_recommended_replicas_from_metadata(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()
        metadata["recommendedReplicas"] = 5

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

            replicas=None,  # Not specified
            log_level=None,
            image_pull_policy=None,
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref=None,
        )

        managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
        image_config = managed_config["imageConfigurationSettings"]
        assert image_config["replicas"] == 5

    def test_default_log_level(self, mocked_cmd, mocked_get_iotops_mgmt_client):
        provider = ConnectorTemplates(mocked_cmd)
        metadata = get_sample_metadata()

        properties = provider._build_template_properties(
            metadata=metadata,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

            replicas=None,
            log_level=None,  # Not specified
            image_pull_policy=None,
            image_pull_secrets=None,
            allocation_policy=None,
            bucket_size=None,
            secrets=None,
            storage_volumes=None,
            connector_config=None,
            trust_settings_secret_ref=None,
        )

        assert properties["diagnostics"]["logs"]["level"] == DEFAULT_LOG_LEVEL


# =====================
# Command Tests with Mocked Responses
# =====================


@pytest.mark.parametrize("req", [
    {},
    {
        "replicas": 3,
        "log_level": "debug",
        "image_pull_policy": "Always",
    },
    {
        "replicas": 5,
        "image_pull_secrets": ["secret1", "secret2"],
        "connector_config": ["key1=value1"],
        "trust_settings_secret_ref": "my-trust-secret",
    },
])
def test_connector_template_create(
    mocked_cmd,
    mocked_get_extended_location,
    mocked_get_iotops_mgmt_client,
    mocked_fetch_connector_metadata,
    mocked_responses: responses,
    mocked_wait_for_terminal_state,
    req: Dict,
):
    """Test connector template create command."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()
    metadata_ref = "mcr.microsoft.com/test/connector-metadata:1.0.0"

    mock_template_record = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_wait_for_terminal_state.return_value = mock_template_record

    result = create_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        connector_metadata_ref=metadata_ref,
        **req
    )

    assert result == mock_template_record
    mocked_fetch_connector_metadata.assert_called_once_with(metadata_ref)
    mocked_get_extended_location.assert_called_once()


def test_connector_template_show(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_responses: responses,
):
    """Test connector template show command."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    mock_template_record = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    # Mock the get operation
    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = mock_template_record

    result = show_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
    )

    assert result == mock_template_record
    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.assert_called_once_with(
        resource_group_name=resource_group,
        instance_name=instance_name,
        akri_connector_template_name=template_name,
    )


def test_connector_template_delete(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_responses: responses,
    mocked_wait_for_terminal_state,
    mocked_should_continue_prompt,
):
    """Test connector template delete command."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    mock_template_record = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    # Mock get (for existence check)
    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = mock_template_record

    # Mock should_continue_prompt to return True
    mocked_should_continue_prompt.return_value = True

    mocked_wait_for_terminal_state.return_value = None

    result = delete_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        confirm_yes=True,
    )

    assert result is None
    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_delete.assert_called_once()


def test_connector_template_delete_bails_on_no_confirm(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_should_continue_prompt,
):
    """Test connector template delete bails when user doesn't confirm."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    mock_template_record = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = mock_template_record
    mocked_should_continue_prompt.return_value = False

    result = delete_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        confirm_yes=False,
    )

    # Should return None and not call delete
    assert result is None
    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_delete.assert_not_called()


def test_connector_template_list(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
):
    """Test connector template list command."""
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    mock_templates = [
        get_sample_connector_template_record(
            template_name=f"template-{i}",
            resource_group=resource_group,
            instance_name=instance_name,
            endpoint_type=f"Microsoft.Type{i}",
        )
        for i in range(3)
    ]

    mgmt_client = mocked_get_iotops_mgmt_client.return_value
    mgmt_client.akri_connector_template.list_by_instance_resource.return_value = mock_templates

    result = list_connector_templates(
        cmd=mocked_cmd,
        resource_group=resource_group,
        instance=instance_name,
    )

    assert len(result) == 3
    for i, summary in enumerate(result):
        assert summary["name"] == f"template-{i}"
        assert summary["connectorType"] == f"Microsoft.Type{i}"


@pytest.mark.parametrize("update_params", [
    {"replicas": 5},
    {"log_level": "warning"},
    {"image_pull_policy": "Never"},
    {"connector_config": ["newKey=newValue"]},
    {"trust_settings_secret_ref": "new-trust-secret"},
])
def test_connector_template_update(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
    update_params: Dict,
):
    """Test connector template update command with various parameters."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    updated_template = deepcopy(existing_template)

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = updated_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        **update_params
    )

    assert result == updated_template
    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.assert_called_once()


def test_connector_template_update_clears_secrets(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test that update can clear secrets with empty string."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )
    # Add existing secrets
    existing_template["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]["secrets"] = [
        {"secretRef": "old", "secretKey": "key", "secretAlias": "alias"}
    ]

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        secrets=[""],  # Clear signal
    )

    assert result == existing_template

    # Verify secrets were removed
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_config = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "secrets" not in managed_config


def test_connector_template_update_version_upgrade(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_fetch_connector_metadata,
    mocked_wait_for_terminal_state,
):
    """Test connector template update with metadata ref version upgrade."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
        version="1.0.0",
    )

    new_metadata = get_sample_metadata(version="1.0.1")
    mocked_fetch_connector_metadata.return_value = new_metadata

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.1",
    )

    assert result == existing_template
    mocked_fetch_connector_metadata.assert_called_once()


def test_connector_template_update_major_version_fails(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_fetch_connector_metadata,
):
    """Test that major version upgrade is blocked."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
        version="1.0.0",
    )

    new_metadata = get_sample_metadata(version="2.0.0")
    mocked_fetch_connector_metadata.return_value = new_metadata

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template

    with pytest.raises(ValidationError) as exc:
        update_connector_template(
            cmd=mocked_cmd,
            name=template_name,
            resource_group=resource_group,
            instance=instance_name,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:2.0.0",
        )

    assert "major version" in str(exc.value).lower()


def test_connector_template_update_endpoint_type_mismatch_fails(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_fetch_connector_metadata,
):
    """Test that endpoint type mismatch is blocked."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
        endpoint_type="Microsoft.Http",
    )

    new_metadata = get_sample_metadata(endpoint_type="Microsoft.Mqtt")
    new_metadata["version"] = "1.0.1"
    mocked_fetch_connector_metadata.return_value = new_metadata

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template

    with pytest.raises(ValidationError) as exc:
        update_connector_template(
            cmd=mocked_cmd,
            name=template_name,
            resource_group=resource_group,
            instance=instance_name,
            connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.1",
        )

    assert "endpoint type mismatch" in str(exc.value).lower()


# =====================
# Additional Coverage Tests
# =====================


def test_connector_template_update_with_allocation_policy(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test update with Bucketized allocation policy and bucket size."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        allocation_policy="Bucketized",
        bucket_size=10,
    )

    assert result == existing_template

    # Verify the allocation policy was set
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_config = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    assert managed_config["allocation"]["policy"] == "Bucketized"
    assert managed_config["allocation"]["bucketSize"] == 10


def test_connector_template_update_invalid_allocation_policy(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
):
    """Test update with invalid allocation policy fails."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template

    with pytest.raises(InvalidArgumentValueError) as exc:
        update_connector_template(
            cmd=mocked_cmd,
            name=template_name,
            resource_group=resource_group,
            instance=instance_name,
            allocation_policy="InvalidPolicy",
        )

    assert "allocation policy" in str(exc.value).lower()


def test_connector_template_update_clears_image_pull_secrets(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test that update can clear image pull secrets with empty string."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )
    # Add existing image pull secrets
    managed_config = existing_template["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    managed_config["imageConfigurationSettings"]["registrySettings"] = {
        "registrySettingsType": "ContainerRegistry",
        "containerRegistrySettings": {
            "registry": "mcr.microsoft.com",
            "imagePullSecrets": [{"secretRef": "old-secret"}]
        }
    }

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        image_pull_secrets=[""],  # Clear signal
    )

    assert result == existing_template

    # Verify image pull secrets were cleared
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_settings = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    image_config = managed_settings["imageConfigurationSettings"]
    assert "imagePullSecrets" not in image_config.get("registrySettings", {}).get("containerRegistrySettings", {})


def test_connector_template_update_with_storage_volumes(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test update with storage volumes."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        storage_volumes=["claimName=myPVC mountPath=/data"],
    )

    assert result == existing_template

    # Verify storage volumes were set
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_config = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "persistentVolumeClaims" in managed_config
    assert managed_config["persistentVolumeClaims"][0]["claimName"] == "myPVC"
    assert managed_config["persistentVolumeClaims"][0]["mountPath"] == "/data"


def test_connector_template_update_clears_storage_volumes(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test that update can clear storage volumes."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )
    # Add existing storage volumes
    managed_config = existing_template["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    managed_config["persistentVolumeClaims"] = [
        {"claimName": "old-pvc", "mountPath": "/old-data"}
    ]

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        storage_volumes=[""],  # Clear signal
    )

    assert result == existing_template

    # Verify storage volumes were cleared
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_config = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "persistentVolumeClaims" not in managed_config


def test_connector_template_update_clears_trust_settings(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test that update can clear trust settings."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )
    # Add existing trust settings
    existing_template["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]["trustSettings"] = {
        "trustListSecretRef": "old-trust-secret"
    }

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        trust_settings_secret_ref="",  # Clear signal
    )

    assert result == existing_template

    # Verify trust settings were cleared
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_config = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "trustSettings" not in managed_config


def test_connector_template_update_clears_connector_config(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test that update can clear connector config."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )
    # Add existing additional configuration
    managed_config = existing_template["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    managed_config["additionalConfiguration"] = {
        "oldKey": "oldValue"
    }

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        connector_config=[""],  # Clear signal
    )

    assert result == existing_template

    # Verify additional configuration was cleared
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_config = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "additionalConfiguration" not in managed_config


def test_connector_template_update_with_new_image_pull_secrets(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_wait_for_terminal_state,
):
    """Test update adding new image pull secrets."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        image_pull_secrets=["new-secret-1", "new-secret-2"],
    )

    assert result == existing_template
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_settings = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    image_config = managed_settings["imageConfigurationSettings"]
    pull_secrets = image_config["registrySettings"]["containerRegistrySettings"]["imagePullSecrets"]
    assert len(pull_secrets) == 2
    assert pull_secrets[0]["secretRef"] == "new-secret-1"
    assert pull_secrets[1]["secretRef"] == "new-secret-2"


def test_connector_template_update_with_metadata_digest(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_fetch_connector_metadata,
    mocked_wait_for_terminal_state,
):
    """Test update with metadata containing digest instead of tag."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
        version="1.0.0",
    )

    new_metadata = get_sample_metadata(version="1.0.1")
    # Replace tag with digest
    del new_metadata["imageConfigurationSettings"]["tag"]
    new_metadata["imageConfigurationSettings"]["digest"] = "sha256:abc123"
    mocked_fetch_connector_metadata.return_value = new_metadata

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    mocked_wait_for_terminal_state.return_value = existing_template

    result = update_connector_template(
        cmd=mocked_cmd,
        name=template_name,
        resource_group=resource_group,
        instance=instance_name,
        connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.1",
    )

    assert result == existing_template
    # Verify digest was set
    call_args = mocked_get_iotops_mgmt_client.return_value.akri_connector_template.begin_create_or_update.call_args
    resource = call_args.kwargs["resource"]
    managed_settings = resource["properties"]["runtimeConfiguration"]["managedConfigurationSettings"]
    image_config = managed_settings["imageConfigurationSettings"]
    assert image_config["tagDigestSettings"]["tagDigestType"] == "Digest"
    assert image_config["tagDigestSettings"]["digest"] == "sha256:abc123"


def test_connector_template_create_with_secrets_checks_secret_sync(
    mocked_cmd,
    mocked_get_extended_location,
    mocked_get_iotops_mgmt_client,
    mocked_fetch_connector_metadata,
    mocked_wait_for_terminal_state,
    mocked_instances,
):
    """Test that creating with secrets validates secret sync is enabled."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()
    metadata_ref = "mcr.microsoft.com/test/connector-metadata:1.0.0"

    # Mock get_default_spc to raise ValidationError (secret sync not enabled)
    mocked_instances.get_default_spc.side_effect = ValidationError("Secret sync not enabled.")

    with pytest.raises(ValidationError) as exc:
        create_connector_template(
            cmd=mocked_cmd,
            name=template_name,
            resource_group=resource_group,
            instance=instance_name,
            connector_metadata_ref=metadata_ref,
            secrets=[["secretRef=my-secret", "secretKey=password", "secretAlias=dbPassword"]],
        )

    assert "secret sync" in str(exc.value).lower()


def test_connector_template_update_with_secrets_checks_secret_sync(
    mocked_cmd,
    mocked_get_iotops_mgmt_client,
    mocked_instances,
):
    """Test that updating with secrets validates secret sync is enabled."""
    template_name = generate_random_string()
    resource_group = generate_random_string()
    instance_name = generate_random_string()

    existing_template = get_sample_connector_template_record(
        template_name=template_name,
        resource_group=resource_group,
        instance_name=instance_name,
    )

    mocked_get_iotops_mgmt_client.return_value.akri_connector_template.get.return_value = existing_template
    # Mock get_default_spc to raise ValidationError (secret sync not enabled)
    mocked_instances.get_default_spc.side_effect = ValidationError("Secret sync not enabled.")

    with pytest.raises(ValidationError) as exc:
        update_connector_template(
            cmd=mocked_cmd,
            name=template_name,
            resource_group=resource_group,
            instance=instance_name,
            secrets=[["secretRef=my-secret", "secretKey=password", "secretAlias=dbPassword"]],
        )

    assert "secret sync" in str(exc.value).lower()


def test_build_template_properties_with_secrets(mocked_cmd, mocked_get_iotops_mgmt_client, mocked_instances):
    """Test building template properties with secrets."""
    provider = ConnectorTemplates(mocked_cmd)
    metadata = get_sample_metadata()

    # Mock get_default_spc to succeed (secret sync is enabled)
    mocked_instances.get_default_spc.return_value = {"name": "my-spc"}

    properties = provider._build_template_properties(
        metadata=metadata,
        connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

        replicas=None,
        log_level=None,
        image_pull_policy=None,
        image_pull_secrets=None,
        allocation_policy=None,
        bucket_size=None,
        secrets=[["secretRef=my-secret", "secretKey=password", "secretAlias=dbPassword"]],
        storage_volumes=None,
        connector_config=None,
        trust_settings_secret_ref=None,
    )

    managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "secrets" in managed_config
    assert managed_config["secrets"][0]["secretRef"] == "my-secret"


def test_build_template_properties_with_storage_volumes(mocked_cmd, mocked_get_iotops_mgmt_client):
    """Test building template properties with storage volumes."""
    provider = ConnectorTemplates(mocked_cmd)
    metadata = get_sample_metadata()

    properties = provider._build_template_properties(
        metadata=metadata,
        connector_metadata_ref="mcr.microsoft.com/test/connector-metadata:1.0.0",

        replicas=None,
        log_level=None,
        image_pull_policy=None,
        image_pull_secrets=None,
        allocation_policy=None,
        bucket_size=None,
        secrets=None,
        storage_volumes=["claimName=myPVC mountPath=/data"],
        connector_config=None,
        trust_settings_secret_ref=None,
    )

    managed_config = properties["runtimeConfiguration"]["managedConfigurationSettings"]
    assert "persistentVolumeClaims" in managed_config
    assert managed_config["persistentVolumeClaims"][0]["claimName"] == "myPVC"


def test_parse_storage_volumes_multiple(mocked_cmd, mocked_get_iotops_mgmt_client):
    """Test parsing multiple storage volumes."""
    provider = ConnectorTemplates(mocked_cmd)
    volumes = [
        "claimName=pvc1 mountPath=/data1",
        "claimName=pvc2 mountPath=/data2",
    ]
    result = provider._parse_storage_volumes(volumes)

    assert len(result) == 2
    assert result[0]["claimName"] == "pvc1"
    assert result[0]["mountPath"] == "/data1"
    assert result[1]["claimName"] == "pvc2"
    assert result[1]["mountPath"] == "/data2"
