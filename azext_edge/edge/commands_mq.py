# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional, List

from knack.log import get_logger
from .providers.base import load_config_context
from .common import METRICS_SERVICE_API_PORT, PROTOBUF_SERVICE_API_PORT

logger = get_logger(__name__)


def stats(
    cmd,
    namespace: Optional[str] = None,
    context_name: Optional[str] = None,
    pod_metrics_port: int = METRICS_SERVICE_API_PORT,
    pod_protobuf_port: int = PROTOBUF_SERVICE_API_PORT,
    raw_response_print: Optional[bool] = None,
    refresh_in_seconds: int = 10,
    watch: Optional[bool] = None,
    trace_ids: Optional[List[str]] = None,
    trace_dir: Optional[str] = None,
):
    load_config_context(context_name=context_name)
    from .providers.edge_api import MQ_ACTIVE_API
    from .providers.stats import get_stats, get_traces

    MQ_ACTIVE_API.is_deployed(raise_on_404=True)
    if trace_ids or trace_dir:
        return get_traces(
            namespace=namespace,
            pod_protobuf_port=pod_protobuf_port,
            trace_ids=trace_ids,
            trace_dir=trace_dir,
        )

    return get_stats(
        namespace=namespace,
        raw_response_print=raw_response_print,
        pod_metrics_port=pod_metrics_port,
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
