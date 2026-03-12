# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from semver.version import Version


def scoped_semver_import() -> "Type[Version]":
    """
    This is necessary to avoid conflicts with Az CLI semver import.
    """
    from semver.version import Version

    return Version
