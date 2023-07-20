# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Optional

from knack.log import get_logger
from .providers.base import load_config_context
from .common import AZEDGE_DIAGNOSTICS_SERVICE, METRICS_SERVICE_API_PORT

logger = get_logger(__name__)


def stats(
    cmd,
    namespace: Optional[str] = None,
    context_name: Optional[str] = None,
    diag_service_pod_prefix: str = AZEDGE_DIAGNOSTICS_SERVICE,
    pod_port: int = METRICS_SERVICE_API_PORT,
    raw_response_print: Optional[bool] = None,
    refresh_in_seconds: int = 10,
    watch: Optional[bool] = None,
):
    load_config_context(context_name=context_name)
    from .common import E4K_API_V1A2
    from .providers.base import get_cluster_custom_api
    from .providers.stats import get_stats

    get_cluster_custom_api(resource_api=E4K_API_V1A2, raise_on_404=True)

    return get_stats(
        namespace=namespace,
        diag_service_pod_prefix=diag_service_pod_prefix,
        raw_response_print=raw_response_print,
        pod_port=pod_port,
        refresh_in_seconds=refresh_in_seconds,
        watch=watch,
    )


def get_password_hash(cmd, passphrase: str, iterations: int = 210000):
    import base64
    from hashlib import pbkdf2_hmac
    from os import urandom

    salt = urandom(16)

    dk = pbkdf2_hmac("sha512", bytes(passphrase, encoding="utf8"), salt, iterations)
    return {
        "hash": f"$pbkdf2-sha512$i={iterations},l={len(dk)}${str(base64.b64encode(salt), encoding='utf-8').rstrip('=')}"
        f"${str(base64.b64encode(dk), encoding='utf-8').rstrip('=')}"
    }
