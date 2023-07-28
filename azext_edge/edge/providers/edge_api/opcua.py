# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class OpcuaResourceKinds(ListableEnum):
    APPLICATION = "application"
    MODULE_TYPE = "moduletype"
    MODULE = "module"
    ASSET_TYPE = "assettype"
    ASSET = "asset"


OPCUA_API_V1 = EdgeResourceApi(group="e4i.microsoft.com", version="v1", moniker="opcua")
