# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""OCI Registry HTTP client using Azure SDK pipeline for consistent logging, retry, and user-agent."""

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError
from azure.core.pipeline import Pipeline
from azure.core.pipeline.policies import (
    HeadersPolicy,
    HttpLoggingPolicy,
    RedirectPolicy,
    RetryPolicy,
    UserAgentPolicy,
)
from azure.core.pipeline.transport import RequestsTransport
from azure.core.rest import HttpRequest, HttpResponse
from knack.log import get_logger

from ...constants import USER_AGENT
from .az_client import AZURE_CLI_CREDENTIAL
from .cloud_config import CloudConfig

logger = get_logger(__name__)


def _get_oci_logging_policy() -> HttpLoggingPolicy:
    """Create HTTP logging policy for OCI requests with --debug support.

    HttpLoggingPolicy logs method, URL, and allowlisted headers only.
    It does NOT log request/response bodies, which keeps tokens secure.
    """
    policy = HttpLoggingPolicy(logger=logger)
    policy.allowed_query_params.update(["scope", "service"])
    policy.allowed_header_names.update([
        "content-type",
        "docker-content-digest",
        "docker-distribution-api-version",
        "www-authenticate",
    ])
    return policy


def _get_oci_retry_policy() -> RetryPolicy:
    """Create retry policy for transient failures (5xx, 429)."""
    return RetryPolicy(
        retry_total=3,
        retry_backoff_factor=0.5,
        retry_backoff_max=30,
        retry_on_status_codes=[429, 500, 502, 503, 504],
    )


def _get_oci_headers_policy() -> HeadersPolicy:
    """Create headers policy with default OCI Accept types."""
    return HeadersPolicy(base_headers={
        "Accept": (
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json, "
            "application/json"
        ),
    })


@dataclass
class OciArtifactInfo:
    """Information about a fetched OCI artifact layer."""

    content: bytes
    content_type: str
    digest: str


class OciRegistryClient:
    """HTTP client for OCI registries with user-agent, debug logging, and retry.

    Provides both low-level HTTP methods (get, post) and high-level OCI API methods
    (fetch_manifest, fetch_blob, fetch_first_layer) that encapsulate OCI registry
    protocol details including authentication.
    """

    DEFAULT_TIMEOUT = 30

    def __init__(self, **kwargs: Any) -> None:
        self._pipeline = Pipeline(
            transport=RequestsTransport(),
            policies=[
                UserAgentPolicy(user_agent=USER_AGENT, **kwargs),
                _get_oci_headers_policy(),
                RedirectPolicy(**kwargs),
                _get_oci_retry_policy(),
                _get_oci_logging_policy(),
            ],
        )

    def send_request(
        self,
        request: HttpRequest,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> HttpResponse:
        """Send an HTTP request through the pipeline."""
        request_copy = deepcopy(request)
        return self._pipeline.run(request_copy, connection_timeout=timeout, **kwargs).http_response

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> HttpResponse:
        """Send a GET request."""
        return self.send_request(
            HttpRequest(method="GET", url=url, headers=headers, params=params),
            timeout=timeout,
            **kwargs,
        )

    def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> HttpResponse:
        """Send a POST request."""
        return self.send_request(
            HttpRequest(method="POST", url=url, headers=headers, data=data, json=json),
            timeout=timeout,
            **kwargs,
        )

    def close(self) -> None:
        self._pipeline.__exit__(None, None, None)

    def __enter__(self) -> "OciRegistryClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # High-level OCI API methods
    # -------------------------------------------------------------------------

    def fetch_manifest(
        self,
        image_ref: str,
        cmd=None,
        expected_config_media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch and validate an OCI manifest from a registry.

        Args:
            image_ref: OCI image reference (e.g., "registry/repo:tag").
            cmd: Azure CLI command context for ACR authentication.
            expected_config_media_type: If provided, validates the manifest config media type.

        Returns:
            The manifest as a dictionary.

        Raises:
            ValidationError: If the reference is invalid, fetch fails, or media type mismatches.
        """
        registry, repository, tag = self._parse_oci_reference(image_ref)
        base_url = f"https://{registry}/v2/{repository}"
        headers = self._get_auth_headers(registry, repository, cmd)

        manifest_url = f"{base_url}/manifests/{tag}"
        response = self.get(manifest_url, headers=headers)

        if response.status_code != 200:
            raise ValidationError(
                f"Failed to fetch manifest for {image_ref}: {response.status_code} {response.text()}"
            )

        manifest = response.json()

        # Validate config media type if expected
        manifest_config = manifest.get("config") or {}
        actual_config_media_type = manifest_config.get("mediaType")

        if expected_config_media_type:
            if not actual_config_media_type:
                raise ValidationError(
                    f"Missing artifact config media type; expected '{expected_config_media_type}'."
                )
            if actual_config_media_type != expected_config_media_type:
                raise ValidationError(
                    f"Artifact config media type '{actual_config_media_type}' does not match expected "
                    f"'{expected_config_media_type}'."
                )
        elif not actual_config_media_type:
            raise ValidationError("Missing artifact config media type.")

        return manifest

    def fetch_blob(
        self,
        image_ref: str,
        digest: str,
        cmd=None,
        verify_digest: bool = True,
    ) -> OciArtifactInfo:
        """Fetch a blob from an OCI registry and optionally verify its digest.

        Args:
            image_ref: OCI image reference for context (registry/repo extraction).
            digest: The blob digest (e.g., "sha256:abc123...").
            cmd: Azure CLI command context for ACR authentication.
            verify_digest: Whether to verify the blob content matches the digest.

        Returns:
            OciArtifactInfo containing the blob content, content type, and digest.

        Raises:
            ValidationError: If fetch fails, digest format is invalid, or verification fails.
        """
        registry, repository, _ = self._parse_oci_reference(image_ref)
        base_url = f"https://{registry}/v2/{repository}"
        headers = self._get_auth_headers(registry, repository, cmd)

        if ":" not in digest:
            raise ValidationError(f"Invalid blob digest format: {digest}")

        algo, expected_hex = digest.split(":", 1)
        if algo.lower() != "sha256":
            raise ValidationError(f"Unsupported digest algorithm '{algo}' for blob {digest}")

        blob_url = f"{base_url}/blobs/{digest}"
        response = self.get(blob_url, headers=headers)

        if response.status_code != 200:
            raise ValidationError(f"Failed to fetch blob {digest}: {response.status_code}")

        content = response.content

        if verify_digest:
            computed_hex = hashlib.sha256(content).hexdigest()
            if computed_hex != expected_hex:
                raise ValidationError(
                    f"Blob digest mismatch: expected {digest}, got sha256:{computed_hex}"
                )

        return OciArtifactInfo(
            content=content,
            content_type=response.headers.get("Content-Type", ""),
            digest=digest,
        )

    def fetch_first_layer(
        self,
        image_ref: str,
        cmd=None,
        expected_config_media_type: Optional[str] = None,
    ) -> OciArtifactInfo:
        """Fetch the first layer blob from an OCI artifact.

        This is a convenience method that fetches the manifest and then retrieves
        the first layer's content. Useful for single-layer artifacts.

        Args:
            image_ref: OCI image reference (e.g., "registry/repo:tag").
            cmd: Azure CLI command context for ACR authentication.
            expected_config_media_type: If provided, validates the manifest config media type.

        Returns:
            OciArtifactInfo containing the first layer's content.

        Raises:
            ValidationError: If manifest has no layers or fetch fails.
        """
        manifest = self.fetch_manifest(
            image_ref=image_ref,
            cmd=cmd,
            expected_config_media_type=expected_config_media_type,
        )

        layers: List[Dict[str, Any]] = manifest.get("layers", [])
        if not layers:
            raise ValidationError(f"Manifest for {image_ref} has no layers.")

        target_digest = layers[0].get("digest")
        if not target_digest:
            raise ValidationError(
                f"First layer in manifest for {image_ref} is missing digest. Layer: {layers[0]}"
            )

        return self.fetch_blob(image_ref=image_ref, digest=target_digest, cmd=cmd)

    # -------------------------------------------------------------------------
    # Authentication helpers
    # -------------------------------------------------------------------------

    def _get_auth_headers(self, registry: str, repository: str, cmd=None) -> Dict[str, str]:
        """Build authentication headers for OCI registry requests."""
        headers: Dict[str, str] = {}

        token = None
        if self._is_acr_registry(registry, cmd=cmd):
            token = self._get_acr_access_token(cmd=cmd, registry=registry, repository=repository)
        if not token:
            token = self._get_anonymous_token(registry, repository)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return headers

    def _get_anonymous_token(self, registry: str, repository: str) -> Optional[str]:
        """Get an anonymous auth token for public registries (MCR/Docker Hub)."""
        auth_url = f"https://{registry}/v2/"
        try:
            resp = self.get(auth_url)

            if resp.status_code == 401 and "Www-Authenticate" in resp.headers:
                auth_header = resp.headers["Www-Authenticate"]
                parts = {}
                for part in auth_header.replace("Bearer ", "").split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        parts[k.strip()] = v.strip().strip('"')

                if "realm" in parts:
                    token_params = {"service": parts.get("service")}
                    if "scope" not in parts:
                        token_params["scope"] = f"repository:{repository}:pull"
                    else:
                        token_params["scope"] = parts.get("scope")

                    token_resp = self.get(parts["realm"], params=token_params)

                    if token_resp.status_code == 200:
                        token = token_resp.json().get("token")
                        logger.info(
                            f"Successfully obtained anonymous auth token (length: {len(token) if token else 0})"
                        )
                        return token
                    else:
                        logger.warning(f"Token request failed with status code: {token_resp.status_code}")
        except HttpResponseError as e:
            logger.warning(f"Failed to obtain auth token: {e}")
        return None

    def _get_acr_access_token(self, cmd, registry: str, repository: str) -> Optional[str]:
        """Acquire an ACR access token using Azure CLI credentials."""
        if cmd is None:
            logger.warning("ACR access token requested without command context; skipping ACR auth.")
            return None

        try:
            arm_token = AZURE_CLI_CREDENTIAL.get_token(CloudConfig(cmd).arm_endpoint_scope).token
        except Exception as ex:  # pragma: no cover - credential failures
            logger.warning(f"Failed to obtain ARM token for ACR: {ex}")
            return None

        # Try to get tenant_id from CLI context first, then fall back to subscription profile
        tenant_id = (cmd.cli_ctx.data or {}).get("tenant_id")
        if not tenant_id:
            from azext_edge.edge.util.az_client import get_tenant_id

            try:
                tenant_id = get_tenant_id()
            except Exception:  # pragma: no cover - profile access failures
                logger.warning(
                    "Tenant ID not found in CLI context or subscription profile; cannot acquire ACR token."
                )
                return None

        exchange_url = f"https://{registry}/oauth2/exchange"
        exchange_payload = {
            "grant_type": "access_token",
            "service": registry,
            "tenant": tenant_id,
            "access_token": arm_token,
        }

        try:
            exchange_resp = self.post(exchange_url, data=exchange_payload)
        except HttpResponseError as ex:  # pragma: no cover - network errors
            logger.warning(f"ACR exchange request failed: {ex}")
            return None

        if exchange_resp.status_code != 200:
            logger.warning(f"ACR exchange failed with status code: {exchange_resp.status_code}")
            return None

        refresh_token = exchange_resp.json().get("refresh_token")
        if not refresh_token:
            logger.warning("ACR exchange response missing refresh_token")
            return None

        token_url = f"https://{registry}/oauth2/token"
        token_payload = {
            "grant_type": "refresh_token",
            "service": registry,
            "scope": f"repository:{repository}:pull",
            "refresh_token": refresh_token,
        }

        try:
            token_resp = self.post(token_url, data=token_payload)
        except HttpResponseError as ex:  # pragma: no cover - network errors
            logger.warning(f"ACR token request failed: {ex}")
            return None

        if token_resp.status_code != 200:
            logger.warning(f"ACR token fetch failed with status code: {token_resp.status_code}")
            return None

        return token_resp.json().get("access_token")

    @staticmethod
    def _is_acr_registry(registry: str, cmd=None) -> bool:
        """Check if the registry is an Azure Container Registry."""
        if cmd is not None:
            try:
                return registry.endswith(CloudConfig(cmd).acr_suffix)
            except AttributeError as ex:  # pragma: no cover - cloud ACR suffix not set
                logger.debug(f"Could not resolve cloud ACR suffix; falling back to default: {ex}")
        return registry.endswith(".azurecr.io")

    @staticmethod
    def _parse_oci_reference(image_ref: str) -> Tuple[str, str, str]:
        """Parse OCI reference into (registry, repository, tag).

        Args:
            image_ref: OCI image reference (e.g., "mcr.microsoft.com/repo/name:v1").

        Returns:
            Tuple of (registry, repository, tag).

        Raises:
            ValidationError: If the reference format is invalid.
        """
        if "/" not in image_ref:
            raise ValidationError(f"Invalid OCI reference: {image_ref}")

        registry, remainder = image_ref.split("/", 1)
        if ":" in remainder:
            repository, tag = remainder.rsplit(":", 1)
        else:
            repository = remainder
            tag = "latest"

        return registry, repository, tag


_oci_client: Optional[OciRegistryClient] = None


def get_oci_client() -> OciRegistryClient:
    """Get or create a shared OCI registry client instance."""
    global _oci_client
    if _oci_client is None:
        _oci_client = OciRegistryClient()
    return _oci_client
