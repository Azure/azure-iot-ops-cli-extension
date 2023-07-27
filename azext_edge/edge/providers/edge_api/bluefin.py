# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class BluefinResourceKinds(ListableEnum):
    DATASET = "dataset"
    INSTANCE = "instance"
    PIPELINE = "pipeline"


BLUEFIN_API_V1 = EdgeResourceApi(
    group="bluefin.az-bluefin.com", version="v1", moniker="bluefin", kinds=frozenset(BluefinResourceKinds.list())
)
