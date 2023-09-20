# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import deploy
from .aio_versions import (
    get_aio_version_def,
    AioVersionDef,
    EdgeServiceMoniker,
    EdgeExtensionName,
    extension_name_to_type_map,
    moniker_to_extension_type_map,
)


__all__ = [
    "deploy",
    "get_aio_version_def",
    "AioVersionDef",
    "EdgeServiceMoniker",
    "EdgeExtensionName",
    "extension_name_to_type_map",
    "moniker_to_extension_type_map",
]
