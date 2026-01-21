# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Unit tests for OCI client, focusing on auth token masking in logs."""

import pytest
from unittest.mock import Mock, patch

OCI_CLIENT_PATH = "azext_edge.edge.util.oci_client"


class TestOciClientTokenMasking:
    """Tests to verify auth tokens are not leaked in log messages."""

    @pytest.fixture
    def mock_client(self):
        """Create an OciRegistryClient with mocked pipeline."""
        with patch(f"{OCI_CLIENT_PATH}.Pipeline"):
            from azext_edge.edge.util.oci_client import OciRegistryClient
            return OciRegistryClient()

    def test_acr_exchange_failure_does_not_log_response_body(self, mock_client, mocker):
        """Verify ACR exchange failure logs status code only, not response body."""
        logger_mock = mocker.patch(f"{OCI_CLIENT_PATH}.logger")

        # Mock credential to return a token
        mock_credential = mocker.patch(f"{OCI_CLIENT_PATH}.AZURE_CLI_CREDENTIAL")
        mock_credential.get_token.return_value = Mock(token="fake_arm_token")

        # Mock cmd with tenant_id
        mock_cmd = Mock()
        mock_cmd.cli_ctx.data = {"tenant_id": "fake-tenant-id"}

        # Mock failed exchange response with sensitive data in body
        sensitive_response_body = '{"error": "invalid_token", "partial_token": "eyJhbGciOiJS..."}'
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text.return_value = sensitive_response_body

        mocker.patch.object(mock_client, "post", return_value=mock_response)

        result = mock_client._get_acr_access_token(
            cmd=mock_cmd, registry="myregistry.azurecr.io", repository="myrepo"
        )

        assert result is None

        # Verify warning was logged
        warning_calls = [call for call in logger_mock.warning.call_args_list]
        assert len(warning_calls) >= 1

        # Verify the sensitive response body is NOT in any log message
        for call in warning_calls:
            log_message = str(call)
            assert "eyJhbGciOiJS" not in log_message
            assert "partial_token" not in log_message
            assert sensitive_response_body not in log_message

        # Verify status code IS logged
        assert any("401" in str(call) for call in warning_calls)

    def test_acr_token_fetch_failure_does_not_log_response_body(self, mock_client, mocker):
        """Verify ACR token fetch failure logs status code only, not response body."""
        logger_mock = mocker.patch(f"{OCI_CLIENT_PATH}.logger")

        # Mock credential
        mock_credential = mocker.patch(f"{OCI_CLIENT_PATH}.AZURE_CLI_CREDENTIAL")
        mock_credential.get_token.return_value = Mock(token="fake_arm_token")

        # Mock cmd
        mock_cmd = Mock()
        mock_cmd.cli_ctx.data = {"tenant_id": "fake-tenant-id"}

        # First call (exchange) succeeds, second call (token) fails
        exchange_response = Mock()
        exchange_response.status_code = 200
        exchange_response.json.return_value = {"refresh_token": "fake_refresh_token"}

        sensitive_token_response = '{"error": "access_denied", "leaked_token": "secret123"}'
        token_response = Mock()
        token_response.status_code = 403
        token_response.text.return_value = sensitive_token_response

        mocker.patch.object(
            mock_client, "post", side_effect=[exchange_response, token_response]
        )

        result = mock_client._get_acr_access_token(
            cmd=mock_cmd, registry="myregistry.azurecr.io", repository="myrepo"
        )

        assert result is None

        # Verify sensitive data is NOT logged
        warning_calls = [call for call in logger_mock.warning.call_args_list]
        for call in warning_calls:
            log_message = str(call)
            assert "leaked_token" not in log_message
            assert "secret123" not in log_message

    def test_anonymous_token_failure_does_not_log_response_body(self, mock_client, mocker):
        """Verify anonymous token failure logs status code only, not response body."""
        logger_mock = mocker.patch(f"{OCI_CLIENT_PATH}.logger")

        # Mock initial 401 response with www-authenticate header
        auth_response = Mock()
        auth_response.status_code = 401
        auth_response.headers = {
            "Www-Authenticate": 'Bearer realm="https://auth.example.com/token",service="registry"'
        }

        # Mock failed token response with sensitive data
        sensitive_body = '{"token": "partial_eyJ...", "error": "unauthorized"}'
        token_response = Mock()
        token_response.status_code = 401
        token_response.text.return_value = sensitive_body

        mocker.patch.object(mock_client, "get", side_effect=[auth_response, token_response])

        result = mock_client._get_anonymous_token(
            registry="mcr.microsoft.com", repository="myrepo"
        )

        assert result is None

        # Verify sensitive data is NOT logged
        warning_calls = [call for call in logger_mock.warning.call_args_list]
        for call in warning_calls:
            log_message = str(call)
            assert "partial_eyJ" not in log_message
            assert sensitive_body not in log_message

    def test_successful_token_logs_length_not_value(self, mock_client, mocker):
        """Verify successful token acquisition logs length, not actual token."""
        logger_mock = mocker.patch(f"{OCI_CLIENT_PATH}.logger")

        # Mock initial 401 response
        auth_response = Mock()
        auth_response.status_code = 401
        auth_response.headers = {
            "Www-Authenticate": 'Bearer realm="https://auth.example.com/token",service="registry"'
        }

        # Mock successful token response
        actual_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret_payload.signature"
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {"token": actual_token}

        mocker.patch.object(mock_client, "get", side_effect=[auth_response, token_response])

        result = mock_client._get_anonymous_token(
            registry="mcr.microsoft.com", repository="myrepo"
        )

        assert result == actual_token

        # Verify the actual token value is NOT logged
        info_calls = [call for call in logger_mock.info.call_args_list]
        for call in info_calls:
            log_message = str(call)
            assert actual_token not in log_message
            assert "secret_payload" not in log_message

        # Verify token length IS logged
        assert any(str(len(actual_token)) in str(call) for call in info_calls)


class TestOciClientParseReference:
    """Tests for OCI reference parsing."""

    def test_parse_valid_reference_with_tag(self):
        """Test parsing a valid OCI reference with tag."""
        from azext_edge.edge.util.oci_client import OciRegistryClient

        registry, repo, tag = OciRegistryClient._parse_oci_reference(
            "myregistry.azurecr.io/myrepo/image:v1.0"
        )
        assert registry == "myregistry.azurecr.io"
        assert repo == "myrepo/image"
        assert tag == "v1.0"

    def test_parse_valid_reference_without_tag(self):
        """Test parsing a valid OCI reference without tag defaults to 'latest'."""
        from azext_edge.edge.util.oci_client import OciRegistryClient

        registry, repo, tag = OciRegistryClient._parse_oci_reference(
            "mcr.microsoft.com/hello/world"
        )
        assert registry == "mcr.microsoft.com"
        assert repo == "hello/world"
        assert tag == "latest"

    def test_parse_invalid_reference_raises(self):
        """Test parsing an invalid OCI reference raises ValidationError."""
        from azure.cli.core.azclierror import ValidationError
        from azext_edge.edge.util.oci_client import OciRegistryClient

        with pytest.raises(ValidationError):
            OciRegistryClient._parse_oci_reference("invalid-no-slash")


class TestOciClientIsAcrRegistry:
    """Tests for ACR registry detection."""

    @pytest.mark.parametrize(
        "registry,expected",
        [
            ("myregistry.azurecr.io", True),
            ("another.azurecr.io", True),
            ("mcr.microsoft.com", False),
            ("docker.io", False),
            ("ghcr.io", False),
        ],
    )
    def test_is_acr_registry(self, registry, expected):
        """Test ACR registry detection."""
        from azext_edge.edge.util.oci_client import OciRegistryClient

        assert OciRegistryClient._is_acr_registry(registry) == expected
