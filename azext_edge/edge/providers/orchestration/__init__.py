# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .deletion import delete_ops_resources
from .work import WorkManager

__all__ = [
    "WorkManager",
    "delete_ops_resources",
]
