# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class AkriResourceKinds(ListableEnum):
    INSTANCE = "instance"
    CONFIGURATION = "configuration"


AKRI_API_V0 = EdgeResourceApi(group="akri.sh", version="v0", moniker="akri")
