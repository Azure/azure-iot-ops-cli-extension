# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class OpcuaResourceKinds(ListableEnum):
    ASSET_TYPE = "assettype"


OPCUA_API_V1 = EdgeResourceApi(
    group="opcuabroker.iotoperations.azure.com",
    version="v1beta1",
    moniker="opcua",
    label="microsoft-iotoperations-opcuabroker",
)
