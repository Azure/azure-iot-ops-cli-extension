# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from typing import Callable, Optional, List
from os import environ
from enum import Enum


class EnvironmentVariables(Enum):
    rg = "azext_edge_rg"
    cluster = "azext_edge_cluster"
    context_name = "azext_edge_context_name"
    kv = "azext_edge_kv"
    skip_init = "azext_edge_skip_init"


class Setting(object):
    pass


def convert_flag(key: Optional[str] = None):
    return key and key.lower() in ["true", "t", "yes", "y"]


# Example of a dynamic class
class DynamoSettings(object):
    def __init__(self, req_env_set: Optional[List[str]] = None, opt_env_set: Optional[List[str]] = None):
        if not req_env_set:
            req_env_set = []

        if not isinstance(req_env_set, list):
            raise TypeError("req_env_set must be a list")

        self.env = Setting()
        self._build_config(req_env_set)

        if opt_env_set:
            if not isinstance(opt_env_set, list):
                raise TypeError("opt_env_set must be a list")
            self._build_config(opt_env_set, optional=True)

    def add_to_config(self, key: str, conversion: Optional[Callable] = None):
        value = environ.get(key)
        if value and (value == "sentinel" or value.startswith("$(azext")):
            value = None
        if value and conversion:
            value = conversion(value)
        setattr(self.env, key, value)
        return value

    def _build_config(self, env_set: List[str], optional: Optional[bool] = False):
        for key in env_set:
            if not self.add_to_config(key):
                if not optional:
                    raise RuntimeError(
                        "{} environment variables required.".format(",".join(env_set))
                    )
