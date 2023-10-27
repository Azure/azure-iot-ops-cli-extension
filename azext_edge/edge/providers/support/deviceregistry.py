# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Iterable

from knack.log import get_logger

from ..edge_api import EdgeResourceApi
from .base import assemble_crd_work

logger = get_logger(__name__)

def prepare_bundle(apis: Iterable[EdgeResourceApi]) -> dict:
    deviceregistry_to_run = {}
    deviceregistry_to_run.update(assemble_crd_work(apis))

    return deviceregistry_to_run
