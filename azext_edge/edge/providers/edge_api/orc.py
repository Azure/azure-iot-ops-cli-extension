# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class OrcResourceKinds(ListableEnum):
    INSTANCE = "instance"
    SOLUTION = "solution"
    TARGET = "target"


ORC_API_V1 = EdgeResourceApi(group="orchestrator.iotoperations.azure.com", version="v1", moniker="orc")
