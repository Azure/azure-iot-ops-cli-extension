# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class OpcuaResourceKinds(ListableEnum):
    ASSET_TYPE = "assettype"


OPCUA_API_V1 = EdgeResourceApi(group="opcuabroker.iotoperations.azure.com", version="v1beta1", moniker="opcua")
