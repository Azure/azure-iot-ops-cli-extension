# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from knack.log import get_logger
from ..base import client


logger = get_logger(__name__)
generic = client.ApiClient()


def fetch_nodes():
    return {
        "data": generic.sanitize_for_serialization(obj=client.CoreV1Api().list_node()),
        "zinfo": "nodes.yaml",
    }


support_shared_elements = {"nodes": fetch_nodes}


def prepare_bundle() -> dict:
    shared_to_run = {}
    shared_to_run.update(support_shared_elements)

    return shared_to_run
