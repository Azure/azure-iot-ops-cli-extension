# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class MetaResourceKinds(ListableEnum):
    Instance = "instance"


META_API_V1 = EdgeResourceApi(
    group="iotoperations.azure.com", version="v1", moniker="meta", label="microsoft-iotoperations"
)
