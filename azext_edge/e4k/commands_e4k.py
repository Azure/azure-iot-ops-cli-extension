# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from knack.log import get_logger
from .providers.base import load_config_context
from .common import AZEDGE_DIAGNOSTICS_SERVICE

logger = get_logger(__name__)


def check(
    cmd,
    pre_deployment_checks: Optional[bool] = None,
    post_deployment_checks: Optional[bool] = None,
    namespace: Optional[str] = None,
    as_list=None,
    context_name=None,
):
    load_config_context(context_name=context_name)
    from .providers.checks import run_checks

    run_pre = True
    run_post = True
    if pre_deployment_checks and not post_deployment_checks:
        run_post = False
    if post_deployment_checks and not pre_deployment_checks:
        run_pre = False

    return run_checks(
        namespace=namespace,
        as_list=as_list,
        pre_deployment=run_pre,
        post_deployment=run_post,
    )


def stats(
    cmd,
    namespace: Optional[str] = None,
    context_name: Optional[str] = None,
    diag_service_pod_prefix: str = AZEDGE_DIAGNOSTICS_SERVICE,
    pod_port: int = 9600,
    raw_response_print: Optional[bool] = None,
    refresh_in_seconds: int = 10,
    watch: Optional[bool] = None,
):
    load_config_context(context_name=context_name)
    from .common import BROKER_RESOURCE
    from .providers.base import get_cluster_custom_resources
    from .providers.stats import get_stats_pods

    get_cluster_custom_resources(BROKER_RESOURCE, raise_on_404=True)

    return get_stats_pods(
        namespace=namespace,
        diag_service_pod_prefix=diag_service_pod_prefix,
        raw_response_print=raw_response_print,
        pod_port=pod_port,
        refresh_in_seconds=refresh_in_seconds,
        watch=watch,
    )


def config(cmd, passphrase: str, iterations: int = 210000):
    import base64
    from hashlib import pbkdf2_hmac
    from os import urandom

    dk = pbkdf2_hmac(
        "sha512", bytes(passphrase, encoding="utf8"), urandom(16), iterations
    )
    return {
        "hash": f"pbkdf2-sha512$i={iterations},l={len(dk)}${str(base64.b64encode(dk), encoding='utf-8')}"
    }
