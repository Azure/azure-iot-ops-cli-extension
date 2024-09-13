# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


ARCCONTAINERSTORAGE_API_V1 = EdgeResourceApi(
    group="arccontainerstorage.azure.net", version="v1", moniker="arccontainerstorage"
)
