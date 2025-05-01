# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Protocol, Any


class HasParse(Protocol):
    def parse(self, version: str) -> Any: ...


def scoped_semver_import() -> HasParse:
    """
    This is necessary to avoid conflicts with Az CLI semver import.
    """
    from semver.version import Version

    return Version
