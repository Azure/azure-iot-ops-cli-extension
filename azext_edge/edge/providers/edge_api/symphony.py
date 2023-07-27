# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class SymphonyResourceKinds(ListableEnum):
    INSTANCE = "instance"
    SOLUTION = "solution"
    TARGET = "target"


SYMPHONY_API_V1 = EdgeResourceApi(
    group="symphony.microsoft.com", version="v1", moniker="symphony", kinds=frozenset(SymphonyResourceKinds.list())
)
