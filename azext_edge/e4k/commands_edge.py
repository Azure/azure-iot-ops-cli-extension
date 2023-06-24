# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from pathlib import PurePath
from typing import Optional, Union

from knack.log import get_logger

from .providers.base import load_config_context
from .providers.support.base import get_bundle_path

logger = get_logger(__name__)


def support_bundle(
    cmd,
    log_age_seconds: int = 60 * 60 * 24,
    edge_service: str = "auto",
    bundle_dir: Optional[str] = None,
    context_name: Optional[str] = None,
) -> dict:
    load_config_context(context_name=context_name)
    from .providers.support_bundle import build_bundle

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir)
    return build_bundle(edge_service=edge_service, bundle_path=str(bundle_path), log_age_seconds=log_age_seconds)


def check(
    cmd,
    pre_deployment_checks: Optional[bool] = None,
    post_deployment_checks: Optional[bool] = None,
    namespace: Optional[str] = None,
    as_list=None,
    context_name=None,
    edge_service: str = "e4k",
) -> Union[dict, None]:
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
