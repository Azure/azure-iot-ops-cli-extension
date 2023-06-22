# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger
from kubernetes.client.models import V1ObjectMeta, V1PodList

from ..base import client
from .base import process_v1_pods, process_crd
from ...common import OPCUA_RESOURCE

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
