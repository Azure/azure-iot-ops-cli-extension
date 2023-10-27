# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Iterable

from knack.log import get_logger

from ..edge_api import DEVICEREGISTRY_API_V1, EdgeResourceApi
from .base import assemble_crd_work, process_customobjects

logger = get_logger(__name__)


SYMPHONY_INSTANCE_LABEL = "app.kubernetes.io/instance in (alice-springs)"
SYMPHONY_APP_LABEL = "app in (symphony-api)"
GENERIC_CONTROLLER_LABEL = "control-plane in (controller-manager)"


def fetch_custom_object():
    processed = process_customobjects(
        resource_api=DEVICEREGISTRY_API_V1,
        plural_object_name="assets",
    )
    processed.extend(
        process_customobjects(
            resource_api=DEVICEREGISTRY_API_V1,
            plural_object_name="assetendpointprofiles",
        )
    )
    return processed


def prepare_bundle(apis: Iterable[EdgeResourceApi]) -> dict:
    deviceregistry_to_run = {}
    deviceregistry_to_run.update(assemble_crd_work(apis))

    deviceregistry_to_run["object"] = fetch_custom_object

    return deviceregistry_to_run
