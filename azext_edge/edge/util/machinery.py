# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Protocol

Version = object  # Placeholder for the actual Version type from semver


class HasSemverParse(Protocol):
    def parse(self, version: str, optional_minor_and_patch: bool = False) -> Version:
        ...


def scoped_semver_import() -> HasSemverParse:
    """
    This is necessary to avoid conflicts with Az CLI semver import.
    """
    from semver.version import Version

    return Version
