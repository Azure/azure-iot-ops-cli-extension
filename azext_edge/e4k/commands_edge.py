# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from os import makedirs
from os.path import abspath, expanduser, isdir
from pathlib import PurePath
from typing import Optional

from knack.log import get_logger

from .providers.base import load_config_context

logger = get_logger(__name__)


def support_bundle(
    cmd,
    log_age_seconds: int = 60 * 60 * 24,
    edge_service: str = "auto",
    bundle_dir: Optional[str] = None,
    context_name: Optional[str] = None,
) -> dict:
    load_config_context(context_name=context_name)
    from .providers.e4i.support_bundle import build_bundle

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir)
    return build_bundle(edge_service=edge_service, bundle_path=str(bundle_path), log_age_seconds=log_age_seconds)


def get_bundle_path(bundle_dir: Optional[str] = None, system_name: str = "pas") -> PurePath:
    if not bundle_dir:
        bundle_dir = "."
    bundle_dir = abspath(bundle_dir)
    if "~" in bundle_dir:
        bundle_dir = expanduser(bundle_dir)
    bundle_dir_pure_path = PurePath(bundle_dir)
    if not isdir(str(bundle_dir_pure_path)):
        makedirs(bundle_dir_pure_path, exist_ok=True)
    bundle_pure_path = bundle_dir_pure_path.joinpath(default_bundle_name(system_name))
    return bundle_pure_path


def default_bundle_name(system_name: str) -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    timestamp = timestamp.replace(":", "-")
    return f"support_bundle_{timestamp}_{system_name}.zip"
