# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class DataProcessorResourceKinds(ListableEnum):
    DATASET = "dataset"
    INSTANCE = "instance"
    PIPELINE = "pipeline"


DATA_PROCESSOR_API_V1 = EdgeResourceApi(group="dataprocessor.iotoperations.azure.com", version="v1", moniker="dataprocessor")
