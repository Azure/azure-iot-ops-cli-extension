# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""OCI Registry HTTP client using Azure SDK pipeline for consistent logging, retry, and user-agent."""

from typing import Any, Dict, Optional

from azure.core.pipeline import Pipeline
from azure.core.pipeline.policies import (
    HeadersPolicy,
    HttpLoggingPolicy,
    NetworkTraceLoggingPolicy,
    RedirectPolicy,
    RetryPolicy,
    UserAgentPolicy,
)
from azure.core.pipeline.transport import RequestsTransport
from azure.core.rest import HttpRequest, HttpResponse
from knack.log import get_logger

from ...constants import USER_AGENT

logger = get_logger(__name__)


def _get_oci_logging_policy() -> HttpLoggingPolicy:
    """Create HTTP logging policy for OCI requests with --debug support."""
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


class OciRegistryClient:
    """HTTP client for OCI registries with user-agent, debug logging, and retry."""

    DEFAULT_TIMEOUT = 30

    def __init__(self, **kwargs: Any) -> None:
        self._pipeline = Pipeline(
            transport=RequestsTransport(),
            policies=[
                UserAgentPolicy(user_agent=USER_AGENT, **kwargs),
                _get_oci_headers_policy(),
                RedirectPolicy(**kwargs),
                _get_oci_retry_policy(),
                NetworkTraceLoggingPolicy(**kwargs),
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
        return self._pipeline.run(request, connection_timeout=timeout, **kwargs).http_response

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


_oci_client: Optional[OciRegistryClient] = None


def get_oci_client() -> OciRegistryClient:
    """Get or create a shared OCI registry client instance."""
    global _oci_client
    if _oci_client is None:
        _oci_client = OciRegistryClient()
    return _oci_client
