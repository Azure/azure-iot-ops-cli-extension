# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from typing import NamedTuple

from .util.common import is_env_flag_enabled

FLAG_PREFIX = "AIO_CLI_"


class Flag(NamedTuple):
    key: str
    description: str = ""


class FeatureFlag(Enum):
    SUPERUSER_MODE = Flag(key=f"{FLAG_PREFIX}SUPERUSER_MODE", description="Overcome preview limitations.")
    PREFLIGHT_DISABLED = Flag(
        key=f"{FLAG_PREFIX}INIT_PREFLIGHT_DISABLED", description="Disable preflight checks during init."
    )


class Features:
    """
    Set feature flags for the app and check if specific feature flags are enabled.
    """

    def __init__(self):
        self.refresh()

    def refresh(self) -> None:
        self.flags: dict[FeatureFlag, bool] = {}
        self.set_flag(FeatureFlag.SUPERUSER_MODE)
        self.set_flag(FeatureFlag.PREFLIGHT_DISABLED)

    def set_flag(self, flag: FeatureFlag) -> None:
        """
        Set a feature flag to a specific value.
        """
        self.flags[flag] = is_env_flag_enabled(flag.value.key)

    def is_enabled(self, flag: FeatureFlag) -> bool:
        return self.flags.get(flag, False)


# Global Features instance to be used across the app.
feature_config = Features()
