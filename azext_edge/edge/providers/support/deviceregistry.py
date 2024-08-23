# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from knack.log import get_logger

from ..edge_api import EdgeResourceApi
from .base import assemble_crd_work

logger = get_logger(__name__)


def prepare_bundle(apis: Optional[Iterable[EdgeResourceApi]] = None) -> dict:
    deviceregistry_to_run = {}

    if apis:
        deviceregistry_to_run.update(assemble_crd_work(apis))

    return deviceregistry_to_run
