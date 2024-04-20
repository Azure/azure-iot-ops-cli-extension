# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .work import deploy
from .removal import remove_ops_resources
from .host import run_host_verify

__all__ = ["deploy", "remove_ops_resources", "run_host_verify"]
